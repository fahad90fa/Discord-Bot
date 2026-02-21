import asyncio
from datetime import datetime, timedelta

import discord
from discord.ext import commands

import db


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _to_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def get_invite_log_channel(guild_id: int) -> int | None:
    row = db.execute(
        "SELECT log_channel_id FROM invite_config WHERE guild_id = %s",
        (int(guild_id),),
        fetchone=True,
    )
    return row.get("log_channel_id") if row else None


def set_invite_log_channel(guild_id: int, channel_id: int | None):
    if channel_id is None:
        db.execute("DELETE FROM invite_config WHERE guild_id = %s", (int(guild_id),))
        return
    db.execute(
        """
        INSERT INTO invite_config (guild_id, log_channel_id)
        VALUES (%s, %s)
        ON CONFLICT (guild_id) DO UPDATE SET log_channel_id = EXCLUDED.log_channel_id
        """,
        (int(guild_id), int(channel_id)),
    )


def insert_invite_join(guild_id: int, user_id: int, invite_code: str | None, inviter_id: int | None, is_fake: bool, rejoin_7d: bool):
    db.execute(
        """
        INSERT INTO invite_events (guild_id, user_id, invite_code, inviter_id, joined_at, left_at, is_fake, rejoin_7d)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (int(guild_id), int(user_id), invite_code, int(inviter_id) if inviter_id else None, _now_iso(), None, bool(is_fake), bool(rejoin_7d)),
    )


def close_latest_open_join(guild_id: int, user_id: int) -> dict | None:
    row = db.execute(
        """
        SELECT id, inviter_id FROM invite_events
        WHERE guild_id = %s AND user_id = %s AND left_at IS NULL
        ORDER BY joined_at DESC
        LIMIT 1
        """,
        (int(guild_id), int(user_id)),
        fetchone=True,
    )
    if not row:
        return None
    db.execute(
        "UPDATE invite_events SET left_at = %s WHERE id = %s",
        (_now_iso(), int(row["id"])),
    )
    return row


def get_latest_leave_dt(guild_id: int, user_id: int) -> datetime | None:
    row = db.execute(
        """
        SELECT left_at FROM invite_events
        WHERE guild_id = %s AND user_id = %s AND left_at IS NOT NULL
        ORDER BY left_at DESC
        LIMIT 1
        """,
        (int(guild_id), int(user_id)),
        fetchone=True,
    )
    return _to_dt(row.get("left_at") if row else None)


def get_invite_stats(guild_id: int, inviter_id: int) -> dict:
    row = db.execute(
        """
        SELECT
          COALESCE(COUNT(*) FILTER (WHERE inviter_id = %s), 0) AS joins,
          COALESCE(COUNT(*) FILTER (WHERE inviter_id = %s AND left_at IS NOT NULL), 0) AS left_count,
          COALESCE(COUNT(*) FILTER (WHERE inviter_id = %s AND is_fake = TRUE), 0) AS fake_count,
          COALESCE(COUNT(*) FILTER (WHERE inviter_id = %s AND rejoin_7d = TRUE), 0) AS rejoin_count
        FROM invite_events
        WHERE guild_id = %s
        """,
        (int(inviter_id), int(inviter_id), int(inviter_id), int(inviter_id), int(guild_id)),
        fetchone=True,
    ) or {}

    joins = int(row.get("joins", 0))
    left_count = int(row.get("left_count", 0))
    fake_count = int(row.get("fake_count", 0))
    rejoin_count = int(row.get("rejoin_count", 0))
    # "Invites" tracks effective active invites, while fake/rejoin remain separate counters.
    net = joins - left_count

    return {
        "net": net,
        "joins": joins,
        "left": left_count,
        "fake": fake_count,
        "rejoins": rejoin_count,
    }

def get_active_invited_members(guild_id: int, inviter_id: int) -> list[dict]:
    return db.execute(
        """
        SELECT user_id, joined_at, invite_code
        FROM invite_events
        WHERE guild_id = %s
          AND inviter_id = %s
          AND left_at IS NULL
        ORDER BY joined_at DESC
        """,
        (int(guild_id), int(inviter_id)),
        fetchall=True,
    ) or []


class InviteTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invite_cache: dict[int, dict[str, int]] = {}

    async def _refresh_guild_cache(self, guild: discord.Guild):
        if not guild.me.guild_permissions.manage_guild:
            self.invite_cache[guild.id] = {}
            return
        try:
            invites = await guild.invites()
            self.invite_cache[guild.id] = {i.code: i.uses or 0 for i in invites}
        except discord.HTTPException:
            self.invite_cache[guild.id] = {}

    async def cog_load(self):
        for guild in self.bot.guilds:
            await self._refresh_guild_cache(guild)

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self._refresh_guild_cache(guild)

    def _build_stats_embed(self, member: discord.Member, stats: dict) -> discord.Embed:
        net = stats["net"]
        joins = stats["joins"]
        left = stats["left"]
        fake = stats["fake"]
        rejoins = stats["rejoins"]

        rank_color = 0x2ecc71 if net > 0 else (0xf1c40f if net == 0 else 0xe74c3c)
        status = "ACTIVE" if net > 0 else ("NEUTRAL" if net == 0 else "NEGATIVE")

        grid = (
            "```ansi\n"
            f"\u001b[1;36mINVITES :\u001b[0m \u001b[1;37m{net}\u001b[0m\n"
            f"\u001b[1;34mJOINS   :\u001b[0m \u001b[0;37m{joins}\u001b[0m\n"
            f"\u001b[1;33mLEFT    :\u001b[0m \u001b[0;37m{left}\u001b[0m\n"
            f"\u001b[1;31mFAKE    :\u001b[0m \u001b[0;37m{fake}\u001b[0m\n"
            f"\u001b[1;35mREJOINS :\u001b[0m \u001b[0;37m{rejoins} (7d)\u001b[0m\n"
            "```"
        )

        embed = discord.Embed(
            title="INVITE INTELLIGENCE BOARD",
            description=(
                "```ansi\n"
                f"\u001b[1;32mTARGET :\u001b[0m \u001b[0;37m{member.display_name}\u001b[0m\n"
                f"\u001b[1;32mSTATUS :\u001b[0m \u001b[0;37m{status}\u001b[0m\n"
                "```\n"
                f"{grid}"
            ),
            color=rank_color,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Real-time Invite Tracker • Traders Union")
        return embed

    @commands.group(name="invite", aliases=["invites", "i", "nvite"], invoke_without_command=True)
    @commands.guild_only()
    async def invite_group(self, ctx, member: discord.Member = None):
        target = member or ctx.author

        loader = await ctx.send("🛰️ `LOCKING ON INVITE TELEMETRY...`")
        await asyncio.sleep(0.35)
        await loader.edit(content="📡 `DECRYPTING REFERRAL FOOTPRINTS...`")
        await asyncio.sleep(0.35)

        stats = get_invite_stats(ctx.guild.id, target.id)
        await loader.edit(content="✅ `INTEL STREAM READY.`")
        await ctx.send(embed=self._build_stats_embed(target, stats))

    @invite_group.command(name="log")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def invite_log(self, ctx, channel: discord.TextChannel = None):
        if channel is None:
            cid = get_invite_log_channel(ctx.guild.id)
            if not cid:
                return await ctx.send("❌ Invite log channel is not set. Use `-invite log #channel`.")
            current = ctx.guild.get_channel(int(cid))
            return await ctx.send(f"✅ Invite log channel: {current.mention if current else f'`{cid}`'}")

        set_invite_log_channel(ctx.guild.id, channel.id)
        await ctx.send(
            embed=discord.Embed(
                title="INVITE LOG ROUTED",
                description=f"Real-time invite logs will be sent to {channel.mention}",
                color=0x2ecc71,
            )
        )

    @invite_group.command(name="off", aliases=["disable"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def invite_log_off(self, ctx):
        set_invite_log_channel(ctx.guild.id, None)
        await ctx.send("✅ Invite log disabled.")

    @invite_group.command(name="show", aliases=["members", "joined"])
    @commands.guild_only()
    async def invite_show_members(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        rows = get_active_invited_members(ctx.guild.id, target.id)

        if not rows:
            embed = discord.Embed(
                title="INVITED MEMBERS",
                description=f"No active joined members found for {target.mention}.",
                color=0x2b2d31,
            )
            embed.set_footer(text="Only currently joined members are counted")
            return await ctx.send(embed=embed)

        lines = []
        for idx, row in enumerate(rows[:25], start=1):
            uid = int(row["user_id"])
            joined_at = _to_dt(row.get("joined_at"))
            ts = f"<t:{int(joined_at.timestamp())}:R>" if joined_at else "`unknown`"
            code = row.get("invite_code") or "unknown"
            lines.append(f"`{idx:02d}` <@{uid}> • code `{code}` • joined {ts}")

        embed = discord.Embed(
            title="INVITED MEMBERS",
            description=(
                f"**Inviter:** {target.mention}\n"
                f"**Active Joined:** `{len(rows)}`\n\n"
                + "\n".join(lines)
            ),
            color=0x2ecc71,
            timestamp=discord.utils.utcnow(),
        )
        if len(rows) > 25:
            embed.set_footer(text=f"Showing first 25 of {len(rows)} active members")
        else:
            embed.set_footer(text="Live list • leaves are auto-deducted")
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        guild = invite.guild
        if not guild:
            return
        if guild.id not in self.invite_cache:
            self.invite_cache[guild.id] = {}
        self.invite_cache[guild.id][invite.code] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        guild = invite.guild
        if not guild:
            return
        self.invite_cache.setdefault(guild.id, {}).pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if not guild or member.bot:
            return

        previous = self.invite_cache.get(guild.id, {})
        invite_code = None
        inviter_id = None

        if guild.me.guild_permissions.manage_guild:
            try:
                invites = await guild.invites()
            except discord.HTTPException:
                invites = []

            current = {i.code: i.uses or 0 for i in invites}
            for inv in invites:
                before_uses = previous.get(inv.code, 0)
                if (inv.uses or 0) > before_uses:
                    invite_code = inv.code
                    inviter_id = inv.inviter.id if inv.inviter else None
                    break

            self.invite_cache[guild.id] = current

        account_age = discord.utils.utcnow() - member.created_at
        is_fake = account_age < timedelta(days=7)

        last_leave = get_latest_leave_dt(guild.id, member.id)
        rejoin_7d = bool(last_leave and (datetime.utcnow() - last_leave) <= timedelta(days=7))

        insert_invite_join(guild.id, member.id, invite_code, inviter_id, is_fake, rejoin_7d)

        log_channel_id = get_invite_log_channel(guild.id)
        if not log_channel_id:
            return
        ch = guild.get_channel(int(log_channel_id))
        if not isinstance(ch, discord.TextChannel):
            return

        embed = discord.Embed(
            title="INVITE JOIN EVENT",
            description=(
                f"**Member:** {member.mention}\n"
                f"**Inviter:** {f'<@{inviter_id}>' if inviter_id else '`Unknown`'}\n"
                f"**Code:** `{invite_code or 'Unknown'}`\n"
                f"**Fake:** `{'YES' if is_fake else 'NO'}`\n"
                f"**Rejoin (7d):** `{'YES' if rejoin_7d else 'NO'}`"
            ),
            color=0x2ecc71,
            timestamp=discord.utils.utcnow(),
        )
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        row = close_latest_open_join(member.guild.id, member.id)
        linked_inviter = f"<@{row.get('inviter_id')}>" if row and row.get("inviter_id") else "`Unknown`"

        log_channel_id = get_invite_log_channel(member.guild.id)
        if not log_channel_id:
            return
        ch = member.guild.get_channel(int(log_channel_id))
        if not isinstance(ch, discord.TextChannel):
            return

        embed = discord.Embed(
            title="INVITE LEAVE EVENT",
            description=(
                f"**Member:** `{member}`\n"
                f"**Linked Inviter:** {linked_inviter}"
            ),
            color=0xe67e22,
            timestamp=discord.utils.utcnow(),
        )
        await ch.send(embed=embed)


async def setup(bot):
    await bot.add_cog(InviteTracker(bot))
