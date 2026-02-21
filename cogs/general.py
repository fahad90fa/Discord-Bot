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
            discord.SelectOption(label="⟨◆⟩ HUB OVERVIEW ⟨◆⟩", value="hub", description="Boot into the nexus core"),
            discord.SelectOption(label="⟨◆⟩ ⚔️ GUARDIAN PROTOCOLS ⟨◆⟩", value="moderation", description="Unleash moderation fury"),
            discord.SelectOption(label="⟨◆⟩ 🛡️ SENTINEL MATRIX ⟨◆⟩", value="security", description="Deploy defensive layers"),
            discord.SelectOption(label="⟨◆⟩ 💎 NEXUS EXCHANGE ⟨◆⟩", value="economy", description="Decode market mysteries"),
            discord.SelectOption(label="⟨◆⟩ 🎮 RECREATION DIMENSION ⟨◆⟩", value="fun", description="Initiate game protocols"),
            discord.SelectOption(label="⟨◆⟩ ⚙️ QUANTUM TOOLKIT ⟨◆⟩", value="utility", description="Access utility systems"),
        ]
        super().__init__(placeholder="⟨◆⟩ SELECT NEXUS SECTOR ⟨◆⟩", min_values=1, max_values=1, options=options)

    def _cmd_box(self, cmd: str, desc: str) -> str:
        return (
            "```"
            "\n╔═══════════════════╗"
            f"\n║  ⟨CMD⟩ {cmd}"
            "\n╠═══════════════════╣"
            f"\n║  {desc}"
            "\n╚═══════════════════╝"
            "\n```"
        )

    async def callback(self, interaction: discord.Interaction):
        bot = self.cog.bot
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        embed = discord.Embed(color=0x0F0F23, timestamp=discord.utils.utcnow())
        embed.set_thumbnail(url=logo)
        embed.set_author(name="⟨◆⟩ QUANTUM NEXUS INTERFACE ⟨◆⟩", icon_url=bot.user.display_avatar.url)

        v = self.values[0]
        if v == "hub":
            latency = round(bot.latency * 1000)
            uptime = discord.utils.utcnow() - self.cog.started_at
            hours = int(uptime.total_seconds() // 3600)
            users = len([m for g in bot.guilds for m in g.members if not m.bot])
            modules = 12

            embed.title = "『 ⟨NEXUS CORE⟩ 』PROTOCOLS INITIALIZED"
            embed.color = 0x5865F2
            embed.description = (
                "━━━━━━ ◦ ❖ ◦ ━━━━━━\n"
                "`*INITIALIZE*  SYS_BOOT.EXE`\n"
                "`*WHOOSH*      Neural bridge online`\n"
                "`Scanning...   [██████████] 100%`\n"
                "```ansi\n"
                "\u001b[1;36m⟨◆⟩ QUANTUM NEXUS COMMAND CENTER ⟨◆⟩\u001b[0m\n"
                "\u001b[1;35mGL1TCH-LINK : ACTIVE // H0L0-MODE : TRUE\u001b[0m\n"
                "```"
                "━━━━━━ ◦ ❖ ◦ ━━━━━━\n"
                "||easter_egg://nexus-heartbeat||"
            )
            embed.add_field(name="◈ Online Modules", value=f"`{modules}`  ▰▰▰▰▰▰▰▰▱▱", inline=True)
            embed.add_field(name="◇ Active Users", value=f"`{users}`  ▰▰▰▰▰▰▱▱▱▱", inline=True)
            embed.add_field(name="❖ System Uptime", value=f"`{hours}h`  ▰▰▰▰▰▱▱▱▱▱", inline=True)
            embed.add_field(name="Classification", value="`S-RANK`", inline=True)
            embed.add_field(name="Required Clearance", value="`👤 USER`", inline=True)
            embed.add_field(name="Cooldown", value="`⏱️ 0s`", inline=True)
            embed.set_footer(text=f"⚡ Neural Link Established | Ping: {latency}ms | Sector: {interaction.guild.name if interaction.guild else 'Unknown'}")

        elif v == "moderation":
            embed.title = "『 ⟨⚔️ GUARDIAN PROTOCOLS⟩ 』PROTOCOLS INITIALIZED"
            embed.color = 0xFF006E
            embed.description = "🌸⚔️  Moderation combat stack online.\n━━━━━━ ◦ ❖ ◦ ━━━━━━"
            embed.add_field(name="BAN/KICK", value=self._cmd_box("-ban / -kick", "Entity removal & strike control"), inline=False)
            embed.add_field(name="MUTE", value=self._cmd_box("-mute", "Voice/text suppression protocol"), inline=False)
            embed.add_field(name="PURGE", value=self._cmd_box("-clear", "Message cleanup burst"), inline=False)
            embed.add_field(name="Required Clearance Level", value="`🛡️ MOD / 👑 ADMIN`", inline=True)
            embed.add_field(name="Classification Level", value="`A-RANK`", inline=True)
            embed.add_field(name="Cooldown", value="`⏱️ 2-5s`", inline=True)

        elif v == "security":
            embed.title = "『 ⟨🛡️ SENTINEL MATRIX⟩ 』PROTOCOLS INITIALIZED"
            embed.color = 0x00D9FF
            embed.description = "⚡🔮  Defensive matrix armed.\n━━━━━━ ◦ ❖ ◦ ━━━━━━"
            embed.add_field(name="ANTILINK", value=self._cmd_box("-antilink on/off", "Link barrier enforcement"), inline=False)
            embed.add_field(name="ANTISPAM", value=self._cmd_box("-antispam on/off", "Flood-rate suppression"), inline=False)
            embed.add_field(name="AUTOMOD", value=self._cmd_box("-anticaps / -antiemoji", "Pattern anomaly filtering"), inline=False)
            embed.add_field(name="Required Clearance Level", value="`👑 ADMIN`", inline=True)
            embed.add_field(name="Classification Level", value="`S-RANK`", inline=True)
            embed.add_field(name="Cooldown", value="`⏱️ 1-3s`", inline=True)

        elif v == "economy":
            embed.title = "『 ⟨💎 NEXUS EXCHANGE⟩ 』PROTOCOLS INITIALIZED"
            embed.color = 0xFFD700
            embed.description = "💫🎴  Market data pipelines unlocked.\n━━━━━━ ◦ ❖ ◦ ━━━━━━"
            embed.add_field(name="FOREX NEWS", value=self._cmd_box("-today / -reminders", "Economic impact events"), inline=False)
            embed.add_field(name="RISK CALC", value=self._cmd_box("-lotsize / -pips", "Lot-size, pips, P/L estimate"), inline=False)
            embed.add_field(name="AI DESK", value=self._cmd_box("-ask", "Forex AI assistant responses"), inline=False)
            embed.add_field(name="Required Clearance Level", value="`👤 USER`", inline=True)
            embed.add_field(name="Classification Level", value="`A-RANK`", inline=True)
            embed.add_field(name="Cooldown", value="`⏱️ 2s`", inline=True)

        elif v == "fun":
            embed.title = "『 ⟨🎮 RECREATION DIMENSION⟩ 』PROTOCOLS INITIALIZED"
            embed.color = 0x9D00FF
            embed.description = "🌸⚔️  Entertainment node engaged.\n━━━━━━ ◦ ❖ ◦ ━━━━━━"
            embed.add_field(name="TTT PvP/AI", value=self._cmd_box("-ttt @user / -ttt ai", "Button duel with unbeatable AI"), inline=False)
            embed.add_field(name="Required Clearance Level", value="`👤 USER`", inline=True)
            embed.add_field(name="Classification Level", value="`B-RANK`", inline=True)
            embed.add_field(name="Cooldown", value="`⏱️ 1s`", inline=True)

        elif v == "utility":
            embed.title = "『 ⟨⚙️ QUANTUM TOOLKIT⟩ 』PROTOCOLS INITIALIZED"
            embed.color = 0x00FF9D
            embed.description = "⚡🔮  Utility deck synchronized.\n━━━━━━ ◦ ❖ ◦ ━━━━━━"
            embed.add_field(name="IDENTITY", value=self._cmd_box("-userinfo / -avatar", "Profile intel scan"), inline=False)
            embed.add_field(name="SERVER", value=self._cmd_box("-membercount / -social", "Guild status + links"), inline=False)
            embed.add_field(name="STATUS", value=self._cmd_box("-afk", "Away-state protocol"), inline=False)
            embed.add_field(name="Required Clearance Level", value="`👤 USER`", inline=True)
            embed.add_field(name="Classification Level", value="`A-RANK`", inline=True)
            embed.add_field(name="Cooldown", value="`⏱️ 1-2s`", inline=True)

        embed.set_footer(text=f"⟨◆⟩ SUPPORT NEXUS ⟨◆⟩ • Last Sync: {discord.utils.utcnow().strftime('%H:%M:%S UTC')}")
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
        embed = discord.Embed(
            title="⟨◆⟩ QUANTUM NEXUS COMMAND CENTER ⟨◆⟩",
            description=(
                "━━━━━━ ◦ ❖ ◦ ━━━━━━\n"
                "`*INITIALIZE*  Booting nexus shell...`\n"
                "`Scanning...   [████████░░] 80%`\n"
                "`Scanning...   [██████████] 100%`\n"
                "```ansi\n"
                "\u001b[1;35mGLITCH_SIGNAL :: SYNCHRONIZED\u001b[0m\n"
                "\u001b[1;36mHYPERLINK GRID READY // SELECT A SECTOR\u001b[0m\n"
                "```"
                "━━━━━━ ◦ ❖ ◦ ━━━━━━\n"
                "||nexus_key: black-rabbit||"
            ),
            color=0x5865F2
        )
        embed.set_author(name="TRADERS UNION MANAGER", icon_url=self.bot.user.display_avatar.url)
        embed.add_field(name="Online Modules", value="`12` ▰▰▰▰▰▰▰▰▱▱", inline=True)
        embed.add_field(name="Active Users", value=f"`{total_users}` ▰▰▰▰▰▱▱▱▱▱", inline=True)
        embed.add_field(name="System Uptime", value=f"`{hours}h` ▰▰▰▰▱▱▱▱▱▱", inline=True)
        embed.set_footer(text=f"⚡ Neural Link Established | Ping: {latency}ms | Sector: {ctx.guild.name}")

        await ctx.send(embed=embed, view=HelpView(self))

async def setup(bot):
    await bot.add_cog(General(bot))
