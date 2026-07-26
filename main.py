import asyncio
import logging

import discord
from discord.ext import commands

import config
from database import Database

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("econobot")

COGS = [
    "cogs.social",
    "cogs.rewards",
    "cogs.work",
    "cogs.bank",
    "cogs.gambling",
    "cogs.pets",
    "cogs.prestige",
    "cogs.events",
]


class EconoBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False
        super().__init__(command_prefix="!disabled!", intents=intents)
        self.db = Database()

    async def setup_hook(self):
        await self.db.connect()
        log.info("Database connected at %s", self.db.path)

        for cog in COGS:
            await self.load_extension(cog)
            log.info("Loaded extension %s", cog)

        synced = await self.tree.sync()
        log.info("Synced %d application commands", len(synced))

    async def close(self):
        await self.db.close()
        await super().close()


bot = EconoBot()


@bot.event
async def on_ready():
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    import discord as _discord
    from utils.embeds import make_embed

    if isinstance(error, discord.app_commands.MissingPermissions):
        message = "You do not have permission to use this command."
    elif isinstance(error, discord.app_commands.CommandOnCooldown):
        message = "This command is on cooldown."
    else:
        log.exception("Unhandled app command error", exc_info=error)
        message = "Something went wrong running that command."

    embed = make_embed("Error", message)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


def main():
    if not config.TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set. Add it to your .env file or Railway variables.")
    asyncio.run(bot.start(config.TOKEN))


if __name__ == "__main__":
    main()
