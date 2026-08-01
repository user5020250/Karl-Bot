import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed


class Messages(commands.Cog):
    """Message clearing and purge commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    purge_group = app_commands.Group(name="purge", description="Delete messages matching a filter.")

    @app_commands.command(name="clear", description="Deletes recent messages.")
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)

    async def _purge(self, interaction: discord.Interaction, amount: int, check):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount, check=check)
        await interaction.followup.send(f"Deleted {len(deleted)} matching messages.", ephemeral=True)

    @purge_group.command(name="user", description="Deletes messages from a specific user.")
    @app_commands.describe(member="The user whose messages to delete", amount="Number of messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_user(self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1, 200] = 100):
        await self._purge(interaction, amount, lambda m: m.author.id == member.id)

    @purge_group.command(name="bots", description="Deletes bot messages.")
    @app_commands.describe(amount="Number of messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_bots(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 100):
        await self._purge(interaction, amount, lambda m: m.author.bot)

    @purge_group.command(name="links", description="Deletes messages containing links.")
    @app_commands.describe(amount="Number of messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_links(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 100):
        await self._purge(interaction, amount, lambda m: "http://" in m.content or "https://" in m.content)

    @purge_group.command(name="invites", description="Deletes Discord invite links.")
    @app_commands.describe(amount="Number of messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_invites(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 100):
        invite_markers = ("discord.gg/", "discord.com/invite/", "discordapp.com/invite/")
        await self._purge(interaction, amount, lambda m: any(marker in m.content.lower() for marker in invite_markers))

    @purge_group.command(name="images", description="Deletes image messages.")
    @app_commands.describe(amount="Number of messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_images(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 100):
        image_exts = (".png", ".jpg", ".jpeg", ".gif", ".webp")

        def check(m):
            return any(a.filename.lower().endswith(image_exts) for a in m.attachments)

        await self._purge(interaction, amount, check)

    @purge_group.command(name="embeds", description="Deletes embedded messages.")
    @app_commands.describe(amount="Number of messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_embeds(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 100):
        await self._purge(interaction, amount, lambda m: len(m.embeds) > 0)

    @purge_group.command(name="files", description="Deletes messages with attachments.")
    @app_commands.describe(amount="Number of messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_files(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 100):
        await self._purge(interaction, amount, lambda m: len(m.attachments) > 0)

    @purge_group.command(name="mentions", description="Deletes messages containing mentions.")
    @app_commands.describe(amount="Number of messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_mentions(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 100):
        await self._purge(interaction, amount, lambda m: len(m.mentions) > 0 or len(m.role_mentions) > 0)

    @purge_group.command(name="contains", description="Deletes messages containing text.")
    @app_commands.describe(text="The text to search for", amount="Number of messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_contains(self, interaction: discord.Interaction, text: str, amount: app_commands.Range[int, 1, 200] = 100):
        await self._purge(interaction, amount, lambda m: text.lower() in m.content.lower())


async def setup(bot: commands.Bot):
    await bot.add_cog(Messages(bot))
