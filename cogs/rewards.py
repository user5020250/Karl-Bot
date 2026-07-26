import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import make_embed, money
from utils.checks import check_cooldown
from utils.economy import roll, apply_prestige_bonus, track_activity
from utils.achievements import check_and_award


class RewardsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    async def _reward(self, interaction: discord.Interaction, name: str, reward_range):
        if not await check_cooldown(interaction, self.db, name, config.COOLDOWNS[name]):
            return

        user = await self.db.get_user(interaction.user.id)
        amount = apply_prestige_bonus(user, roll(reward_range))
        await self.db.earn(interaction.user.id, amount)
        leveled_up = await track_activity(self.db, interaction.user.id)

        desc = f"You claimed your {name} reward of {money(amount)}."
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed(f"{name.capitalize()} Reward", desc)
        await interaction.response.send_message(embed=embed)

        newly = await check_and_award(self.db, interaction.user.id)
        for ach in newly:
            await interaction.followup.send(embed=make_embed("Achievement Unlocked", f"**{ach['name']}** - {ach['description']}"))

    @app_commands.command(name="daily", description="Claim your daily reward")
    async def daily_cmd(self, interaction: discord.Interaction):
        await self._reward(interaction, "daily", config.DAILY_REWARD)

    @app_commands.command(name="weekly", description="Claim your weekly reward")
    async def weekly_cmd(self, interaction: discord.Interaction):
        await self._reward(interaction, "weekly", config.WEEKLY_REWARD)

    @app_commands.command(name="monthly", description="Claim your monthly reward")
    async def monthly_cmd(self, interaction: discord.Interaction):
        await self._reward(interaction, "monthly", config.MONTHLY_REWARD)

    @app_commands.command(name="yearly", description="Claim your yearly reward")
    async def yearly_cmd(self, interaction: discord.Interaction):
        await self._reward(interaction, "yearly", config.YEARLY_REWARD)


async def setup(bot: commands.Bot):
    await bot.add_cog(RewardsCog(bot))
