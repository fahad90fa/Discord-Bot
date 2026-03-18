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

    @commands.command(name="help")
    async def help_command(self, ctx):
        """Show the Traders Union Help Terminal"""
        embed = discord.Embed(
            title="🛰️ TERMINAL MAIN-FRAME",
            description=(
                "```ansi\n"
                "\u001b[1;36mSYSTEM ACCESS : GRANTED\u001b[0m\n"
                "---------------------------\n"
                "Use the following commands to navigate the system:\n"
                "-help : Show this menu\n"
                "-av : Show user avatar\n"
                "-userinfo : Show user information\n"
                "-serverinfo : Show server information\n"
                "```"
            ),
            color=0x2b2d31
        )
        embed.set_author(name="TRADERS UNION MANAGER", icon_url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Institutional GRADE Automation")

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(General(bot))

 
