import json
import os
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

def load_json(filename):
    return db.get_setting(filename, None, {})

def save_json(filename, data):
    db.set_setting(filename, None, data)

def load_json_guild(filename, guild_id, default=None):
    if default is None:
        default = {}
    return db.get_setting(filename, int(guild_id), default)

def save_json_guild(filename, guild_id, data):
    db.set_setting(filename, int(guild_id), data)

def load_afk(guild_id=None):
    if guild_id is None:
        return load_json(AFK_FILE)
    return load_json_guild(AFK_FILE, guild_id, {})

def save_afk(data, guild_id=None):
    if guild_id is None:
        return save_json(AFK_FILE, data)
    return save_json_guild(AFK_FILE, guild_id, data)

def load_ban_limits(guild_id=None):
    if guild_id is None:
        return load_json(BAN_LIMIT_FILE)
    return load_json_guild(BAN_LIMIT_FILE, guild_id, {})

def save_ban_limits(data, guild_id=None):
    if guild_id is None:
        return save_json(BAN_LIMIT_FILE, data)
    return save_json_guild(BAN_LIMIT_FILE, guild_id, data)

def load_data(guild_id=None):
    if guild_id is None:
        return load_json(FILE)
    return load_json_guild(FILE, guild_id, {"owners": [], "admins": [], "mods": []})

def save_data(data, guild_id=None):
    if guild_id is None:
        return save_json(FILE, data)
    return save_json_guild(FILE, guild_id, data)

def get_modlog_channel(guild_id):
    data = load_json_guild(MODLOG_FILE, guild_id, {})
    return data.get("channel_id")

def set_modlog_channel(guild_id, channel_id):
    save_json_guild(MODLOG_FILE, guild_id, {"channel_id": channel_id})

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
    data = load_json_guild(NEWS_CONFIG_FILE, guild_id, {})
    return data.get("news_channel")

def set_news_channel_guild(guild_id, channel_id):
    data = load_json_guild(NEWS_CONFIG_FILE, guild_id, {})
    data["news_channel"] = channel_id
    save_json_guild(NEWS_CONFIG_FILE, guild_id, data)

def get_reminder_channel_guild(guild_id):
    data = load_json_guild(NEWS_CONFIG_FILE, guild_id, {})
    return data.get("reminder_channel")

def set_reminder_channel_guild(guild_id, channel_id):
    data = load_json_guild(NEWS_CONFIG_FILE, guild_id, {})
    data["reminder_channel"] = channel_id
    save_json_guild(NEWS_CONFIG_FILE, guild_id, data)

def get_antilink_config(guild_id):
    data = load_json_guild(ANTILINK_FILE, guild_id, {"enabled": False, "punishment": "mute", "duration": 60})
    return data

def set_antilink_config(guild_id, **kwargs):
    guild_data = load_json_guild(ANTILINK_FILE, guild_id, {"enabled": False, "punishment": "mute", "duration": 60})
    for key, value in kwargs.items():
        guild_data[key] = value
    save_json_guild(ANTILINK_FILE, guild_id, guild_data)

def get_antispam_config(guild_id):
    data = load_json_guild(ANTISPAM_FILE, guild_id, {"enabled": False, "punishment": "mute", "duration": 60, "limit": 4})
    return data

def set_antispam_config(guild_id, **kwargs):
    guild_data = load_json_guild(ANTISPAM_FILE, guild_id, {"enabled": False, "punishment": "mute", "duration": 60, "limit": 4})
    for key, value in kwargs.items():
        guild_data[key] = value
    save_json_guild(ANTISPAM_FILE, guild_id, guild_data)

def get_automod_config(guild_id):
    data = load_json_guild(AUTOMOD_FILE, guild_id, {
        "anticaps": {"enabled": False, "punishment": "mute", "duration": 10, "ratio": 0.5, "min_len": 5},
        "antiemoji": {"enabled": False, "punishment": "mute", "duration": 10, "limit": 5},
        "bypass_role": None
    })
    return data

def set_automod_config(guild_id, key, value):
    guild_data = load_json_guild(AUTOMOD_FILE, guild_id, {
        "anticaps": {"enabled": False, "punishment": "mute", "duration": 10, "ratio": 0.5, "min_len": 5},
        "antiemoji": {"enabled": False, "punishment": "mute", "duration": 10, "limit": 5},
        "bypass_role": None
    })
    
    if "." in key:
        k1, k2 = key.split(".")
        guild_data[k1][k2] = value
    else:
        guild_data[key] = value
        
    save_json_guild(AUTOMOD_FILE, guild_id, guild_data)

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
