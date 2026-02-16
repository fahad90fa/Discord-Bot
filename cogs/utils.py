import discord
import db

FILE = "moderation.json"
BAN_LIMIT_FILE = "ban_limit.json"
DAILY_BAN_LIMIT = 10
AFK_FILE = "afk.json"
MODLOG_FILE = "modlogs.json"
NEWS_CONFIG_FILE = "news_config.json"
ANTILINK_FILE = "antilink.json"
ANTISPAM_FILE = "antispam.json"
AUTOMOD_FILE = "automod.json"

def load_afk(guild_id=None):
    if guild_id is None:
        return {}
    rows = db.execute(
        "SELECT user_id, reason FROM afk_status WHERE guild_id = %s",
        (int(guild_id),),
        fetchall=True
    ) or []
    return {str(r["user_id"]): r["reason"] for r in rows}

def save_afk(data, guild_id=None):
    if guild_id is None:
        return
    gid = int(guild_id)
    db.execute("DELETE FROM afk_status WHERE guild_id = %s", (gid,))
    for user_id, reason in (data or {}).items():
        db.execute(
            "INSERT INTO afk_status (guild_id, user_id, reason) VALUES (%s, %s, %s)",
            (gid, int(user_id), str(reason))
        )

def load_ban_limits(guild_id=None):
    if guild_id is None:
        return {}
    rows = db.execute(
        "SELECT admin_id, day_key, count FROM ban_limits WHERE guild_id = %s",
        (int(guild_id),),
        fetchall=True
    ) or []
    data = {}
    for r in rows:
        data.setdefault(str(r["admin_id"]), {})[r["day_key"]] = r["count"]
    return data

def save_ban_limits(data, guild_id=None):
    if guild_id is None:
        return
    gid = int(guild_id)
    db.execute("DELETE FROM ban_limits WHERE guild_id = %s", (gid,))
    for admin_id, days in (data or {}).items():
        for day_key, count in (days or {}).items():
            db.execute(
                "INSERT INTO ban_limits (guild_id, admin_id, day_key, count) VALUES (%s, %s, %s, %s)",
                (gid, int(admin_id), str(day_key), int(count))
            )

def load_data(guild_id=None):
    if guild_id is None:
        return {"owners": [], "admins": [], "mods": []}
    rows = db.execute(
        "SELECT role, user_id FROM bot_role_members WHERE guild_id = %s",
        (int(guild_id),),
        fetchall=True
    ) or []
    data = {"owners": [], "admins": [], "mods": []}
    for r in rows:
        role = r["role"]
        if role in data:
            data[role].append(int(r["user_id"]))
    return data

def save_data(data, guild_id=None):
    if guild_id is None:
        return
    gid = int(guild_id)
    db.execute("DELETE FROM bot_role_members WHERE guild_id = %s", (gid,))
    for role in ("owners", "admins", "mods"):
        for user_id in data.get(role, []):
            db.execute(
                "INSERT INTO bot_role_members (guild_id, role, user_id) VALUES (%s, %s, %s)",
                (gid, role, int(user_id))
            )

def get_modlog_channel(guild_id):
    row = db.execute(
        "SELECT channel_id FROM modlog_config WHERE guild_id = %s",
        (int(guild_id),),
        fetchone=True
    )
    return row["channel_id"] if row else None

def set_modlog_channel(guild_id, channel_id):
    db.execute(
        """
        INSERT INTO modlog_config (guild_id, channel_id)
        VALUES (%s, %s)
        ON CONFLICT (guild_id) DO UPDATE SET channel_id = EXCLUDED.channel_id
        """,
        (int(guild_id), int(channel_id))
    )

from discord.ext import commands

def is_owner_check():
    async def predicate(ctx):
        guild_id = ctx.guild.id if ctx.guild else None
        data = load_data(guild_id) if guild_id else load_data()
        # Accept either "owners" list in config or bot.owner_ids (ctx.bot.is_owner).
        return ctx.author.id in data.get("owners", []) or await ctx.bot.is_owner(ctx.author)
    return commands.check(predicate)

def get_news_channel():
    raise RuntimeError("get_news_channel now requires guild_id")

def set_news_channel(channel_id):
    raise RuntimeError("set_news_channel now requires guild_id")

def get_reminder_channel():
    raise RuntimeError("get_reminder_channel now requires guild_id")

def set_reminder_channel(channel_id):
    raise RuntimeError("set_reminder_channel now requires guild_id")

def get_news_channel_guild(guild_id):
    row = db.execute(
        "SELECT news_channel_id FROM news_config WHERE guild_id = %s",
        (int(guild_id),),
        fetchone=True
    )
    return row["news_channel_id"] if row else None

def set_news_channel_guild(guild_id, channel_id):
    db.execute(
        """
        INSERT INTO news_config (guild_id, news_channel_id)
        VALUES (%s, %s)
        ON CONFLICT (guild_id) DO UPDATE SET news_channel_id = EXCLUDED.news_channel_id
        """,
        (int(guild_id), int(channel_id))
    )

def get_reminder_channel_guild(guild_id):
    row = db.execute(
        "SELECT reminder_channel_id FROM news_config WHERE guild_id = %s",
        (int(guild_id),),
        fetchone=True
    )
    return row["reminder_channel_id"] if row else None

def set_reminder_channel_guild(guild_id, channel_id):
    db.execute(
        """
        INSERT INTO news_config (guild_id, reminder_channel_id)
        VALUES (%s, %s)
        ON CONFLICT (guild_id) DO UPDATE SET reminder_channel_id = EXCLUDED.reminder_channel_id
        """,
        (int(guild_id), int(channel_id))
    )

def get_welcome_channel(guild_id):
    row = db.execute(
        "SELECT channel_id FROM welcome_config WHERE guild_id = %s",
        (int(guild_id),),
        fetchone=True
    )
    return row["channel_id"] if row else None

def set_welcome_channel(guild_id, channel_id):
    if channel_id is None:
        db.execute("DELETE FROM welcome_config WHERE guild_id = %s", (int(guild_id),))
        return
    db.execute(
        """
        INSERT INTO welcome_config (guild_id, channel_id)
        VALUES (%s, %s)
        ON CONFLICT (guild_id) DO UPDATE SET channel_id = EXCLUDED.channel_id
        """,
        (int(guild_id), int(channel_id))
    )

def get_antilink_config(guild_id):
    row = db.execute(
        "SELECT enabled, punishment, duration_minutes FROM antilink_config WHERE guild_id = %s",
        (int(guild_id),),
        fetchone=True
    )
    if not row:
        return {"enabled": False, "punishment": "mute", "duration": 60}
    return {
        "enabled": row["enabled"],
        "punishment": row["punishment"],
        "duration": row["duration_minutes"],
    }

def set_antilink_config(guild_id, **kwargs):
    data = get_antilink_config(guild_id)
    for key, value in kwargs.items():
        data[key] = value
    db.execute(
        """
        INSERT INTO antilink_config (guild_id, enabled, punishment, duration_minutes)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (guild_id)
        DO UPDATE SET enabled = EXCLUDED.enabled, punishment = EXCLUDED.punishment, duration_minutes = EXCLUDED.duration_minutes
        """,
        (int(guild_id), bool(data["enabled"]), str(data["punishment"]), int(data["duration"]))
    )

def get_antispam_config(guild_id):
    row = db.execute(
        "SELECT enabled, punishment, duration_minutes, limit_count FROM antispam_config WHERE guild_id = %s",
        (int(guild_id),),
        fetchone=True
    )
    if not row:
        return {"enabled": False, "punishment": "mute", "duration": 60, "limit": 4}
    return {
        "enabled": row["enabled"],
        "punishment": row["punishment"],
        "duration": row["duration_minutes"],
        "limit": row["limit_count"]
    }

def set_antispam_config(guild_id, **kwargs):
    data = get_antispam_config(guild_id)
    for key, value in kwargs.items():
        data[key] = value
    db.execute(
        """
        INSERT INTO antispam_config (guild_id, enabled, punishment, duration_minutes, limit_count)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (guild_id)
        DO UPDATE SET enabled = EXCLUDED.enabled, punishment = EXCLUDED.punishment,
          duration_minutes = EXCLUDED.duration_minutes, limit_count = EXCLUDED.limit_count
        """,
        (int(guild_id), bool(data["enabled"]), str(data["punishment"]), int(data["duration"]), int(data["limit"]))
    )

def get_automod_config(guild_id):
    caps = db.execute(
        "SELECT enabled, punishment, duration_minutes, ratio, min_len FROM automod_caps_config WHERE guild_id = %s",
        (int(guild_id),),
        fetchone=True
    ) or {}
    emoji = db.execute(
        "SELECT enabled, punishment, limit_count FROM automod_emoji_config WHERE guild_id = %s",
        (int(guild_id),),
        fetchone=True
    ) or {}
    bypass = db.execute(
        "SELECT role_id FROM automod_bypass_role WHERE guild_id = %s",
        (int(guild_id),),
        fetchone=True
    )
    return {
        "anticaps": {
            "enabled": caps.get("enabled", False),
            "punishment": caps.get("punishment", "mute"),
            "duration": caps.get("duration_minutes", 10),
            "ratio": float(caps.get("ratio", 0.5)),
            "min_len": caps.get("min_len", 5)
        },
        "antiemoji": {
            "enabled": emoji.get("enabled", False),
            "punishment": emoji.get("punishment", "mute"),
            "limit": emoji.get("limit_count", 5)
        },
        "bypass_role": bypass["role_id"] if bypass else None
    }

def set_automod_config(guild_id, key, value):
    cfg = get_automod_config(guild_id)
    if "." in key:
        k1, k2 = key.split(".")
        cfg[k1][k2] = value
    else:
        cfg[key] = value

    db.execute(
        """
        INSERT INTO automod_caps_config (guild_id, enabled, punishment, duration_minutes, ratio, min_len)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (guild_id) DO UPDATE SET enabled = EXCLUDED.enabled, punishment = EXCLUDED.punishment,
          duration_minutes = EXCLUDED.duration_minutes, ratio = EXCLUDED.ratio, min_len = EXCLUDED.min_len
        """,
        (int(guild_id),
         bool(cfg["anticaps"]["enabled"]),
         str(cfg["anticaps"]["punishment"]),
         int(cfg["anticaps"]["duration"]),
         float(cfg["anticaps"]["ratio"]),
         int(cfg["anticaps"]["min_len"]))
    )
    db.execute(
        """
        INSERT INTO automod_emoji_config (guild_id, enabled, punishment, limit_count)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (guild_id) DO UPDATE SET enabled = EXCLUDED.enabled, punishment = EXCLUDED.punishment,
          limit_count = EXCLUDED.limit_count
        """,
        (int(guild_id),
         bool(cfg["antiemoji"]["enabled"]),
         str(cfg["antiemoji"]["punishment"]),
         int(cfg["antiemoji"]["limit"]))
    )
    db.execute(
        """
        INSERT INTO automod_bypass_role (guild_id, role_id)
        VALUES (%s, %s)
        ON CONFLICT (guild_id) DO UPDATE SET role_id = EXCLUDED.role_id
        """,
        (int(guild_id), cfg["bypass_role"])
    )

async def send_modlog(bot, ctx, action: str, target=None, **kwargs):
    modlog_id = get_modlog_channel(ctx.guild.id)
    if not modlog_id:
        return

    modlog_channel = ctx.guild.get_channel(modlog_id)
    if not modlog_channel:
        return

    embed = discord.Embed(
        title=f"📝 Mod Log | {action}",
        color=discord.Color.red() if action.lower() in ["ban", "kick"] else discord.Color.orange()
    )
    if target:
        if isinstance(target, (discord.Member, discord.User)):
            embed.add_field(name="User", value=f"{target.mention} ({target})", inline=True)
        else:
            embed.add_field(name="Target", value=str(target), inline=True)
            
    embed.add_field(name="Moderator", value=f"{ctx.author.mention}", inline=True)
    embed.add_field(name="Executed In", value=f"{ctx.channel.mention}", inline=False)
    embed.set_footer(text=f"{ctx.guild.name}")
    for key, value in kwargs.items():
        embed.add_field(name=str(key).replace("_", " ").title(), value=str(value), inline=False)

    await modlog_channel.send(embed=embed)
