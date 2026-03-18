import discord
from discord.ext import commands
import asyncio
import random
from datetime import datetime, timezone
from .utils import load_afk, save_afk

ROAST_OPENERS = [
    "You move like",
    "You think like",
    "You roast like",
    "You plan like",
    "You code like",
    "You argue like",
    "You flex like",
    "You react like",
    "You lead like",
    "You game like",
]

ROAST_MIDDLES = [
    "a lagging calculator",
    "an offline GPS",
    "a muted microphone",
    "a cracked compass",
    "a buffering stream",
    "a broken keyboard",
    "a low-battery drone",
    "a frozen loading bar",
    "a sleepy firewall",
    "a confused autocorrect",
]

ROAST_ENDINGS = [
    "on 1% battery.",
    "during a software update.",
    "with no internet.",
    "in airplane mode.",
    "after three system errors.",
    "inside a power outage.",
    "while the app is crashing.",
    "with the tutorial still open.",
    "during peak lag hour.",
    "while asking for admin rights.",
]

# Keep exactly 100 ready-to-use roast lines.
ROAST_LINES = [
    f"{opener} {middle} {ending}"
    for opener in ROAST_OPENERS
    for middle in ROAST_MIDDLES
    for ending in ROAST_ENDINGS
][:100]

class TTTButton(discord.ui.Button):
    def __init__(self, x: int, y: int):
        super().__init__(label="\u200b", style=discord.ButtonStyle.secondary, row=y)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        view: "TTTView" = self.view  # type: ignore
        await view.handle_move(interaction, self)


class TTTView(discord.ui.View):
    def __init__(self, player_x: discord.Member, player_o: discord.Member | None, ai_mode: bool = False):
        super().__init__(timeout=180)
        self.player_x = player_x
        self.player_o = player_o
        self.ai_mode = ai_mode
        self.current = player_x
        self.board = [["" for _ in range(3)] for _ in range(3)]
        self.moves = 0
        self.game_over = False
        self.message: discord.Message | None = None

        for y in range(3):
            for x in range(3):
                self.add_item(TTTButton(x, y))

    def _mark_for(self, member: discord.Member) -> str:
        return "X" if member.id == self.player_x.id else "O"

    def _style_for(self, mark: str) -> discord.ButtonStyle:
        return discord.ButtonStyle.danger if mark == "X" else discord.ButtonStyle.success

    def _check_winner(self, mark: str) -> bool:
        b = self.board
        for i in range(3):
            if all(b[i][j] == mark for j in range(3)):
                return True
            if all(b[j][i] == mark for j in range(3)):
                return True
        if all(b[i][i] == mark for i in range(3)):
            return True
        if all(b[i][2 - i] == mark for i in range(3)):
            return True
        return False

    def _disable_all(self):
        for child in self.children:
            child.disabled = True  # type: ignore

    def _build_embed(self, title: str, status: str, color: int) -> discord.Embed:
        embed = discord.Embed(title=title, description=status, color=color)
        embed.add_field(name="Player X", value=self.player_x.mention, inline=True)
        embed.add_field(name="Player O", value=self.player_o.mention if self.player_o else "`TTT AI`", inline=True)
        embed.set_footer(text="Tic-Tac-Toe • 3x3 Grid")
        return embed

    def _check_winner_board(self, board: list[list[str]], mark: str) -> bool:
        for i in range(3):
            if all(board[i][j] == mark for j in range(3)):
                return True
            if all(board[j][i] == mark for j in range(3)):
                return True
        if all(board[i][i] == mark for i in range(3)):
            return True
        if all(board[i][2 - i] == mark for i in range(3)):
            return True
        return False

    def _minimax(self, board: list[list[str]], depth: int, is_ai_turn: bool) -> int:
        if self._check_winner_board(board, "O"):
            return 10 - depth
        if self._check_winner_board(board, "X"):
            return depth - 10

        empty = [(y, x) for y in range(3) for x in range(3) if board[y][x] == ""]
        if not empty:
            return 0

        if is_ai_turn:
            best = -999
            for y, x in empty:
                board[y][x] = "O"
                score = self._minimax(board, depth + 1, False)
                board[y][x] = ""
                best = max(best, score)
            return best

        best = 999
        for y, x in empty:
            board[y][x] = "X"
            score = self._minimax(board, depth + 1, True)
            board[y][x] = ""
            best = min(best, score)
        return best

    def _best_ai_move(self) -> tuple[int, int] | None:
        best_score = -999
        best_move = None
        for y in range(3):
            for x in range(3):
                if self.board[y][x] == "":
                    self.board[y][x] = "O"
                    score = self._minimax(self.board, 0, False)
                    self.board[y][x] = ""
                    if score > best_score:
                        best_score = score
                        best_move = (y, x)
        return best_move

    def _find_button(self, y: int, x: int) -> TTTButton | None:
        for child in self.children:
            if isinstance(child, TTTButton) and child.y == y and child.x == x:
                return child
        return None

    def _apply_mark(self, y: int, x: int, mark: str):
        self.board[y][x] = mark
        self.moves += 1
        btn = self._find_button(y, x)
        if btn:
            btn.label = mark
            btn.style = self._style_for(mark)
            btn.disabled = True

    async def handle_move(self, interaction: discord.Interaction, button: TTTButton):
        if self.game_over:
            return await interaction.response.send_message("Game already finished.", ephemeral=True)

        if self.ai_mode:
            if interaction.user.id != self.player_x.id:
                return await interaction.response.send_message("Only starter can play against AI.", ephemeral=True)
        else:
            if not self.player_o or interaction.user.id not in {self.player_x.id, self.player_o.id}:
                return await interaction.response.send_message("You are not in this match.", ephemeral=True)

        if interaction.user.id != self.current.id:
            return await interaction.response.send_message("It is not your turn.", ephemeral=True)

        if self.board[button.y][button.x]:
            return await interaction.response.send_message("That cell is already used.", ephemeral=True)

        mark = self._mark_for(self.current)
        self._apply_mark(button.y, button.x, mark)

        if self._check_winner(mark):
            self.game_over = True
            self._disable_all()
            embed = self._build_embed(
                "TIC-TAC-TOE",
                f"🏆 Winner: {self.current.mention} (`{mark}`)",
                0x2ecc71,
            )
            return await interaction.response.edit_message(embed=embed, view=self)

        if self.moves >= 9:
            self.game_over = True
            self._disable_all()
            embed = self._build_embed("TIC-TAC-TOE", "🤝 Match ended in a draw.", 0xf1c40f)
            return await interaction.response.edit_message(embed=embed, view=self)

        if self.ai_mode:
            self.current = self.player_o if self.player_o else self.player_x
            move = self._best_ai_move()
            if move:
                ay, ax = move
                self._apply_mark(ay, ax, "O")

                if self._check_winner("O"):
                    self.game_over = True
                    self._disable_all()
                    embed = self._build_embed("TIC-TAC-TOE", "🤖 Winner: `TTT AI` (`O`)", 0xe74c3c)
                    return await interaction.response.edit_message(embed=embed, view=self)

                if self.moves >= 9:
                    self.game_over = True
                    self._disable_all()
                    embed = self._build_embed("TIC-TAC-TOE", "🤝 Match ended in a draw.", 0xf1c40f)
                    return await interaction.response.edit_message(embed=embed, view=self)

            self.current = self.player_x
            embed = self._build_embed("TIC-TAC-TOE", f"Turn: {self.current.mention}", 0x2b2d31)
            return await interaction.response.edit_message(embed=embed, view=self)

        self.current = self.player_o if self.current.id == self.player_x.id else self.player_x
        embed = self._build_embed("TIC-TAC-TOE", f"Turn: {self.current.mention}", 0x2b2d31)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if self.game_over:
            return
        self.game_over = True
        self._disable_all()
        if self.message:
            embed = self._build_embed("TIC-TAC-TOE", "⌛ Match expired (timeout).", 0xe67e22)
            try:
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass

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
            discord.SelectOption(label="/ Giveaways & Events", value="Giveaways & Events", description="Giveaways + scheduled announcements"),
            discord.SelectOption(label="/ Logging & Audit", value="Logging & Audit", description="Advanced server audit logs"),
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
            embed.add_field(name="🚫 [BAN / UNBAN]", value="```ansi\n\u001b[0;37m-ban @user [reason]\n-unban <id>\u001b[0m\n```", inline=False)
            embed.add_field(name="👢 [KICK]", value="```ansi\n\u001b[0;37m-kick @user [reason]\n\u001b[0m\n```", inline=False)
            embed.add_field(name="🔇 [MUTE / UNMUTE]", value="```ansi\n\u001b[0;37m-mute @user [mins] [reason]\n-unmute @user\u001b[0m\n```", inline=False)
            embed.add_field(name="🧹 [CLEAR / PURGE]", value="```ansi\n\u001b[0;37m-clear [amount]\n-purgeuser @user [amount]\n-purgebot [amount]\u001b[0m\n```", inline=False)
            embed.add_field(name="🔒 [LOCK / UNLOCK]", value="```ansi\n\u001b[0;37m-lock\n-unlock\u001b[0m\n```", inline=False)
            embed.add_field(name="👁️ [HIDE / UNHIDE]", value="```ansi\n\u001b[0;37m-hide\n-unhide\u001b[0m\n```", inline=False)

        elif self.values[0] == "Overwatch Security":
            embed.title = "🛰️ SECTOR: DEFENSE"
            embed.color = 0x1abc9c
            embed.add_field(name="🔗 [ANTILINK]", value="```ansi\n\u001b[0;37m-antilink on/off\n-antilink punishment <type> [duration]\u001b[0m\n```", inline=False)
            embed.add_field(name="⚙️ [ANTISPAM]", value="```ansi\n\u001b[0;37m-antispam on/off\n-antispam punishment <type> [duration]\u001b[0m\n```", inline=False)
            embed.add_field(name="🛡️ [AUTOMOD]", value="```ansi\n\u001b[0;37m-automod list (Status overview)\u001b[0m\n```", inline=False)
            embed.add_field(name="💎 [BYPASS]", value="```ansi\n\u001b[0;37m-bypass (Set auto-mod immunity role)\u001b[0m\n```", inline=False)

        elif self.values[0] == "Market Intelligence":
            embed.title = "📈 SECTOR: ECONOMICS"
            embed.color = 0x2ecc71
            embed.add_field(name="📰 [TODAY / NEWS]", value="```ansi\n\u001b[0;37m-today (Live economic news feed)\n-refreshnews (Force update)\u001b[0m\n```", inline=False)
            embed.add_field(name="🤖 [ASK / PREDICT]", value="```ansi\n\u001b[0;37m-ask <question> (Forex AI)\n-predict (Market sentiment)\u001b[0m\n```", inline=False)
            embed.add_field(name="🧮 [PIPS]", value="```ansi\n\u001b[0;37m-pips (Pip/Trade calculator)\u001b[0m\n```", inline=False)
            embed.add_field(name="🔔 [ALERTS / REMINDERS]", value="```ansi\n\u001b[0;37m-alert (Session alerts config)\n-reminders (Check scheduled alerts)\u001b[0m\n```", inline=False)

        elif self.values[0] == "Attendance System":
            embed.title = "📋 SECTOR: ATTENDANCE"
            embed.color = 0x3498db
            embed.add_field(name="⚙️ [SETUP]", value="```ansi\n\u001b[0;37m-setupattendance\n-addbatch @role BatchName\u001b[0m\n```", inline=False)
            embed.add_field(name="📊 [VIEW]", value="```ansi\n\u001b[0;37m-listbatches\n-attendancefordate DD/MM/YY\n-showuserattendance @user\u001b[0m\n```", inline=False)
            embed.add_field(name="📝 [EDIT]", value="```ansi\n\u001b[0;37m-edituserattendance @user DD/MM/YY present/absent\n-editattendancefordate DD/MM/YY\u001b[0m\n```", inline=False)
            embed.add_field(name="🔔 [REMINDER]", value="```ansi\n\u001b[0;37m-attendancereminder #channel\u001b[0m\n```", inline=False)

        elif self.values[0] == "System Utilities":
            embed.title = "⚙️ SECTOR: UTILITIES"
            embed.color = 0x9b59b6
            embed.add_field(name="🕵️ [USERINFO / SERVERINFO]", value="```ansi\n\u001b[0;37m-userinfo @user\n-serverinfo\u001b[0m\n```", inline=False)
            embed.add_field(name="👥 [MEMBERCOUNT / MC]", value="```ansi\n\u001b[0;37mServer member statistics.\u001b[0m\n```", inline=False)
            embed.add_field(name="📷 [AVATAR / AV]", value="```ansi\n\u001b[0;37m-av @user (Quantum Scan)\u001b[0m\n```", inline=False)
            embed.add_field(name="🎯 [SNIPE]", value="```ansi\n\u001b[0;37m-snipe (Recover deleted messages)\u001b[0m\n```", inline=False)
            embed.add_field(name="🏓 [PING]", value="```ansi\n\u001b[0;37mLatency check.\u001b[0m\n```", inline=False)
            embed.add_field(name="🎮 [TTT]", value="```ansi\n\u001b[0;37mTic-Tac-Toe (PvP + AI).\u001b[0m\n```", inline=False)
            embed.add_field(name="💤 [AFK]", value="```ansi\n\u001b[0;37m-afk [reason]\u001b[0m\n```", inline=False)

        elif self.values[0] == "Giveaways & Events":
            embed.title = "🎉 SECTOR: GIVEAWAYS & EVENTS"
            embed.color = 0x2ecc71
            embed.add_field(name="🎁 [GIVEAWAY]", value="```ansi\n\u001b[0;37m-giveaway start <dur> <win> <prize>\n-giveaway end <id>\n-giveaway reroll <id>\n-giveaway list\u001b[0m\n```", inline=False)
            embed.add_field(name="📅 [ANNOUNCEMENTS]", value="```ansi\n\u001b[0;37m-announce add #ch <date> <time> <msg>\n-announce list\n-announce cancel <id>\u001b[0m\n```", inline=False)

        elif self.values[0] == "Logging & Audit":
            embed.title = "🧾 SECTOR: LOGGING & AUDIT"
            embed.color = 0x3498db
            embed.add_field(name="🛰️ [AUDIT LOG]", value="```ansi\n\u001b[0;37m-setauditlog #channel\n-auditlogoff\u001b[0m\n```", inline=False)

        elif self.values[0] == "Union Points":
            embed.title = "💎 SECTOR: UNION POINTS"
            embed.color = 0xf39c12
            embed.add_field(name="💰 [UNION CHECK / LB]", value="```ansi\n\u001b[0;37m-union check @user\n-union lb\u001b[0m\n```", inline=False)
            embed.add_field(name="🛠️ [UNION ADMIN]", value="```ansi\n\u001b[0;37m-union add/remove @user <pts>\n-union managers\n-union logs\u001b[0m\n```", inline=False)
            embed.add_field(name="⚙️ [UNION CONFIG]", value="```ansi\n\u001b[0;37m-union setlog #channel\n-union setlb #channel\u001b[0m\n```", inline=False)

        elif self.values[0] == "High Command":
            embed.title = "👑 SECTOR: COMMAND"
            embed.color = 0xf1c40f
            embed.add_field(name="📝 [LOGGING / STATUS]", value="```ansi\n\u001b[0;37m-setmodlog #channel\n-setstatus <status> <type> <text>\u001b[0m\n```", inline=False)
            embed.add_field(name="🎫 [TICKET SETUP]", value="```ansi\n\u001b[0;37m-ticket setup #panel #log #cat @role\u001b[0m\n```", inline=False)
            embed.add_field(name="🛡️ [PERMISSIONS]", value="```ansi\n\u001b[0;37m-addowner / -addadmin / -addmod\n-np add @user (No Prefix access)\u001b[0m\n```", inline=False)
            embed.add_field(name="🔌 [SYSTEM]", value="```ansi\n\u001b[0;37m-db status\n-shutdown (Backend kill)\u001b[0m\n```", inline=False)

        try:
            await interaction.response.edit_message(embed=embed)
        except:
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass

class HelpView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.add_item(HelpDropdown(bot))

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.started_at = discord.utils.utcnow()

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

    @commands.command(name="roast")
    @commands.guild_only()
    async def roast(self, ctx, member: discord.Member = None):
        """Roast a user. Usage: -roast @user"""
        if member is None:
            return await ctx.send("❌ Use: `-roast @user`")
        if member.id == ctx.author.id:
            return await ctx.send("❌ Khud ko roast nahi kar sakte.")
        if member.bot:
            return await ctx.send("❌ Bots ko roast mat karo.")

        line = random.choice(ROAST_LINES)
        embed = discord.Embed(
            title="🔥 ROAST",
            description=f"{member.mention} {line}",
            color=0xe74c3c,
        )
        embed.set_footer(text=f"Requested by {ctx.author}")
        await ctx.send(embed=embed)

    @commands.command(name="ttt", aliases=["tictactoe", "tic"])
    @commands.guild_only()
    async def ttt_game(self, ctx, *, opponent: str = None):
        """Play Tic-Tac-Toe with buttons. Usage: -ttt @user | -ttt ai"""
        player_x = ctx.author
        ai_mode = False
        player_o = None

        if opponent is None or opponent.lower().strip() in {"ai", "bot", "cpu"}:
            ai_mode = True
        else:
            try:
                player_o = await commands.MemberConverter().convert(ctx, opponent)
            except commands.BadArgument:
                return await ctx.send("❌ Invalid user. Use `-ttt @user` or `-ttt ai`.")
            if player_o.bot:
                return await ctx.send("❌ Use `-ttt ai` for bot mode.")
            if player_o.id == player_x.id:
                return await ctx.send("❌ Mention another user or use `-ttt ai`.")

        view = TTTView(player_x, player_o, ai_mode=ai_mode)
        embed = discord.Embed(
            title="TIC-TAC-TOE",
            description=f"Turn: {player_x.mention}",
            color=0x2b2d31,
        )
        embed.add_field(name="Player X", value=player_x.mention, inline=True)
        embed.add_field(name="Player O", value=(player_o.mention if player_o else "`TTT AI`"), inline=True)
        embed.set_footer(text="Clean Competitive Mode • Unbeatable AI Enabled")
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.command()
    async def afk(self, ctx, *, reason="AFK"):
        """Initialize AFK protocol for the user"""
        if "@everyone" in reason or "@here" in reason or "<@&" in reason:
            return await ctx.send("apni dalali apne ghar dekhye")
            
        afk_data = load_afk(ctx.guild.id)
        afk_data[str(ctx.author.id)] = reason
        save_afk(afk_data, ctx.guild.id)
        
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

    @commands.command(name="dev", aliases=["developer"])
    async def developer_info(self, ctx):
        """Show bot developer information"""
        developer_id = 1170979888019292261
        embed = discord.Embed(
            title="👨‍💻 BOT DEVELOPER",
            description=(
                f"**Developer:** <@{developer_id}>\n"
                f"**ID:** `{developer_id}`\n"
                "**Username:** `90_alones`\n"
                "**Name:** `fahad`\n"
                "**Note:** `Single developer of this bot`"
            ),
            color=0x2b2d31
        )
        embed.set_footer(text="TRADERS UNION • Developer Info")
        await ctx.send(embed=embed)

    @commands.command(name="help")
    async def help_command(self, ctx):
        """Show the Traders Union Help Terminal"""
        view = HelpView(self.bot)
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        
        embed = discord.Embed(
            title="🛰️ TERMINAL MAIN-FRAME",
            description=(
                "```ansi\n"
                "\u001b[1;36mAUTHORIZED OPERATOR IDENTIFIED\u001b[0m\n"
                "-------------------------------------------\n"
                "Welcome to the Traders Union Command Bridge.\n"
                "Navigate via the slash-prefixed dropdown menu.\n"
                "```"
            ),
            color=0x2b2d31
        )
        embed.set_author(name="TRADERS UNION MANAGER", icon_url=self.bot.user.display_avatar.url)
        embed.set_thumbnail(url=logo)
        embed.add_field(name="📈 Connection State", value="`STABLE_V7.0_ENCRYPTED`", inline=True)
        embed.add_field(name="🔐 Auth Level", value="`ADMINISTRATOR`", inline=True)
        embed.add_field(name="📡 Sector Status", value="8 Active Sectors Online", inline=False)
        embed.set_footer(text="CORE ACCESS GRANTED • INSTITUTIONAL ENCRYPTION ACTIVE")

        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(General(bot))

 
