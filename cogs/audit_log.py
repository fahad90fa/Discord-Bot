import discord
from discord.ext import commands
from collections import OrderedDict
from datetime import datetime
import db

AUDIT_CONFIG_FILE = "audit_log_config.json"


def _load_json(guild_id, default):
    data = db.get_json_scoped(AUDIT_CONFIG_FILE, str(guild_id), default, migrate_file=AUDIT_CONFIG_FILE)
    if not data:
        legacy = db.get_json(AUDIT_CONFIG_FILE, {}, migrate_file=AUDIT_CONFIG_FILE)
        if isinstance(legacy, dict):
            legacy_val = legacy.get(str(guild_id))
            if legacy_val:
                migrated = {"channel_id": legacy_val}
                db.set_json_scoped(AUDIT_CONFIG_FILE, str(guild_id), migrated)
                return migrated
    return data


def _save_json(guild_id, data):
    db.set_json_scoped(AUDIT_CONFIG_FILE, str(guild_id), data)


def _truncate(s: str, n: int = 900) -> str:
    s = s or ""
    if len(s) <= n:
        return s
    return s[: n - 3] + "..."


def _fmt_attachments(atts):
    if not atts:
        return None
    lines = []
    for a in atts:
        try:
            lines.append(f"- {a.filename}: {a.url}")
        except Exception:
            continue
    return "\n".join(lines) if lines else None


class AuditLog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # message_id -> snapshot
        self._cache = OrderedDict()
        self._cache_max = 2000

    def _cache_put(self, message: discord.Message):
        if not message.guild:
            return
        key = f"{message.channel.id}:{message.id}"
        snap = {
            "guild_id": message.guild.id,
            "channel_id": message.channel.id,
            "author_id": message.author.id,
            "author_tag": str(message.author),
            "content": message.content or "",
            "attachments": [{"filename": a.filename, "url": a.url} for a in (message.attachments or [])],
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }
        self._cache[key] = snap
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

    def _get_log_channel(self, guild: discord.Guild):
        cfg = _load_json(guild.id, {})
        ch_id = cfg.get("channel_id")
        if not ch_id:
            return None
        try:
            ch_id_int = int(ch_id)
        except (TypeError, ValueError):
            return None

        # bot cache resolves threads too; prefer it.
        ch = self.bot.get_channel(ch_id_int)
        if ch and getattr(ch, "guild", None) and ch.guild.id == guild.id:
            return ch
        return guild.get_channel(ch_id_int)

    async def _send(self, guild: discord.Guild, embed: discord.Embed, *, content: str | None = None):
        ch = self._get_log_channel(guild)
        if not ch:
            return
        try:
            await ch.send(
                content=content,
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none()
            )
        except Exception:
            # Missing perms / deleted channel / rate limits should not break listeners.
            return

    @commands.command(name="setauditlog", aliases=["auditset", "auditlogset"])
    @commands.has_permissions(administrator=True)
    async def set_audit_log(self, ctx, channel: discord.TextChannel):
        cfg = _load_json(ctx.guild.id, {})
        cfg["channel_id"] = channel.id
        _save_json(ctx.guild.id, cfg)

        embed = discord.Embed(
            title="✅ AUDIT LOG ENABLED",
            description=f"Audit logs will be sent to {channel.mention}",
            color=0x2ecc71
        )
        await ctx.send(embed=embed)

    @commands.command(name="auditlogoff", aliases=["setauditoff", "auditoff"])
    @commands.has_permissions(administrator=True)
    async def audit_log_off(self, ctx):
        cfg = _load_json(ctx.guild.id, {})
        if "channel_id" in cfg:
            del cfg["channel_id"]
            _save_json(ctx.guild.id, cfg)
        await ctx.send("✅ Audit log disabled.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        self._cache_put(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not after.guild or after.author.bot:
            return
        if (before.content or "") == (after.content or "") and (before.attachments or []) == (after.attachments or []):
            return

        self._cache_put(after)

        embed = discord.Embed(
            title="✏️ Message Edited",
            color=0xf1c40f,
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="User", value=f"{after.author.mention} (`{after.author.id}`)", inline=False)
        embed.add_field(name="Channel", value=after.channel.mention, inline=True)
        embed.add_field(name="Message ID", value=f"`{after.id}`", inline=True)
        embed.add_field(name="Before", value=_truncate(before.content) or "`(empty)`", inline=False)
        embed.add_field(name="After", value=_truncate(after.content) or "`(empty)`", inline=False)

        att_txt = _fmt_attachments(after.attachments)
        if att_txt:
            embed.add_field(name="Attachments", value=_truncate(att_txt, 900), inline=False)

        await self._send(after.guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or (message.author and message.author.bot):
            return

        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=0xe74c3c,
            timestamp=datetime.utcnow()
        )
        author = message.author
        if author:
            embed.add_field(name="User", value=f"{author.mention} (`{author.id}`)", inline=False)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="Message ID", value=f"`{message.id}`", inline=True)
        embed.add_field(name="Content", value=_truncate(message.content) or "`(empty)`", inline=False)

        att_txt = _fmt_attachments(message.attachments)
        if att_txt:
            embed.add_field(name="Attachments", value=_truncate(att_txt, 900), inline=False)

        await self._send(message.guild, embed)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        # Always log deletes; include cached content if available.
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        key = f"{payload.channel_id}:{payload.message_id}"
        snap = self._cache.get(key)
        # Avoid duplicates: if we have a snapshot, on_message_delete likely logged already.
        if snap:
            return

        channel = guild.get_channel(payload.channel_id)
        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=0xe74c3c,
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Channel", value=channel.mention if channel else f"`{payload.channel_id}`", inline=True)
        embed.add_field(name="Message ID", value=f"`{payload.message_id}`", inline=True)
        embed.add_field(name="Content", value="`(not cached)`", inline=False)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        channel = guild.get_channel(payload.channel_id)
        ids = list(payload.message_ids or [])

        embed = discord.Embed(
            title="🧹 Bulk Messages Deleted",
            color=0xe67e22,
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Channel", value=channel.mention if channel else f"`{payload.channel_id}`", inline=True)
        embed.add_field(name="Count", value=f"`{len(ids)}`", inline=True)

        # Include a small sample of cached messages (if available).
        samples = []
        for mid in ids[:25]:
            snap = self._cache.get(f"{payload.channel_id}:{mid}")
            if not snap:
                continue
            samples.append(f"- `{snap.get('author_tag')}`: {_truncate(snap.get('content'), 120) or '(empty)'}")
            if len(samples) >= 5:
                break
        if samples:
            embed.add_field(name="Cached Samples", value="\n".join(samples)[:950], inline=False)

        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        data = payload.data or {}
        # Only log if content is present in the update payload.
        if "content" not in data and "attachments" not in data:
            return

        channel = guild.get_channel(payload.channel_id)
        key = f"{payload.channel_id}:{payload.message_id}"
        before_snap = self._cache.get(key)

        after_content = data.get("content", "")
        embed = discord.Embed(
            title="✏️ Message Edited (Raw)",
            color=0xf1c40f,
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Channel", value=channel.mention if channel else f"`{payload.channel_id}`", inline=True)
        embed.add_field(name="Message ID", value=f"`{payload.message_id}`", inline=True)
        if before_snap:
            embed.add_field(name="Before", value=_truncate(before_snap.get("content")) or "`(empty)`", inline=False)
        else:
            embed.add_field(name="Before", value="`(not cached)`", inline=False)
        embed.add_field(name="After", value=_truncate(after_content) or "`(empty)`", inline=False)

        await self._send(guild, embed)

        # Update cache with the latest view we have.
        try:
            author = data.get("author") or {}
            self._cache[key] = {
                "guild_id": payload.guild_id,
                "channel_id": payload.channel_id,
                "author_id": int(author.get("id")) if author.get("id") else (before_snap.get("author_id") if before_snap else 0),
                "author_tag": f"{author.get('username','Unknown')}#{author.get('discriminator','0000')}" if author.get("username") else (before_snap.get("author_tag") if before_snap else "Unknown"),
                "content": after_content or "",
                "attachments": before_snap.get("attachments") if before_snap else [],
                "created_at": before_snap.get("created_at") if before_snap else None,
            }
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_max:
                self._cache.popitem(last=False)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        embed = discord.Embed(title="➕ Member Joined", color=0x2ecc71, timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="Created", value=f"`{member.created_at.isoformat() if member.created_at else 'N/A'}`", inline=False)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        embed = discord.Embed(title="➖ Member Left", color=0xe74c3c, timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"`{member}` (`{member.id}`)", inline=False)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(title="🔨 Member Banned", color=0xe74c3c, timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"`{user}` (`{user.id}`)", inline=False)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(title="♻️ Member Unbanned", color=0x2ecc71, timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"`{user}` (`{user.id}`)", inline=False)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        guild = role.guild
        embed = discord.Embed(title="🧩 Role Created", color=0x2ecc71, timestamp=datetime.utcnow())
        embed.add_field(name="Role", value=f"{role.mention} (`{role.id}`)", inline=False)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        embed = discord.Embed(title="🧨 Role Deleted", color=0xe74c3c, timestamp=datetime.utcnow())
        embed.add_field(name="Role", value=f"`{role.name}` (`{role.id}`)", inline=False)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        guild = after.guild
        changes = []
        if before.name != after.name:
            changes.append(f"Name: `{before.name}` -> `{after.name}`")
        if before.color != after.color:
            changes.append(f"Color: `{before.color}` -> `{after.color}`")
        if before.permissions != after.permissions:
            changes.append("Permissions: `changed`")
        if not changes:
            return
        embed = discord.Embed(title="🛠️ Role Updated", color=0xf39c12, timestamp=datetime.utcnow())
        embed.add_field(name="Role", value=f"{after.mention} (`{after.id}`)", inline=False)
        embed.add_field(name="Changes", value="\n".join(changes)[:950], inline=False)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not after.guild:
            return

        # Roles
        before_roles = set(r.id for r in before.roles)
        after_roles = set(r.id for r in after.roles)
        if before_roles != after_roles:
            added = [after.guild.get_role(rid) for rid in (after_roles - before_roles)]
            removed = [after.guild.get_role(rid) for rid in (before_roles - after_roles)]
            added_txt = ", ".join(r.mention for r in added if r) or "`None`"
            removed_txt = ", ".join(r.mention for r in removed if r) or "`None`"

            embed = discord.Embed(
                title="🏷️ Roles Updated",
                color=0x3498db,
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="User", value=f"{after.mention} (`{after.id}`)", inline=False)
            embed.add_field(name="Added", value=added_txt, inline=False)
            embed.add_field(name="Removed", value=removed_txt, inline=False)
            await self._send(after.guild, embed)

        # Nickname
        if before.nick != after.nick:
            embed = discord.Embed(
                title="🧾 Nickname Updated",
                color=0x9b59b6,
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="User", value=f"{after.mention} (`{after.id}`)", inline=False)
            embed.add_field(name="Before", value=before.nick or "`None`", inline=True)
            embed.add_field(name="After", value=after.nick or "`None`", inline=True)
            await self._send(after.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        embed = discord.Embed(title="📌 Channel Created", color=0x2ecc71, timestamp=datetime.utcnow())
        embed.add_field(name="Channel", value=f"{channel.mention} (`{channel.id}`)", inline=False)
        embed.add_field(name="Type", value=f"`{channel.type}`", inline=True)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        embed = discord.Embed(title="🧨 Channel Deleted", color=0xe74c3c, timestamp=datetime.utcnow())
        embed.add_field(name="Channel", value=f"`{channel.name}` (`{channel.id}`)", inline=False)
        embed.add_field(name="Type", value=f"`{channel.type}`", inline=True)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        guild = after.guild
        changes = []
        if getattr(before, "name", None) != getattr(after, "name", None):
            changes.append(f"Name: `{getattr(before,'name',None)}` -> `{getattr(after,'name',None)}`")
        if getattr(before, "category_id", None) != getattr(after, "category_id", None):
            changes.append(f"Category: `{getattr(before,'category_id',None)}` -> `{getattr(after,'category_id',None)}`")

        if not changes:
            return

        embed = discord.Embed(title="🛠️ Channel Updated", color=0xf39c12, timestamp=datetime.utcnow())
        embed.add_field(name="Channel", value=f"{after.mention} (`{after.id}`)", inline=False)
        embed.add_field(name="Changes", value="\n".join(changes)[:950], inline=False)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        changes = []

        if before.channel != after.channel:
            if before.channel and after.channel:
                changes.append(f"Moved: `{before.channel.name}` -> `{after.channel.name}`")
            elif after.channel and not before.channel:
                changes.append(f"Joined: `{after.channel.name}`")
            elif before.channel and not after.channel:
                changes.append(f"Left: `{before.channel.name}`")

        if before.self_mute != after.self_mute:
            changes.append(f"Self Mute: `{before.self_mute}` -> `{after.self_mute}`")
        if before.self_deaf != after.self_deaf:
            changes.append(f"Self Deaf: `{before.self_deaf}` -> `{after.self_deaf}`")
        if before.mute != after.mute:
            changes.append(f"Server Mute: `{before.mute}` -> `{after.mute}`")
        if before.deaf != after.deaf:
            changes.append(f"Server Deaf: `{before.deaf}` -> `{after.deaf}`")

        if not changes:
            return

        embed = discord.Embed(title="🎙️ Voice Update", color=0x2b2d31, timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="Changes", value="\n".join(changes)[:950], inline=False)
        await self._send(guild, embed)


async def setup(bot):
    await bot.add_cog(AuditLog(bot))
