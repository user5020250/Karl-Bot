import asyncio
import operator
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

BLACK = discord.Color.from_str("#000000")

# ---------------------------------------------------------------------------
# Word banks / data
# ---------------------------------------------------------------------------
HANGMAN_WORDS = [
    "python", "discord", "keyboard", "server", "moderator", "developer",
    "elephant", "mountain", "guitar", "sunshine", "backpack", "internet",
]

WORDLE_WORDS = [
    "apple", "bread", "chair", "dream", "eagle", "flame", "grape",
    "house", "input", "juice", "knife", "lemon", "mango", "night",
]

SCRAMBLE_WORDS = [
    "python", "discord", "gaming", "server", "computer", "keyboard",
    "monitor", "network", "software", "hardware", "internet", "database",
]

TYPING_SENTENCES = [
    "The quick brown fox jumps over the lazy dog.",
    "Discord bots make servers more fun and interactive.",
    "Practice makes perfect when it comes to typing speed.",
    "Never underestimate the power of a well placed semicolon.",
    "Packed with courage, the small kitten explored the yard.",
]

MEMORY_EMOJIS = ["🔴", "🟢", "🔵", "🟡", "🟣", "🟠", "⚪", "⚫"]

MATH_OPS = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
}

HANGMAN_STAGES = [
    "```\n\n\n\n\n\n```",
    "```\n |\n |\n |\n |\n_|_\n```",
    "```\n___\n|\n|\n|\n_|_\n```",
    "```\n___\n|  |\n|\n|\n_|_\n```",
    "```\n___\n|  |\n|  O\n|\n_|_\n```",
    "```\n___\n|  |\n|  O\n| /|\n_|_\n```",
    "```\n___\n|  |\n|  O\n| /|\\\n_|_\n```",
    "```\n___\n|  |\n|  O\n| /|\\\n| / \\\n_|_\n```",
]


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
# /guess - number guessing game
# ---------------------------------------------------------------------------
class GuessModal(discord.ui.Modal, title="Make a Guess"):
    guess = discord.ui.TextInput(label="Your guess (1-100)", max_length=3)

    def __init__(self, view: "GuessView"):
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        await self.view_ref.handle_guess(interaction, self.guess.value)


class GuessView(discord.ui.View):
    def __init__(self, author_id: int, target: int, max_attempts: int = 7):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.target = target
        self.attempts = 0
        self.max_attempts = max_attempts
        self.message: discord.Message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Make a Guess", style=discord.ButtonStyle.primary)
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GuessModal(self))

    async def handle_guess(self, interaction: discord.Interaction, raw: str):
        if not raw.strip().lstrip("-").isdigit():
            await interaction.response.send_message("Enter a whole number.", ephemeral=True)
            return
        value = int(raw.strip())
        self.attempts += 1

        if value == self.target:
            for item in self.children:
                item.disabled = True
            embed = make_embed(
                "Guess the Number",
                f"🎉 Correct! The number was **{self.target}**.\nAttempts: `{self.attempts}`",
            )
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
            return

        if self.attempts >= self.max_attempts:
            for item in self.children:
                item.disabled = True
            embed = make_embed(
                "Guess the Number",
                f"❌ Out of attempts! The number was **{self.target}**.",
            )
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
            return

        hint = "higher 📈" if value < self.target else "lower 📉"
        embed = make_embed(
            "Guess the Number",
            f"`{value}` is not it — try **{hint}**.\nAttempts: `{self.attempts}/{self.max_attempts}`",
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await safe_edit(self.message, view=self)


# ---------------------------------------------------------------------------
# /hangman
# ---------------------------------------------------------------------------
class HangmanModal(discord.ui.Modal, title="Guess a Letter"):
    letter = discord.ui.TextInput(label="Letter", max_length=1)

    def __init__(self, view: "HangmanView"):
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        await self.view_ref.handle_letter(interaction, self.letter.value)


class HangmanView(discord.ui.View):
    def __init__(self, author_id: int, word: str):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.word = word.lower()
        self.guessed: set[str] = set()
        self.wrong = 0
        self.max_wrong = len(HANGMAN_STAGES) - 1
        self.message: discord.Message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return False
        return True

    def display_word(self) -> str:
        return " ".join(c if c in self.guessed else "\\_" for c in self.word)

    def build_embed(self, extra: str = "") -> discord.Embed:
        embed = make_embed("Hangman", HANGMAN_STAGES[min(self.wrong, self.max_wrong)])
        embed.add_field(name="Word", value=self.display_word(), inline=False)
        wrong_letters = ", ".join(sorted(l for l in self.guessed if l not in self.word)) or "None"
        embed.add_field(name="Wrong guesses", value=wrong_letters, inline=False)
        embed.set_footer(text=f"{self.wrong}/{self.max_wrong} wrong guesses")
        if extra:
            embed.add_field(name="\u200b", value=extra, inline=False)
        return embed

    @discord.ui.button(label="Guess a Letter", style=discord.ButtonStyle.primary)
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(HangmanModal(self))

    async def handle_letter(self, interaction: discord.Interaction, raw: str):
        letter = raw.lower().strip()
        if not letter.isalpha() or len(letter) != 1:
            await interaction.response.send_message("Enter a single letter.", ephemeral=True)
            return
        if letter in self.guessed:
            await interaction.response.send_message("Already guessed that letter.", ephemeral=True)
            return

        self.guessed.add(letter)
        if letter not in self.word:
            self.wrong += 1

        won = all(c in self.guessed for c in self.word)
        lost = self.wrong >= self.max_wrong

        if won or lost:
            for item in self.children:
                item.disabled = True
            extra = (
                f"🎉 You won! The word was **{self.word}**."
                if won
                else f"💀 You lost! The word was **{self.word}**."
            )
            await interaction.response.edit_message(embed=self.build_embed(extra), view=self)
            self.stop()
            return

        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await safe_edit(self.message, view=self)


# ---------------------------------------------------------------------------
# /wordle
# ---------------------------------------------------------------------------
class WordleModal(discord.ui.Modal, title="Guess the Word"):
    def __init__(self, view: "WordleView"):
        super().__init__()
        self.view_ref = view
        self.word_input = discord.ui.TextInput(label="5-letter word", max_length=5, min_length=5)
        self.add_item(self.word_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.view_ref.handle_guess(interaction, self.word_input.value)


class WordleView(discord.ui.View):
    def __init__(self, author_id: int, target: str, max_attempts: int = 6):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.target = target.lower()
        self.max_attempts = max_attempts
        self.guesses: list[str] = []
        self.message: discord.Message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return False
        return True

    def score_guess(self, guess: str) -> str:
        result = []
        for i, c in enumerate(guess):
            if c == self.target[i]:
                result.append("🟩")
            elif c in self.target:
                result.append("🟨")
            else:
                result.append("⬜")
        return "".join(result)

    def build_embed(self, extra: str = "") -> discord.Embed:
        lines = [f"{self.score_guess(g)}   `{g.upper()}`" for g in self.guesses]
        description = "\n".join(lines) if lines else "No guesses yet."
        embed = make_embed("Wordle", description)
        embed.set_footer(text=f"{len(self.guesses)}/{self.max_attempts} guesses")
        if extra:
            embed.add_field(name="\u200b", value=extra, inline=False)
        return embed

    @discord.ui.button(label="Guess", style=discord.ButtonStyle.primary)
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WordleModal(self))

    async def handle_guess(self, interaction: discord.Interaction, raw: str):
        guess = raw.lower().strip()
        if len(guess) != 5 or not guess.isalpha():
            await interaction.response.send_message("Enter a valid 5-letter word.", ephemeral=True)
            return

        self.guesses.append(guess)
        won = guess == self.target
        lost = len(self.guesses) >= self.max_attempts

        if won or lost:
            for item in self.children:
                item.disabled = True
            extra = (
                "🎉 You guessed it!"
                if won
                else f"❌ Out of guesses! The word was **{self.target.upper()}**."
            )
            await interaction.response.edit_message(embed=self.build_embed(extra), view=self)
            self.stop()
            return

        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await safe_edit(self.message, view=self)


# ---------------------------------------------------------------------------
# /typingtest
# ---------------------------------------------------------------------------
class TypingModal(discord.ui.Modal, title="Type the Sentence"):
    def __init__(self, view: "TypingView"):
        super().__init__()
        self.view_ref = view
        self.text_input = discord.ui.TextInput(
            label="Type it exactly", style=discord.TextStyle.paragraph, max_length=200
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.view_ref.handle_submission(interaction, self.text_input.value)


class TypingView(discord.ui.View):
    def __init__(self, author_id: int, sentence: str):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.sentence = sentence
        self.start_time: float | None = None
        self.message: discord.Message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Start Typing", style=discord.ButtonStyle.primary)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.start_time = time.monotonic()
        await interaction.response.send_modal(TypingModal(self))

    async def handle_submission(self, interaction: discord.Interaction, typed: str):
        elapsed = max(time.monotonic() - (self.start_time or time.monotonic()), 0.01)
        words = len(self.sentence.split())
        wpm = round((words / elapsed) * 60, 1)
        compare_len = min(len(typed), len(self.sentence)) or 1
        matches = sum(1 for a, b in zip(typed, self.sentence) if a == b)
        accuracy = round((matches / max(len(self.sentence), 1)) * 100, 1)

        for item in self.children:
            item.disabled = True

        embed = make_embed(
            "Typing Test",
            f"**Sentence:** {self.sentence}\n**You typed:** {typed}",
        )
        embed.add_field(name="Time", value=f"{elapsed:.2f}s", inline=True)
        embed.add_field(name="WPM", value=str(wpm), inline=True)
        embed.add_field(name="Accuracy", value=f"{accuracy}%", inline=True)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await safe_edit(self.message, view=self)


# ---------------------------------------------------------------------------
# /memory
# ---------------------------------------------------------------------------
class MemoryModal(discord.ui.Modal, title="Recall the Sequence"):
    def __init__(self, view: "MemoryView"):
        super().__init__()
        self.view_ref = view
        self.answer = discord.ui.TextInput(
            label="Enter emojis in order, space separated", max_length=100
        )
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction):
        await self.view_ref.handle_answer(interaction, self.answer.value)


class MemoryView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.round = 1
        self.sequence: list[str] = []
        self.message: discord.Message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return False
        return True

    def next_sequence(self):
        self.sequence = [random.choice(MEMORY_EMOJIS) for _ in range(self.round + 2)]

    @discord.ui.button(label="Recall", style=discord.ButtonStyle.primary)
    async def recall_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MemoryModal(self))

    async def handle_answer(self, interaction: discord.Interaction, raw: str):
        answer = raw.strip().split()
        if answer == self.sequence:
            self.round += 1
            self.next_sequence()
            embed = make_embed(
                "Memory Challenge",
                f"✅ Correct! Round `{self.round}`.\n\nMemorize: {' '.join(self.sequence)}",
            )
            embed.set_footer(text="The sequence will be hidden shortly.")
            await interaction.response.edit_message(embed=embed, view=self)
            await asyncio.sleep(3)
            hidden = make_embed(
                "Memory Challenge", f"Round `{self.round}` — recall the sequence you saw."
            )
            try:
                await interaction.edit_original_response(embed=hidden, view=self)
            except discord.HTTPException:
                pass
        else:
            for item in self.children:
                item.disabled = True
            embed = make_embed(
                "Memory Challenge",
                f"❌ Wrong! You reached round `{self.round}`.\nCorrect sequence: {' '.join(self.sequence)}",
            )
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await safe_edit(self.message, view=self)


# ---------------------------------------------------------------------------
# /math
# ---------------------------------------------------------------------------
class MathModal(discord.ui.Modal, title="Solve the Problem"):
    def __init__(self, view: "MathView"):
        super().__init__()
        self.view_ref = view
        self.answer = discord.ui.TextInput(label="Answer", max_length=10)
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction):
        await self.view_ref.handle_answer(interaction, self.answer.value)


class MathView(discord.ui.View):
    def __init__(self, author_id: int, expression: str, answer: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.expression = expression
        self.answer_value = answer
        self.start_time = time.monotonic()
        self.message: discord.Message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Answer", style=discord.ButtonStyle.primary)
    async def answer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MathModal(self))

    async def handle_answer(self, interaction: discord.Interaction, raw: str):
        for item in self.children:
            item.disabled = True
        elapsed = time.monotonic() - self.start_time
        try:
            correct = int(raw.strip()) == self.answer_value
        except ValueError:
            correct = False

        if correct:
            embed = make_embed(
                "Math Challenge",
                f"🎉 Correct! `{self.expression} = {self.answer_value}`\nTime: {elapsed:.2f}s",
            )
        else:
            embed = make_embed(
                "Math Challenge",
                f"❌ Wrong! `{self.expression} = {self.answer_value}`, you said `{raw}`.",
            )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await safe_edit(self.message, view=self)


# ---------------------------------------------------------------------------
# /fastclick
# ---------------------------------------------------------------------------
class FastClickView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.armed = False
        self.arm_time: float | None = None
        self.message: discord.Message = None
        self.click.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return False
        return True

    async def arm(self):
        delay = random.uniform(2, 6)
        await asyncio.sleep(delay)
        self.armed = True
        self.arm_time = time.monotonic()
        self.click.disabled = False
        self.click.label = "CLICK NOW!"
        self.click.style = discord.ButtonStyle.success
        await safe_edit(self.message, view=self)

    @discord.ui.button(label="Wait for it...", style=discord.ButtonStyle.secondary)
    async def click(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.armed:
            for item in self.children:
                item.disabled = True
            embed = make_embed("Fast Click", "❌ Too early! You clicked before it was time.")
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
            return

        reaction = time.monotonic() - self.arm_time
        for item in self.children:
            item.disabled = True
        embed = make_embed("Fast Click", f"⚡ Reaction time: `{reaction * 1000:.0f}ms`")
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await safe_edit(self.message, view=self)


# ---------------------------------------------------------------------------
# /scramble
# ---------------------------------------------------------------------------
class ScrambleModal(discord.ui.Modal, title="Unscramble the Word"):
    def __init__(self, view: "ScrambleView"):
        super().__init__()
        self.view_ref = view
        self.answer = discord.ui.TextInput(label="Your answer", max_length=30)
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction):
        await self.view_ref.handle_answer(interaction, self.answer.value)


class ScrambleView(discord.ui.View):
    def __init__(self, author_id: int, word: str, scrambled: str):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.word = word
        self.scrambled = scrambled
        self.attempts = 0
        self.message: discord.Message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Guess", style=discord.ButtonStyle.primary)
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ScrambleModal(self))

    async def handle_answer(self, interaction: discord.Interaction, raw: str):
        self.attempts += 1
        if raw.strip().lower() == self.word:
            for item in self.children:
                item.disabled = True
            embed = make_embed(
                "Scramble",
                f"🎉 Correct! The word was **{self.word}**.\nAttempts: `{self.attempts}`",
            )
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
            return

        embed = make_embed(
            "Scramble",
            f"Scrambled: `{self.scrambled}`\n❌ Not quite, try again.\nAttempts: `{self.attempts}`",
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await safe_edit(self.message, view=self)


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
            f"{self.render_board()}\n\n{self.P1} {self.order[0].mention}  vs  {self.P2} {self.order[1].mention}",
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
            "I'm thinking of a number between **1** and **100**. You have `7` attempts.",
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

    @app_commands.command(name="memory", description="Memory challenge.")
    async def memory(self, interaction: discord.Interaction):
        view = MemoryView(author_id=interaction.user.id)
        view.next_sequence()
        embed = make_embed(
            "Memory Challenge",
            f"Round `1` — memorize this sequence:\n\n{' '.join(view.sequence)}",
        )
        embed.set_footer(text="Click Recall once you're ready to enter it.")
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="math", description="Solve a random math problem.")
    async def math(self, interaction: discord.Interaction):
        a, b = random.randint(1, 50), random.randint(1, 50)
        op = random.choice(list(MATH_OPS.keys()))
        expression = f"{a} {op} {b}"
        answer = MATH_OPS[op](a, b)
        view = MathView(author_id=interaction.user.id, expression=expression, answer=answer)
        embed = make_embed("Math Challenge", f"Solve: `{expression}`\nYou have `60` seconds.")
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="fastclick", description="Click as fast as possible.")
    async def fastclick(self, interaction: discord.Interaction):
        view = FastClickView(author_id=interaction.user.id)
        embed = make_embed(
            "Fast Click",
            "Wait for the button to turn green, then click it as fast as you can!\nClicking too early loses.",
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
        embed = make_embed("Scramble", f"Unscramble this word: `{scrambled}`")
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


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
