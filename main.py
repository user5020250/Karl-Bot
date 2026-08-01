import logging
import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("BOT_PREFIX", "!")
GUILD_ID = os.getenv("GUILD_ID")  # set this in Railway variables, or hardcode below

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

EXTENSIONS = [
    "cogs.moderation",
    "cogs.messages",
    "cogs.channels",
    "cogs.voice",
    "cogs.roles",
    "cogs.automod",
    "cogs.server",
    "cogs.modlogs",
    "cogs.utility",
    "cogs.info",
    "cogs.afk",
    "cogs.jail",
    "cogs.help",
    "cogs.social",
    "cogs.games",
]


class ModBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=PREFIX, intents=intents, help_command=None)

    async def setup_hook(self):
        for extension in EXTENSIONS:
            try:
                await self.load_extension(extension)
                log.info("Loaded extension: %s", extension)
            except Exception:
                log.exception("Failed to load extension: %s", extension)

        synced = await self.tree.sync()
        log.info("Synced %d application commands", len(synced))

        # Guild-scoped sync so command changes apply instantly instead of
        # waiting on Discord's global propagation delay (up to ~1 hour).
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            synced_guild = await self.tree.sync(guild=guild)
            log.info("Guild-synced %d commands instantly to %s", len(synced_guild), GUILD_ID)
        else:
            log.warning("GUILD_ID not set — skipping instant guild sync")

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="the server")
        )


bot = ModBot()


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        message = "You do not have permission to use this command."
    elif isinstance(error, app_commands.BotMissingPermissions):
        message = "I am missing the permissions required to do that."
    elif isinstance(error, app_commands.CommandOnCooldown):
        message = str(error)
    else:
        log.exception("Unhandled app command error", exc_info=error)
        message = "Something went wrong while running that command."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN is not set. Set it in your .env file locally, "
            "or in the Railway project's Variables tab when deployed."
        )
    bot.run(TOKEN)
