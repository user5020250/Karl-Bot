import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

log = logging.getLogger("serverstats-bot")

CATEGORY_NAME = "📊 Server Stats"
UPDATE_INTERVAL_MINUTES = 10  # Discord rate-limits channel renames to
                              # ~2 per 10 min per channel, so don't go lower
                              # than ~5 min on larger servers.


def format_number(n: int) -> str:
    return f"{n:,}"


class ServerStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.refresh_loop.start()

    def cog_unload(self):
        self.refresh_loop.cancel()

    # ---------- stat computation ----------

    @staticmethod
    def compute_stats(guild: discord.Guild) -> dict[str, str]:
        members = guild.members
        total_members = guild.member_count or len(members)
        bots = sum(1 for m in members if m.bot)

        # status is only populated if the presences intent is enabled
        # and the guild has been fully chunked/cached.
        online = sum(
            1
            for m in members
            if not m.bot and m.status != discord.Status.offline
        )

        boosts = guild.premium_subscription_count or 0
        boost_level = int(guild.premium_tier or 0)

        in_voice = 0
        streaming = 0
        live = 0
        for vc in guild.voice_channels:
            for member in vc.members:
                in_voice += 1
                vstate = member.voice
                if vstate is None:
                    continue
                if vstate.self_stream:
                    streaming += 1
                if vstate.self_video:
                    live += 1

        return {
            "Members": format_number(total_members),
            "Online": format_number(online),
            "Bots": format_number(bots),
            "Boosts": format_number(boosts),
            "Boost Level": str(boost_level),
            "In Voice": format_number(in_voice),
            "Streaming": format_number(streaming),
            "Live": format_number(live),
        }

    # ---------- channel creation / update ----------

    @staticmethod
    def locked_overwrites(guild: discord.Guild) -> dict:
        everyone = guild.default_role
        return {
            everyone: discord.PermissionOverwrite(
                view_channel=True,
                connect=False,
                manage_channels=False,
                manage_roles=False,
            )
        }

    async def sync_guild_stats(self, guild: discord.Guild):
        # Make sure the member cache is populated (needed for accurate
        # counts even outside the initial on_ready chunking).
        if guild.large and not guild.chunked:
            await guild.chunk()

        stats = self.compute_stats(guild)

        category = discord.utils.get(
            guild.categories, name=CATEGORY_NAME
        )
        overwrites = self.locked_overwrites(guild)

        if category is None:
            category = await guild.create_category(
                CATEGORY_NAME, overwrites=overwrites
            )

        existing = {
            c.name.split(":")[0]: c
            for c in category.voice_channels
        }

        for label, value in stats.items():
            channel_name = f"{label}: {value}"
            channel = existing.get(label)
            if channel is not None:
                if channel.name != channel_name:
                    await channel.edit(name=channel_name)
            else:
                await guild.create_voice_channel(
                    channel_name, category=category, overwrites=overwrites
                )

    # ---------- background refresh ----------

    @tasks.loop(minutes=UPDATE_INTERVAL_MINUTES)
    async def refresh_loop(self):
        for guild in self.bot.guilds:
            try:
                # Only refresh guilds that already have the stats category,
                # so we don't touch servers that never ran /serverstats.
                if discord.utils.get(guild.categories, name=CATEGORY_NAME):
                    await self.sync_guild_stats(guild)
            except discord.Forbidden:
                log.warning(f"Missing permissions in guild {guild.id}")
            except Exception:
                log.exception(f"Failed to refresh stats for guild {guild.id}")

    @refresh_loop.before_loop
    async def before_refresh_loop(self):
        await self.bot.wait_until_ready()

    # ---------- slash command ----------

    @app_commands.command(
        name="serverstats",
        description="Create or refresh a locked category of live server statistic channels.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def serverstats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(
                "This command must be run inside a server."
            )
            return

        try:
            await self.sync_guild_stats(guild)
            await interaction.followup.send(
                f"✅ Server stats channels created/updated. "
                f"They'll auto-refresh every {UPDATE_INTERVAL_MINUTES} minutes."
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I'm missing permissions. Make sure I have **Manage Channels**."
            )
        except Exception:
            log.exception("serverstats command failed")
            await interaction.followup.send(
                "❌ Something went wrong creating the stat channels."
            )

    @serverstats.error
    async def serverstats_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You need **Manage Server** permission to use this.",
                ephemeral=True,
            )
        elif isinstance(error, app_commands.BotMissingPermissions):
            await interaction.response.send_message(
                "I need **Manage Channels** permission to do this.",
                ephemeral=True,
            )
        else:
            log.exception("Unhandled serverstats error", exc_info=error)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStats(bot))
