import time
import json
import os
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from utils.embeds import make_embed, money
from utils.checks import check_cooldown
from utils.economy import roll, apply_prestige_bonus, track_activity
from utils.achievements import check_and_award

_JOBS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.json")
with open(_JOBS_PATH, "r", encoding="utf-8") as f:
    JOB_DEFS = json.load(f)
JOB_DEFS_BY_KEY = {j["key"]: j for j in JOB_DEFS}


class JobGroup(app_commands.Group):
    """Named 'job' (not 'work') since Discord does not allow a command to be
    both a standalone command (/work) and a group with subcommands at once."""

    def __init__(self, cog: "WorkCog"):
        super().__init__(name="job", description="Manage your job")
        self.cog = cog

    @app_commands.command(name="apply", description="Apply for a job")
    @app_commands.describe(job="The job to apply for")
    async def apply(self, interaction: discord.Interaction, job: str):
        job = job.lower()
        if job not in JOB_DEFS_BY_KEY:
            await interaction.response.send_message(embed=make_embed("Error", "That job does not exist. Use `/jobs` to see the list."), ephemeral=True)
            return

        user = await self.cog.db.get_user(interaction.user.id)
        if user["job"]:
            await interaction.response.send_message(embed=make_embed("Error", f"You already work as **{JOB_DEFS_BY_KEY[user['job']]['name']}**. Resign first with `/job resign`."), ephemeral=True)
            return

        job_row = await self.cog.db.get_job(job)
        if not job_row or job_row["stock"] <= 0:
            await interaction.response.send_message(embed=make_embed("Error", "This job has no open positions right now."), ephemeral=True)
            return

        await self.cog.db.set_job_stock(job, job_row["stock"] - 1, job_row["next_refresh"])
        await self.cog.db.set_field(interaction.user.id, "job", job)
        leveled_up = await track_activity(self.cog.db, interaction.user.id)

        desc = f"You are now working as **{JOB_DEFS_BY_KEY[job]['name']}**. Use `/work` to start earning."
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("Job Application Approved", desc)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="resign", description="Resign from your job")
    async def resign(self, interaction: discord.Interaction):
        user = await self.cog.db.get_user(interaction.user.id)
        if not user["job"]:
            await interaction.response.send_message(embed=make_embed("Error", "You are not currently employed."), ephemeral=True)
            return

        job_row = await self.cog.db.get_job(user["job"])
        job_name = JOB_DEFS_BY_KEY[user["job"]]["name"]
        if job_row:
            await self.cog.db.set_job_stock(user["job"], job_row["stock"] + 1, job_row["next_refresh"])
        await self.cog.db.set_field(interaction.user.id, "job", None)
        leveled_up = await track_activity(self.cog.db, interaction.user.id)

        desc = f"You have resigned from **{job_name}**."
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("Resigned", desc)
        await interaction.response.send_message(embed=embed)


class WorkCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.job_group = JobGroup(self)
        bot.tree.add_command(self.job_group)
        self.refresh_job_stock.start()

    def cog_unload(self):
        self.refresh_job_stock.cancel()

    @tasks.loop(seconds=60)
    async def refresh_job_stock(self):
        await self.bot.wait_until_ready()
        now = time.time()
        for job in JOB_DEFS:
            row = await self.db.get_job(job["key"])
            if row is None:
                await self.db.upsert_job(
                    job["key"], job["name"], job["pay_min"], job["pay_max"],
                    job["max_stock"], job["max_stock"], now + config.JOB_STOCK_REFRESH_SECONDS,
                )
            elif row["next_refresh"] <= now:
                await self.db.set_job_stock(job["key"], job["max_stock"], now + config.JOB_STOCK_REFRESH_SECONDS)

    async def _do_income(self, interaction: discord.Interaction, command_name: str, reward_range):
        if not await check_cooldown(interaction, self.db, command_name, config.COOLDOWNS[command_name]):
            return

        user = await self.db.get_user(interaction.user.id)
        amount = apply_prestige_bonus(user, roll(reward_range))
        await self.db.earn(interaction.user.id, amount)
        leveled_up = await track_activity(self.db, interaction.user.id)

        if command_name == "work":
            await self.db.increment_field(interaction.user.id, "work_count", 1)

        desc = f"You earned {money(amount)}."
        if leveled_up:
            desc += "\nYou leveled up!"

        embed = make_embed(command_name.capitalize(), desc)
        await interaction.response.send_message(embed=embed)

        newly = await check_and_award(self.db, interaction.user.id)
        for ach in newly:
            await interaction.followup.send(embed=make_embed("Achievement Unlocked", f"**{ach['name']}** - {ach['description']}"))

    @app_commands.command(name="jobs", description="Show the list of jobs")
    async def jobs_cmd(self, interaction: discord.Interaction):
        await track_activity(self.db, interaction.user.id)
        lines = []
        for job in JOB_DEFS:
            row = await self.db.get_job(job["key"])
            stock = row["stock"] if row else job["max_stock"]
            status = f"`Available ({stock}/{job['max_stock']})`" if stock > 0 else "`Unavailable`"
            lines.append(
                f"**{job['name']}** (`{job['key']}`) - {money(job['pay_min'])} to {money(job['pay_max'])} - {status}"
            )
        embed = make_embed("Jobs", "\n".join(lines), footer="Stock refreshes every 30 minutes")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="work", description="Earn money working your job")
    async def work_cmd(self, interaction: discord.Interaction):
        user = await self.db.get_user(interaction.user.id)
        if not user["job"] or user["job"] not in JOB_DEFS_BY_KEY:
            await interaction.response.send_message(
                embed=make_embed("Error", "You need a job before you can `/work`. Apply with `/job apply`."),
                ephemeral=True,
            )
            return
        job = JOB_DEFS_BY_KEY[user["job"]]
        reward_range = (job["pay_min"], job["pay_max"])
        await self._do_income(interaction, "work", reward_range)

    @app_commands.command(name="overtime", description="Earn more money working overtime")
    async def overtime_cmd(self, interaction: discord.Interaction):
        await self._do_income(interaction, "overtime", config.OVERTIME_REWARD)

    @app_commands.command(name="beg", description="Beg for money")
    async def beg_cmd(self, interaction: discord.Interaction):
        await self._do_income(interaction, "beg", config.BEG_REWARD)

    @app_commands.command(name="cook", description="Earn money cooking")
    async def cook_cmd(self, interaction: discord.Interaction):
        await self._do_income(interaction, "cook", config.COOK_REWARD)

    @app_commands.command(name="fish", description="Earn money fishing")
    async def fish_cmd(self, interaction: discord.Interaction):
        await self._do_income(interaction, "fish", config.FISH_REWARD)

    @app_commands.command(name="farm", description="Earn money farming")
    async def farm_cmd(self, interaction: discord.Interaction):
        await self._do_income(interaction, "farm", config.FARM_REWARD)

    @app_commands.command(name="harvest", description="Earn money harvesting")
    async def harvest_cmd(self, interaction: discord.Interaction):
        await self._do_income(interaction, "harvest", config.HARVEST_REWARD)


async def setup(bot: commands.Bot):
    await bot.add_cog(WorkCog(bot))
