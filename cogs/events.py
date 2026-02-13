import discord
from discord.ext import commands
import re
from datetime import timedelta
from collections import defaultdict
from .utils import (
    load_json, save_json, AFK_FILE, 
    get_antilink_config, load_data, 
    get_antispam_config, get_automod_config
)

WELCOME_FILE = "welcome_config.json"

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spam_monitor = defaultdict(list) # user_id: [timestamps]

    # ═══════════════════════════════════════════════════════════════
    #                    WELCOME SYSTEM
    # ═══════════════════════════════════════════════════════════════
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Send aesthetic welcome message when a user joins"""
        if member.bot:
            return
            
        welcome_config = load_json(WELCOME_FILE)
        guild_id = str(member.guild.id)
        
        if guild_id not in welcome_config:
            return
            
        channel_id = welcome_config[guild_id].get("channel")
        if not channel_id:
            return
            
        channel = member.guild.get_channel(int(channel_id))
        if not channel:
            return
        
        total_members = member.guild.member_count
        
        # Aesthetic animated-style welcome embed
        embed = discord.Embed(
            color=0x2b2d31
        )
        
        # Main welcome banner
        embed.set_author(
            name="✦ TRADER UNION GLOBALE ✦",
            icon_url=member.guild.icon.url if member.guild.icon else None
        )
        
        embed.title = "━━━━━━━ 🌐 NEW MEMBER DETECTED 🌐 ━━━━━━━"
        
        embed.description = (
            f"\n"
            f"╔══════════════════════════════════════╗\n"
            f"║                                      ║\n"
            f"║   🎯 **WELCOME TO THE UNION** 🎯    ║\n"
            f"║                                      ║\n"
            f"╚══════════════════════════════════════╝\n"
            f"\n"
            f"```ansi\n"
            f"\u001b[1;36m◈ ENTITY    :\u001b[0m \u001b[1;37m{member.name}\u001b[0m\n"
            f"\u001b[1;36m◈ ID        :\u001b[0m \u001b[0;37m{member.id}\u001b[0m\n"
            f"\u001b[1;36m◈ STATUS    :\u001b[0m \u001b[1;32mACTIVATED\u001b[0m\n"
            f"```\n"
            f"\n"
            f">>> {member.mention}\n"
            f"**Welcome to Trader Union Globale!** 🚀\n"
            f"*You are now part of the elite trading community.*\n"
        )
        
        embed.add_field(
            name="📊 UNION STATISTICS",
            value=(
                f"```fix\n"
                f"Total Members: {total_members}\n"
                f"```"
            ),
            inline=True
        )
        
        embed.add_field(
            name="⚡ QUICK START",
            value=(
                f"```yaml\n"
                f"• Read the rules\n"
                f"• Introduce yourself\n"
                f"• Start trading!\n"
                f"```"
            ),
            inline=True
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        
        # Animated GIF banner (trading themed)
        embed.set_image(url="https://i.pinimg.com/originals/07/44/78/074478e5be57d51f2eb92366f4541bf9.gif")
        
        embed.set_footer(
            text=f"✦ Trader Union Globale • Member #{total_members} ✦",
            icon_url=self.bot.user.display_avatar.url
        )
        
        embed.timestamp = discord.utils.utcnow()
        
        await channel.send(content=f"||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​|| {member.mention}", embed=embed)

    @commands.command(name="welcome", aliases=["setwelcome", "welcomechannel"])
    @commands.has_permissions(administrator=True)
    async def set_welcome_channel(self, ctx, channel: discord.TextChannel = None):
        """Set the welcome channel for new members"""
        welcome_config = load_json(WELCOME_FILE)
        guild_id = str(ctx.guild.id)
        
        if channel is None:
            # Disable welcome messages
            if guild_id in welcome_config:
                del welcome_config[guild_id]
                save_json(WELCOME_FILE, welcome_config)
                
            embed = discord.Embed(
                title="⚙️ WELCOME SYSTEM",
                description=(
                    "```ansi\n"
                    "\u001b[1;31mSTATUS :\u001b[0m \u001b[0;37mDISABLED\u001b[0m\n"
                    "```\n"
                    "Welcome messages have been disabled."
                ),
                color=0xe74c3c
            )
        else:
            # Enable welcome messages for the specified channel
            welcome_config[guild_id] = {"channel": str(channel.id)}
            save_json(WELCOME_FILE, welcome_config)
            
            embed = discord.Embed(
                title="⚙️ WELCOME SYSTEM",
                description=(
                    "```ansi\n"
                    "\u001b[1;32mSTATUS  :\u001b[0m \u001b[0;37mACTIVE\u001b[0m\n"
                    f"\u001b[1;32mCHANNEL :\u001b[0m \u001b[0;37m#{channel.name}\u001b[0m\n"
                    "```\n"
                    f"New members will be welcomed in {channel.mention}"
                ),
                color=0x2ecc71
            )
        
        embed.set_author(name="TRADERS UNION MANAGER", icon_url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Trader Union Globale • Welcome System")
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Get bot prefix to check if message is a command
        ctx = await self.bot.get_context(message)
        
        afk_data = load_json(AFK_FILE)
        author_id = str(message.author.id)
        
        # Check if user returning from AFK (but not if they're using the afk command)
        if author_id in afk_data:
            # Don't remove AFK if user is using the afk command itself
            if ctx.valid and ctx.command and ctx.command.name == "afk":
                return
            
            del afk_data[author_id]
            save_json(AFK_FILE, afk_data)
            
            embed = discord.Embed(
                title="🌐 CONNECTION RESTORED",
                description=(
                    "```ansi\n"
                    f"\u001b[1;32mSTATUS :\u001b[0m \u001b[0;37mONLINE\u001b[0m\n"
                    f"\u001b[1;32mENTITY :\u001b[0m \u001b[0;37m{message.author.name}\u001b[0m\n"
                    "```"
                ),
                color=0x2ecc71
            )
            embed.set_author(name="TRADERS UNION MANAGER", icon_url=self.bot.user.display_avatar.url)
            await message.channel.send(embed=embed)

        # Check if mentioned users are AFK
        for user in message.mentions:
            user_id = str(user.id)
            if user_id in afk_data:
                reason = afk_data[user_id]
                embed = discord.Embed(
                    title="🛰️ ENTITY OFF-GRID",
                    description=(
                        "```ansi\n"
                        f"\u001b[1;33mTARGET :\u001b[0m \u001b[0;37m{user.name}\u001b[0m\n"
                        f"\u001b[1;33mREASON :\u001b[0m \u001b[0;37m{reason}\u001b[0m\n"
                        "```"
                    ),
                    color=0xffcc00
                )
                embed.set_author(name="TRADERS UNION MONITOR", icon_url=self.bot.user.display_avatar.url)
                await message.channel.send(embed=embed)

        # Institutional Security Check (Bypass Logic)
        if message.guild and not message.author.bot:
            am_config = get_automod_config(message.guild.id)
            bypass_role_id = am_config.get("bypass_role")
            
            mod_data = load_data()
            is_bypassed = (
                message.author.id in mod_data.get("owners", []) or 
                message.author.id in mod_data.get("admins", []) or 
                message.author.id in mod_data.get("mods", []) or 
                message.author.guild_permissions.administrator or 
                (bypass_role_id and discord.utils.get(message.author.roles, id=int(bypass_role_id)))
            )

            if is_bypassed:
                return

            # 1. Anti-Link Protection Logic
            link_config = get_antilink_config(message.guild.id)
            if link_config.get("enabled"):
                if re.search(r"https?://\S+|www\.\S+", message.content):
                    try:
                        await message.delete()
                        punishment = link_config.get("punishment", "mute")
                        duration = link_config.get("duration", 60)
                        await message.channel.send(f"⚠️ {message.author.mention}, `UNAUTHORIZED LINK DETECTED. EXECUTING {punishment.upper()} PROTOCOL.`", delete_after=5)
                        if punishment == "ban":
                            await message.author.ban(reason="[AUTO] Anti-Link Violation")
                        elif punishment == "kick":
                            await message.author.kick(reason="[AUTO] Anti-Link Violation")
                        elif punishment == "mute":
                            await message.author.timeout(discord.utils.utcnow() + timedelta(minutes=duration), reason="[AUTO] Anti-Link Violation")
                        return # Stop processing after violation
                    except Exception as e:
                        print(f"Anti-Link Execution Error: {e}")

            # 2. Anti-Spam Protection Logic
            spam_config = get_antispam_config(message.guild.id)
            if spam_config.get("enabled"):
                user_id = message.author.id
                now = discord.utils.utcnow()
                self.spam_monitor[user_id] = [t for t in self.spam_monitor[user_id] if (now - t).total_seconds() < 5]
                self.spam_monitor[user_id].append(now)
                
                limit = spam_config.get("limit", 4)
                if len(self.spam_monitor[user_id]) >= limit:
                    try:
                        self.spam_monitor[user_id] = []
                        punishment = spam_config.get("punishment", "mute")
                        duration = spam_config.get("duration", 60)
                        try: await message.channel.purge(limit=limit, check=lambda m: m.author == message.author)
                        except: pass

                        if punishment == "ban":
                            await message.author.ban(reason="[AUTO] Anti-Spam Violation")
                        elif punishment == "kick":
                            await message.author.kick(reason="[AUTO] Anti-Spam Violation")
                        elif punishment == "mute":
                            await message.author.timeout(discord.utils.utcnow() + timedelta(minutes=duration), reason="[AUTO] Anti-Spam Violation")
                        return # Stop processing
                    except Exception as e:
                        print(f"Anti-Spam Execution Error: {e}")

            # 3. Auto-Mod (Caps & Emojis)
            # Anti-Caps logic
            caps_cfg = am_config["anticaps"]
            if caps_cfg["enabled"] and len(message.content) >= caps_cfg.get("min_len", 5):
                # Filter words that contain alphabetic characters
                alpha_words = [w for w in message.content.split() if any(c.isalpha() for c in w)]
                
                if alpha_words:
                    # Check if the entire alphabetic content is uppercase
                    all_alpha_content = "".join(re.findall(r'[a-zA-Z]', message.content))
                    is_full_caps = all_alpha_content.isupper() if all_alpha_content else False
                    
                    # Check for individually capitalized words (len > 1 to avoid 'A', 'I')
                    caps_words = [w for w in alpha_words if w.isupper() and len(re.findall(r'[a-zA-Z]', w)) > 1]
                    target_ratio = caps_cfg.get("ratio", 0.5)
                    current_ratio = len(caps_words) / len(alpha_words)

                    try:
                        d = caps_cfg.get("duration", 10)
                        if is_full_caps:
                            await message.delete()
                            await message.channel.send(f"⚠️ {message.author.mention}, `SENTENCE DECAPITALIZATION VOID. EXECUTING MUTE PROTOCOL.`", delete_after=5)
                            await message.author.timeout(discord.utils.utcnow() + timedelta(minutes=d), reason="[AUTO] Anti-Caps Violation (Full Sentence)")
                            return
                        elif current_ratio >= target_ratio:
                            await message.delete()
                            await message.channel.send(f"⚠️ {message.author.mention}, `EXCESSIVE WORD CAPS DETECTED. EXECUTING MUTE PROTOCOL.`", delete_after=5)
                            await message.author.timeout(discord.utils.utcnow() + timedelta(minutes=d), reason="[AUTO] Anti-Caps Violation (Word Ratio)")
                            return
                    except: pass

            # Anti-Emoji logic
            emoji_cfg = am_config["antiemoji"]
            if emoji_cfg["enabled"]:
                emoji_count = len(re.findall(r'<a?:.+?:\d+>|[\u263a-\U0001f645]', message.content))
                if emoji_count > emoji_cfg["limit"]:
                    try:
                        await message.delete()
                        p = emoji_cfg["punishment"]
                        d = emoji_cfg.get("duration", 10)
                        await message.channel.send(f"⚠️ {message.author.mention}, `EMOJI FLOOD DETECTED. EXECUTING {p.upper()} PROTOCOL.`", delete_after=5)
                        if p == "mute": await message.author.timeout(discord.utils.utcnow() + timedelta(minutes=d), reason="[AUTO] Anti-Emoji Violation")
                        elif p == "kick": await message.author.kick(reason="[AUTO] Anti-Emoji Violation")
                        elif p == "ban": await message.author.ban(reason="[AUTO] Anti-Emoji Violation")
                    except: pass

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            usage = ctx.command.usage or f"{ctx.prefix}{ctx.command.name} {ctx.command.signature}"
            await ctx.send(f"❌ | Missing arguments!\n**Usage:** `{usage}`")
        elif isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.BadArgument):
            usage = ctx.command.usage or f"{ctx.prefix}{ctx.command.name} {ctx.command.signature}"
            await ctx.send(f"❌ | Invalid argument!\n**Usage:** `{usage}`")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("❌ | You don't have permission to use this command.")
        else:
            print(f"Error in command {ctx.command}: {error}")

async def setup(bot):
    await bot.add_cog(Events(bot))
