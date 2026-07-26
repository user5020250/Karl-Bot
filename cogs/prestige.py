import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import make_embed, money
from utils.economy import tier_cost, track_activity


class PrestigeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    @app_commands.command(name="prestige", description="Prestige for permanent bonuses")
    async def prestige_cmd(self, interaction: discord.Interaction):
        user = await self.db.get_user(interaction.user.id)

        if user["prestige"] >= config.PRESTIGE_MAX_LEVEL:
            await interaction.response.send_message(embed=make_embed("Error", f"You have reached the maximum prestige level (`{config.PRESTIGE_MAX_LEVEL}`)."), ephemeral=True)
            return

        cost = tier_cost(user["prestige"])
        net_worth = user["balance"] + user["bank"]
        if net_worth < cost:
            await interaction.response.send_message(
                embed=make_embed("Error", f"You need {money(cost)} net worth to prestige. You have {money(net_worth)}."),
                ephemeral=True,
            )
            return

        # Deduct cost from cash first, then bank.
        remaining_cost = cost
        take_from_balance = min(user["balance"], remaining_cost)
        remaining_cost -= take_from_balance
        take_from_bank = min(user["bank"], remaining_cost)

        await self.db.add_bank(interaction.user.id, -take_from_bank)

        # Balance always resets to 0 on prestige (whatever wasn't spent on the
        # cost is lost); bank keeps whatever remains; level is never touched.
        await self.db.set_field(interaction.user.id, "balance", 0)

        new_prestige = user["prestige"] + 1
        new_title = f"Prestige {new_prestige}"
        await self.db.set_field(interaction.user.id, "prestige", new_prestige)
        await self.db.unlock_title(interaction.user.id, new_title)
        await self.db.set_field(interaction.user.id, "title", new_title)
        await self.db.add_bank_capacity(interaction.user.id, config.BANK_CAPACITY_PRESTIGE_INCREASE)

        leveled_up = await track_activity(self.db, interaction.user.id)

        bonus_pct = new_prestige * config.PRESTIGE_INCOME_BONUS_PER_LEVEL * 100
        desc = (
            f"You are now **Prestige {new_prestige}**.\n"
            f"Permanent income bonus: `+{bonus_pct:.0f}%`\n"
            f"Bank capacity increased by {money(config.BANK_CAPACITY_PRESTIGE_INCREASE)}.\n"
            f"Your balance has been reset (your bank and level are unaffected).\n"
            f"New title unlocked: **{new_title}**"
        )
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("Prestige Complete", desc)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(PrestigeCog(bot))
