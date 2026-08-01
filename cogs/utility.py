import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed
from storage import storage

BLACK = discord.Color.from_str("#000000")


class Utility(commands.Cog):
    """Utility commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==========================================================
    # Helpers
    # ==========================================================

    async def send_success(
        self,
        interaction: discord.Interaction,
        message: str
    ):
        await interaction.response.send_message(
            embed=make_embed(
                "Success",
                message
            ),
            ephemeral=True
        )

    async def send_error(
        self,
        interaction: discord.Interaction,
        message: str
    ):
        await interaction.response.send_message(
            embed=make_embed(
                "Error",
                message
            ),
            ephemeral=True
        )

    # ==========================================================
    # /say
    # ==========================================================

    @app_commands.command(
        name="say",
        description="Send a message as the bot."
    )
    @app_commands.describe(
        message="Message to send.",
        channel="Channel to send it in."
    )
    @app_commands.checks.has_permissions(
        manage_messages=True
    )
    async def say(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: discord.TextChannel | None = None
    ):

        channel = channel or interaction.channel

        await channel.send(message)

        await self.send_success(
            interaction,
            f"Message sent in {channel.mention}."
        )

    # ==========================================================
    # /embed
    # ==========================================================

    @app_commands.command(
        name="embed",
        description="Send a custom embed."
    )
    @app_commands.describe(
        title="Embed title",
        description="Embed description",
        channel="Channel"
    )
    @app_commands.checks.has_permissions(
        manage_messages=True
    )
    async def embed(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        channel: discord.TextChannel | None = None
    ):

        channel = channel or interaction.channel

        await channel.send(
            embed=make_embed(
                title,
                description
            )
        )

        await self.send_success(
            interaction,
            f"Embed sent in {channel.mention}."
        )

    # ==========================================================
    # /announce
    # ==========================================================

    @app_commands.command(
        name="announce",
        description="Send an announcement."
    )
    @app_commands.describe(
        message="Announcement text",
        channel="Target channel",
        mention_everyone="Mention everyone"
    )
    @app_commands.checks.has_permissions(
        manage_messages=True
    )
    @app_commands.checks.bot_has_permissions(
        mention_everyone=True
    )
    async def announce(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: discord.TextChannel | None = None,
        mention_everyone: bool = False
    ):

        channel = channel or interaction.channel

        await channel.send(
            content="@everyone" if mention_everyone else None,
            embed=make_embed(
                "Announcement",
                message
            ),
            allowed_mentions=discord.AllowedMentions(
                everyone=mention_everyone
            )
        )

        await self.send_success(
            interaction,
            f"Announcement sent in {channel.mention}."
        )

    # ==========================================================
    # /poll
    # ==========================================================

    @app_commands.command(
        name="poll",
        description="Create a poll."
    )
    @app_commands.describe(
        question="Poll question",
        option1="Option 1",
        option2="Option 2",
        option3="Option 3",
        option4="Option 4"
    )
    @app_commands.checks.has_permissions(
        manage_messages=True
    )
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str,
        option3: str | None = None,
        option4: str | None = None
    ):

        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

        options = [
            option1,
            option2
        ]

        if option3:
            options.append(option3)

        if option4:
            options.append(option4)

        description = "\n".join(
            f"{emojis[i]} {option}"
            for i, option in enumerate(options)
        )

        embed = make_embed(
            question,
            description
        )

        await interaction.response.send_message(
            embed=embed
        )

        msg = await interaction.original_response()

        for emoji in emojis[:len(options)]:
            await msg.add_reaction(emoji)
