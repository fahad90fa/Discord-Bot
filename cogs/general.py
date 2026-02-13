import discord
from discord.ext import commands
import asyncio
from .utils import load_afk, save_afk

class HelpDropdown(discord.ui.Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label="/ System Overview", value="System Overview", description="Main terminal entry point"),
            discord.SelectOption(label="/ Moderation Core", value="Moderation Core", description="Sector security & entity control"),
            discord.SelectOption(label="/ Overwatch Security", value="Overwatch Security", description="Automated defense protocols"),
            discord.SelectOption(label="/ Market Intelligence", value="Market Intelligence", description="Forex tools & economic data"),
            discord.SelectOption(label="/ Union Points", value="Union Points", description="Member ranking & rewards system"),
            discord.SelectOption(label="/ Attendance System", value="Attendance System", description="Batch attendance tracking"),
            discord.SelectOption(label="/ System Utilities", value="System Utilities", description="General tools & identity scans"),
            discord.SelectOption(label="/ High Command", value="High Command", description="Institutional governance & config")
        ]
        super().__init__(placeholder="📡 CHOOSE SECTOR TO ACCESS...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        
        embed = discord.Embed(color=0x2b2d31)
        embed.set_author(name="QUANTUM TERMINAL SYSTEM v7.0", icon_url=self.bot.user.display_avatar.url)
        embed.set_thumbnail(url=logo)
        embed.set_footer(text="CORE ACCESS GRANTED • INSTITUTIONAL ENCRYPTION ACTIVE")

        if self.values[0] == "System Overview":
            embed.title = "🛰️ TERMINAL MAIN-FRAME"
            embed.color = 0x3498db
            embed.description = (
                "```ansi\n"
                "\u001b[1;36mAUTHORIZED OPERATOR IDENTIFIED\u001b[0m\n"
                "-------------------------------------------\n"
                "Welcome to the Traders Union Command Bridge.\n"
                "Navigate via the slash-prefixed dropdown menu.\n"
                "```"
            )
            embed.add_field(name="📈 Connection State", value="`STABLE_V7.0_ENCRYPTED`", inline=True)
            embed.add_field(name="🔐 Auth Level", value="`ADMINISTRATOR`", inline=True)
            embed.add_field(name="📡 Sector Status", value="8 Active Sectors Online", inline=False)

        elif self.values[0] == "Moderation Core":
            embed.title = "🛡️ SECTOR: MODERATION"
            embed.color = 0xff4757
            embed.add_field(name="🚫 [BAN / KICK]", value="```ansi\n\u001b[0;37mPermanent or immediate removal.\u001b[0m\n```", inline=False)
            embed.add_field(name="🔇 [MUTE]", value="```ansi\n\u001b[0;37mSystem communication lockout.\u001b[0m\n```", inline=False)
            embed.add_field(name="🧹 [CLEAR / PURGE]", value="```ansi\n\u001b[0;37mSurgical message deletions.\u001b[0m\n```", inline=False)
            embed.add_field(name="🔒 [LOCK / HIDE]", value="```ansi\n\u001b[0;37mChannel accessibility control.\u001b[0m\n```", inline=False)

        elif self.values[0] == "Overwatch Security":
            embed.title = "🛰️ SECTOR: DEFENSE"
            embed.color = 0x1abc9c
            embed.add_field(name="🔗 [ANTILINK]", value="```ansi\n\u001b[0;37mRedirection suppression.\u001b[0m\n```", inline=False)
            embed.add_field(name="⚙️ [ANTISPAM]", value="```ansi\n\u001b[0;37mFlood Engine Control.\u001b[0m\n```", inline=False)
            embed.add_field(name="🅰️ [ANTICAPS]", value="```ansi\n\u001b[0;37mCapitalization Override.\u001b[0m\n```", inline=False)
            embed.add_field(name="🎭 [ANTIEMOJI]", value="```ansi\n\u001b[0;37mVisual flood suppression.\u001b[0m\n```", inline=False)

        elif self.values[0] == "Market Intelligence":
            embed.title = "📈 SECTOR: ECONOMICS"
            embed.color = 0x2ecc71
            embed.add_field(name="📰 [TODAY]", value="```ansi\n\u001b[0;37mLive economic news feed.\u001b[0m\n```", inline=False)
            embed.add_field(name="🧮 [LOTSIZE]", value="```ansi\n\u001b[0;37mInstitutional Risk Calc.\u001b[0m\n```", inline=False)
            embed.add_field(name="🔔 [REMINDERS]", value="```ansi\n\u001b[0;37mSubscription alert feed.\u001b[0m\n```", inline=False)
            embed.add_field(name="💎 [XAUUSD]", value="```ansi\n\u001b[0;37mGold market pulse data.\u001b[0m\n```", inline=False)
            embed.add_field(name="🤖 [ASK / AI]", value="```ansi\n\u001b[0;37mForex AI Expert System.\u001b[0m\n```", inline=False)

        elif self.values[0] == "Attendance System":
            embed.title = "📋 SECTOR: ATTENDANCE"
            embed.color = 0x3498db
            embed.description = "```ansi\n\u001b[1;36mBATCH ATTENDANCE TRACKING SYSTEM\u001b[0m\n\u001b[0;37mTime: 4PM-9PM (Mon-Fri)\u001b[0m\n```"
            embed.add_field(name="⚙️ [SETUP]", value="```ansi\n\u001b[0;37m-setattendancechannel #channel\n-setattendancelog #channel\n-addbatch @role BatchName\n-setupattendance\u001b[0m\n```", inline=False)
            embed.add_field(name="📊 [VIEW]", value="```ansi\n\u001b[0;37m-listbatches\n-attendancefordate DD/MM/YY\n-showuserattendance @user\u001b[0m\n```", inline=False)
            embed.add_field(name="📝 [EDIT]", value="```ansi\n\u001b[0;37m-edituserattendance @user DD/MM/YY present/absent\n-editattendancefordate DD/MM/YY\n-removebatch BatchName\u001b[0m\n```", inline=False)
            embed.add_field(name="ℹ️ [INFO]", value="```ansi\n\u001b[0;33mAuto list posts at 9PM daily\nWeekends disabled\nLogs sent to log channel\u001b[0m\n```", inline=False)

        elif self.values[0] == "System Utilities":
            embed.title = "⚙️ SECTOR: UTILITIES"
            embed.color = 0x9b59b6
            embed.add_field(name="🕵️ [USERINFO]", value="```ansi\n\u001b[0;37mEntity Metadata Scan.\u001b[0m\n```", inline=False)
            embed.add_field(name="🔗 [SOCIAL]", value="```ansi\n\u001b[0;37mUnion Network Links.\u001b[0m\n```", inline=False)
            embed.add_field(name="📷 [AVATAR]", value="```ansi\n\u001b[0;37mVisual Identity Profile.\u001b[0m\n```", inline=False)
            embed.add_field(name="📦 [STEAL]", value="```ansi\n\u001b[0;37mAsset (Emoji) Extraction.\u001b[0m\n```", inline=False)
            embed.add_field(name="💤 [AFK]", value="```ansi\n\u001b[0;37mOff-Grid Status Mode.\u001b[0m\n```", inline=False)

        elif self.values[0] == "Union Points":
            embed.title = "💎 SECTOR: UNION POINTS"
            embed.color = 0xf39c12
            embed.description = "```ansi\n\u001b[1;33m⚠️ ALL COMMANDS OWNER-ONLY (Except CHECK)\u001b[0m\n```"
            embed.add_field(name="💰 [UNION CHECK]", value="```ansi\n\u001b[0;37mView points & rank (Public).\u001b[0m\n```", inline=False)
            embed.add_field(name="🏆 [UNION LB]", value="```ansi\n\u001b[0;37mView leaderboard (Owner).\u001b[0m\n```", inline=False)
            embed.add_field(name="✅ [UNION ADD]", value="```ansi\n\u001b[0;37mAdd points (Owner).\u001b[0m\n```", inline=False)
            embed.add_field(name="❌ [UNION REMOVE]", value="```ansi\n\u001b[0;37mRemove points (Owner).\u001b[0m\n```", inline=False)
            embed.add_field(name="🔄 [UNION RESET]", value="```ansi\n\u001b[0;37mReset user points (Owner).\u001b[0m\n```", inline=False)
            embed.add_field(name="📋 [UNION LOGS]", value="```ansi\n\u001b[0;37mView action logs (Owner).\u001b[0m\n```", inline=False)
            embed.add_field(name="👥 [UNION MANAGERS]", value="```ansi\n\u001b[0;37mList managers (Owner).\u001b[0m\n```", inline=False)
            embed.add_field(name="📡 [UNION SETLB]", value="```ansi\n\u001b[0;37mSetup live leaderboard (Owner).\u001b[0m\n```", inline=False)
            embed.add_field(name="📝 [UNION SETLOG]", value="```ansi\n\u001b[0;37mSetup auto-logging (Owner).\u001b[0m\n```", inline=False)

        elif self.values[0] == "High Command":
            embed.title = "👑 SECTOR: COMMAND"
            embed.color = 0xf1c40f
            embed.add_field(name="📝 [SETMODLOG]", value="```ansi\n\u001b[0;37mSecure overwatch logging.\u001b[0m\n```", inline=False)
            embed.add_field(name="📍 [SETNEWS]", value="```ansi\n\u001b[0;37mNews feed channel setup.\u001b[0m\n```", inline=False)
            embed.add_field(name="🛡️ [BYPASS]", value="```ansi\n\u001b[0;37mAuto-Mod immunity role.\u001b[0m\n```", inline=False)
            embed.add_field(name="⚙️ [SETSTATUS]", value="```ansi\n\u001b[0;37mPresence & activity config.\u001b[0m\n```", inline=False)

        try:
            await interaction.response.edit_message(embed=embed)
        except:
            try: await interaction.followup.send(embed=embed, ephemeral=True)
            except: pass

class HelpView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.add_item(HelpDropdown(bot))

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="membercount", aliases=["mc"])
    async def member_count(self, ctx):
        """Show server member count"""
        guild = ctx.guild
        if guild is None:
            return await ctx.send("❌ This command can only be used in a server.")

        total_members = guild.member_count or len(guild.members)
        human_members = sum(1 for m in guild.members if not m.bot)
        bot_members = sum(1 for m in guild.members if m.bot)

        embed = discord.Embed(
            title="👥 MEMBER COUNT",
            color=0x3498db,
            description=(
                f"**Server:** {guild.name}\n"
                f"**Total:** `{total_members}`\n"
                f"**Humans:** `{human_members}`\n"
                f"**Bots:** `{bot_members}`"
            ),
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def afk(self, ctx, *, reason="AFK"):
        """Initialize AFK protocol for the user"""
        if "@everyone" in reason or "@here" in reason or "<@&" in reason:
            return await ctx.send("apni dalali apne ghar dekhye")
            
        afk_data = load_afk()
        afk_data[str(ctx.author.id)] = reason
        save_afk(afk_data)
        
        embed = discord.Embed(
            title="🛰️ AFK PROTOCOL ACTIVATED",
            description=(
                "```ansi\n"
                f"\u001b[1;33mSTATUS :\u001b[0m \u001b[0;37mOFF-GRID\u001b[0m\n"
                f"\u001b[1;33mREASON :\u001b[0m \u001b[0;37m{reason}\u001b[0m\n"
                "```"
            ),
            color=0xffcc00
        )
        embed.set_author(name="TRADERS UNION MANAGER", icon_url=self.bot.user.display_avatar.url)
        embed.set_footer(text=f"User: {ctx.author.name} • Deep Sleep Mode")
        await ctx.send(embed=embed)

    @commands.command(name="help")
    async def help_command(self, ctx):
        """Show the interactive Traders Union Help Terminal"""
        embed = discord.Embed(
            title="🛰️ TERMINAL MAIN-FRAME",
            description=(
                "```ansi\n"
                "\u001b[1;36mSYSTEM ACCESS : GRANTED\u001b[0m\n"
                "---------------------------\n"
                "Select a sector from the menu below to initialize mission protocols.\n"
                "```"
            ),
            color=0x2b2d31
        )
        embed.set_author(name="TRADERS UNION MANAGER", icon_url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Institutional GRADE Automation • v7.0")
        
        await ctx.send(embed=embed, view=HelpView(self.bot))

async def setup(bot):
    await bot.add_cog(General(bot))
