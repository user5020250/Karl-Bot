import time
import random
import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import make_embed, money, format_seconds, progress_bar
from utils.checks import check_cooldown
from utils.achievements import ACHIEVEMENTS, ACHIEVEMENTS_BY_KEY, check_and_award, mark_bankrupt_if_needed
from utils.economy import bank_capacity_for, exp_progress, track_activity
from utils.parsing import parse_amount, AmountParseError

try:
    from cogs.gambling import GAME_NAMES
except Exception:  # pragma: no cover - gambling cog should always be present
    GAME_NAMES = {}


# ---------------------------------------------------------------------------
# /profile "Cooldowns" grouping - mirrors the /help categories so the two
# stay visually consistent. Only commands that actually have a cooldown
# (i.e. appear in config.COOLDOWNS) end up shown; anything with a cooldown
# that isn't listed here falls into "Other" automatically.
# ---------------------------------------------------------------------------
COOLDOWN_CATEGORIES = {
    "Rewards": ["daily", "weekly", "monthly", "yearly"],
    "Work & Side Hustles": ["work", "overtime", "beg", "cook", "fish", "farm", "harvest"],
    "Bank": ["interest"],
    "Pets": ["feed"],
    "Social": ["rob"],
}


# ---------------------------------------------------------------------------
# /help dropdown
# ---------------------------------------------------------------------------
HELP_CATEGORIES = {
    "Social": [
        ("/help", "Show all commands"),
        ("/profile", "View your profile (includes cooldowns, achievements, gambling, pets)"),
        ("/leaderboard", "Show the richest players"),
        ("/achievements", "Show the list of achievements"),
        ("/balance", "View your balance"),
        ("/give", "Give money to another player"),
        ("/rob", "Attempt to steal money from another player"),
    ],
    "Rewards": [
        ("/daily", "Claim your daily reward"),
        ("/weekly", "Claim your weekly reward"),
        ("/monthly", "Claim your monthly reward"),
        ("/yearly", "Claim your yearly reward"),
    ],
    "Work & Side Hustles": [
        ("/jobs", "Show the list of jobs and stock"),
        ("/job apply", "Apply for a job (required before using /work)"),
        ("/job resign", "Resign from your job"),
        ("/work", "Earn money working your job"),
        ("/overtime", "Earn more money working overtime"),
        ("/beg", "Beg for money"),
        ("/cook", "Earn money cooking"),
        ("/fish", "Earn money fishing"),
        ("/farm", "Earn money farming"),
        ("/harvest", "Earn money harvesting"),
    ],
    "Bank": [
        ("/deposit", "Deposit cash into your bank"),
        ("/withdraw", "Withdraw cash from your bank"),
        ("/interest", "Claim your daily bank interest"),
        ("/bank upg", "Upgrade your bank capacity"),
        ("/bank info", "View your bank information"),
    ],
    "Gambling": [
        ("/scatter", "Try your luck at Scatter"),
        ("/777", "Spin for the jackpot - hit all 7s to win the whole pool"),
        ("/jackpot", "Check the current jackpot pool"),
    ],
    "Pets": [
        ("/petshop", "Show the pet shop"),
        ("/adopt", "Adopt a pet (give it a species and a name)"),
        ("/pet rename", "Rename a pet"),
        ("/pet disowned", "Abandon a pet"),
        ("/feed", "Feed a pet"),
        ("/play", "Play with a pet"),
        ("/pet race challeneg", "Challene another player to a pet race"),
        ("/pet race accept", "Accept a pending race challenge"),
        ("/pet race decline", "Decline a pending race challenge"),
        ("/pet race cancel", "Cancel a race challenge you sent"),
    ],
    "Prestige": [
        ("/prestige up", "Prestige for permanent bonuses (costs money only)"),
        ("/prestige info", "View prestige information"),
    ],
    "Events": [
        ("/event setchannel", "Set the channel for random events"),
        ("/claim", "Claim an active event reward"),
    ],
}


class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=cat, description=f"View {cat} commands")
            for cat in HELP_CATEGORIES
        ]
        super().__init__(placeholder="Select a category", options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        commands_list = HELP_CATEGORIES[category]
        description = "\n".join(f"**{name}** - {desc}" for name, desc in commands_list)
        embed = make_embed(category, description)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(HelpSelect())


# ---------------------------------------------------------------------------
# /profile dropdown
# ---------------------------------------------------------------------------
class ProfileSelect(discord.ui.Select):
    def __init__(self, cog: "SocialCog", target: discord.User):
        self.cog = cog
        self.target = target
        options = [
            discord.SelectOption(label="Main", description="Level, balance, commands used, pet, title"),
            discord.SelectOption(label="Pets", description="All pets you own and their IDs"),
            discord.SelectOption(label="Cooldowns", description="Every command with a cooldown and its status"),
            discord.SelectOption(label="Achievements", description="All achievements you've unlocked"),
            discord.SelectOption(label="Gambling", description="Per-game gambling earnings and stats"),
        ]
        super().__init__(placeholder="Select a category", options=options)

    async def callback(self, interaction: discord.Interaction):
        embed = await self.cog.build_profile_embed(self.values[0], self.target)
        await interaction.response.edit_message(embed=embed, view=self.view)


class ProfileView(discord.ui.View):
    def __init__(self, cog: "SocialCog", target: discord.User):
        super().__init__(timeout=120)
        self.add_item(ProfileSelect(cog, target))


class SocialCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    # -- /help ---------------------------------------------------------------
    @app_commands.command(name="help", description="Show all commands")
    async def help_cmd(self, interaction: discord.Interaction):
        await track_activity(self.db, interaction.user.id)
        embed = make_embed("Help", "Select a category below to view its commands.")
        await interaction.response.send_message(embed=embed, view=HelpView())

    # -- /profile --------------------------------------------------------------
    async def build_profile_embed(self, section: str, target: discord.User) -> discord.Embed:
        user = await self.db.get_user(target.id)

        if section == "Main":
            pets = await self.db.get_pets(target.id)
            pet_text = f"{len(pets)} owned" if pets else "None"
            level, into_level, needed, fraction = exp_progress(user["exp"])
            embed = make_embed(f"{target.display_name}'s Profile - Main")
            embed.add_field(name="Level", value=f"`{level}`", inline=True)
            embed.add_field(
                name="Balance",
                value=f"{money(user['balance'])} (Bank: {money(user['bank'])} / {money(bank_capacity_for(user))})",
                inline=True,
            )
            embed.add_field(name="Total Commands Used", value=f"`{user['total_commands']}`", inline=True)
            embed.add_field(name="Pets Owned", value=f"`{pet_text}`", inline=True)
            embed.add_field(name="Title", value=f"`{user['title'] or 'None'}`", inline=True)
            embed.add_field(name="Prestige", value=f"`{user['prestige']}`", inline=True)
            embed.add_field(
                name=f"EXP Progress (Level {level} -> {level + 1})",
                value=f"{progress_bar(fraction)} ({into_level:,}/{needed:,} exp)",
                inline=False,
            )
            return embed

        if section == "Pets":
            pets = await self.db.get_pets(target.id, alive_only=False)
            embed = make_embed(f"{target.display_name}'s Profile - Pets")
            if not pets:
                embed.description = "No pets owned. Use `/adopt` to get one."
            else:
                lines = []
                for p in pets:
                    status = "Alive" if p["alive"] else "Deceased"
                    lines.append(
                        f"**ID {p['pet_id']}** - {p['species']} \"{p['name'] or 'Unnamed'}\" "
                        f"- Level `{p['level']}` - `{status}`"
                    )
                embed.description = "\n".join(lines)
            return embed

        if section == "Cooldowns":
            rows = {r["command"]: r["expires_at"] for r in await self.db.get_all_cooldowns(target.id)}
            embed = make_embed(f"{target.display_name}'s Profile - Cooldowns")
            now = time.time()

            def status_for(command_name: str) -> str:
                expires_at = rows.get(command_name)
                if expires_at and expires_at > now:
                    return f"`{format_seconds(expires_at - now)}` remaining"
                return "`Ready`"

            categorized = set()
            blocks = []
            for category, command_names in COOLDOWN_CATEGORIES.items():
                present = [c for c in command_names if c in config.COOLDOWNS]
                if not present:
                    continue
                categorized.update(present)
                lines = [f"**/{c}** - {status_for(c)}" for c in present]
                blocks.append(f"**{category}**\n" + "\n".join(lines))

            leftover = [c for c in sorted(config.COOLDOWNS) if c not in categorized]
            if leftover:
                lines = [f"**/{c}** - {status_for(c)}" for c in leftover]
                blocks.append("**Other**\n" + "\n".join(lines))

            embed.description = "\n\n".join(blocks)
            return embed

        if section == "Achievements":
            unlocked = await self.db.get_unlocked_achievements(target.id)
            embed = make_embed(f"{target.display_name}'s Profile - Achievements")
            embed.add_field(name="Total Achievements", value=f"`{len(ACHIEVEMENTS)}`", inline=True)
            embed.add_field(name="Unlocked", value=f"`{len(unlocked)}`", inline=True)
            if not unlocked:
                embed.description = "No achievements unlocked yet."
            else:
                lines = []
                for key in unlocked:
                    ach = ACHIEVEMENTS_BY_KEY.get(key)
                    if not ach:
                        continue
                    lines.append(f"**{ach['name']}** - {ach['description']}")
                embed.description = "\n".join(lines)
            return embed

        if section == "Gambling":
            embed = make_embed(f"{target.display_name}'s Profile - Gambling")
            embed.add_field(name="Total Amount Earned", value=money(user["gambling_won"]), inline=True)
            embed.add_field(name="Total Amount Lost", value=money(user["gambling_lost"]), inline=True)
            embed.add_field(name="Total Gambling Commands Used", value=f"`{user['gambling_count']}`", inline=True)

            stats_by_game = {r["game"]: r for r in await self.db.get_gambling_stats(target.id)}
            lines = []
            for game_key in ("scatter", "777"):
                name = GAME_NAMES.get(game_key, "777 Jackpot" if game_key == "777" else game_key.capitalize())
                stat = stats_by_game.get(game_key)
                won = stat["won"] if stat else 0
                lost = stat["lost"] if stat else 0
                count = stat["count"] if stat else 0
                lines.append(f"**/{game_key}** ({name}) - Earned: {money(won)} - Lost: {money(lost)} - Used: `{count}`")
            embed.add_field(name="Per-Game Breakdown", value="\n".join(lines), inline=False)
            return embed

        return make_embed("Profile", "Unknown section.")

    @app_commands.command(name="profile", description="View a profile")
    @app_commands.describe(user="Whose profile to view (defaults to you)")
    async def profile_cmd(self, interaction: discord.Interaction, user: discord.User = None):
        target = user or interaction.user
        await self.db.ensure_user(target.id)
        await track_activity(self.db, interaction.user.id)
        embed = await self.build_profile_embed("Main", target)
        await interaction.response.send_message(embed=embed, view=ProfileView(self, target))

    # -- /leaderboard ------------------------------------------------------
    @app_commands.command(name="leaderboard", description="Show the richest players")
    async def leaderboard_cmd(self, interaction: discord.Interaction):
        await track_activity(self.db, interaction.user.id)
        rows = await self.db.get_leaderboard(10)
        if not rows:
            embed = make_embed("Leaderboard", "No players yet.")
            await interaction.response.send_message(embed=embed)
            return

        lines = []
        for i, row in enumerate(rows, start=1):
            member = interaction.guild.get_member(row["user_id"]) if interaction.guild else None
            name = member.display_name if member else f"User {row['user_id']}"
            lines.append(f"**{i}. {name}** - {money(row['net'])}")

        embed = make_embed("Leaderboard - Richest Players", "\n".join(lines))
        await interaction.response.send_message(embed=embed)

    # -- /achievements -----------------------------------------------------
    @app_commands.command(name="achievements", description="Show the list of achievements")
    async def achievements_cmd(self, interaction: discord.Interaction):
        await track_activity(self.db, interaction.user.id)
        unlocked = set(await self.db.get_unlocked_achievements(interaction.user.id))
        lines = []
        for ach in ACHIEVEMENTS:
            if ach["secret"] and ach["key"] not in unlocked:
                continue
            status = "Unlocked" if ach["key"] in unlocked else "Locked"
            lines.append(f"**{ach['name']}** - {ach['description']} (`{status}`)")
        embed = make_embed("Achievements", "\n".join(lines))
        await interaction.response.send_message(embed=embed)

    # -- /balance ------------------------------------------------------------
    @app_commands.command(name="balance", description="View your balance")
    @app_commands.describe(user="Whose balance to view (defaults to you)")
    async def balance_cmd(self, interaction: discord.Interaction, user: discord.User = None):
        target = user or interaction.user
        await track_activity(self.db, interaction.user.id)
        u = await self.db.get_user(target.id)
        embed = make_embed(f"{target.display_name}'s Balance")
        embed.add_field(name="Cash", value=money(u["balance"]), inline=True)
        embed.add_field(name="Bank", value=f"{money(u['bank'])} / {money(bank_capacity_for(u))}", inline=True)
        embed.add_field(name="Net Worth", value=money(u["balance"] + u["bank"]), inline=True)
        await interaction.response.send_message(embed=embed)

    # -- /give ---------------------------------------------------------------
    @app_commands.command(name="give", description="Give money to another player")
    @app_commands.describe(user="Who to give money to", amount="Amount to give, e.g. 1000, 1k, 2.5m, or 'all'")
    async def give_cmd(self, interaction: discord.Interaction, user: discord.User, amount: str):
        if user.id == interaction.user.id:
            await interaction.response.send_message(embed=make_embed("Error", "You cannot give money to yourself."), ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message(embed=make_embed("Error", "You cannot give money to a bot."), ephemeral=True)
            return

        sender = await self.db.get_user(interaction.user.id)

        try:
            value = parse_amount(amount, available=sender["balance"])
        except AmountParseError as e:
            await interaction.response.send_message(embed=make_embed("Error", str(e)), ephemeral=True)
            return

        if value > sender["balance"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not have enough cash on hand."), ephemeral=True)
            return

        await self.db.add_balance(interaction.user.id, -value)
        await self.db.add_balance(user.id, value)
        await mark_bankrupt_if_needed(self.db, interaction.user.id)
        leveled_up = await track_activity(self.db, interaction.user.id)

        desc = f"You gave {money(value)} to **{user.display_name}**."
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("Transfer Complete", desc)
        await interaction.response.send_message(embed=embed)

    # -- /rob ------------------------------------------------------------------
    @app_commands.command(name="rob", description="Attempt to steal money from another player")
    @app_commands.describe(user="Who to rob")
    async def rob_cmd(self, interaction: discord.Interaction, user: discord.User):
        if user.id == interaction.user.id or user.bot:
            await interaction.response.send_message(embed=make_embed("Error", "Invalid target."), ephemeral=True)
            return
        if not await check_cooldown(interaction, self.db, "rob", config.COOLDOWNS["rob"]):
            return

        target_user = await self.db.get_user(user.id)
        if target_user["balance"] < config.ROB_MIN_TARGET_BALANCE:
            leveled_up = await track_activity(self.db, interaction.user.id)
            desc = f"**{user.display_name}** doesn't have enough cash on hand to rob."
            if leveled_up:
                desc += "\nYou leveled up!"
            embed = make_embed("Rob Failed", desc)
            await interaction.response.send_message(embed=embed)
            return

        success = random.random() < config.ROB_SUCCESS_CHANCE
        if success:
            percent = random.uniform(*config.ROB_STEAL_PERCENT)
            stolen = max(1, round(target_user["balance"] * percent))
            await self.db.add_balance(user.id, -stolen)
            await self.db.earn(interaction.user.id, stolen)
            await mark_bankrupt_if_needed(self.db, user.id)
            desc = f"You stole {money(stolen)} from **{user.display_name}**."
        else:
            penalty = round(config.ROB_MIN_TARGET_BALANCE * random.uniform(0.5, 1.0))
            robber = await self.db.get_user(interaction.user.id)
            penalty = min(penalty, robber["balance"])
            await self.db.add_balance(interaction.user.id, -penalty)
            desc = f"You got caught and paid a fine of {money(penalty)}."

        leveled_up = await track_activity(self.db, interaction.user.id)
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("Rob Successful" if success else "Rob Failed", desc)

        await interaction.response.send_message(embed=embed)
        newly = await check_and_award(self.db, interaction.user.id)
        for ach in newly:
            await interaction.followup.send(embed=make_embed("Achievement Unlocked", f"**{ach['name']}** - {ach['description']}"))


async def setup(bot: commands.Bot):
    await bot.add_cog(SocialCog(bot))
