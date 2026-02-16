import discord
from discord.ext import commands, tasks
from datetime import datetime
import io
import db
import asyncio

TICKET_FILE = "tickets.json"
MAX_TRANSCRIPT_MESSAGES = 2000


def _load_config(guild_id):
    gid = int(guild_id)
    cfg = db.execute(
        "SELECT panel_channel_id, log_channel_id, category_id, auto_close_hours FROM tickets_config WHERE guild_id = %s",
        (gid,),
        fetchone=True
    ) or {}
    staff_rows = db.execute(
        "SELECT role_id FROM ticket_staff_roles WHERE guild_id = %s",
        (gid,),
        fetchall=True
    ) or []
    reason_rows = db.execute(
        "SELECT reason FROM ticket_reasons WHERE guild_id = %s",
        (gid,),
        fetchall=True
    ) or []
    ticket_rows = db.execute(
        "SELECT channel_id, user_id, created_at, last_activity, reason FROM tickets WHERE guild_id = %s",
        (gid,),
        fetchall=True
    ) or []
    open_tickets = {}
    for r in ticket_rows:
        open_tickets[str(r["channel_id"])] = {
            "user_id": str(r["user_id"]),
            "created_at": r["created_at"],
            "last_activity": r["last_activity"],
            "reason": r["reason"]
        }
    return {
        "panel_channel_id": cfg.get("panel_channel_id"),
        "log_channel_id": cfg.get("log_channel_id"),
        "category_id": cfg.get("category_id"),
        "auto_close_hours": cfg.get("auto_close_hours", 0),
        "staff_roles": [str(r["role_id"]) for r in staff_rows],
        "reason_prompts": [r["reason"] for r in reason_rows] or ["Support", "Billing", "Technical", "Other"],
        "panel_message_id": None,
        "open_tickets": open_tickets
    }


def _save_config(guild_id, data):
    gid = int(guild_id)
    db.execute(
        """
        INSERT INTO tickets_config (guild_id, panel_channel_id, log_channel_id, category_id, auto_close_hours)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (guild_id)
        DO UPDATE SET panel_channel_id = EXCLUDED.panel_channel_id,
          log_channel_id = EXCLUDED.log_channel_id,
          category_id = EXCLUDED.category_id,
          auto_close_hours = EXCLUDED.auto_close_hours
        """,
        (gid,
         int(data["panel_channel_id"]) if data.get("panel_channel_id") else None,
         int(data["log_channel_id"]) if data.get("log_channel_id") else None,
         int(data["category_id"]) if data.get("category_id") else None,
         int(data.get("auto_close_hours", 0)))
    )

    db.execute("DELETE FROM ticket_staff_roles WHERE guild_id = %s", (gid,))
    for rid in data.get("staff_roles", []):
        db.execute(
            "INSERT INTO ticket_staff_roles (guild_id, role_id) VALUES (%s, %s)",
            (gid, int(rid))
        )

    db.execute("DELETE FROM ticket_reasons WHERE guild_id = %s", (gid,))
    for reason in data.get("reason_prompts", []):
        db.execute(
            "INSERT INTO ticket_reasons (guild_id, reason) VALUES (%s, %s)",
            (gid, str(reason))
        )

    db.execute("DELETE FROM tickets WHERE guild_id = %s", (gid,))
    for ch_id, info in data.get("open_tickets", {}).items():
        db.execute(
            """
            INSERT INTO tickets (guild_id, channel_id, user_id, created_at, last_activity, reason)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                gid,
                int(ch_id),
                int(info.get("user_id")),
                info.get("created_at"),
                info.get("last_activity") or info.get("created_at"),
                info.get("reason")
            )
        )


def _ticket_owner_from_name(name: str) -> str | None:
    if not name:
        return None
    if name.startswith("ticket-") and "-" in name[7:]:
        return name.split("-")[-1]
    return None


def _build_overwrites(guild, user, staff_roles):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    }
    for rid in staff_roles:
        role = guild.get_role(int(rid))
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)
    overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True)
    return overwrites


async def _build_transcript(channel: discord.TextChannel):
    lines = []
    async for msg in channel.history(limit=MAX_TRANSCRIPT_MESSAGES, oldest_first=True):
        ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        author = f"{msg.author} ({msg.author.id})"
        content = msg.content or ""
        if msg.attachments:
            att = ", ".join(a.url for a in msg.attachments)
            content = f"{content}\n[Attachments] {att}" if content else f"[Attachments] {att}"
        if msg.embeds:
            content = f"{content}\n[Embeds] {len(msg.embeds)}" if content else f"[Embeds] {len(msg.embeds)}"
        lines.append(f"[{ts}] {author}: {content}")
    transcript_text = "\n".join(lines) if lines else "No messages in transcript."
    return io.BytesIO(transcript_text.encode("utf-8"))


class TicketPanelView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="🎫 Open Ticket", style=discord.ButtonStyle.green, custom_id="ticket_open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.bot:
            return await interaction.response.send_message("❌ Bots cannot open tickets.", ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        config = _load_config(guild_id)
        category_id = config.get("category_id")
        if not category_id:
            return await interaction.response.send_message("❌ Ticket category not configured.", ephemeral=True)

        open_tickets = config.get("open_tickets", {})
        user_id = str(interaction.user.id)
        for ch_id, info in open_tickets.items():
            if info.get("user_id") == user_id:
                ch = interaction.guild.get_channel(int(ch_id))
                if ch:
                    return await interaction.response.send_message(f"✅ You already have an open ticket: {ch.mention}", ephemeral=True)

        category = interaction.guild.get_channel(int(category_id))
        if not isinstance(category, discord.CategoryChannel):
            return await interaction.response.send_message("❌ Ticket category not found.", ephemeral=True)

        prompts = config.get("reason_prompts", ["Support", "Billing", "Technical", "Other"])
        view = TicketReasonView(self.bot, prompts)
        await interaction.response.send_message("Select a reason to open your ticket:", view=view, ephemeral=True)


class TicketCloseView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Invalid channel.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        config = _load_config(guild_id)
        if str(interaction.channel.id) not in config.get("open_tickets", {}):
            return await interaction.response.send_message("❌ This channel is not a ticket.", ephemeral=True)

        await interaction.response.send_message("✅ Closing ticket and generating transcript...", ephemeral=True)
        await close_ticket_channel(self.bot, interaction.channel, interaction.user, config)


class TicketReasonView(discord.ui.View):
    def __init__(self, bot, reasons):
        super().__init__(timeout=120)
        self.bot = bot
        self.reasons = reasons
        self.add_item(TicketReasonSelect(reasons))


class TicketReasonSelect(discord.ui.Select):
    def __init__(self, reasons):
        options = [discord.SelectOption(label=r[:100], value=r) for r in reasons[:25]]
        super().__init__(placeholder="Choose a ticket reason...", min_values=1, max_values=1, options=options, custom_id="ticket_reason_select")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
        guild_id = str(interaction.guild.id)
        config = _load_config(guild_id)
        category_id = config.get("category_id")
        if not category_id:
            return await interaction.response.send_message("❌ Ticket category not configured.", ephemeral=True)

        open_tickets = config.get("open_tickets", {})
        user_id = str(interaction.user.id)
        for ch_id, info in open_tickets.items():
            if info.get("user_id") == user_id:
                ch = interaction.guild.get_channel(int(ch_id))
                if ch:
                    return await interaction.response.send_message(f"✅ You already have an open ticket: {ch.mention}", ephemeral=True)

        category = interaction.guild.get_channel(int(category_id))
        if not isinstance(category, discord.CategoryChannel):
            return await interaction.response.send_message("❌ Ticket category not found.", ephemeral=True)

        ticket_id = str(interaction.user.id)[-4:]
        channel_name = f"ticket-{interaction.user.name.lower()[:12]}-{ticket_id}"
        overwrites = _build_overwrites(interaction.guild, interaction.user, config.get("staff_roles", []))
        channel = await interaction.guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Ticket opened by {interaction.user}"
        )

        open_tickets[str(channel.id)] = {
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            "reason": self.values[0]
        }
        config["open_tickets"] = open_tickets
        _save_config(guild_id, config)

        embed = discord.Embed(
            title="🎫 TICKET OPENED",
            description=(
                f"**User:** {interaction.user.mention}\n"
                f"**Reason:** `{self.values[0]}`\n"
                f"**Channel:** {channel.mention}\n"
                "A staff member will be with you shortly."
            ),
            color=0x2ecc71
        )
        embed.set_footer(text="TRADERS UNION • Ticket System")
        await channel.send(embed=embed, view=TicketCloseView(self.view.bot))

        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)


async def close_ticket_channel(bot, channel: discord.TextChannel, closed_by: discord.Member, config: dict):
    guild_id = str(channel.guild.id)
    log_channel_id = config.get("log_channel_id")

    transcript = await _build_transcript(channel)
    file = discord.File(transcript, filename=f"transcript-{channel.id}.txt")

    embed = discord.Embed(
        title="🎫 TICKET CLOSED",
        description=(
            f"**Channel:** {channel.name}\n"
            f"**Closed By:** {closed_by.mention} (`{closed_by.id}`)\n"
            f"**Closed At:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        ),
        color=0xe74c3c
    )
    embed.set_footer(text="TRADERS UNION • Ticket Archive")

    if log_channel_id:
        log_channel = channel.guild.get_channel(int(log_channel_id))
        if log_channel:
            try:
                await log_channel.send(embed=embed, file=file)
            except Exception:
                pass

    open_tickets = config.get("open_tickets", {})
    if str(channel.id) in open_tickets:
        del open_tickets[str(channel.id)]
        config["open_tickets"] = open_tickets
        _save_config(guild_id, config)

    try:
        await channel.delete(reason=f"Ticket closed by {closed_by}")
    except Exception:
        pass


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(TicketPanelView(bot))
        self.bot.add_view(TicketCloseView(bot))
        self.auto_close_task.start()

    @commands.group(name="ticket", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def ticket_group(self, ctx):
        await ctx.send(
            "Use:\n"
            "`-ticket setup #panel #log #category @Staff @Support`\n"
            "`-ticket panel` (repost panel)\n"
            "`-ticket close` (in a ticket channel)\n"
            "`-ticket rename <new-name>`\n"
            "`-ticket add @user`\n"
            "`-ticket remove @user`\n"
            "`-ticket autoclose <hours>`\n"
            "`-ticket reasons add <name>` / `-ticket reasons remove <name>` / `-ticket reasons list`"
        )

    @ticket_group.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    async def ticket_setup(
        self,
        ctx,
        panel_channel: discord.TextChannel,
        log_channel: discord.TextChannel,
        category: discord.CategoryChannel,
        *staff_roles: discord.Role
    ):
        """Setup ticket system with panel channel, log channel, category, and staff roles."""
        config = _load_config(ctx.guild.id)
        config["panel_channel_id"] = panel_channel.id
        config["log_channel_id"] = log_channel.id
        config["category_id"] = category.id
        config["staff_roles"] = [r.id for r in staff_roles] if staff_roles else []
        _save_config(ctx.guild.id, config)

        embed = discord.Embed(
            title="✅ TICKET SYSTEM CONFIGURED",
            description=(
                f"**Panel Channel:** {panel_channel.mention}\n"
                f"**Log Channel:** {log_channel.mention}\n"
                f"**Category:** {category.name}\n"
                f"**Staff Roles:** {', '.join(r.mention for r in staff_roles) if staff_roles else 'None'}"
            ),
            color=0x2ecc71
        )
        embed.set_footer(text="TRADERS UNION • Ticket System")
        await ctx.send(embed=embed)

        await self._send_panel(panel_channel, ctx.guild)

    @ticket_group.command(name="panel")
    @commands.has_permissions(manage_guild=True)
    async def ticket_panel(self, ctx):
        config = _load_config(ctx.guild.id)
        channel_id = config.get("panel_channel_id")
        if not channel_id:
            return await ctx.send("❌ Panel channel not set. Use `-ticket setup` first.")
        channel = ctx.guild.get_channel(int(channel_id))
        if not channel:
            return await ctx.send("❌ Panel channel not found.")
        await self._send_panel(channel, ctx.guild)
        await ctx.send(f"✅ Ticket panel sent to {channel.mention}")

    @ticket_group.command(name="close")
    @commands.has_permissions(manage_guild=True)
    async def ticket_close(self, ctx):
        if not isinstance(ctx.channel, discord.TextChannel):
            return await ctx.send("❌ Invalid channel.")
        config = _load_config(ctx.guild.id)
        if str(ctx.channel.id) not in config.get("open_tickets", {}):
            return await ctx.send("❌ This channel is not a ticket.")
        await ctx.send("🔒 Closing ticket and generating transcript...")
        await close_ticket_channel(self.bot, ctx.channel, ctx.author, config)

    @ticket_group.command(name="rename")
    @commands.has_permissions(manage_guild=True)
    async def ticket_rename(self, ctx, *, new_name: str):
        if not isinstance(ctx.channel, discord.TextChannel):
            return await ctx.send("❌ Invalid channel.")
        config = _load_config(ctx.guild.id)
        if str(ctx.channel.id) not in config.get("open_tickets", {}):
            return await ctx.send("❌ This channel is not a ticket.")
        safe_name = new_name.strip().lower().replace(" ", "-")[:90]
        if not safe_name:
            return await ctx.send("❌ Invalid name.")
        await ctx.channel.edit(name=safe_name, reason=f"Ticket renamed by {ctx.author}")
        await ctx.send(f"✅ Renamed to `{safe_name}`")

    @ticket_group.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def ticket_add(self, ctx, member: discord.Member):
        if not isinstance(ctx.channel, discord.TextChannel):
            return await ctx.send("❌ Invalid channel.")
        config = _load_config(ctx.guild.id)
        if str(ctx.channel.id) not in config.get("open_tickets", {}):
            return await ctx.send("❌ This channel is not a ticket.")
        await ctx.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await ctx.send(f"✅ Added {member.mention} to this ticket.")

    @ticket_group.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def ticket_remove(self, ctx, member: discord.Member):
        if not isinstance(ctx.channel, discord.TextChannel):
            return await ctx.send("❌ Invalid channel.")
        config = _load_config(ctx.guild.id)
        if str(ctx.channel.id) not in config.get("open_tickets", {}):
            return await ctx.send("❌ This channel is not a ticket.")
        await ctx.channel.set_permissions(member, overwrite=None)
        await ctx.send(f"✅ Removed {member.mention} from this ticket.")

    @ticket_group.command(name="autoclose")
    @commands.has_permissions(manage_guild=True)
    async def ticket_autoclose(self, ctx, hours: int):
        if hours < 0 or hours > 720:
            return await ctx.send("❌ Hours must be between 0 and 720.")
        config = _load_config(ctx.guild.id)
        config["auto_close_hours"] = hours
        _save_config(ctx.guild.id, config)
        state = "disabled" if hours == 0 else f"set to {hours} hours"
        await ctx.send(f"✅ Auto-close {state}.")

    @ticket_group.group(name="reasons", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def ticket_reasons(self, ctx):
        await ctx.send("Use: `-ticket reasons add <name>` / `-ticket reasons remove <name>` / `-ticket reasons list`")

    @ticket_reasons.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def ticket_reasons_list(self, ctx):
        config = _load_config(ctx.guild.id)
        reasons = config.get("reason_prompts", [])
        text = "\n".join(f"• {r}" for r in reasons) if reasons else "None"
        await ctx.send(f"📋 Ticket reasons:\n{text}")

    @ticket_reasons.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def ticket_reasons_add(self, ctx, *, name: str):
        name = name.strip()
        if not name:
            return await ctx.send("❌ Provide a reason name.")
        config = _load_config(ctx.guild.id)
        reasons = config.get("reason_prompts", [])
        if name in reasons:
            return await ctx.send("⚠️ Reason already exists.")
        reasons.append(name)
        config["reason_prompts"] = reasons[:25]
        _save_config(ctx.guild.id, config)
        await ctx.send(f"✅ Added reason: `{name}`")

    @ticket_reasons.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def ticket_reasons_remove(self, ctx, *, name: str):
        config = _load_config(ctx.guild.id)
        reasons = config.get("reason_prompts", [])
        if name not in reasons:
            return await ctx.send("❌ Reason not found.")
        reasons.remove(name)
        config["reason_prompts"] = reasons
        _save_config(ctx.guild.id, config)
        await ctx.send(f"✅ Removed reason: `{name}`")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        config = _load_config(message.guild.id)
        open_tickets = config.get("open_tickets", {})
        ch_id = str(message.channel.id)
        if ch_id in open_tickets:
            open_tickets[ch_id]["last_activity"] = datetime.utcnow().isoformat()
            config["open_tickets"] = open_tickets
            _save_config(message.guild.id, config)

    @tasks.loop(minutes=10)
    async def auto_close_task(self):
        now = datetime.utcnow()
        for guild in self.bot.guilds:
            config = _load_config(guild.id)
            hours = int(config.get("auto_close_hours") or 0)
            if hours <= 0:
                continue
            cutoff = now.timestamp() - (hours * 3600)
            open_tickets = config.get("open_tickets", {})
            for ch_id, info in list(open_tickets.items()):
                last = info.get("last_activity") or info.get("created_at")
                if not last:
                    continue
                try:
                    last_dt = datetime.fromisoformat(last)
                except Exception:
                    continue
                if last_dt.timestamp() <= cutoff:
                    ch = guild.get_channel(int(ch_id))
                    if ch:
                        await close_ticket_channel(self.bot, ch, guild.me, config)

    @auto_close_task.before_loop
    async def before_auto_close(self):
        await self.bot.wait_until_ready()

    async def _send_panel(self, channel: discord.TextChannel, guild: discord.Guild):
        embed = discord.Embed(
            title="🎫 TRADERS UNION SUPPORT",
            description=(
                "Click the button below to open a private ticket.\n"
                "Our staff will respond as soon as possible."
            ),
            color=0x2b2d31
        )
        embed.set_footer(text="TRADERS UNION • Ticket System")
        msg = await channel.send(embed=embed, view=TicketPanelView(self.bot))

        config = _load_config(guild.id)
        config["panel_message_id"] = msg.id
        _save_config(guild.id, config)


async def setup(bot):
    await bot.add_cog(Tickets(bot))
