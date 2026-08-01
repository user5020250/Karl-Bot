import asyncio
import random

import discord
from discord import app_commands
from discord.ext import commands

try:
    import chess  # pip install chess
except ImportError:  # pragma: no cover
    chess = None

BLACK = discord.Color.from_str("#000000")

def make_embed(title: str, description: str = "", color=BLACK) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=color)


async def safe_edit(message: discord.Message, **kwargs):
    if message is None:
        return
    try:
        await message.edit(**kwargs)
    except discord.HTTPException:
        pass
        
# ---------------------------------------------------------------------------
# /connect4
# ---------------------------------------------------------------------------
class Connect4Button(discord.ui.Button):
    def __init__(self, col: int):
        super().__init__(label=str(col + 1), style=discord.ButtonStyle.secondary, row=col // 4)
        self.col = col

    async def callback(self, interaction: discord.Interaction):
        view: "Connect4View" = self.view
        token = view.players[interaction.user.id]

        if not view.drop(self.col, token):
            await interaction.response.send_message("That column is full.", ephemeral=True)
            return

        if view.check_win(token):
            for item in view.children:
                item.disabled = True
            embed = view.build_embed(f"🎉 {interaction.user.mention} wins!")
            await interaction.response.edit_message(embed=embed, view=view)
            view.stop()
            return

        if view.board_full():
            for item in view.children:
                item.disabled = True
            embed = view.build_embed("🤝 It's a draw!")
            await interaction.response.edit_message(embed=embed, view=view)
            view.stop()
            return

        view.turn = 1 - view.turn
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class Connect4View(discord.ui.View):
    ROWS = 6
    COLS = 7
    EMPTY = "⚪"
    P1 = "🔴"
    P2 = "🟡"

    def __init__(self, player1: discord.abc.User, player2: discord.abc.User):
        super().__init__(timeout=300)
        self.players = {player1.id: self.P1, player2.id: self.P2}
        self.order = [player1, player2]
        self.turn = 0
        self.board = [[self.EMPTY] * self.COLS for _ in range(self.ROWS)]
        self.last_move: tuple[int, int] | None = None
        self.message: discord.Message = None
        for col in range(self.COLS):
            self.add_item(Connect4Button(col))

    @property
    def current_player(self) -> discord.abc.User:
        return self.order[self.turn]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.current_player.id:
            await interaction.response.send_message("It's not your turn.", ephemeral=True)
            return False
        return True

    def render_board(self) -> str:
        numbers = "".join(f"{i + 1}\u20e3" for i in range(self.COLS))
        rows = ["".join(row) for row in self.board]
        return numbers + "\n" + "\n".join(rows)

    def drop(self, col: int, token: str) -> bool:
        for row in reversed(range(self.ROWS)):
            if self.board[row][col] == self.EMPTY:
                self.board[row][col] = token
                self.last_move = (row, col)
                return True
        return False

    def check_win(self, token: str) -> bool:
        if self.last_move is None:
            return False
        row, col = self.last_move
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            count = 1
            for sign in (1, -1):
                r, c = row + dr * sign, col + dc * sign
                while 0 <= r < self.ROWS and 0 <= c < self.COLS and self.board[r][c] == token:
                    count += 1
                    r += dr * sign
                    c += dc * sign
            if count >= 4:
                return True
        return False

    def board_full(self) -> bool:
        return all(self.board[0][c] != self.EMPTY for c in range(self.COLS))

    def build_embed(self, extra: str = "") -> discord.Embed:
        embed = make_embed(
            "Connect Four",
            f"{self.render_board()}\n\n{self.P1} {self.order[0].mention}  vs  {self.P2} {self.order[1].mention}\n\n"
            "Click a numbered column button to drop your piece there. "
            "First to connect **4 in a row** — horizontally, vertically, or diagonally — wins!",
        )
        if extra:
            embed.add_field(name="\u200b", value=extra, inline=False)
        else:
            embed.set_footer(
                text=f"It's {self.current_player.display_name}'s turn ({self.players[self.current_player.id]})"
            )
        return embed

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await safe_edit(self.message, view=self)


# ---------------------------------------------------------------------------
# /rps
# ---------------------------------------------------------------------------
class RPSView(discord.ui.View):
    CHOICES = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
    BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}

    def __init__(self, player1: discord.abc.User, player2: discord.abc.User):
        super().__init__(timeout=60)
        self.players = [player1, player2]
        self.choices: dict[int, str] = {}
        self.message: discord.Message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in (p.id for p in self.players):
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return False
        if interaction.user.id in self.choices:
            await interaction.response.send_message("You've already chosen.", ephemeral=True)
            return False
        return True

    def build_embed(self, extra: str = "") -> discord.Embed:
        status = "\n".join(
            f"{p.mention}: {'✅ chosen' if p.id in self.choices else '⏳ waiting'}"
            for p in self.players
        )
        embed = make_embed(
            "Rock Paper Scissors",
            f"{self.players[0].mention} vs {self.players[1].mention}\n\n"
            "**How to play:** each player privately picks Rock, Paper, or Scissors below. "
            "Once both have chosen, the choices are revealed and a winner is decided.\n\n"
            f"{status}",
        )
        if extra:
            embed.add_field(name="\u200b", value=extra, inline=False)
        return embed

    async def register_choice(self, interaction: discord.Interaction, choice: str):
        self.choices[interaction.user.id] = choice
        await interaction.response.send_message(
            f"You chose {self.CHOICES[choice]} **{choice.title()}**.", ephemeral=True
        )

        if len(self.choices) < 2:
            await safe_edit(self.message, embed=self.build_embed(), view=self)
            return

        for item in self.children:
            item.disabled = True

        p1, p2 = self.players
        c1, c2 = self.choices[p1.id], self.choices[p2.id]
        if c1 == c2:
            result = "🤝 It's a tie!"
        elif self.BEATS[c1] == c2:
            result = f"🎉 {p1.mention} wins!"
        else:
            result = f"🎉 {p2.mention} wins!"

        reveal = (
            f"{p1.mention}: {self.CHOICES[c1]} **{c1.title()}**\n"
            f"{p2.mention}: {self.CHOICES[c2]} **{c2.title()}**\n\n{result}"
        )
        embed = make_embed("Rock Paper Scissors", reveal)
        await safe_edit(self.message, embed=embed, view=self)

    @discord.ui.button(label="Rock", emoji="🪨", style=discord.ButtonStyle.secondary)
    async def rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.register_choice(interaction, "rock")

    @discord.ui.button(label="Paper", emoji="📄", style=discord.ButtonStyle.secondary)
    async def paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.register_choice(interaction, "paper")

    @discord.ui.button(label="Scissors", emoji="✂️", style=discord.ButtonStyle.secondary)
    async def scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.register_choice(interaction, "scissors")

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await safe_edit(self.message, view=self)

# ---------------------------------------------------------------------------
# /battleship
# ---------------------------------------------------------------------------
class BattleshipGame:
    SIZE = 6
    SHIP_SIZES = [3, 2, 2]

    def __init__(self):
        self.ships = {"p1": self._place_ships(), "p2": self._place_ships()}
        self.shots: dict[str, dict[tuple[int, int], str]] = {"p1": {}, "p2": {}}

    def _place_ships(self) -> set[tuple[int, int]]:
        occupied: set[tuple[int, int]] = set()
        for size in self.SHIP_SIZES:
            while True:
                horizontal = random.choice([True, False])
                if horizontal:
                    r = random.randint(0, self.SIZE - 1)
                    c = random.randint(0, self.SIZE - size)
                    cells = {(r, c + i) for i in range(size)}
                else:
                    r = random.randint(0, self.SIZE - size)
                    c = random.randint(0, self.SIZE - 1)
                    cells = {(r + i, c) for i in range(size)}
                if not (cells & occupied):
                    occupied |= cells
                    break
        return occupied

    def fire(self, attacker: str, r: int, c: int) -> str:
        target = "p2" if attacker == "p1" else "p1"
        hit = (r, c) in self.ships[target]
        self.shots[attacker][(r, c)] = "hit" if hit else "miss"
        return "hit" if hit else "miss"

    def already_fired(self, attacker: str, r: int, c: int) -> bool:
        return (r, c) in self.shots[attacker]

    def is_winner(self, attacker: str) -> bool:
        target = "p2" if attacker == "p1" else "p1"
        hit_cells = {pos for pos, res in self.shots[attacker].items() if res == "hit"}
        return self.ships[target] <= hit_cells

    def render_tracking(self, attacker: str) -> str:
        keycaps = ["0\u20e3", "1\u20e3", "2\u20e3", "3\u20e3", "4\u20e3", "5\u20e3"]
        letters = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫"]
        header = "⬛" + "".join(keycaps[: self.SIZE])
        lines = [header]
        for r in range(self.SIZE):
            row_cells = [letters[r]]
            for c in range(self.SIZE):
                res = self.shots[attacker].get((r, c))
                if res == "hit":
                    row_cells.append("🔥")
                elif res == "miss":
                    row_cells.append("🌊")
                else:
                    row_cells.append("⬜")
            lines.append("".join(row_cells))
        return "\n".join(lines)


class BattleshipRowSelect(discord.ui.Select):
    def __init__(self):
        letters = ["A", "B", "C", "D", "E", "F"]
        options = [
            discord.SelectOption(label=f"Row {letter}", value=str(i))
            for i, letter in enumerate(letters[: BattleshipGame.SIZE])
        ]
        super().__init__(placeholder="Row", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: "BattleshipView" = self.view
        view.pending_row = int(self.values[0])
        view.update_fire_button()
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class BattleshipColSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=f"Column {i + 1}", value=str(i))
            for i in range(BattleshipGame.SIZE)
        ]
        super().__init__(placeholder="Column", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: "BattleshipView" = self.view
        view.pending_col = int(self.values[0])
        view.update_fire_button()
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class BattleshipFireButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Fire!", style=discord.ButtonStyle.danger, disabled=True, row=2)

    async def callback(self, interaction: discord.Interaction):
        view: "BattleshipView" = self.view
        await view.fire(interaction)


class BattleshipView(discord.ui.View):
    def __init__(self, player1: discord.abc.User, player2: discord.abc.User):
        super().__init__(timeout=900)
        self.game = BattleshipGame()
        self.players = {"p1": player1, "p2": player2}
        self.turn = "p1"
        self.pending_row: int | None = None
        self.pending_col: int | None = None
        self.message: discord.Message = None
        self.fire_button = BattleshipFireButton()
        self.add_item(BattleshipRowSelect())
        self.add_item(BattleshipColSelect())
        self.add_item(self.fire_button)

    def current_player(self) -> discord.abc.User:
        return self.players[self.turn]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.current_player().id:
            await interaction.response.send_message("It's not your turn.", ephemeral=True)
            return False
        return True

    def update_fire_button(self):
        self.fire_button.disabled = self.pending_row is None or self.pending_col is None

    def build_embed(self, extra: str = "") -> discord.Embed:
        p1, p2 = self.players["p1"], self.players["p2"]
        embed = make_embed(
            "Battleship",
            f"{p1.mention}'s shots:\n{self.game.render_tracking('p1')}\n\n"
            f"{p2.mention}'s shots:\n{self.game.render_tracking('p2')}\n\n"
            f"**How to play:** each fleet has hidden ships of size "
            f"`{'`, `'.join(str(s) for s in BattleshipGame.SHIP_SIZES)}` on a "
            f"`{BattleshipGame.SIZE}x{BattleshipGame.SIZE}` grid. Pick a row and column below, "
            "then click **Fire!** 🔥 = hit, 🌊 = miss. Sink every ship cell to win.",
        )
        embed.set_footer(text=f"It's {self.current_player().display_name}'s turn to fire")
        if extra:
            embed.add_field(name="\u200b", value=extra, inline=False)
        return embed

    async def fire(self, interaction: discord.Interaction):
        r, c = self.pending_row, self.pending_col
        if self.game.already_fired(self.turn, r, c):
            await interaction.response.send_message("You've already fired there.", ephemeral=True)
            return

        result = self.game.fire(self.turn, r, c)
        self.pending_row = None
        self.pending_col = None
        self.update_fire_button()

        if self.game.is_winner(self.turn):
            for item in self.children:
                item.disabled = True
            embed = self.build_embed(
                f"🎉 {self.current_player().mention} sank the whole fleet and wins!"
            )
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
            return

        outcome = "🔥 Hit!" if result == "hit" else "🌊 Miss!"
        self.turn = "p2" if self.turn == "p1" else "p1"
        await interaction.response.edit_message(embed=self.build_embed(outcome), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await safe_edit(self.message, view=self)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class Games(commands.Cog):
    """Fun and interactive mini-games."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="connect4", description="Play Connect Four with another user.")
    @app_commands.describe(opponent="The user you want to challenge.")
    async def connect4(self, interaction: discord.Interaction, opponent: discord.Member):
        if opponent.bot:
            await interaction.response.send_message("You can't play against a bot.", ephemeral=True)
            return
        if opponent.id == interaction.user.id:
            await interaction.response.send_message("You can't play against yourself.", ephemeral=True)
            return

        view = Connect4View(player1=interaction.user, player2=opponent)
        await interaction.response.send_message(embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="rps", description="Rock Paper Scissors battle.")
    @app_commands.describe(opponent="The user you want to challenge.")
    async def rps(self, interaction: discord.Interaction, opponent: discord.Member):
        if opponent.bot:
            await interaction.response.send_message("You can't play against a bot.", ephemeral=True)
            return
        if opponent.id == interaction.user.id:
            await interaction.response.send_message("You can't play against yourself.", ephemeral=True)
            return

        view = RPSView(player1=interaction.user, player2=opponent)
        await interaction.response.send_message(embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="battleship", description="Guess and destroy the opponent's ships.")
    @app_commands.describe(opponent="The user you want to challenge.")
    async def battleship(self, interaction: discord.Interaction, opponent: discord.Member):
        if opponent.bot:
            await interaction.response.send_message("You can't play against a bot.", ephemeral=True)
            return
        if opponent.id == interaction.user.id:
            await interaction.response.send_message("You can't play against yourself.", ephemeral=True)
            return

        view = BattleshipView(player1=interaction.user, player2=opponent)
        await interaction.response.send_message(embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
