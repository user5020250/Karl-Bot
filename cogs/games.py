import asyncio
import operator
import random
import time

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
# /checkers
# ---------------------------------------------------------------------------
class CheckersGame:
    SIZE = 8

    def __init__(self):
        self.board: list[list[str | None]] = [[None] * self.SIZE for _ in range(self.SIZE)]
        for row in range(3):
            for col in range(self.SIZE):
                if (row + col) % 2 == 1:
                    self.board[row][col] = "b"
        for row in range(5, 8):
            for col in range(self.SIZE):
                if (row + col) % 2 == 1:
                    self.board[row][col] = "r"

    def in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.SIZE and 0 <= c < self.SIZE

    def is_king(self, piece: str) -> bool:
        return piece is not None and piece.isupper()

    def owner(self, piece: str | None) -> str | None:
        if piece is None:
            return None
        return "black" if piece.lower() == "b" else "red"

    def directions_for(self, piece: str) -> list[tuple[int, int]]:
        if self.is_king(piece):
            return [(1, -1), (1, 1), (-1, -1), (-1, 1)]
        return [(1, -1), (1, 1)] if piece.lower() == "b" else [(-1, -1), (-1, 1)]

    def simple_moves(self, r: int, c: int) -> list[tuple[int, int]]:
        piece = self.board[r][c]
        moves = []
        for dr, dc in self.directions_for(piece):
            nr, nc = r + dr, c + dc
            if self.in_bounds(nr, nc) and self.board[nr][nc] is None:
                moves.append((nr, nc))
        return moves

    def capture_moves(self, r: int, c: int) -> list[tuple[int, int, int, int]]:
        piece = self.board[r][c]
        moves = []
        for dr, dc in self.directions_for(piece):
            mr, mc = r + dr, c + dc
            jr, jc = r + 2 * dr, c + 2 * dc
            if (
                self.in_bounds(jr, jc)
                and self.board[jr][jc] is None
                and self.in_bounds(mr, mc)
                and self.board[mr][mc] is not None
                and self.owner(self.board[mr][mc]) != self.owner(piece)
            ):
                moves.append((jr, jc, mr, mc))
        return moves

    def player_pieces(self, color: str) -> list[tuple[int, int]]:
        return [
            (r, c)
            for r in range(self.SIZE)
            for c in range(self.SIZE)
            if self.board[r][c] is not None and self.owner(self.board[r][c]) == color
        ]

    def any_captures(self, color: str) -> bool:
        return any(self.capture_moves(r, c) for r, c in self.player_pieces(color))

    def movable_pieces(self, color: str) -> list[tuple[int, int]]:
        must_capture = self.any_captures(color)
        result = []
        for r, c in self.player_pieces(color):
            if must_capture:
                if self.capture_moves(r, c):
                    result.append((r, c))
            elif self.simple_moves(r, c):
                result.append((r, c))
        return result

    def legal_destinations(self, r: int, c: int) -> list[tuple[int, int, int | None, int | None]]:
        captures = self.capture_moves(r, c)
        if captures:
            return [(jr, jc, mr, mc) for jr, jc, mr, mc in captures]
        return [(nr, nc, None, None) for nr, nc in self.simple_moves(r, c)]

    def move(self, r: int, c: int, dest_r: int, dest_c: int) -> tuple[int, int] | None:
        piece = self.board[r][c]
        self.board[r][c] = None
        captured = None
        if abs(dest_r - r) == 2:
            mid_r, mid_c = (r + dest_r) // 2, (c + dest_c) // 2
            captured = (mid_r, mid_c)
            self.board[mid_r][mid_c] = None
        if piece == "b" and dest_r == self.SIZE - 1:
            piece = "B"
        elif piece == "r" and dest_r == 0:
            piece = "R"
        self.board[dest_r][dest_c] = piece
        return captured

    def winner(self) -> str | None:
        if not self.player_pieces("black") or not self.movable_pieces("black"):
            return "red"
        if not self.player_pieces("red") or not self.movable_pieces("red"):
            return "black"
        return None

    def render(self) -> str:
        keycaps = ["0\u20e3", "1\u20e3", "2\u20e3", "3\u20e3", "4\u20e3", "5\u20e3", "6\u20e3", "7\u20e3"]
        symbol = {"b": "⚫", "B": "🔵", "r": "🔴", "R": "🟡"}
        header = "⬛" + "".join(keycaps)
        lines = [header]
        for r in range(self.SIZE):
            row_cells = [keycaps[r]]
            for c in range(self.SIZE):
                if (r + c) % 2 == 0:
                    row_cells.append("⬜")
                else:
                    piece = self.board[r][c]
                    row_cells.append(symbol.get(piece, "⬛"))
            lines.append("".join(row_cells))
        return "\n".join(lines)


class CheckersPieceSelect(discord.ui.Select):
    def __init__(self, view: "CheckersView"):
        pieces = view.game.movable_pieces(view.turn)
        options = [
            discord.SelectOption(label=f"Piece at row {r}, col {c}", value=f"{r}{c}")
            for r, c in pieces
        ] or [discord.SelectOption(label="No moves available", value="none")]
        super().__init__(placeholder="Select a piece to move", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        view: "CheckersView" = self.view
        if self.values[0] == "none":
            await interaction.response.send_message("No legal moves for that piece.", ephemeral=True)
            return
        r, c = int(self.values[0][0]), int(self.values[0][1])
        await view.select_piece(interaction, r, c)


class CheckersDestSelect(discord.ui.Select):
    def __init__(self, view: "CheckersView", origin, destinations):
        self.origin = origin
        self.dest_map = {}
        options = []
        for dr, dc, cr, cc in destinations:
            key = f"{dr}{dc}"
            self.dest_map[key] = (dr, dc)
            label = f"Move to row {dr}, col {dc}" + (" (capture)" if cr is not None else "")
            options.append(discord.SelectOption(label=label, value=key))
        super().__init__(placeholder="Select a destination", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        view: "CheckersView" = self.view
        dest = self.dest_map[self.values[0]]
        await view.select_destination(interaction, self.origin, dest)


class CheckersView(discord.ui.View):
    def __init__(self, black_player: discord.abc.User, red_player: discord.abc.User):
        super().__init__(timeout=600)
        self.game = CheckersGame()
        self.players = {"black": black_player, "red": red_player}
        self.turn = "black"
        self.message: discord.Message = None
        self.rebuild_piece_select()

    def current_player(self) -> discord.abc.User:
        return self.players[self.turn]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.current_player().id:
            await interaction.response.send_message("It's not your turn.", ephemeral=True)
            return False
        return True

    def rebuild_piece_select(self):
        self.clear_items()
        self.add_item(CheckersPieceSelect(self))

    def rebuild_dest_select(self, origin, destinations):
        self.clear_items()
        self.add_item(CheckersDestSelect(self, origin, destinations))

    def build_embed(self, extra: str = "") -> discord.Embed:
        black, red = self.players["black"], self.players["red"]
        embed = make_embed(
            "Checkers",
            f"{self.game.render()}\n\n"
            f"⚫ {black.mention}   vs   🔴 {red.mention}\n\n"
            "**How to play:** pick one of your pieces from the first dropdown, then pick a "
            "destination from the second dropdown. Captures are mandatory when available — jump "
            "over an adjacent enemy piece to remove it. Reach the far row to promote to a king "
            "(🔵/🟡), which can move in any diagonal direction.",
        )
        color_emoji = "⚫" if self.turn == "black" else "🔴"
        embed.set_footer(text=f"It's {self.current_player().display_name}'s turn ({color_emoji})")
        if extra:
            embed.add_field(name="\u200b", value=extra, inline=False)
        return embed

    async def select_piece(self, interaction: discord.Interaction, r: int, c: int):
        destinations = self.game.legal_destinations(r, c)
        self.rebuild_dest_select((r, c), destinations)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def select_destination(self, interaction: discord.Interaction, origin, dest):
        r, c = origin
        dr, dc = dest
        captured = self.game.move(r, c, dr, dc)

        if captured is not None and self.game.capture_moves(dr, dc):
            self.rebuild_dest_select((dr, dc), self.game.legal_destinations(dr, dc))
            await interaction.response.edit_message(
                embed=self.build_embed("Capture again with the same piece!"), view=self
            )
            return

        winner = self.game.winner()
        if winner:
            for item in self.children:
                item.disabled = True
            embed = self.build_embed(f"🎉 {self.players[winner].mention} wins!")
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
            return

        self.turn = "red" if self.turn == "black" else "black"
        self.rebuild_piece_select()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await safe_edit(self.message, view=self)


# ---------------------------------------------------------------------------
# /chess (requires the third-party "chess" package: pip install chess)
# ---------------------------------------------------------------------------
class ChessModal(discord.ui.Modal, title="Make a Move"):
    def __init__(self, view: "ChessView"):
        super().__init__()
        self.view_ref = view
        self.move_input = discord.ui.TextInput(
            label="Move (e.g. e4, Nf3, O-O, or e2e4)", max_length=10
        )
        self.add_item(self.move_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.view_ref.handle_move(interaction, self.move_input.value)


class ChessView(discord.ui.View):
    def __init__(self, white_player: discord.abc.User, black_player: discord.abc.User):
        super().__init__(timeout=1800)
        self.board = chess.Board()
        self.players = {chess.WHITE: white_player, chess.BLACK: black_player}
        self.message: discord.Message = None

    def current_player(self) -> discord.abc.User:
        return self.players[self.board.turn]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.current_player().id:
            await interaction.response.send_message("It's not your turn.", ephemeral=True)
            return False
        return True

    def build_embed(self, extra: str = "") -> discord.Embed:
        board_text = self.board.unicode(borders=False, invert_color=False)
        white, black = self.players[chess.WHITE], self.players[chess.BLACK]
        embed = make_embed(
            "Chess",
            f"```\n{board_text}\n```\n"
            f"⚪ {white.mention}   vs   ⚫ {black.mention}\n\n"
            "**How to play:** click **Make a Move** and enter a move in standard algebraic "
            "notation (e.g. `e4`, `Nf3`, `O-O` for kingside castling) or coordinate form "
            "(e.g. `e2e4`).",
        )
        turn_name = "White" if self.board.turn == chess.WHITE else "Black"
        embed.set_footer(text=f"It's {self.current_player().display_name}'s turn ({turn_name})")
        if self.board.is_check() and not self.board.is_checkmate():
            embed.add_field(name="\u200b", value="⚠️ Check!", inline=False)
        if extra:
            embed.add_field(name="\u200b", value=extra, inline=False)
        return embed

    @discord.ui.button(label="Make a Move", style=discord.ButtonStyle.primary)
    async def move_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ChessModal(self))

    async def handle_move(self, interaction: discord.Interaction, raw: str):
        text = raw.strip()
        move = None
        try:
            move = self.board.parse_san(text)
        except ValueError:
            try:
                candidate = chess.Move.from_uci(text.lower())
                if candidate in self.board.legal_moves:
                    move = candidate
            except ValueError:
                move = None

        if move is None:
            await interaction.response.send_message(
                "That's not a legal move. Try algebraic notation like `e4` or `Nf3`, "
                "or coordinate form like `e2e4`.",
                ephemeral=True,
            )
            return

        mover = self.current_player()
        self.board.push(move)

        if self.board.is_checkmate():
            for item in self.children:
                item.disabled = True
            embed = self.build_embed(f"🎉 Checkmate! {mover.mention} wins!")
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
            return

        if (
            self.board.is_stalemate()
            or self.board.is_insufficient_material()
            or self.board.is_seventyfive_moves()
        ):
            for item in self.children:
                item.disabled = True
            embed = self.build_embed("🤝 The game is a draw.")
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
            return

        await interaction.response.edit_message(embed=self.build_embed(), view=self)

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

    @app_commands.command(name="guess", description="Guess the hidden number.")
    async def guess(self, interaction: discord.Interaction):
        target = random.randint(1, 100)
        view = GuessView(author_id=interaction.user.id, target=target)
        embed = make_embed(
            "Guess the Number",
            "I'm thinking of a number between **1** and **100**.\n\n"
            "**How to play:** click **Make a Guess**, type a number, and submit. "
            "I'll tell you if the answer is **higher** or **lower** so you can narrow it down.\n\n"
            "You have `7` attempts.",
        )
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="hangman", description="Guess the hidden word.")
    async def hangman(self, interaction: discord.Interaction):
        word = random.choice(HANGMAN_WORDS)
        view = HangmanView(author_id=interaction.user.id, word=word)
        await interaction.response.send_message(embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="wordle", description="Play Wordle.")
    async def wordle(self, interaction: discord.Interaction):
        word = random.choice(WORDLE_WORDS)
        view = WordleView(author_id=interaction.user.id, target=word)
        await interaction.response.send_message(embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="typingtest", description="Test typing speed.")
    async def typingtest(self, interaction: discord.Interaction):
        sentence = random.choice(TYPING_SENTENCES)
        view = TypingView(author_id=interaction.user.id, sentence=sentence)
        embed = make_embed(
            "Typing Test",
            f"Click **Start Typing** when ready, then type this sentence:\n\n> {sentence}",
        )
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="math", description="Solve a random math problem.")
    async def math(self, interaction: discord.Interaction):
        a, b = random.randint(1, 50), random.randint(1, 50)
        op = random.choice(list(MATH_OPS.keys()))
        expression = f"{a} {op} {b}"
        answer = MATH_OPS[op](a, b)
        view = MathView(author_id=interaction.user.id, expression=expression, answer=answer)
        embed = make_embed(
            "Math Challenge",
            f"Solve: `{expression}`\n\nClick **Answer** and type the result as a whole number. "
            "You have `60` seconds.",
        )
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="fastclick", description="Click as fast as possible.")
    async def fastclick(self, interaction: discord.Interaction):
        view = FastClickView(author_id=interaction.user.id)
        embed = make_embed(
            "Fast Click",
            "The button below says **Wait for it...** — don't click it yet!\n"
            "After a random delay it will turn green and say **CLICK NOW!** — click it as fast as you can. "
            "Clicking before it turns green loses instantly.",
        )
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()
        self.bot.loop.create_task(view.arm())

    @app_commands.command(name="scramble", description="Unscramble a word.")
    async def scramble(self, interaction: discord.Interaction):
        word = random.choice(SCRAMBLE_WORDS)
        letters = list(word)
        scrambled = word
        while scrambled == word:
            random.shuffle(letters)
            scrambled = "".join(letters)
        view = ScrambleView(author_id=interaction.user.id, word=word, scrambled=scrambled)
        embed = make_embed(
            "Scramble",
            f"Unscramble this word: `{scrambled}`\n\n"
            f"It's `{len(word)}` letters long. Click **Guess** and type your answer.",
        )
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

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

    @app_commands.command(name="checkers", description="Play checkers against another player.")
    @app_commands.describe(opponent="The user you want to challenge.")
    async def checkers(self, interaction: discord.Interaction, opponent: discord.Member):
        if opponent.bot:
            await interaction.response.send_message("You can't play against a bot.", ephemeral=True)
            return
        if opponent.id == interaction.user.id:
            await interaction.response.send_message("You can't play against yourself.", ephemeral=True)
            return

        view = CheckersView(black_player=interaction.user, red_player=opponent)
        await interaction.response.send_message(embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="chess", description="Play chess against another player.")
    @app_commands.describe(opponent="The user you want to challenge.")
    async def chess_command(self, interaction: discord.Interaction, opponent: discord.Member):
        if chess is None:
            await interaction.response.send_message(
                "Chess support requires the `chess` package to be installed on the bot "
                "(`pip install chess`).",
                ephemeral=True,
            )
            return
        if opponent.bot:
            await interaction.response.send_message("You can't play against a bot.", ephemeral=True)
            return
        if opponent.id == interaction.user.id:
            await interaction.response.send_message("You can't play against yourself.", ephemeral=True)
            return

        view = ChessView(white_player=interaction.user, black_player=opponent)
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
