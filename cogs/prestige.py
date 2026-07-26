import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import make_embed, money
from utils.economy import tier_cost, track_activity


class PrestigeGroup(app_commands.Group):
    def __init__(self, cog: "PrestigeCog"):
        super().__init__(name="prestige", description="Prestige system")
        self.cog = cog

    @app_commands.command(name="info", description="View prestige information")
    async def info(self, interaction: discord.Interaction):
        db = self.cog.db
        user = await db.get_user(interaction.user.id)

        current = user["prestige"]
        max_level = config.PRESTIGE_MAX_LEVEL
        cost = tier_cost(current)
        income_bonus = current * config.PRESTIGE_INCOME_BONUS_PER_LEVEL * 100

        if current >= max_level:
            status = "You have reached the maximum prestige level."
        elif user["balance"] >= cost:
            status = "You are eligible to prestige."
        else:
            status = "You do not have enough cash to prestige."

        embed = make_embed(
            "Prestige Information",
            (
                f"Current Prestige: `{current}/{max_level}`\n"
                f"Current Income Bonus: `+{income_bonus:.0f}%`\n\n"
                f"Next Prestige Cost: {money(cost)}\n"
                f"Bank Capacity Reward: +{money(config.BANK_CAPACITY_PRESTIGE_INCREASE)}\n"
                f"Income Bonus After Prestige: `+{income_bonus + (config.PRESTIGE_INCOME_BONUS_PER_LEVEL * 100):.0f}%`\n\n"
                f"Status: {status}"
            ),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="up", description="Prestige for permanent bonuses")
    async def up(self, interaction: discord.Interaction):
        user = await self.cog.db.get_user(interaction.user.id)

        if user["prestige"] >= config.PRESTIGE_MAX_LEVEL:
            await interaction.response.send_message(
                embed=make_embed("Error", f"You have reached the maximum prestige level (`{config.PRESTIGE_MAX_LEVEL}`)."),
                ephemeral=True,
            )
            return

        cost = tier_cost(user["prestige"])
        if user["balance"] < cost:
            await interaction.response.send_message(
                embed=make_embed(
                    "Error",
                    f"You need {money(cost)} in cash to prestige. You have {money(user['balance'])} in cash. "
                    f"Withdraw from your bank with `/withdraw` if you need more.",
                ),
                ephemeral=True,
            )
            return

        await self.cog.db.set_field(interaction.user.id, "balance", 0)

        new_prestige = user["prestige"] + 1
        new_title = f"Prestige {new_prestige}"

        await self.cog.db.set_field(interaction.user.id, "prestige", new_prestige)
        await self.cog.db.unlock_title(interaction.user.id, new_title)
        await self.cog.db.set_field(interaction.user.id, "title", new_title)
        await self.cog.db.add_bank_capacity(
            interaction.user.id,
            config.BANK_CAPACITY_PRESTIGE_INCREASE,
        )

        leveled_up = await track_activity(self.cog.db, interaction.user.id)

        bonus_pct = new_prestige * config.PRESTIGE_INCOME_BONUS_PER_LEVEL * 100

        desc = (
            f"You are now **Prestige {new_prestige}**.\n"
            f"Permanent income bonus: `+{bonus_pct:.0f}%`\n"
            f"Bank capacity increased by {money(config.BANK_CAPACITY_PRESTIGE_INCREASE)}.\n"
            f"Your balance has been reset (your bank and level are untouched).\n"
            f"New title unlocked: **{new_title}**"
        )

        if leveled_up:
            desc += "\nYou leveled up!"

        await interaction.response.send_message(
            embed=make_embed("Prestige Complete", desc)
        )


class PrestigeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

        self.prestige_group = PrestigeGroup(self)
        bot.tree.add_command(self.prestige_group)


async def setup(bot: commands.Bot):
    await bot.add_cog(PrestigeCog(bot))
