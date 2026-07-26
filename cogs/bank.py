import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import make_embed, money
from utils.checks import check_cooldown
from utils.economy import bank_capacity_for, tier_cost, track_activity
from utils.parsing import parse_amount, AmountParseError
from utils.achievements import check_and_award


class BankGroup(app_commands.Group):
    def __init__(self, cog: "BankCog"):
        super().__init__(name="bank", description="Manage your bank capacity")
        self.cog = cog

    # ------------------------------
    # /bank info
    # ------------------------------
    @app_commands.command(name="info", description="View your bank information")
    async def info(self, interaction: discord.Interaction):
        db = self.cog.db
        user = await db.get_user(interaction.user.id)

        capacity = bank_capacity_for(user)
        next_capacity = capacity + config.BANK_UPG_CAPACITY_INCREASE
        upgrade_cost = tier_cost(user["prestige"])

        embed = make_embed(
            "Bank Information",
            (
                f"Current Bank Balance: {money(user['bank'])}\n"
                f"Current Capacity: {money(capacity)}\n"
                f"Available Space: {money(capacity - user['bank'])}\n\n"
                f"Next Upgrade Cost: {money(upgrade_cost)}\n"
                f"Capacity Increase: {money(config.BANK_UPG_CAPACITY_INCREASE)}\n"
                f"New Capacity: {money(next_capacity)}"
            ),
        )

        await interaction.response.send_message(embed=embed)

    # ------------------------------
    # /bank upg
    # ------------------------------
    @app_commands.command(name="upg", description="Upgrade your bank capacity")
    async def upg(self, interaction: discord.Interaction):
        db = self.cog.db
        user = await db.get_user(interaction.user.id)
        cost = tier_cost(user["prestige"])
        net_worth = user["balance"] + user["bank"]

        if net_worth < cost:
            await interaction.response.send_message(
                embed=make_embed("Error", f"You need {money(cost)} net worth to upgrade your bank. You have {money(net_worth)}."),
                ephemeral=True,
            )
            return

        remaining_cost = cost
        take_from_balance = min(user["balance"], remaining_cost)
        remaining_cost -= take_from_balance
        take_from_bank = min(user["bank"], remaining_cost)

        await db.add_balance(interaction.user.id, -take_from_balance)
        await db.add_bank(interaction.user.id, -take_from_bank)
        await db.add_bank_capacity(interaction.user.id, config.BANK_UPG_CAPACITY_INCREASE)

        leveled_up = await track_activity(db, interaction.user.id)
        new_capacity = bank_capacity_for(user) + config.BANK_UPG_CAPACITY_INCREASE

        desc = (
            f"Paid {money(cost)} to upgrade your bank.\n"
            f"New bank capacity: {money(new_capacity)}"
        )
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("Bank Upgraded", desc)
        await interaction.response.send_message(embed=embed)


class BankCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.bank_group = BankGroup(self)
        bot.tree.add_command(self.bank_group)

    @app_commands.command(name="deposit", description="Deposit cash into your bank")
    @app_commands.describe(amount="Amount to deposit, e.g. 1000, 1k, 2.5m, or 'all'")
    async def deposit_cmd(self, interaction: discord.Interaction, amount: str):
        user = await self.db.get_user(interaction.user.id)

        try:
            value = parse_amount(amount, available=user["balance"])
        except AmountParseError as e:
            await interaction.response.send_message(embed=make_embed("Error", str(e)), ephemeral=True)
            return

        if value > user["balance"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not have that much cash on hand."), ephemeral=True)
            return

        capacity = bank_capacity_for(user)
        room = capacity - user["bank"]
        if room <= 0:
            await interaction.response.send_message(
                embed=make_embed("Error", f"Your bank is full (capacity {money(capacity)}). Use `/bank upg` to increase it."),
                ephemeral=True,
            )
            return

        if value > room:
            await interaction.response.send_message(
                embed=make_embed(
                    "Error",
                    f"Your bank only has room for {money(room)} more (capacity {money(capacity)}). "
                    f"Use `/bank upg` to increase it.",
                ),
                ephemeral=True,
            )
            return

        await self.db.add_balance(interaction.user.id, -value)
        await self.db.add_bank(interaction.user.id, value)
        leveled_up = await track_activity(self.db, interaction.user.id)

        desc = f"You deposited {money(value)} into your bank."
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("Deposit Successful", desc)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="withdraw", description="Withdraw cash from your bank")
    @app_commands.describe(amount="Amount to withdraw, e.g. 1000, 1k, 2.5m, or 'all'")
    async def withdraw_cmd(self, interaction: discord.Interaction, amount: str):
        user = await self.db.get_user(interaction.user.id)

        try:
            value = parse_amount(amount, available=user["bank"])
        except AmountParseError as e:
            await interaction.response.send_message(embed=make_embed("Error", str(e)), ephemeral=True)
            return

        if value > user["bank"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not have that much money in the bank."), ephemeral=True)
            return

        await self.db.add_bank(interaction.user.id, -value)
        await self.db.add_balance(interaction.user.id, value)
        leveled_up = await track_activity(self.db, interaction.user.id)

        desc = f"You withdrew {money(value)} from your bank."
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("Withdraw Successful", desc)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="interest", description="Claim your daily bank interest")
    async def interest_cmd(self, interaction: discord.Interaction):
        if not await check_cooldown(interaction, self.db, "interest", config.COOLDOWNS["interest"]):
            return

        user = await self.db.get_user(interaction.user.id)
        gained = round(user["bank"] * config.BANK_DAILY_INTEREST_RATE)

        leveled_up = await track_activity(self.db, interaction.user.id)

        if gained <= 0:
            desc = "You have no money in the bank to earn interest on."
            if leveled_up:
                desc += "\nYou leveled up!"
            embed = make_embed("Interest", desc)
            await interaction.response.send_message(embed=embed)
            return

        await self.db.add_bank(interaction.user.id, gained)
        desc = f"You earned {money(gained)} in bank interest."
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("Interest Claimed", desc)
        await interaction.response.send_message(embed=embed)

        newly = await check_and_award(self.db, interaction.user.id)
        for ach in newly:
            await interaction.followup.send(embed=make_embed("Achievement Unlocked", f"**{ach['name']}** - {ach['description']}"))


async def setup(bot: commands.Bot):
    await bot.add_cog(BankCog(bot))
