import discord
from discord.ext import commands, tasks
import shlex
from datetime import datetime
import pytz
import db

ANNOUNCE_FILE = "scheduled_announcements.json"


def _load_json(path, default):
    return db.get_json(path, default, migrate_file=path)


def _save_json(path, data):
    db.set_json(path, data)


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


def parse_pkt_datetime(date_s: str, time_s: str) -> datetime:
    """
    Parse PKT date/time formats:
    - YYYY-MM-DD HH:MM
    - DD/MM/YY HH:MM
    Returns UTC datetime.
    """
    tz = pytz.timezone("Asia/Karachi")
    dt_local = None
    for fmt in ("%Y-%m-%d %H:%M", "%d/%m/%y %H:%M"):
        try:
            dt_local = datetime.strptime(f"{date_s} {time_s}", fmt)
            break
        except Exception:
            continue
    if not dt_local:
        raise ValueError("bad datetime")
    dt_local = tz.localize(dt_local)
    return dt_local.astimezone(pytz.UTC)


class Announcements(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.announcement_watcher.start()

    def cog_unload(self):
        if self.announcement_watcher.is_running():
            self.announcement_watcher.cancel()

    @tasks.loop(seconds=20)
    async def announcement_watcher(self):
        data = _load_json(ANNOUNCE_FILE, {"items": []})
        items = data.get("items", [])
        if not items:
            return

        now = _utcnow()
        changed = False
        remaining = []

        for item in items:
            if item.get("sent"):
                continue
            try:
                run_at = _fromiso(item["run_at"])
            except Exception:
                continue
            if run_at > now:
                remaining.append(item)
                continue

            channel = self.bot.get_channel(int(item["channel_id"]))
            if not channel:
                item["sent"] = True
                changed = True
                continue

            try:
                await channel.send(item["content"], allowed_mentions=discord.AllowedMentions.all())
            except Exception:
                # Keep it for retry
                remaining.append(item)
                continue

            item["sent"] = True
            item["sent_at"] = _iso(now)
            changed = True

        # Keep unsent items only (sent items are dropped)
        if changed:
            data["items"] = remaining
            _save_json(ANNOUNCE_FILE, data)

    @announcement_watcher.before_loop
    async def before_announcement_watcher(self):
        await self.bot.wait_until_ready()

    @commands.group(name="announce", aliases=["schedule"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def announce_group(self, ctx):
        await ctx.send(
            "Use:\n"
            "`-announce add #channel <YYYY-MM-DD> <HH:MM> <message...>` (PKT)\n"
            "`-announce list`\n"
            "`-announce cancel <id>`\n"
            "`-announce test #channel <message...>`"
        )

    @announce_group.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def announce_add(self, ctx, channel: discord.TextChannel, date_s: str, time_s: str, *, content: str):
        try:
            run_at_utc = parse_pkt_datetime(date_s, time_s)
        except Exception:
            return await ctx.send("❌ Invalid date/time. Example: `-announce add #ch 2026-02-15 21:00 hello`")

        if run_at_utc <= _utcnow():
            return await ctx.send("❌ Time must be in the future (PKT).")

        data = _load_json(ANNOUNCE_FILE, {"items": []})
        next_id = 1
        if data["items"]:
            try:
                next_id = max(int(x.get("id", 0)) for x in data["items"]) + 1
            except Exception:
                next_id = len(data["items"]) + 1

        item = {
            "id": next_id,
            "guild_id": str(ctx.guild.id),
            "channel_id": str(channel.id),
            "run_at": _iso(run_at_utc),
            "content": content,
            "created_by": str(ctx.author.id),
            "created_at": _iso(_utcnow()),
            "sent": False
        }
        data["items"].append(item)
        _save_json(ANNOUNCE_FILE, data)

        pkt = run_at_utc.astimezone(pytz.timezone("Asia/Karachi"))
        embed = discord.Embed(
            title="✅ ANNOUNCEMENT SCHEDULED",
            description=f"**ID:** `{next_id}`\n**Channel:** {channel.mention}\n**Time (PKT):** `{pkt.strftime('%b %d, %I:%M %p')}`",
            color=0x2ecc71
        )
        await ctx.send(embed=embed)

    @announce_group.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def announce_list(self, ctx):
        data = _load_json(ANNOUNCE_FILE, {"items": []})
        items = [i for i in data.get("items", []) if str(i.get("guild_id")) == str(ctx.guild.id) and not i.get("sent")]
        if not items:
            return await ctx.send("📋 No scheduled announcements.")

        embed = discord.Embed(title="📋 SCHEDULED ANNOUNCEMENTS", color=0x3498db)
        for item in sorted(items, key=lambda x: x.get("run_at", ""))[:15]:
            try:
                run_at = _fromiso(item["run_at"]).astimezone(pytz.timezone("Asia/Karachi"))
                when = run_at.strftime("%Y-%m-%d %I:%M %p PKT")
            except Exception:
                when = "Unknown"
            content_preview = (item.get("content") or "").replace("\n", " ")
            if len(content_preview) > 80:
                content_preview = content_preview[:77] + "..."
            embed.add_field(
                name=f"ID `{item.get('id')}` • <#{item.get('channel_id')}>",
                value=f"`{when}`\n{content_preview}",
                inline=False
            )
        await ctx.send(embed=embed)

    @announce_group.command(name="cancel")
    @commands.has_permissions(manage_guild=True)
    async def announce_cancel(self, ctx, ann_id: int):
        data = _load_json(ANNOUNCE_FILE, {"items": []})
        before = len(data.get("items", []))
        data["items"] = [i for i in data.get("items", []) if not (str(i.get("guild_id")) == str(ctx.guild.id) and int(i.get("id", 0)) == ann_id)]
        after = len(data.get("items", []))
        _save_json(ANNOUNCE_FILE, data)
        if after == before:
            return await ctx.send("❌ Announcement ID not found.")
        await ctx.send("✅ Announcement cancelled.")

    @announce_group.command(name="test")
    @commands.has_permissions(manage_guild=True)
    async def announce_test(self, ctx, channel: discord.TextChannel, *, content: str):
        await channel.send(content, allowed_mentions=discord.AllowedMentions.all())
        await ctx.send(f"✅ Test announcement sent to {channel.mention}")


async def setup(bot):
    await bot.add_cog(Announcements(bot))
