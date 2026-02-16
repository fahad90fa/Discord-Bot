import discord
from discord.ext import commands, tasks
import random
import shlex
from datetime import datetime, timedelta
import pytz
import db

GIVEAWAYS_FILE = "giveaways.json"


def _load_json(guild_id, default):
    return db.get_setting(GIVEAWAYS_FILE, int(guild_id), default)


def _save_json(guild_id, data):
    db.set_setting(GIVEAWAYS_FILE, int(guild_id), data)


def parse_duration(s: str) -> int:
    """
    Parse duration like: 10m, 2h, 1d, 1w, 90s.
    Returns seconds (int). Raises ValueError.
    """
    s = (s or "").strip().lower()
    if not s:
        raise ValueError("empty")
    num = ""
    unit = ""
    for ch in s:
        if ch.isdigit():
            num += ch
        else:
            unit += ch
    if not num:
        raise ValueError("missing number")
    n = int(num)
    unit = unit.strip() or "s"
    mult = {"s": 1, "sec": 1, "secs": 1, "m": 60, "min": 60, "mins": 60, "h": 3600, "hr": 3600, "hrs": 3600, "d": 86400, "day": 86400, "days": 86400, "w": 604800}.get(unit)
    if mult is None:
        raise ValueError("bad unit")
    return n * mult


def _utcnow():
    return datetime.now(pytz.UTC)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(pytz.UTC).isoformat()


def _fromiso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(pytz.UTC)


def _format_dt_pkt(dt_utc: datetime) -> str:
    pkt = dt_utc.astimezone(pytz.timezone("Asia/Karachi"))
    return pkt.strftime("%b %d, %I:%M %p PKT")


async def _eligible_members_from_message(
    message: discord.Message,
    required_role_id: int | None,
    min_join_seconds: int,
):
    """
    Reaction-based entries: users who reacted with 🎉.
    Filters bots and requirement constraints.
    """
    guild = message.guild
    if not guild:
        return []

    reaction = discord.utils.get(message.reactions, emoji="🎉")
    if not reaction:
        return []

    users = []
    async for user in reaction.users(limit=None):
        if user.bot:
            continue
        member = guild.get_member(user.id)
        if not member:
            continue

        if required_role_id and not discord.utils.get(member.roles, id=required_role_id):
            continue

        if min_join_seconds > 0:
            if not member.joined_at:
                continue
            joined_at = member.joined_at
            if joined_at.tzinfo is None:
                joined_at = pytz.UTC.localize(joined_at)
            if (_utcnow() - joined_at).total_seconds() < min_join_seconds:
                continue

        users.append(member)

    return users


class Giveaways(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.giveaway_watcher.start()

    def cog_unload(self):
        if self.giveaway_watcher.is_running():
            self.giveaway_watcher.cancel()

    @tasks.loop(seconds=30)
    async def giveaway_watcher(self):
        now = _utcnow()
        for guild in self.bot.guilds:
            data = _load_json(guild.id, {"giveaways": []})
            giveaways = data.get("giveaways", [])
            if not giveaways:
                continue

            changed = False

            for gw in giveaways:
                if not gw.get("active", False):
                    continue
                try:
                    ends_at = _fromiso(gw["ends_at"])
                except Exception:
                    continue

                if ends_at > now:
                    continue

                # End it
                ok = await self._end_giveaway_by_record(gw, reason="AUTO_END")
                if ok:
                    gw["active"] = False
                    gw["ended_at"] = _iso(now)
                    changed = True

            if changed:
                _save_json(guild.id, data)

    @giveaway_watcher.before_loop
    async def before_giveaway_watcher(self):
        await self.bot.wait_until_ready()

    async def _end_giveaway_by_record(self, gw: dict, reason: str):
        try:
            channel = self.bot.get_channel(int(gw["channel_id"]))
            if not channel:
                return False
            message = await channel.fetch_message(int(gw["message_id"]))
            if not message:
                return False
        except Exception:
            return False

        required_role_id = gw.get("required_role_id")
        min_join_seconds = int(gw.get("min_join_seconds", 0) or 0)
        winners_count = int(gw.get("winners", 1) or 1)

        eligible = await _eligible_members_from_message(
            message,
            int(required_role_id) if required_role_id else None,
            min_join_seconds,
        )

        if eligible:
            winners = random.sample(eligible, k=min(winners_count, len(eligible)))
            winner_mentions = ", ".join(w.mention for w in winners)
            gw["winner_ids"] = [w.id for w in winners]
        else:
            winners = []
            winner_mentions = None
            gw["winner_ids"] = []

        # Update giveaway embed to ended
        try:
            embed = message.embeds[0] if message.embeds else discord.Embed(color=0x2b2d31)
            embed.title = "🎁 GIVEAWAY ENDED"
            embed.color = 0xe74c3c
            embed.add_field(name="Result", value=(winner_mentions or "`No valid entries.`"), inline=False)
            embed.set_footer(text=f"Ended • {reason}")
            await message.edit(embed=embed)
        except Exception:
            pass

        # Announce winners
        try:
            if winner_mentions:
                await channel.send(f"🎉 Congratulations {winner_mentions}! You won **{gw.get('prize','the giveaway')}**.")
            else:
                await channel.send("⚠️ Giveaway ended, but there were no valid entries.")
        except Exception:
            pass

        return True

    @commands.group(name="giveaway", aliases=["gaw", "gw"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def giveaway_group(self, ctx):
        await ctx.send(
            "Use:\n"
            "`-giveaway start <duration> <winners> [#channel] [--join 7d] [--role @Role] <prize...>`\n"
            "`-giveaway end <message_id> [#channel]`\n"
            "`-giveaway reroll <message_id> [#channel]`"
        )

    @giveaway_group.command(name="start")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_start(self, ctx, *, args: str):
        """
        Start a giveaway (reaction-based).
        Example:
        -giveaway start 2h 1 #giveaways --join 7d --role @VIP Nitro Classic
        """
        try:
            tokens = shlex.split(args)
        except Exception:
            return await ctx.send("❌ Invalid arguments.")

        if len(tokens) < 3:
            return await ctx.send("❌ Usage: `-giveaway start <duration> <winners> [#channel] [--join 7d] [--role @Role] <prize...>`")

        duration_s = tokens[0]
        winners_s = tokens[1]

        try:
            duration_seconds = parse_duration(duration_s)
            winners = int(winners_s)
            if winners <= 0:
                raise ValueError()
        except Exception:
            return await ctx.send("❌ Invalid duration or winners. Example: `2h 1` or `30m 3`.")

        # discord.py Context doesn't expose channel_mentions; use message channel_mentions.
        channel = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else ctx.channel
        role = ctx.message.role_mentions[0] if ctx.message.role_mentions else None

        min_join_seconds = 0
        prize_tokens = []
        i = 2
        while i < len(tokens):
            t = tokens[i]
            if t == "--join" and i + 1 < len(tokens):
                try:
                    min_join_seconds = parse_duration(tokens[i + 1])
                except Exception:
                    return await ctx.send("❌ Invalid `--join` value. Example: `--join 7d`.")
                i += 2
                continue
            if t == "--role":
                # role mention is taken from ctx.message.role_mentions; just skip flag + value if present
                i += 2 if i + 1 < len(tokens) else 1
                continue
            prize_tokens.append(t)
            i += 1

        prize = " ".join(prize_tokens).strip()
        if not prize:
            return await ctx.send("❌ Missing prize text.")

        ends_at = _utcnow() + timedelta(seconds=duration_seconds)

        embed = discord.Embed(
            title="🎁 GIVEAWAY",
            description=f"**Prize:** {prize}\n\nReact with 🎉 to enter.",
            color=0x2b2d31,
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Winners", value=f"`{winners}`", inline=True)
        embed.add_field(name="Ends", value=f"`{_format_dt_pkt(ends_at)}`", inline=True)
        if role:
            embed.add_field(name="Required Role", value=role.mention, inline=False)
        if min_join_seconds > 0:
            days = int(min_join_seconds // 86400)
            embed.add_field(name="Min Time In Server", value=f"`{days} day(s)`", inline=False)
        embed.set_footer(text=f"Host: {ctx.author.name}")

        msg = await channel.send(embed=embed)
        try:
            await msg.add_reaction("🎉")
        except Exception:
            pass

        data = _load_json(ctx.guild.id, {"giveaways": []})
        record = {
            "guild_id": str(ctx.guild.id),
            "channel_id": str(channel.id),
            "message_id": str(msg.id),
            "host_id": str(ctx.author.id),
            "prize": prize,
            "winners": winners,
            "required_role_id": str(role.id) if role else None,
            "min_join_seconds": min_join_seconds,
            "starts_at": _iso(_utcnow()),
            "ends_at": _iso(ends_at),
            "active": True,
            "winner_ids": []
        }
        data["giveaways"].append(record)
        _save_json(ctx.guild.id, data)

        conf = discord.Embed(
            title="✅ GIVEAWAY STARTED",
            description=f"Posted in {channel.mention}\nEnds: `{_format_dt_pkt(ends_at)}`",
            color=0x2ecc71
        )
        await ctx.send(embed=conf)

    @giveaway_group.command(name="end")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_end(self, ctx, message_id: int, channel: discord.TextChannel | None = None):
        channel = channel or ctx.channel
        data = _load_json(ctx.guild.id, {"giveaways": []})

        gw = None
        for r in data.get("giveaways", []):
            if str(r.get("guild_id")) == str(ctx.guild.id) and str(r.get("message_id")) == str(message_id):
                gw = r
                break

        if not gw or not gw.get("active", False):
            return await ctx.send("❌ Active giveaway not found for that message ID.")

        ok = await self._end_giveaway_by_record(gw, reason="MANUAL_END")
        if ok:
            gw["active"] = False
            gw["ended_at"] = _iso(_utcnow())
            _save_json(ctx.guild.id, data)
            return await ctx.send("✅ Giveaway ended.")
        return await ctx.send("❌ Failed to end giveaway (message not found?).")

    @giveaway_group.command(name="reroll")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_reroll(self, ctx, message_id: int, channel: discord.TextChannel | None = None):
        channel = channel or ctx.channel
        data = _load_json(ctx.guild.id, {"giveaways": []})

        gw = None
        for r in data.get("giveaways", []):
            if str(r.get("guild_id")) == str(ctx.guild.id) and str(r.get("message_id")) == str(message_id):
                gw = r
                break

        if not gw or gw.get("active", False):
            return await ctx.send("❌ Giveaway not found or still active (end it first).")

        try:
            msg = await channel.fetch_message(message_id)
        except Exception:
            return await ctx.send("❌ Giveaway message not found in that channel.")

        required_role_id = gw.get("required_role_id")
        min_join_seconds = int(gw.get("min_join_seconds", 0) or 0)
        winners_count = int(gw.get("winners", 1) or 1)
        prev_winner_ids = set(int(x) for x in (gw.get("winner_ids") or []))

        eligible = await _eligible_members_from_message(
            msg,
            int(required_role_id) if required_role_id else None,
            min_join_seconds,
        )
        eligible = [m for m in eligible if m.id not in prev_winner_ids]

        if not eligible:
            return await ctx.send("⚠️ No eligible users to reroll.")

        winners = random.sample(eligible, k=min(winners_count, len(eligible)))
        gw["winner_ids"] = [w.id for w in winners]
        _save_json(ctx.guild.id, data)

        winner_mentions = ", ".join(w.mention for w in winners)
        await channel.send(f"🔁 Reroll winners: {winner_mentions} (Prize: **{gw.get('prize','giveaway')}**)")

    @giveaway_group.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_list(self, ctx):
        data = _load_json(ctx.guild.id, {"giveaways": []})
        active = [g for g in data.get("giveaways", []) if g.get("active", False) and str(g.get("guild_id")) == str(ctx.guild.id)]
        if not active:
            return await ctx.send("📋 No active giveaways.")

        embed = discord.Embed(title="📋 ACTIVE GIVEAWAYS", color=0x3498db)
        for gw in active[:15]:
            try:
                ends = _fromiso(gw["ends_at"])
                ends_txt = _format_dt_pkt(ends)
            except Exception:
                ends_txt = "Unknown"
            embed.add_field(
                name=f"🎁 {gw.get('prize','Giveaway')[:80]}",
                value=f"Channel: <#{gw.get('channel_id')}>\nMessage: `{gw.get('message_id')}`\nEnds: `{ends_txt}`",
                inline=False
            )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Giveaways(bot))
