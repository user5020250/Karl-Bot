import random
import discord
from discord import app_commands
from discord.ext import commands
import config
from utils.embeds import make_embed, money
from utils.parsing import parse_amount, AmountParseError
from utils.economy import track_activity
from utils.achievements import check_and_award, mark_bankrupt_if_needed

GAME_NAMES = {
    "scatter": "Scatter",
}

# Win chance per game. Kept separate from GAME_NAMES and never surfaced in any
# command description so players can't just read the odds off of /scatter etc.
GAME_WIN_CHANCE = {
    "scatter": 0.50,
}

# Reel symbols for /777. Winning the jackpot requires all three reels to land
# on the last symbol (7). Odds: (1/7)^3 = 1 in 343 per spin (~0.29%).
JACKPOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "🔔", "⭐", "7️⃣"]
JACKPOT_WINNING_SYMBOL = JACKPOT_SYMBOLS[-1]


class GamblingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    async def _gamble(self, interaction: discord.Interaction, game_key: str, bet: str):
        user = await self.db.get_user(interaction.user.id)
        try:
            amount = parse_amount(bet, available=user["balance"])
        except AmountParseError as e:
            await interaction.response.send_message(embed=make_embed("Error", str(e)), ephemeral=True)
            return
        if amount < config.GAMBLING_MIN_BET:
            await interaction.response.send_message(
                embed=make_embed("Error", f"Minimum bet is {money(config.GAMBLING_MIN_BET)}."), ephemeral=True
            )
            return
        if amount > user["balance"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not have enough cash on hand."), ephemeral=True)
            return
        game_name = GAME_NAMES[game_key]
        await self.db.increment_field(interaction.user.id, "gambling_count", 1)
        won = random.random() < GAME_WIN_CHANCE[game_key]
        if won:
            await self.db.add_balance(interaction.user.id, amount)
            await self.db.increment_field(interaction.user.id, "gambling_won", amount)
            await self.db.record_gamble(interaction.user.id, game_key, amount, 0)
            desc = f"You won! You gained {money(amount)}."
        else:
            await self.db.add_balance(interaction.user.id, -amount)
            await self.db.increment_field(interaction.user.id, "gambling_lost", amount)
            await self.db.record_gamble(interaction.user.id, game_key, 0, amount)
            await self.db.add_to_jackpot(amount)
            await mark_bankrupt_if_needed(self.db, interaction.user.id)
            desc = f"You lost. You lost {money(amount)}."
        leveled_up = await track_activity(self.db, interaction.user.id)
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed(game_name, desc)
        await interaction.response.send_message(embed=embed)
        newly = await check_and_award(self.db, interaction.user.id, {"gamble_won": won})
        for ach in newly:
            await interaction.followup.send(embed=make_embed("Achievement Unlocked", f"**{ach['name']}** - {ach['description']}"))

    @app_commands.command(name="scatter", description="Try your luck at Scatter")
    @app_commands.describe(bet="Amount to bet, e.g. 1000, 1k, 2.5m, or 'all'")
    async def scatter_cmd(self, interaction: discord.Interaction, bet: str):
        await self._gamble(interaction, "scatter", bet)

    @app_commands.command(name="777", description="Spin for the jackpot - hit all 7s to win the whole pool")
    @app_commands.describe(bet="Amount to bet, e.g. 1000, 1k, 2.5m, or 'all'")
    async def jackpot_spin_cmd(self, interaction: discord.Interaction, bet: str):
        user = await self.db.get_user(interaction.user.id)
        try:
            amount = parse_amount(bet, available=user["balance"])
        except AmountParseError as e:
            await interaction.response.send_message(embed=make_embed("Error", str(e)), ephemeral=True)
            return
        if amount < config.GAMBLING_MIN_BET:
            await interaction.response.send_message(
                embed=make_embed("Error", f"Minimum bet is {money(config.GAMBLING_MIN_BET)}."), ephemeral=True
            )
            return
        if amount > user["balance"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not have enough cash on hand."), ephemeral=True)
            return

        await self.db.increment_field(interaction.user.id, "gambling_count", 1)
        await self.db.add_balance(interaction.user.id, -amount)
        await self.db.add_to_jackpot(amount)

        reels = [random.choice(JACKPOT_SYMBOLS) for _ in range(3)]
        reel_display = " ".join(reels)
        hit_jackpot = all(r == JACKPOT_WINNING_SYMBOL for r in reels)

        if hit_jackpot:
            winnings = await self.db.take_jackpot()
            await self.db.add_balance(interaction.user.id, winnings)
            await self.db.increment_field(interaction.user.id, "gambling_won", winnings)
            await self.db.record_gamble(interaction.user.id, "777", winnings, 0)
            desc = f"{reel_display}\n\n**JACKPOT!** You won the entire pool: {money(winnings)}!"
            won = True
        else:
            await self.db.increment_field(interaction.user.id, "gambling_lost", amount)
            await self.db.record_gamble(interaction.user.id, "777", 0, amount)
            await mark_bankrupt_if_needed(self.db, interaction.user.id)
            pool = await self.db.get_jackpot()
            desc = f"{reel_display}\n\nNo jackpot this time. You lost {money(amount)}.\nCurrent pool: {money(pool)}"
            won = False

        leveled_up = await track_activity(self.db, interaction.user.id)
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("777", desc)
        await interaction.response.send_message(embed=embed)

        newly = await check_and_award(self.db, interaction.user.id, {"gamble_won": won})
        for ach in newly:
            await interaction.followup.send(embed=make_embed("Achievement Unlocked", f"**{ach['name']}** - {ach['description']}"))

    @app_commands.command(name="jackpot", description="Check the current jackpot pool")
    async def jackpot_check_cmd(self, interaction: discord.Interaction):
        pool = await self.db.get_jackpot()
        await interaction.response.send_message(
            embed=make_embed("Jackpot", f"The current jackpot pool is {money(pool)}.\nTry `/777` to go for it.")
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(GamblingCog(bot))
