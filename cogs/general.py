import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timezone
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
    def __init__(self, cog: "General"):
        self.cog = cog
        options = [
            discord.SelectOption(label="Moderation", value="moderation", emoji="🔴", description="Server moderation tools"),
            discord.SelectOption(label="Security", value="security", emoji="🟢", description="Automated protection systems"),
            discord.SelectOption(label="Economy", value="economy", emoji="🟡", description="Market and trading utilities"),
            discord.SelectOption(label="Utilities", value="utilities", emoji="🔵", description="General utility commands"),
            discord.SelectOption(label="Settings", value="settings", emoji="⚪", description="Administrative configuration"),
        ]
        super().__init__(placeholder="Select Category...", min_values=1, max_values=1, options=options)

    def _category_embed(self, key: str) -> discord.Embed:
        configs = {
            "moderation": {
                "title": "◆ Moderation",
                "color": 0xED4245,
                "desc": (
                    "**ban / kick**\nMember removal and disciplinary control.\n"
                    "────────────────────────\n"
                    "**mute / unmute**\nTemporary communication restriction.\n"
                    "────────────────────────\n"
                    "**clear**\nBulk message cleanup.\n"
                    "────────────────────────\n"
                    "**lock / unlock**\nChannel write access control.\n"
                ),
                "usage": "`-ban @user reason`",
            },
            "security": {
                "title": "◆ Security",
                "color": 0x57F287,
                "desc": (
                    "**antilink**\nDetect and block unauthorized links.\n"
                    "────────────────────────\n"
                    "**antispam**\nMessage flood mitigation.\n"
                    "────────────────────────\n"
                    "**anticaps**\nExcessive caps enforcement.\n"
                    "────────────────────────\n"
                    "**antiemoji**\nEmoji spam protection.\n"
                ),
                "usage": "`-antispam on`",
            },
            "economy": {
                "title": "◆ Economy",
                "color": 0xF5A623,
                "desc": (
                    "**today**\nUpcoming economic events.\n"
                    "────────────────────────\n"
                    "**pips**\nPip movement and P/L estimate.\n"
                    "────────────────────────\n"
                    "**lotsize**\nRisk-based lot sizing.\n"
                    "────────────────────────\n"
                    "**ask**\nForex AI assistant guidance.\n"
                ),
                "usage": "`-pips 1.0845 1.0870 0.5 EURUSD`",
            },
            "utilities": {
                "title": "◆ Utilities",
                "color": 0x5865F2,
                "desc": (
                    "**membercount**\nServer population overview.\n"
                    "────────────────────────\n"
                    "**userinfo**\nDetailed profile inspection.\n"
                    "────────────────────────\n"
                    "**avatar**\nDisplay profile avatar.\n"
                    "────────────────────────\n"
                    "**ttt**\nTic-Tac-Toe against users or AI.\n"
                ),
                "usage": "`-ttt ai`",
            },
            "settings": {
                "title": "◆ Settings",
                "color": 0x99AAB5,
                "desc": (
                    "**setnews / alert**\nNews and session alert routing.\n"
                    "────────────────────────\n"
                    "**setauditlog / auditlogoff**\nAudit log channel control.\n"
                    "────────────────────────\n"
                    "**ticket setup**\nTicket panel and staff setup.\n"
                    "────────────────────────\n"
                    "**vc setup**\nVoice interface provisioning.\n"
                ),
                "usage": "`-ticket setup #panel #log #category @Staff`",
            },
        }
        c = configs[key]
        embed = discord.Embed(
            title=c["title"],
            description=c["desc"],
            color=c["color"],
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Usage", value=c["usage"], inline=False)
        embed.set_footer(text="◂ Back to main help")
        return embed

    async def callback(self, interaction: discord.Interaction):
        embed = self._category_embed(self.values[0])
        embed.set_author(name=f"{self.cog.bot.user.name} ✅", icon_url=self.cog.bot.user.display_avatar.url)
        try:
            await interaction.response.edit_message(embed=embed)
        except Exception:
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception:
                pass

class HelpView(discord.ui.View):
    def __init__(self, cog: "General"):
        super().__init__(timeout=180)
        self.add_item(HelpDropdown(cog))

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
        latency = round(self.bot.latency * 1000)
        uptime = discord.utils.utcnow() - self.started_at
        hours = int(uptime.total_seconds() // 3600)
        total_users = len([m for g in self.bot.guilds for m in g.members if not m.bot])
        modules = 12
        embed = discord.Embed(
            title="TRADERS UNION ◆",
            description=(
                "Institutional Grade Management System\n"
                "─────────────────────────────────────\n"
                "Unified command surface for moderation, security,\n"
                "market operations, utility workflows, and configuration.\n"
                "Select a category to continue."
            ),
            color=0x2b2d31,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=f"{self.bot.user.name} ✅", icon_url=self.bot.user.display_avatar.url)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(name="◆ Moderation", value="Member discipline and channel control.", inline=True)
        embed.add_field(name="◆ Security", value="Automated protection and risk controls.", inline=True)
        embed.add_field(name="◆ Economy", value="Forex tools and market operations.", inline=True)
        embed.add_field(name="◆ Utilities", value="Identity, stats, and utility actions.", inline=True)
        embed.add_field(name="◆ Settings", value="System configuration and routing.", inline=True)
        embed.add_field(name="◆ Platform", value=f"Modules: `{modules}` • Users: `{total_users}` • Uptime: `{hours}h`", inline=True)

        sector = ctx.guild.name if ctx.guild else "Direct"
        embed.set_footer(text=f"Select a category below • Ping: {latency}ms • Sector: {sector}")

        await ctx.send(embed=embed, view=HelpView(self))

async def setup(bot):
    await bot.add_cog(General(bot))
