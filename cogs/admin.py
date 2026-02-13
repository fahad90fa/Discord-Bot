import discord
from discord.ext import commands
import json
import asyncio
import sys
import os
import platform
import socket
import shutil
from datetime import datetime, timezone
from .utils import (
    load_data, save_data, set_modlog_channel, 
    get_antilink_config, set_antilink_config, 
    get_antispam_config, set_antispam_config,
    get_automod_config, set_automod_config,
    is_owner_check
)

def is_botowner():
    async def predicate(ctx):
        data = load_data()
        return ctx.author.id in data["owners"]
    return commands.check(predicate)

def is_mod_admin_owner():
    async def predicate(ctx):
        data = load_data()
        return (
            ctx.author.id in data["owners"]
            or ctx.author.id in data["admins"]
            or ctx.author.id in data["mods"]
        )
    return commands.check(predicate)

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.boot_time = datetime.now(timezone.utc)

    def _format_id_list(self, ids, label):
        if not ids:
            return f"⚠️ No {label} configured."
        return "\n".join(f"• <@{user_id}> (`{user_id}`)" for user_id in ids)

    @commands.group(name="list", invoke_without_command=True)
    @is_owner_check()
    async def list_group(self, ctx):
        """List bot permission groups"""
        await ctx.send("Usage: `list owners`, `list admins`, `list mod`")

    @list_group.command(name="owners", aliases=["owner"])
    @is_owner_check()
    async def list_owners(self, ctx):
        data = load_data()
        embed = discord.Embed(title="👑 BOT OWNERS", color=0xf1c40f)
        embed.description = self._format_id_list(data.get("owners", []), "owners")
        await ctx.send(embed=embed)

    @list_group.command(name="admins", aliases=["admin"])
    @is_owner_check()
    async def list_admins(self, ctx):
        data = load_data()
        embed = discord.Embed(title="🛡️ BOT ADMINS", color=0x3498db)
        embed.description = self._format_id_list(data.get("admins", []), "admins")
        await ctx.send(embed=embed)

    @list_group.command(name="mod", aliases=["mods", "moderators"])
    @is_owner_check()
    async def list_mods(self, ctx):
        data = load_data()
        embed = discord.Embed(title="⚔️ BOT MODS", color=0x2ecc71)
        embed.description = self._format_id_list(data.get("mods", []), "mods")
        await ctx.send(embed=embed)

    @commands.group(name="automod", invoke_without_command=True)
    @is_owner_check()
    async def automod_group(self, ctx):
        """Auto-mod overview commands"""
        await ctx.send("Usage: `automod list`")

    @automod_group.command(name="list", aliases=["status"])
    @is_owner_check()
    async def automod_list(self, ctx):
        config = get_automod_config(ctx.guild.id)
        anti_caps = config.get("anticaps", {})
        anti_emoji = config.get("antiemoji", {})
        bypass_role_id = config.get("bypass_role")
        bypass_role = f"<@&{bypass_role_id}>" if bypass_role_id else "Not set"

        embed = discord.Embed(title="🛡️ AUTOMOD STATUS", color=0x2b2d31)
        embed.add_field(
            name="ANTI-CAPS",
            value=(
                f"Enabled: `{anti_caps.get('enabled', False)}`\n"
                f"Punishment: `{anti_caps.get('punishment', 'mute')}`\n"
                f"Duration: `{anti_caps.get('duration', 10)} mins`\n"
                f"Ratio: `{int(anti_caps.get('ratio', 0.5) * 100)}%`\n"
                f"Min Length: `{anti_caps.get('min_len', 5)}`"
            ),
            inline=False,
        )
        embed.add_field(
            name="ANTI-EMOJI",
            value=(
                f"Enabled: `{anti_emoji.get('enabled', False)}`\n"
                f"Punishment: `{anti_emoji.get('punishment', 'mute')}`\n"
                f"Limit: `{anti_emoji.get('limit', 5)}`"
            ),
            inline=False,
        )
        embed.add_field(name="BYPASS ROLE", value=bypass_role, inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @is_owner_check()
    async def addowner(self, ctx, user: discord.User):
        """Add a new bot owner (Owner Only)"""
        data = load_data()
        if user.id not in data["owners"]:
            data["owners"].append(user.id)
            save_data(data)
            await ctx.send(f"✅ Added {user.mention} as a **Bot Owner**.")
        else:
            await ctx.send(f"⚠️ {user.mention} is already an owner.")

    @commands.command()
    @is_owner_check()
    async def removeowner(self, ctx, user: discord.User):
        """Remove a bot owner (Owner Only)"""
        data = load_data()
        if user.id in data["owners"]:
            # Prevent removing self
            if user.id == ctx.author.id:
                return await ctx.send("❌ You cannot remove yourself as an owner.")
                
            data["owners"].remove(user.id)
            save_data(data)
            await ctx.send(f"❌ Removed {user.mention} from **Bot Owners**.")
        else:
            await ctx.send(f"⚠️ {user.mention} is not an owner.")

    @commands.command()
    @is_owner_check()
    async def addadmin(self, ctx, user_id: int):
        data = load_data()
        if user_id not in data["admins"]:
            data["admins"].append(user_id)
            save_data(data)
            await ctx.send(f"✅ Added <@{user_id}> as **Admin**")

    @commands.command()
    @is_owner_check()
    async def removeadmin(self, ctx, user_id: int):
        data = load_data()
        if user_id in data["admins"]:
            data["admins"].remove(user_id)
            save_data(data)
            await ctx.send(f"❌ Removed <@{user_id}> from **Admins**")

    @commands.command()
    @is_owner_check()
    async def addmod(self, ctx, user_id: int):
        data = load_data()
        if user_id not in data["mods"]:
            data["mods"].append(user_id)
            save_data(data)
            await ctx.send(f"✅ Added <@{user_id}> as **Mod**")

    @commands.command()
    @is_owner_check()
    async def removemod(self, ctx, user_id: int):
        data = load_data()
        if user_id in data["mods"]:
            data["mods"].remove(user_id)
            save_data(data)
            await ctx.send(f"❌ Removed <@{user_id}> from **Mods**")

    @commands.command()
    @is_botowner()
    async def addowner(self, ctx, user: discord.User):
        """Add a new bot owner (Owner Only)"""
        data = load_data()
        if user.id not in data["owners"]:
            data["owners"].append(user.id)
            save_data(data)
            await ctx.send(f"✅ Added {user.mention} as a **Bot Owner**.")
        else:
            await ctx.send(f"⚠️ {user.mention} is already an owner.")

    @commands.command()
    @is_owner_check()
    async def setstatus(self, ctx, status: str, activity_type: str = None, *, activity_text: str = None):
        """Update the bot's status and activity"""
        status = status.lower()
        activity_type = activity_type.lower() if activity_type else None
        status_map = {"online": discord.Status.online, "idle": discord.Status.idle, "dnd": discord.Status.dnd, "invisible": discord.Status.invisible}
        if status not in status_map:
            return await ctx.send("❌ Invalid status. Use: `online`, `idle`, `dnd`, `invisible`.")
        activity_obj = None
        if activity_type and activity_text:
            type_map = {"playing": discord.ActivityType.playing, "watching": discord.ActivityType.watching, "listening": discord.ActivityType.listening, "competing": discord.ActivityType.competing}
            if activity_type not in type_map: return await ctx.send("❌ Invalid activity type.")
            activity_obj = discord.Activity(type=type_map[activity_type], name=activity_text)
        await self.bot.change_presence(status=status_map[status], activity=activity_obj)
        embed = discord.Embed(title="✅ Bot Status Updated", color=discord.Color.green())
        embed.add_field(name="Status", value=f"`{status}`", inline=True)
        embed.add_field(name="Activity", value=f"`{activity_type or 'None'} {activity_text or ''}`", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="setmodlog")
    @is_owner_check()
    async def setmodlog(self, ctx, channel: discord.TextChannel):
        """Set the moderation logs channel for this server"""
        load_msg = await ctx.send("🛰️ `CONFIGURING OVERWATCH LINK...`")
        set_modlog_channel(ctx.guild.id, channel.id)
        await asyncio.sleep(0.5)
        await load_msg.edit(content="🕵️ `ESTABLISHING SECURE DATA PIPELINE...`")
        await asyncio.sleep(0.5)
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        embed = discord.Embed(title="🛡️ MOD-LOG SYSTEM ONLINE", description=("```ansi\n"f"\u001b[1;36mSTATUS  :\u001b[0m \u001b[0;37mOPERATIONAL\u001b[0m\n"f"\u001b[1;36mSECTOR  :\u001b[0m \u001b[0;37m{channel.name.upper()}\u001b[0m\n"f"\u001b[1;32mGATEWAY :\u001b[0m \u001b[0;37mSECURED\u001b[0m\n""```"), color=0x2ecc71)
        embed.set_author(name="TRADERS UNION COMMAND", icon_url=logo)
        embed.set_footer(text="Institutional Log Encryption Enabled")
        await load_msg.delete()
        await ctx.send(embed=embed)

    @commands.group(name="np", invoke_without_command=True)
    async def np(self, ctx: commands.Context):
        """No Prefix management command"""
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @np.command()
    @is_owner_check()
    async def add(self, ctx, user: discord.Member):
        try:
            with open('info.json', 'r') as f: data = json.load(f)
            if user.id in data["np"]:
                await ctx.send(f"❌ {user.name} already has no prefix.")
            else:
                data["np"].append(user.id)
                with open('info.json', 'w') as f: json.dump(data, f, indent=4)
                await ctx.send(f"✅ Added no prefix to {user.name}")
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @np.command()
    @is_owner_check()
    async def remove(self, ctx, user: discord.Member):
        try:
            with open('info.json', 'r') as f: data = json.load(f)
            if user.id in data["np"]:
                data["np"].remove(user.id)
                with open('info.json', 'w') as f: json.dump(data, f, indent=4)
                await ctx.send(f"✅ Removed no prefix from {user.name}")
            else:
                await ctx.send("❌ User doesn't have no prefix.")
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @commands.group(name="antilink", invoke_without_command=True)
    @is_owner_check()
    async def antilink(self, ctx):
        """Quantum Anti-Link Protection Suite"""
        if ctx.subcommand_passed is None:
            config = get_antilink_config(ctx.guild.id)
            status = "ENABLED" if config["enabled"] else "DISABLED"
            punishment = config["punishment"].upper()
            duration = config["duration"]
            
            embed = discord.Embed(title="🛡️ ANTI-LINK CONFIGURATION", color=0x2b2d31)
            embed.set_author(name="TRADERS UNION SECURITY", icon_url=self.bot.user.display_avatar.url)
            embed.description = (
                f"```ansi\n"
                f"\u001b[1;36mSTATUS     :\u001b[0m \u001b[0;37m{status}\u001b[0m\n"
                f"\u001b[1;36mPUNISHMENT :\u001b[0m \u001b[0;37m{punishment}\u001b[0m\n"
                f"\u001b[1;36mDURATION   :\u001b[0m \u001b[0;37m{duration} MINS\u001b[0m\n"
                f"```"
            )
            embed.set_footer(text="Institutional Security Protocol v4.0")
            await ctx.send(embed=embed)

    @antilink.command()
    async def on(self, ctx):
        set_antilink_config(ctx.guild.id, enabled=True)
        await ctx.send("✅ `ANTI-LINK PROTECTION ACTIVATED.`")

    @antilink.command()
    async def off(self, ctx):
        set_antilink_config(ctx.guild.id, enabled=False)
        await ctx.send("❌ `ANTI-LINK PROTECTION DEACTIVATED.`")

    @antilink.command()
    async def punishment(self, ctx, type: str, duration: int = 60):
        type = type.lower()
        if type not in ["ban", "mute", "kick"]:
            return await ctx.send("❌ `INVALID PUNISHMENT. USE: BAN, MUTE, OR KICK.`")
        
        set_antilink_config(ctx.guild.id, punishment=type, duration=duration)
        await ctx.send(f"✅ `PUNISHMENT SET TO {type.upper()} ({duration} MINS IF MUTE).`")

    @commands.group(name="antispam", invoke_without_command=True)
    @is_owner_check()
    async def antispam(self, ctx):
        """Quantum Anti-Spam Protection Suite"""
        if ctx.subcommand_passed is None:
            config = get_antispam_config(ctx.guild.id)
            status = "ENABLED" if config["enabled"] else "DISABLED"
            punishment = config["punishment"].upper()
            duration = config["duration"]
            limit = config.get("limit", 4)
            
            embed = discord.Embed(title="🛡️ ANTI-SPAM CONFIGURATION", color=0x2b2d31)
            embed.set_author(name="TRADERS UNION SECURITY", icon_url=self.bot.user.display_avatar.url)
            embed.description = (
                f"```ansi\n"
                f"\u001b[1;36mSTATUS     :\u001b[0m \u001b[0;37m{status}\u001b[0m\n"
                f"\u001b[1;36mPUNISHMENT :\u001b[0m \u001b[0;37m{punishment}\u001b[0m\n"
                f"\u001b[1;36mLIMIT      :\u001b[0m \u001b[0;37m{limit} MSGS\u001b[0m\n"
                f"\u001b[1;36mDURATION   :\u001b[0m \u001b[0;37m{duration} MINS\u001b[0m\n"
                f"```"
            )
            embed.set_footer(text="Institutional Anti-Flood Protocol v4.0")
            await ctx.send(embed=embed)

    @antispam.command()
    async def on(self, ctx):
        set_antispam_config(ctx.guild.id, enabled=True)
        await ctx.send("✅ `ANTI-SPAM PROTECTION ACTIVATED.`")

    @antispam.command()
    async def off(self, ctx):
        set_antispam_config(ctx.guild.id, enabled=False)
        await ctx.send("❌ `ANTI-SPAM PROTECTION DEACTIVATED.`")

    @antispam.command()
    async def limit(self, ctx, count: int):
        if count < 2:
            return await ctx.send("❌ `LIMIT MUST BE AT LEAST 2 MESSAGES.`")
        set_antispam_config(ctx.guild.id, limit=count)
        await ctx.send(f"✅ `SPAM LIMIT SET TO {count} MESSAGES IN A ROW.`")

    @antispam.command(name="punishment")
    async def spam_punishment(self, ctx, type: str, duration: int = 60):
        type = type.lower()
        if type not in ["ban", "mute", "kick"]:
            return await ctx.send("❌ `INVALID PUNISHMENT. USE: BAN, MUTE, OR KICK.`")
        
        set_antispam_config(ctx.guild.id, punishment=type, duration=duration)
        await ctx.send(f"✅ `ANTI-SPAM PUNISHMENT SET TO {type.upper()} ({duration} MINS IF MUTE).`")

    @commands.group(name="anticaps", invoke_without_command=True)
    @is_owner_check()
    async def anticaps(self, ctx):
        """Quantum Anti-Caps Protection Suite"""
        if ctx.subcommand_passed is None:
            config = get_automod_config(ctx.guild.id)["anticaps"]
            status = "ENABLED" if config["enabled"] else "DISABLED"
            punishment = config["punishment"].upper()
            duration = config["duration"]
            ratio = int(config.get("ratio", 0.5) * 100)
            min_len = config.get("min_len", 5)
            
            embed = discord.Embed(title="🛡️ ANTI-CAPS CONFIGURATION", color=0x2b2d31)
            embed.set_author(name="TRADERS UNION SECURITY", icon_url=self.bot.user.display_avatar.url)
            embed.description = (
                f"```ansi\n"
                f"\u001b[1;36mSTATUS     :\u001b[0m \u001b[0;37m{status}\u001b[0m\n"
                f"\u001b[1;36mPUNISHMENT :\u001b[0m \u001b[0;37m{punishment}\u001b[0m\n"
                f"\u001b[1;36mRATIO      :\u001b[0m \u001b[0;37m{ratio}%\u001b[0m\n"
                f"\u001b[1;36mMIN LENGTH :\u001b[0m \u001b[0;37m{min_len} CHARS\u001b[0m\n"
                f"\u001b[1;36mDURATION   :\u001b[0m \u001b[0;37m{duration} MINS\u001b[0m\n"
                f"```"
            )
            await ctx.send(embed=embed)

    @anticaps.command(name="on")
    async def caps_on(self, ctx):
        set_automod_config(ctx.guild.id, "anticaps.enabled", True)
        await ctx.send("✅ `ANTI-CAPS PROTECTION ACTIVATED.`")

    @anticaps.command(name="off")
    async def caps_off(self, ctx):
        set_automod_config(ctx.guild.id, "anticaps.enabled", False)
        await ctx.send("❌ `ANTI-CAPS PROTECTION DEACTIVATED.`")

    @anticaps.command(name="punishment")
    async def caps_punishment(self, ctx, type: str, duration: int = 10):
        type = type.lower()
        if type not in ["mute", "kick", "ban"]: return await ctx.send("❌ `INVALID TYPE.`")
        set_automod_config(ctx.guild.id, "anticaps.punishment", type)
        set_automod_config(ctx.guild.id, "anticaps.duration", duration)
        await ctx.send(f"✅ `CAPS PUNISHMENT SET TO {type.upper()}.`")

    @anticaps.command(name="ratio")
    async def caps_ratio(self, ctx, percentage: int):
        """Set the percentage of capital words to trigger punishment (1-100)"""
        if not (1 <= percentage <= 100):
            return await ctx.send("❌ `PERCENTAGE MUST BE BETWEEN 1 AND 100.`")
        
        ratio = percentage / 100
        set_automod_config(ctx.guild.id, "anticaps.ratio", ratio)
        await ctx.send(f"✅ `CAPS RATIO SET TO {percentage}%.`")

    @anticaps.command(name="minlen")
    async def caps_minlen(self, ctx, length: int):
        """Set the minimum message length to check for caps"""
        if length < 1:
            return await ctx.send("❌ `LENGTH MUST BE AT LEAST 1.`")
        
        set_automod_config(ctx.guild.id, "anticaps.min_len", length)
        await ctx.send(f"✅ `CAPS MINIMUM LENGTH SET TO {length} CHARACTERS.`")

    @commands.group(name="antiemoji", invoke_without_command=True)
    @is_owner_check()
    async def antiemoji(self, ctx):
        """Quantum Anti-Emoji Spam Suite"""
        if ctx.subcommand_passed is None:
            config = get_automod_config(ctx.guild.id)["antiemoji"]
            status = "ENABLED" if config["enabled"] else "DISABLED"
            limit = config["limit"]
            punishment = config["punishment"].upper()
            
            embed = discord.Embed(title="🛡️ ANTI-EMOJI CONFIGURATION", color=0x2b2d31)
            embed.set_author(name="TRADERS UNION SECURITY", icon_url=self.bot.user.display_avatar.url)
            embed.description = (
                f"```ansi\n"
                f"\u001b[1;36mSTATUS     :\u001b[0m \u001b[0;37m{status}\u001b[0m\n"
                f"\u001b[1;36mLIMIT      :\u001b[0m \u001b[0;37m{limit} EMOJIS\u001b[0m\n"
                f"\u001b[1;36mPUNISHMENT :\u001b[0m \u001b[0;37m{punishment}\u001b[0m\n"
                f"```"
            )
            await ctx.send(embed=embed)

    @antiemoji.command(name="on")
    async def emoji_on(self, ctx):
        set_automod_config(ctx.guild.id, "antiemoji.enabled", True)
        await ctx.send("✅ `ANTI-EMOJI PROTECTION ACTIVATED.`")

    @antiemoji.command(name="off")
    async def emoji_off(self, ctx):
        set_automod_config(ctx.guild.id, "antiemoji.enabled", False)
        await ctx.send("❌ `ANTI-EMOJI PROTECTION DEACTIVATED.`")

    @antiemoji.command(name="limit")
    async def emoji_limit(self, ctx, count: int):
        set_automod_config(ctx.guild.id, "antiemoji.limit", count)
        await ctx.send(f"✅ `EMOJI LIMIT SET TO {count}.`")

    @commands.command(name="setupbypass")
    @is_owner_check()
    async def setup_bypass(self, ctx, role: discord.Role):
        """Configure the official Auto-Mod bypass role"""
        set_automod_config(ctx.guild.id, "bypass_role", role.id)
        await ctx.send(f"✅ `BYPASS ROLE SET TO {role.mention}.`")

    @commands.command(name="restart")
    async def restart_bot(self, ctx):
        """Restart the entire bot (Specific User Only)"""
        # Only allow specific user ID
        if ctx.author.id != 1170979888019292261:
            return await ctx.send("❌ You don't have permission to use this command.")
        
        load_msg = await ctx.send("🔄 `INITIALIZING SYSTEM RESTART...`")
        await asyncio.sleep(0.5)
        await load_msg.edit(content="📡 `CLOSING ALL CONNECTIONS...`")
        await asyncio.sleep(0.5)
        await load_msg.edit(content="🔌 `SHUTTING DOWN CORE SYSTEMS...`")
        await asyncio.sleep(0.5)
        
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        
        embed = discord.Embed(
            title="♻️ SYSTEM RESTART INITIATED",
            description=(
                "```ansi\n"
                "\u001b[1;33mSTATUS  : RESTARTING\u001b[0m\n"
                "\u001b[1;36mMODE    : FULL SYSTEM REBOOT\u001b[0m\n"
                "\u001b[1;32mETA     : 5-10 SECONDS\u001b[0m\n"
                "```\n"
                "Bot will be back online shortly..."
            ),
            color=0xf39c12
        )
        embed.set_author(name="TRADERS UNION COMMAND", icon_url=logo)
        embed.set_footer(text="System will reconnect automatically")
        
        await load_msg.delete()
        await ctx.send(embed=embed)
        
        # Close bot connection
        await self.bot.close()
        
        # Restart the process
        os.execv(sys.executable, ['python'] + sys.argv)

    @commands.command(name="systeminfo", aliases=["sysinfo", "specs"])
    async def system_info(self, ctx):
        """Show runtime system information (Specific User Only)"""
        if ctx.author.id != 1170979888019292261:
            return await ctx.send("❌ You don't have permission to use this command.")

        now_utc = datetime.now(timezone.utc)
        uptime_delta = now_utc - self.boot_time
        uptime_text = str(uptime_delta).split(".")[0]

        # Disk usage for root filesystem (works in Railway/Linux containers)
        total_disk, used_disk, free_disk = shutil.disk_usage("/")
        gb = 1024 ** 3

        # Best-effort memory detection without external deps
        memory_text = "N/A"
        try:
            if os.path.exists("/proc/meminfo"):
                mem_total_kb = None
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            mem_total_kb = int(line.split()[1])
                            break
                if mem_total_kb:
                    memory_text = f"{mem_total_kb / (1024 * 1024):.2f} GB"
        except Exception:
            pass

        embed = discord.Embed(
            title="🖥️ SYSTEM INFORMATION",
            color=0x3498db,
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Host", value=f"`{socket.gethostname()}`", inline=True)
        embed.add_field(name="Platform", value=f"`{platform.system()} {platform.release()}`", inline=True)
        embed.add_field(name="Architecture", value=f"`{platform.machine()}`", inline=True)
        embed.add_field(name="Python", value=f"`{platform.python_version()}`", inline=True)
        embed.add_field(name="CPU Cores", value=f"`{os.cpu_count() or 'N/A'}`", inline=True)
        embed.add_field(name="RAM (Total)", value=f"`{memory_text}`", inline=True)
        embed.add_field(name="Disk Total", value=f"`{total_disk / gb:.2f} GB`", inline=True)
        embed.add_field(name="Disk Used", value=f"`{used_disk / gb:.2f} GB`", inline=True)
        embed.add_field(name="Disk Free", value=f"`{free_disk / gb:.2f} GB`", inline=True)
        embed.add_field(name="Process", value=f"`PID {os.getpid()}`", inline=True)
        embed.add_field(name="Bot Uptime", value=f"`{uptime_text}`", inline=True)
        embed.add_field(name="Runtime", value=f"`{sys.executable}`", inline=False)
        embed.set_footer(text="Restricted command • System diagnostics")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Admin(bot))
