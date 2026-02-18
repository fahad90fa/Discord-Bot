import re
from datetime import datetime

import discord
from discord.ext import commands

import db


def _parse_user_id(raw: str) -> int | None:
    if not raw:
        return None
    m = re.search(r"(\d{15,22})", raw)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _format_template(template: str, member: discord.Member) -> str:
    base = template or "{user}'s VC"
    name = (
        base.replace("{user}", member.display_name)
        .replace("{username}", member.name)
        .replace("{id}", str(member.id))
    )
    name = re.sub(r"\s+", " ", name).strip()
    return name[:100] if name else f"{member.display_name}'s VC"


def get_vc_config(guild_id: int) -> dict:
    row = db.execute(
        """
        SELECT guild_id, lobby_channel_id, category_id, interface_channel_id, interface_message_id,
               naming_template, default_user_limit
        FROM vc_config
        WHERE guild_id = %s
        """,
        (int(guild_id),),
        fetchone=True,
    ) or {}
    return {
        "guild_id": row.get("guild_id"),
        "lobby_channel_id": row.get("lobby_channel_id"),
        "category_id": row.get("category_id"),
        "interface_channel_id": row.get("interface_channel_id"),
        "interface_message_id": row.get("interface_message_id"),
        "naming_template": row.get("naming_template") or "{user}'s VC",
        "default_user_limit": row.get("default_user_limit") or 0,
    }


def save_vc_config(guild_id: int, data: dict):
    db.execute(
        """
        INSERT INTO vc_config
            (guild_id, lobby_channel_id, category_id, interface_channel_id, interface_message_id,
             naming_template, default_user_limit)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (guild_id) DO UPDATE SET
            lobby_channel_id = EXCLUDED.lobby_channel_id,
            category_id = EXCLUDED.category_id,
            interface_channel_id = EXCLUDED.interface_channel_id,
            interface_message_id = EXCLUDED.interface_message_id,
            naming_template = EXCLUDED.naming_template,
            default_user_limit = EXCLUDED.default_user_limit
        """,
        (
            int(guild_id),
            data.get("lobby_channel_id"),
            data.get("category_id"),
            data.get("interface_channel_id"),
            data.get("interface_message_id"),
            data.get("naming_template") or "{user}'s VC",
            int(data.get("default_user_limit") or 0),
        ),
    )


def delete_vc_config(guild_id: int):
    db.execute("DELETE FROM vc_config WHERE guild_id = %s", (int(guild_id),))


def get_temp_channel(guild_id: int, channel_id: int) -> dict | None:
    return db.execute(
        "SELECT guild_id, channel_id, owner_id, created_at FROM vc_temp_channels WHERE guild_id = %s AND channel_id = %s",
        (int(guild_id), int(channel_id)),
        fetchone=True,
    )


def get_owned_channel(guild_id: int, owner_id: int) -> dict | None:
    return db.execute(
        "SELECT guild_id, channel_id, owner_id, created_at FROM vc_temp_channels WHERE guild_id = %s AND owner_id = %s ORDER BY created_at DESC LIMIT 1",
        (int(guild_id), int(owner_id)),
        fetchone=True,
    )


def list_temp_channels(guild_id: int) -> list[dict]:
    return db.execute(
        "SELECT guild_id, channel_id, owner_id, created_at FROM vc_temp_channels WHERE guild_id = %s ORDER BY created_at DESC",
        (int(guild_id),),
        fetchall=True,
    ) or []


def save_temp_channel(guild_id: int, channel_id: int, owner_id: int):
    db.execute(
        """
        INSERT INTO vc_temp_channels (guild_id, channel_id, owner_id, created_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (guild_id, channel_id) DO UPDATE SET owner_id = EXCLUDED.owner_id
        """,
        (int(guild_id), int(channel_id), int(owner_id), datetime.utcnow().isoformat()),
    )


def set_temp_owner(guild_id: int, channel_id: int, owner_id: int):
    db.execute(
        "UPDATE vc_temp_channels SET owner_id = %s WHERE guild_id = %s AND channel_id = %s",
        (int(owner_id), int(guild_id), int(channel_id)),
    )


def delete_temp_channel(guild_id: int, channel_id: int):
    db.execute(
        "DELETE FROM vc_temp_channels WHERE guild_id = %s AND channel_id = %s",
        (int(guild_id), int(channel_id)),
    )


class BaseOwnerModal(discord.ui.Modal):
    def __init__(self, cog: "VoiceControl", title: str):
        super().__init__(title=title)
        self.cog = cog

    async def _owner_channel(self, interaction: discord.Interaction) -> tuple[discord.VoiceChannel | None, dict | None]:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not member.guild or not member.voice or not isinstance(member.voice.channel, discord.VoiceChannel):
            await interaction.response.send_message("You must be inside your temp voice channel.", ephemeral=True)
            return None, None
        channel = member.voice.channel
        row = get_temp_channel(member.guild.id, channel.id)
        if not row:
            await interaction.response.send_message("This is not a temp voice channel.", ephemeral=True)
            return None, None
        if int(row["owner_id"]) != member.id:
            await interaction.response.send_message("Only channel owner can do this.", ephemeral=True)
            return None, None
        return channel, row


class RenameModal(BaseOwnerModal):
    name = discord.ui.TextInput(label="New Channel Name", max_length=100, required=True)

    def __init__(self, cog: "VoiceControl"):
        super().__init__(cog, "Rename Voice Channel")

    async def on_submit(self, interaction: discord.Interaction):
        channel, _ = await self._owner_channel(interaction)
        if not channel:
            return
        await channel.edit(name=str(self.name).strip()[:100], reason=f"VC rename by {interaction.user}")
        await interaction.response.send_message("Renamed.", ephemeral=True)


class LimitModal(BaseOwnerModal):
    limit = discord.ui.TextInput(label="User Limit (0-99)", placeholder="0", max_length=2, required=True)

    def __init__(self, cog: "VoiceControl"):
        super().__init__(cog, "Set User Limit")

    async def on_submit(self, interaction: discord.Interaction):
        channel, _ = await self._owner_channel(interaction)
        if not channel:
            return
        try:
            v = int(str(self.limit).strip())
        except ValueError:
            return await interaction.response.send_message("Limit must be a number.", ephemeral=True)
        v = max(0, min(99, v))
        await channel.edit(user_limit=v, reason=f"VC limit by {interaction.user}")
        await interaction.response.send_message(f"User limit set to {v}.", ephemeral=True)


class BitrateModal(BaseOwnerModal):
    bitrate = discord.ui.TextInput(label="Bitrate Kbps", placeholder="64", max_length=4, required=True)

    def __init__(self, cog: "VoiceControl"):
        super().__init__(cog, "Set Bitrate")

    async def on_submit(self, interaction: discord.Interaction):
        channel, _ = await self._owner_channel(interaction)
        if not channel:
            return
        try:
            kbps = int(str(self.bitrate).strip())
        except ValueError:
            return await interaction.response.send_message("Bitrate must be a number.", ephemeral=True)
        min_bps = 8000
        max_bps = int(channel.guild.bitrate_limit)
        bps = max(min_bps, min(max_bps, kbps * 1000))
        await channel.edit(bitrate=bps, reason=f"VC bitrate by {interaction.user}")
        await interaction.response.send_message(f"Bitrate set to {bps // 1000} kbps.", ephemeral=True)


class RegionModal(BaseOwnerModal):
    region = discord.ui.TextInput(
        label="Region (auto/us-west/eu-central/etc)",
        placeholder="auto",
        max_length=32,
        required=True,
    )

    def __init__(self, cog: "VoiceControl"):
        super().__init__(cog, "Set Region")

    async def on_submit(self, interaction: discord.Interaction):
        channel, _ = await self._owner_channel(interaction)
        if not channel:
            return
        raw = str(self.region).strip().lower()
        rtc_region = None if raw in {"", "auto", "none"} else raw
        try:
            await channel.edit(rtc_region=rtc_region, reason=f"VC region by {interaction.user}")
            await interaction.response.send_message(f"Region set to `{raw or 'auto'}`.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to set region: {e}", ephemeral=True)


class TemplateModal(BaseOwnerModal):
    template = discord.ui.TextInput(
        label="Template ({user}, {username}, {id})",
        placeholder="{user}'s VC",
        max_length=80,
        required=True,
    )

    def __init__(self, cog: "VoiceControl"):
        super().__init__(cog, "Set Naming Template")

    async def on_submit(self, interaction: discord.Interaction):
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not member.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)

        cfg = get_vc_config(member.guild.id)
        cfg["naming_template"] = str(self.template).strip()
        save_vc_config(member.guild.id, cfg)
        await interaction.response.send_message("Template updated for next created channels.", ephemeral=True)


class MemberTargetModal(BaseOwnerModal):
    target = discord.ui.TextInput(label="User mention or ID", max_length=64, required=True)

    def __init__(self, cog: "VoiceControl", action: str):
        self.action = action
        super().__init__(cog, f"{action.title()} Member")

    async def on_submit(self, interaction: discord.Interaction):
        channel, _ = await self._owner_channel(interaction)
        if not channel:
            return

        user_id = _parse_user_id(str(self.target))
        if not user_id:
            return await interaction.response.send_message("Invalid user mention/ID.", ephemeral=True)
        member = channel.guild.get_member(user_id)
        if not member:
            return await interaction.response.send_message("Member not found in this server.", ephemeral=True)

        overwrite = channel.overwrites_for(member)
        if self.action == "invite":
            overwrite.view_channel = True
            overwrite.connect = True
            overwrite.speak = True
        elif self.action == "ban":
            overwrite.connect = False
            overwrite.speak = False
            overwrite.view_channel = False
            if member.voice and member.voice.channel and member.voice.channel.id == channel.id:
                try:
                    await member.move_to(None, reason=f"Banned from VC by {interaction.user}")
                except discord.HTTPException:
                    pass
        else:  # permit
            overwrite.connect = None
            overwrite.speak = None
            overwrite.view_channel = None

        await channel.set_permissions(member, overwrite=overwrite, reason=f"VC {self.action} by {interaction.user}")
        await interaction.response.send_message(f"{self.action.title()} complete for {member.mention}.", ephemeral=True)


class TransferModal(BaseOwnerModal):
    target = discord.ui.TextInput(label="New owner mention or ID", max_length=64, required=True)

    def __init__(self, cog: "VoiceControl"):
        super().__init__(cog, "Transfer Ownership")

    async def on_submit(self, interaction: discord.Interaction):
        channel, _ = await self._owner_channel(interaction)
        if not channel:
            return

        user_id = _parse_user_id(str(self.target))
        if not user_id:
            return await interaction.response.send_message("Invalid member mention/ID.", ephemeral=True)

        target = channel.guild.get_member(user_id)
        if not target:
            return await interaction.response.send_message("Member not found in this server.", ephemeral=True)
        if not target.voice or not target.voice.channel or target.voice.channel.id != channel.id:
            return await interaction.response.send_message("Target must be in your voice channel.", ephemeral=True)

        prev_owner = interaction.user if isinstance(interaction.user, discord.Member) else None
        if prev_owner:
            await channel.set_permissions(prev_owner, overwrite=None, reason="VC ownership transfer")

        owner_overwrite = channel.overwrites_for(target)
        owner_overwrite.manage_channels = True
        owner_overwrite.manage_permissions = True
        owner_overwrite.move_members = True
        owner_overwrite.connect = True
        owner_overwrite.speak = True
        await channel.set_permissions(target, overwrite=owner_overwrite, reason="VC ownership transfer")

        set_temp_owner(channel.guild.id, channel.id, target.id)
        await interaction.response.send_message(f"Ownership transferred to {target.mention}.", ephemeral=True)


class VcControlView(discord.ui.View):
    def __init__(self, cog: "VoiceControl"):
        super().__init__(timeout=None)
        self.cog = cog

    async def _owner_channel(self, interaction: discord.Interaction) -> tuple[discord.VoiceChannel | None, dict | None]:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not member.guild or not member.voice or not isinstance(member.voice.channel, discord.VoiceChannel):
            await interaction.response.send_message("Join your temp VC first.", ephemeral=True)
            return None, None
        channel = member.voice.channel
        row = get_temp_channel(member.guild.id, channel.id)
        if not row:
            await interaction.response.send_message("This channel is not a managed temp VC.", ephemeral=True)
            return None, None
        if int(row["owner_id"]) != member.id:
            await interaction.response.send_message("Only the VC owner can use this control.", ephemeral=True)
            return None, None
        return channel, row

    @discord.ui.button(label="Lock", emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="vc:lock", row=0)
    async def lock(self, interaction: discord.Interaction, _: discord.ui.Button):
        channel, _r = await self._owner_channel(interaction)
        if not channel:
            return
        await channel.set_permissions(channel.guild.default_role, connect=False, reason=f"VC lock by {interaction.user}")
        await interaction.response.send_message("Locked.", ephemeral=True)

    @discord.ui.button(label="Unlock", emoji="🔓", style=discord.ButtonStyle.secondary, custom_id="vc:unlock", row=0)
    async def unlock(self, interaction: discord.Interaction, _: discord.ui.Button):
        channel, _r = await self._owner_channel(interaction)
        if not channel:
            return
        overwrite = channel.overwrites_for(channel.guild.default_role)
        overwrite.connect = None
        await channel.set_permissions(channel.guild.default_role, overwrite=overwrite, reason=f"VC unlock by {interaction.user}")
        await interaction.response.send_message("Unlocked.", ephemeral=True)

    @discord.ui.button(label="Hide", emoji="🙈", style=discord.ButtonStyle.secondary, custom_id="vc:hide", row=0)
    async def hide(self, interaction: discord.Interaction, _: discord.ui.Button):
        channel, _r = await self._owner_channel(interaction)
        if not channel:
            return
        overwrite = channel.overwrites_for(channel.guild.default_role)
        overwrite.view_channel = False
        await channel.set_permissions(channel.guild.default_role, overwrite=overwrite, reason=f"VC hide by {interaction.user}")
        await interaction.response.send_message("Hidden from @everyone.", ephemeral=True)

    @discord.ui.button(label="Unhide", emoji="👁️", style=discord.ButtonStyle.secondary, custom_id="vc:unhide", row=0)
    async def unhide(self, interaction: discord.Interaction, _: discord.ui.Button):
        channel, _r = await self._owner_channel(interaction)
        if not channel:
            return
        overwrite = channel.overwrites_for(channel.guild.default_role)
        overwrite.view_channel = None
        await channel.set_permissions(channel.guild.default_role, overwrite=overwrite, reason=f"VC unhide by {interaction.user}")
        await interaction.response.send_message("Visible to @everyone.", ephemeral=True)

    @discord.ui.button(label="Limit", emoji="👥", style=discord.ButtonStyle.secondary, custom_id="vc:limit", row=1)
    async def limit(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(LimitModal(self.cog))

    @discord.ui.button(label="Invite", emoji="➕", style=discord.ButtonStyle.secondary, custom_id="vc:invite", row=1)
    async def invite(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(MemberTargetModal(self.cog, "invite"))

    @discord.ui.button(label="Ban", emoji="⛔", style=discord.ButtonStyle.secondary, custom_id="vc:ban", row=1)
    async def ban(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(MemberTargetModal(self.cog, "ban"))

    @discord.ui.button(label="Permit", emoji="✅", style=discord.ButtonStyle.secondary, custom_id="vc:permit", row=1)
    async def permit(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(MemberTargetModal(self.cog, "permit"))

    @discord.ui.button(label="Rename", emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="vc:rename", row=2)
    async def rename(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(RenameModal(self.cog))

    @discord.ui.button(label="Bitrate", emoji="🎧", style=discord.ButtonStyle.secondary, custom_id="vc:bitrate", row=2)
    async def bitrate(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(BitrateModal(self.cog))

    @discord.ui.button(label="Region", emoji="🌍", style=discord.ButtonStyle.secondary, custom_id="vc:region", row=2)
    async def region(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(RegionModal(self.cog))

    @discord.ui.button(label="Template", emoji="🧩", style=discord.ButtonStyle.secondary, custom_id="vc:template", row=2)
    async def template(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(TemplateModal(self.cog))

    @discord.ui.button(label="Chat", emoji="💬", style=discord.ButtonStyle.secondary, custom_id="vc:chat", row=3)
    async def chat(self, interaction: discord.Interaction, _: discord.ui.Button):
        channel, _r = await self._owner_channel(interaction)
        if not channel:
            return

        category = channel.category
        existing = discord.utils.get(channel.guild.text_channels, topic=f"vc_chat_for:{channel.id}")
        if existing:
            return await interaction.response.send_message(f"Chat already exists: {existing.mention}", ephemeral=True)

        overwrites = {
            channel.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        }
        for m in channel.members:
            overwrites[m] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        name = f"chat-{channel.name}"[:100]
        text = await channel.guild.create_text_channel(
            name=name,
            category=category,
            overwrites=overwrites,
            topic=f"vc_chat_for:{channel.id}",
            reason=f"VC chat created by {interaction.user}",
        )
        await interaction.response.send_message(f"Created chat: {text.mention}", ephemeral=True)

    @discord.ui.button(label="Waiting", emoji="🕒", style=discord.ButtonStyle.secondary, custom_id="vc:waiting", row=3)
    async def waiting(self, interaction: discord.Interaction, _: discord.ui.Button):
        channel, _r = await self._owner_channel(interaction)
        if not channel:
            return

        current = len(channel.members)
        if channel.user_limit == current and current > 0:
            await channel.edit(user_limit=0, reason=f"VC waiting off by {interaction.user}")
            await interaction.response.send_message("Waiting mode disabled.", ephemeral=True)
        else:
            await channel.edit(user_limit=max(1, current), reason=f"VC waiting on by {interaction.user}")
            await interaction.response.send_message("Waiting mode enabled.", ephemeral=True)

    @discord.ui.button(label="Claim", emoji="👑", style=discord.ButtonStyle.secondary, custom_id="vc:claim", row=3)
    async def claim(self, interaction: discord.Interaction, _: discord.ui.Button):
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not member.voice or not isinstance(member.voice.channel, discord.VoiceChannel):
            return await interaction.response.send_message("Join the temp VC first.", ephemeral=True)

        channel = member.voice.channel
        row = get_temp_channel(member.guild.id, channel.id)
        if not row:
            return await interaction.response.send_message("This is not a managed temp VC.", ephemeral=True)
        owner = member.guild.get_member(int(row["owner_id"]))
        if owner and owner.voice and owner.voice.channel and owner.voice.channel.id == channel.id:
            return await interaction.response.send_message("Owner is currently in this VC. Cannot claim.", ephemeral=True)

        await channel.set_permissions(member, overwrite=discord.PermissionOverwrite(
            manage_channels=True,
            manage_permissions=True,
            move_members=True,
            connect=True,
            speak=True,
        ), reason="VC claim")
        set_temp_owner(member.guild.id, channel.id, member.id)
        await interaction.response.send_message("You claimed this VC.", ephemeral=True)

    @discord.ui.button(label="Transfer", emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="vc:transfer", row=3)
    async def transfer(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(TransferModal(self.cog))


class VoiceControl(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.view = VcControlView(self)
        self.bot.add_view(self.view)

    def _build_interface_embed(self, guild: discord.Guild) -> discord.Embed:
        embed = discord.Embed(
            title="Astro Interface",
            description=(
                "You can use this interface to manage your voice channel.\n"
                "You can also use `-vc` commands!"
            ),
            color=0x2b2d31,
        )
        embed.add_field(
            name="Controls",
            value=(
                "`Lock` `Unlock` `Hide` `Unhide`\n"
                "`Limit` `Invite` `Ban` `Permit`\n"
                "`Rename` `Bitrate` `Region` `Template`\n"
                "`Chat` `Waiting` `Claim` `Transfer`"
            ),
            inline=False,
        )
        embed.set_footer(text="Use the buttons below to manage your voice channel")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        return embed

    async def send_panel(self, guild: discord.Guild, channel: discord.TextChannel) -> discord.Message:
        msg = await channel.send(embed=self._build_interface_embed(guild), view=self.view)
        cfg = get_vc_config(guild.id)
        cfg["interface_channel_id"] = channel.id
        cfg["interface_message_id"] = msg.id
        save_vc_config(guild.id, cfg)
        return msg

    @commands.group(name="vc", invoke_without_command=True)
    @commands.guild_only()
    async def vc_group(self, ctx):
        await ctx.send(
            "Use: `-vc setup <join_channel_id> [interface_channel_id] [category_id]`, "
            "`-vc panel`, `-vc status`, `-vc template <text>`, `-vc disable`, `-vc cleanup`"
        )

    @vc_group.command(name="setup")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def vc_setup(self, ctx, join_channel_id: int, interface_channel_id: int = None, category_id: int = None):
        guild = ctx.guild
        join = guild.get_channel(join_channel_id)
        if not isinstance(join, discord.VoiceChannel):
            return await ctx.send("❌ join_channel_id must be a voice channel ID.")

        interface_channel = guild.get_channel(interface_channel_id) if interface_channel_id else ctx.channel
        if not isinstance(interface_channel, discord.TextChannel):
            return await ctx.send("❌ interface_channel_id must be a text channel ID.")

        category = guild.get_channel(category_id) if category_id else (join.category)
        if category_id and not isinstance(category, discord.CategoryChannel):
            return await ctx.send("❌ category_id must be a category channel ID.")

        cfg = get_vc_config(guild.id)
        cfg.update(
            {
                "lobby_channel_id": join.id,
                "interface_channel_id": interface_channel.id,
                "category_id": category.id if category else None,
            }
        )
        save_vc_config(guild.id, cfg)

        panel = await self.send_panel(guild, interface_channel)
        await ctx.send(
            f"✅ VC system enabled.\n"
            f"Join-to-create channel: {join.mention}\n"
            f"Interface panel: {panel.jump_url}"
        )

    @vc_group.command(name="panel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def vc_panel(self, ctx, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        panel = await self.send_panel(ctx.guild, target)
        await ctx.send(f"✅ Panel sent: {panel.jump_url}")

    @vc_group.command(name="status")
    @commands.guild_only()
    async def vc_status(self, ctx):
        cfg = get_vc_config(ctx.guild.id)
        if not cfg.get("lobby_channel_id"):
            return await ctx.send("❌ VC system is not configured. Use `-vc setup ...`")

        lobby = ctx.guild.get_channel(int(cfg["lobby_channel_id"]))
        iface = ctx.guild.get_channel(int(cfg["interface_channel_id"])) if cfg.get("interface_channel_id") else None
        category = ctx.guild.get_channel(int(cfg["category_id"])) if cfg.get("category_id") else None
        temp_rows = list_temp_channels(ctx.guild.id)

        embed = discord.Embed(title="VC System Status", color=0x2b2d31)
        embed.add_field(name="Lobby", value=lobby.mention if lobby else f"`{cfg['lobby_channel_id']}`", inline=False)
        embed.add_field(name="Interface", value=iface.mention if iface else "Not set", inline=False)
        embed.add_field(name="Category", value=category.name if category else "Lobby category", inline=False)
        embed.add_field(name="Template", value=f"`{cfg.get('naming_template')}`", inline=False)
        embed.add_field(name="Active temp channels", value=f"`{len(temp_rows)}`", inline=False)
        await ctx.send(embed=embed)

    @vc_group.command(name="template")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def vc_template(self, ctx, *, template: str):
        cfg = get_vc_config(ctx.guild.id)
        cfg["naming_template"] = template.strip()[:80]
        save_vc_config(ctx.guild.id, cfg)
        await ctx.send(f"✅ VC naming template updated to `{cfg['naming_template']}`")

    @vc_group.command(name="disable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def vc_disable(self, ctx):
        delete_vc_config(ctx.guild.id)
        await ctx.send("✅ VC system disabled for this server.")

    @vc_group.command(name="cleanup")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def vc_cleanup(self, ctx):
        rows = list_temp_channels(ctx.guild.id)
        removed = 0
        for row in rows:
            if not ctx.guild.get_channel(int(row["channel_id"])):
                delete_temp_channel(ctx.guild.id, int(row["channel_id"]))
                removed += 1
        await ctx.send(f"✅ Cleanup complete. Removed `{removed}` stale VC records.")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if isinstance(channel, discord.VoiceChannel):
            delete_temp_channel(channel.guild.id, channel.id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot or not member.guild:
            return

        cfg = get_vc_config(member.guild.id)
        lobby_id = cfg.get("lobby_channel_id")
        if not lobby_id:
            return

        # Join-to-create trigger
        if after.channel and after.channel.id == int(lobby_id):
            existing = get_owned_channel(member.guild.id, member.id)
            if existing:
                existing_ch = member.guild.get_channel(int(existing["channel_id"]))
                if isinstance(existing_ch, discord.VoiceChannel):
                    if member.voice and member.voice.channel and member.voice.channel.id != existing_ch.id:
                        try:
                            await member.move_to(existing_ch, reason="Move to your existing temp VC")
                        except discord.HTTPException:
                            pass
                    return

            category = member.guild.get_channel(int(cfg["category_id"])) if cfg.get("category_id") else after.channel.category
            template = cfg.get("naming_template") or "{user}'s VC"
            name = _format_template(template, member)

            overwrites = {
                member.guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                member: discord.PermissionOverwrite(
                    connect=True,
                    speak=True,
                    manage_channels=True,
                    manage_permissions=True,
                    move_members=True,
                ),
            }

            try:
                vc = await member.guild.create_voice_channel(
                    name=name,
                    category=category,
                    user_limit=int(cfg.get("default_user_limit") or 0),
                    overwrites=overwrites,
                    reason=f"Join-to-create for {member}",
                )
            except discord.HTTPException:
                return

            save_temp_channel(member.guild.id, vc.id, member.id)

            try:
                await member.move_to(vc, reason="Join-to-create channel")
            except discord.HTTPException:
                pass

        # Auto-delete temp VC when empty
        if before.channel and isinstance(before.channel, discord.VoiceChannel):
            row = get_temp_channel(member.guild.id, before.channel.id)
            if row and len(before.channel.members) == 0:
                delete_temp_channel(member.guild.id, before.channel.id)
                try:
                    await before.channel.delete(reason="Temp VC empty")
                except discord.HTTPException:
                    pass


async def setup(bot):
    await bot.add_cog(VoiceControl(bot))
