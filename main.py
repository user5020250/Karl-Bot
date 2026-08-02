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
CLEAR_GUILD_COMMANDS = os.getenv("CLEAR_GUILD_COMMANDS", "false").lower() == "true"

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
    "cogs.logs",
]


class ModBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=PREFIX, intents=intents, help_command=None)
        self._synced = False

    async def setup_hook(self):
        for extension in EXTENSIONS:
            try:
                await self.load_extension(extension)
                log.info("Loaded extension: %s", extension)
            except Exception:
                log.exception("Failed to load extension: %s", extension)

        # Global sync only — this bot registers commands globally.
        # Per-server behavior comes from each command reading/writing
        # settings keyed by guild_id, not from guild-scoped command sync.
        synced = await self.tree.sync()
        log.info("Synced %d application commands (global)", len(synced))

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="the server")
        )

        # One-time cleanup: clears any leftover guild-scoped command
        # registrations left over from earlier testing, which is what
        # causes commands to show up twice in a given server. Only runs
        # when CLEAR_GUILD_COMMANDS=true is set, and only once per process.
        if CLEAR_GUILD_COMMANDS and not self._synced:
            self._synced = True
            for guild in self.guilds:
                try:
                    self.tree.clear_commands(guild=guild)
                    await self.tree.sync(guild=guild)
                    log.info("Cleared stale guild commands for %s (%s)", guild.name, guild.id)
                except discord.HTTPException:
                    log.exception("Failed clearing guild commands for %s", guild.id)
            log.info("Guild command cleanup complete. You can unset CLEAR_GUILD_COMMANDS now.")


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
