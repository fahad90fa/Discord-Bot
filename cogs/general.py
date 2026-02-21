import discord
from discord.ext import commands
import asyncio
from .utils import load_afk, save_afk

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
            # AI commands disabled

        elif self.values[0] == "Attendance System":
            embed.title = "📋 SECTOR: ATTENDANCE"
            embed.color = 0x3498db
            embed.description = (
                "```ansi\n"
                "\u001b[1;36mBATCH ATTENDANCE TRACKING SYSTEM\u001b[0m\n"
                "\u001b[0;37mTime: 4PM-9PM (Mon-Fri)\u001b[0m\n"
                "\u001b[0;37mButton: Mark Attendance (One mark per day)\u001b[0m\n"
                "```"
            )
            embed.add_field(name="⚙️ [SETUP]", value="```ansi\n\u001b[0;37m-setupattendance #channel\n-setattendancelog #channel\n-addbatch @role BatchName\u001b[0m\n```", inline=False)
            embed.add_field(name="📊 [VIEW]", value="```ansi\n\u001b[0;37m-listbatches\n-attendancefordate DD/MM/YY\n-showuserattendance @user\u001b[0m\n```", inline=False)
            embed.add_field(name="📝 [EDIT]", value="```ansi\n\u001b[0;37m-edituserattendance @user DD/MM/YY present/absent\n-editattendancefordate DD/MM/YY\n-removebatch BatchName\u001b[0m\n```", inline=False)
            embed.add_field(name="ℹ️ [INFO]", value="```ansi\n\u001b[0;33mAuto list posts at 9PM daily\nWeekends disabled\nLogs sent to log channel\u001b[0m\n```", inline=False)

        elif self.values[0] == "System Utilities":
            embed.title = "⚙️ SECTOR: UTILITIES"
            embed.color = 0x9b59b6
            embed.add_field(name="🕵️ [USERINFO]", value="```ansi\n\u001b[0;37mEntity Metadata Scan.\u001b[0m\n```", inline=False)
            embed.add_field(name="👥 [MEMBERCOUNT / MC]", value="```ansi\n\u001b[0;37mServer member statistics.\u001b[0m\n```", inline=False)
            embed.add_field(name="🎮 [TTT]", value="```ansi\n\u001b[0;37mTic-Tac-Toe (PvP + unbeatable AI).\u001b[0m\n```", inline=False)
            embed.add_field(name="🔗 [SOCIAL]", value="```ansi\n\u001b[0;37mUnion Network Links.\u001b[0m\n```", inline=False)
            embed.add_field(name="📷 [AVATAR]", value="```ansi\n\u001b[0;37mVisual Identity Profile.\u001b[0m\n```", inline=False)
            embed.add_field(name="📦 [STEAL]", value="```ansi\n\u001b[0;37mAsset (Emoji) Extraction.\u001b[0m\n```", inline=False)
            embed.add_field(name="💤 [AFK]", value="```ansi\n\u001b[0;37mOff-Grid Status Mode.\u001b[0m\n```", inline=False)

        elif self.values[0] == "Giveaways & Events":
            embed.title = "🎉 SECTOR: GIVEAWAYS & EVENTS"
            embed.color = 0x2ecc71
            embed.description = (
                "```ansi\n"
                "\u001b[1;36mGIVEAWAY MANAGER + SCHEDULED ANNOUNCEMENTS\u001b[0m\n"
                "```"
            )
            embed.add_field(
                name="🎁 [GIVEAWAY START]",
                value="```ansi\n\u001b[0;37m-giveaway start 2h 1 #channel --join 7d --role @Role Prize\u001b[0m\n```",
                inline=False
            )
            embed.add_field(
                name="🛑 [GIVEAWAY END]",
                value="```ansi\n\u001b[0;37m-giveaway end <message_id> [#channel]\u001b[0m\n```",
                inline=False
            )
            embed.add_field(
                name="🔁 [GIVEAWAY REROLL]",
                value="```ansi\n\u001b[0;37m-giveaway reroll <message_id> [#channel]\u001b[0m\n```",
                inline=False
            )
            embed.add_field(
                name="📋 [GIVEAWAY LIST]",
                value="```ansi\n\u001b[0;37m-giveaway list\u001b[0m\n```",
                inline=False
            )
            embed.add_field(
                name="📅 [ANNOUNCE ADD]",
                value="```ansi\n\u001b[0;37m-announce add #channel 2026-02-15 21:00 Message (PKT)\u001b[0m\n```",
                inline=False
            )
            embed.add_field(
                name="📋 [ANNOUNCE LIST/CANCEL]",
                value="```ansi\n\u001b[0;37m-announce list\n-announce cancel <id>\u001b[0m\n```",
                inline=False
            )

        elif self.values[0] == "Logging & Audit":
            embed.title = "🧾 SECTOR: LOGGING & AUDIT"
            embed.color = 0x3498db
            embed.description = (
                "```ansi\n"
                "\u001b[1;36mADVANCED AUDIT LOGS (MESSAGE / ROLES / CHANNELS / VOICE)\u001b[0m\n"
                "```"
            )
            embed.add_field(
                name="🛰️ [SET AUDIT CHANNEL]",
                value="```ansi\n\u001b[0;37m-setauditlog #channel\u001b[0m\n```",
                inline=False
            )
            embed.add_field(
                name="🧹 [AUDIT OFF]",
                value="```ansi\n\u001b[0;37m-auditlogoff\u001b[0m\n```",
                inline=False
            )

        elif self.values[0] == "Union Points":
            embed.title = "💎 SECTOR: UNION POINTS"
            embed.color = 0xf39c12
            embed.description = "```ansi\n\u001b[1;33m⚠️ ALL COMMANDS OWNER-ONLY (Except CHECK)\u001b[0m\n```"
            embed.add_field(name="💰 [UNION CHECK]", value="```ansi\n\u001b[0;37mView points & rank (Public).\u001b[0m\n```", inline=False)
            embed.add_field(name="🏆 [UNION LB]", value="```ansi\n\u001b[0;37mView leaderboard (Owner).\u001b[0m\n```", inline=False)
            embed.add_field(name="ℹ️ [UNION]", value="```ansi\n\u001b[0;37mBase command only. Use subcommands.\u001b[0m\n```", inline=False)
            embed.add_field(name="✅ [UNION ADD]", value="```ansi\n\u001b[0;37mAdd points (Owner).\u001b[0m\n```", inline=False)
            embed.add_field(name="❌ [UNION REMOVE]", value="```ansi\n\u001b[0;37mRemove points (Owner).\u001b[0m\n```", inline=False)
            embed.add_field(name="🔄 [UNION RESET]", value="```ansi\n\u001b[0;37mReset user / all points (Owner).\u001b[0m\n```", inline=False)
            embed.add_field(name="📋 [UNION LOGS]", value="```ansi\n\u001b[0;37mView action logs (Owner).\u001b[0m\n```", inline=False)
            embed.add_field(name="👥 [UNION MANAGERS]", value="```ansi\n\u001b[0;37mList managers (Owner).\u001b[0m\n```", inline=False)
            embed.add_field(name="📡 [UNION SETLB]", value="```ansi\n\u001b[0;37mSetup live leaderboard (Owner).\u001b[0m\n```", inline=False)
            embed.add_field(name="📝 [UNION SETLOG]", value="```ansi\n\u001b[0;37mSetup auto-logging (Owner).\u001b[0m\n```", inline=False)

        elif self.values[0] == "High Command":
            embed.title = "👑 SECTOR: COMMAND"
            embed.color = 0xf1c40f
            embed.add_field(name="📝 [SETMODLOG]", value="```ansi\n\u001b[0;37mSecure overwatch logging.\u001b[0m\n```", inline=False)
            embed.add_field(name="📍 [SETNEWS]", value="```ansi\n\u001b[0;37mNews feed channel setup.\u001b[0m\n```", inline=False)
            embed.add_field(name="🧾 [SETAUDITLOG]", value="```ansi\n\u001b[0;37mAudit channel setup.\u001b[0m\n```", inline=False)
            embed.add_field(name="🎫 [TICKET SETUP]", value="```ansi\n\u001b[0;37m-ticket setup #panel #log #category @roles\u001b[0m\n```", inline=False)
            embed.add_field(name="🗄️ [DB STATUS]", value="```ansi\n\u001b[0;37m-db status\u001b[0m\n```", inline=False)
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
