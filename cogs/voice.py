import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed, send_log


class Voice(commands.Cog):
    """Voice channel moderation commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="voicekick", description="Disconnects a user from voice.")
    @app_commands.describe(member="The member to disconnect", reason="Reason")
    @app_commands.checks.has_permissions(move_members=True)
    @app_commands.checks.bot_has_permissions(move_members=True)
    async def voicekick(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        if member.voice is None or member.voice.channel is None:
            await interaction.response.send_message(f"{member.mention} is not in a voice channel.", ephemeral=True)
            return
        await member.move_to(None, reason=reason)
        embed = make_embed("Voice Kick", f"{member.mention} was disconnected from voice.\nReason: {reason or 'No reason provided'}")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)

    @app_commands.command(name="move", description="Moves a member.")
    @app_commands.describe(member="The member to move", channel="The voice channel to move them to")
    @app_commands.checks.has_permissions(move_members=True)
    @app_commands.checks.bot_has_permissions(move_members=True)
    async def move(self, interaction: discord.Interaction, member: discord.Member, channel: discord.VoiceChannel):
        if member.voice is None or member.voice.channel is None:
            await interaction.response.send_message(f"{member.mention} is not in a voice channel.", ephemeral=True)
            return
        await member.move_to(channel)
        embed = make_embed("Member Moved", f"{member.mention} was moved to {channel.mention}.")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)

    @app_commands.command(name="moveall", description="Moves everyone in a voice channel.")
    @app_commands.describe(source="The voice channel to move everyone from", destination="The voice channel to move everyone to")
    @app_commands.checks.has_permissions(move_members=True)
    @app_commands.checks.bot_has_permissions(move_members=True)
    async def moveall(self, interaction: discord.Interaction, source: discord.VoiceChannel, destination: discord.VoiceChannel):
        await interaction.response.defer()
        moved = 0
        for member in list(source.members):
            try:
                await member.move_to(destination)
                moved += 1
            except discord.HTTPException:
                continue
        embed = make_embed("Voice Channel Moved", f"Moved {moved} member(s) from {source.mention} to {destination.mention}.")
        await interaction.followup.send(embed=embed)
        await send_log(interaction.guild, embed)

    @app_commands.command(name="mutevoice", description="Server mutes a member.")
    @app_commands.describe(member="The member to server mute", reason="Reason")
    @app_commands.checks.has_permissions(mute_members=True)
    @app_commands.checks.bot_has_permissions(mute_members=True)
    async def mutevoice(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        await member.edit(mute=True, reason=reason)
        embed = make_embed("Member Server Muted", f"{member.mention} has been server muted.\nReason: {reason or 'No reason provided'}")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)

    @app_commands.command(name="unmutevoice", description="Removes server mute.")
    @app_commands.describe(member="The member to unmute", reason="Reason")
    @app_commands.checks.has_permissions(mute_members=True)
    @app_commands.checks.bot_has_permissions(mute_members=True)
    async def unmutevoice(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        await member.edit(mute=False, reason=reason)
        embed = make_embed("Server Mute Removed", f"{member.mention} is no longer server muted.")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)

    @app_commands.command(name="deafen", description="Server deafens a member.")
    @app_commands.describe(member="The member to server deafen", reason="Reason")
    @app_commands.checks.has_permissions(deafen_members=True)
    @app_commands.checks.bot_has_permissions(deafen_members=True)
    async def deafen(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        await member.edit(deafen=True, reason=reason)
        embed = make_embed("Member Server Deafened", f"{member.mention} has been server deafened.\nReason: {reason or 'No reason provided'}")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)

    @app_commands.command(name="undeafen", description="Removes server deafening.")
    @app_commands.describe(member="The member to undeafen", reason="Reason")
    @app_commands.checks.has_permissions(deafen_members=True)
    @app_commands.checks.bot_has_permissions(deafen_members=True)
    async def undeafen(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        await member.edit(deafen=False, reason=reason)
        embed = make_embed("Server Deafen Removed", f"{member.mention} is no longer server deafened.")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Voice(bot))
