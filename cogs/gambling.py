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
    "colorgame": "Color Game",
    "tongits": "Tongits",
    "sabong": "Sabong",
}


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
        won = random.random() < 0.5

        if won:
            await self.db.add_balance(interaction.user.id, amount)
            await self.db.increment_field(interaction.user.id, "gambling_won", amount)
            await self.db.record_gamble(interaction.user.id, game_key, amount, 0)
            desc = f"You won! You gained {money(amount)}."
        else:
            await self.db.add_balance(interaction.user.id, -amount)
            await self.db.increment_field(interaction.user.id, "gambling_lost", amount)
            await self.db.record_gamble(interaction.user.id, game_key, 0, amount)
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

    @app_commands.command(name="scatter", description="Bet on a 50/50 chance")
    @app_commands.describe(bet="Amount to bet, e.g. 1000, 1k, 2.5m, or 'all'")
    async def scatter_cmd(self, interaction: discord.Interaction, bet: str):
        await self._gamble(interaction, "scatter", bet)

    @app_commands.command(name="colorgame", description="Bet on a 50/50 chance")
    @app_commands.describe(bet="Amount to bet, e.g. 1000, 1k, 2.5m, or 'all'")
    async def colorgame_cmd(self, interaction: discord.Interaction, bet: str):
        await self._gamble(interaction, "colorgame", bet)

    @app_commands.command(name="tongits", description="Bet on a 50/50 chance")
    @app_commands.describe(bet="Amount to bet, e.g. 1000, 1k, 2.5m, or 'all'")
    async def tongits_cmd(self, interaction: discord.Interaction, bet: str):
        await self._gamble(interaction, "tongits", bet)

    @app_commands.command(name="sabong", description="Bet on a 50/50 chance")
    @app_commands.describe(bet="Amount to bet, e.g. 1000, 1k, 2.5m, or 'all'")
    async def sabong_cmd(self, interaction: discord.Interaction, bet: str):
        await self._gamble(interaction, "sabong", bet)


async def setup(bot: commands.Bot):
    await bot.add_cog(GamblingCog(bot))
