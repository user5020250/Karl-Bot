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

    @app_commands.command(name="slowmode", description="Sets channel slowmode.")
    @app_commands.describe(seconds="Slowmode delay in seconds (0-21600, 0 disables it)", channel="The channel to update (defaults to this channel)")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600], channel: discord.TextChannel = None):
        channel = channel or interaction.channel
        await channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            desc = f"Slowmode disabled in {channel.mention}."
        else:
            desc = f"Slowmode set to {seconds} seconds in {channel.mention}."
        embed = make_embed("Slowmode Updated", desc)
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed, category="channels_roles")

    @app_commands.command(name="clone", description="Clones a channel.")
    @app_commands.describe(channel="The channel to clone (defaults to this channel)")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def clone(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        channel = channel or interaction.channel
        new_channel = await channel.clone(reason=f"Cloned by {interaction.user}")
        await new_channel.move(after=channel)
        embed = make_embed("Channel Cloned", f"Created {new_channel.mention} as a clone of {channel.mention}.")
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

    @app_commands.command(name="archive", description="Archives a channel.")
    @app_commands.describe(channel="The channel to archive (defaults to this channel)", category="Category to move the channel into")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def archive(self, interaction: discord.Interaction, channel: discord.TextChannel = None, category: discord.CategoryChannel = None):
        channel = channel or interaction.channel
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        overwrite.view_channel = overwrite.view_channel  # unchanged, kept viewable by default
        await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason="Archived")
        if category is not None:
            await channel.edit(category=category, reason="Archived")
        embed = make_embed("Channel Archived", f"{channel.mention} has been archived and locked for new messages.")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed, category="channels_roles")

    @app_commands.command(name="renamechannel", description="Renames a channel.")
    @app_commands.describe(new_name="The new channel name", channel="The channel to rename (defaults to this channel)")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def renamechannel(self, interaction: discord.Interaction, new_name: str, channel: discord.abc.GuildChannel = None):
        channel = channel or interaction.channel
        old_name = channel.name
        await channel.edit(name=new_name, reason=f"Renamed by {interaction.user}")
        embed = make_embed("Channel Renamed", f"Renamed #{old_name} to #{new_name}.")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed, category="channels_roles")


async def setup(bot: commands.Bot):
    await bot.add_cog(Channels(bot))
