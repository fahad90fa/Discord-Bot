import json
import os
import discord

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
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.decoder.JSONDecodeError:
        return {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

def load_afk():
    return load_json(AFK_FILE)

def save_afk(data):
    save_json(AFK_FILE, data)

def load_ban_limits():
    return load_json(BAN_LIMIT_FILE)

def save_ban_limits(data):
    save_json(BAN_LIMIT_FILE, data)

def load_data():
    return load_json(FILE)

def save_data(data):
    save_json(FILE, data)

def get_modlog_channel(guild_id):
    data = load_json(MODLOG_FILE)
    return data.get(str(guild_id))

def set_modlog_channel(guild_id, channel_id):
    data = load_json(MODLOG_FILE)
    data[str(guild_id)] = channel_id
    save_json(MODLOG_FILE, data)

from discord.ext import commands

def is_owner_check():
    async def predicate(ctx):
        data = load_json(FILE)
        return ctx.author.id in data.get("owners", [])
    return commands.check(predicate)

def get_news_channel():
    data = load_json(NEWS_CONFIG_FILE)
    return data.get("news_channel")

def set_news_channel(channel_id):
    data = load_json(NEWS_CONFIG_FILE)
    data["news_channel"] = channel_id
    save_json(NEWS_CONFIG_FILE, data)

def get_reminder_channel():
    data = load_json(NEWS_CONFIG_FILE)
    return data.get("reminder_channel")

def set_reminder_channel(channel_id):
    data = load_json(NEWS_CONFIG_FILE)
    data["reminder_channel"] = channel_id
    save_json(NEWS_CONFIG_FILE, data)

def get_antilink_config(guild_id):
    data = load_json(ANTILINK_FILE)
    return data.get(str(guild_id), {"enabled": False, "punishment": "mute", "duration": 60})

def set_antilink_config(guild_id, **kwargs):
    data = load_json(ANTILINK_FILE)
    guild_data = data.get(str(guild_id), {"enabled": False, "punishment": "mute", "duration": 60})
    for key, value in kwargs.items():
        guild_data[key] = value
    data[str(guild_id)] = guild_data
    save_json(ANTILINK_FILE, data)

def get_antispam_config(guild_id):
    data = load_json(ANTISPAM_FILE)
    return data.get(str(guild_id), {"enabled": False, "punishment": "mute", "duration": 60, "limit": 4})

def set_antispam_config(guild_id, **kwargs):
    data = load_json(ANTISPAM_FILE)
    guild_data = data.get(str(guild_id), {"enabled": False, "punishment": "mute", "duration": 60, "limit": 4})
    for key, value in kwargs.items():
        guild_data[key] = value
    data[str(guild_id)] = guild_data
    save_json(ANTISPAM_FILE, data)

def get_automod_config(guild_id):
    data = load_json(AUTOMOD_FILE)
    return data.get(str(guild_id), {
        "anticaps": {"enabled": False, "punishment": "mute", "duration": 10, "ratio": 0.5, "min_len": 5},
        "antiemoji": {"enabled": False, "punishment": "mute", "duration": 10, "limit": 5},
        "bypass_role": None
    })

def set_automod_config(guild_id, key, value):
    data = load_json(AUTOMOD_FILE)
    guild_data = data.get(str(guild_id), {
        "anticaps": {"enabled": False, "punishment": "mute", "duration": 10, "ratio": 0.5, "min_len": 5},
        "antiemoji": {"enabled": False, "punishment": "mute", "duration": 10, "limit": 5},
        "bypass_role": None
    })
    
    if "." in key:
        k1, k2 = key.split(".")
        guild_data[k1][k2] = value
    else:
        guild_data[key] = value
        
    data[str(guild_id)] = guild_data
    save_json(AUTOMOD_FILE, data)

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
