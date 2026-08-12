import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed, send_log


class Channels(commands.Cog):
    """Channel management commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="lock", description="Locks a channel.")
    @app_commands.describe(channel="The channel to lock (defaults to this channel)", reason="Reason for locking")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction, channel: discord.TextChannel = None, reason: str = None):
        channel = channel or interaction.channel
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)
        embed = make_embed("Channel Locked", f"{channel.mention} has been locked.\nReason: {reason or 'No reason provided'}")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed, category="channels_roles")

    @app_commands.command(name="unlock", description="Unlocks a channel.")
    @app_commands.describe(channel="The channel to unlock (defaults to this channel)", reason="Reason for unlocking")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction, channel: discord.TextChannel = None, reason: str = None):
        channel = channel or interaction.channel
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)
        embed = make_embed("Channel Unlocked", f"{channel.mention} has been unlocked.\nReason: {reason or 'No reason provided'}")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed, category="channels_roles")



    @app_commands.command(name="nuke", description="Deletes all messages by recreating the channel.")
    @app_commands.describe(channel="The channel to nuke (defaults to this channel)")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def nuke(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        channel = channel or interaction.channel
        position = channel.position
        new_channel = await channel.clone(reason=f"Nuked by {interaction.user}")
        await channel.delete(reason=f"Nuked by {interaction.user}")
        await new_channel.edit(position=position)
        embed = make_embed("Channel Nuked", "This channel has been nuked.")
        await new_channel.send(embed=embed)
        await send_log(interaction.guild, embed, category="channels_roles")
        if not interaction.response.is_done():
            await interaction.response.send_message("Channel nuked.", ephemeral=True)




async def setup(bot: commands.Bot):
    await bot.add_cog(Channels(bot))
