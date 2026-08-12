import asyncio
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from helpers import action_embed, make_embed, send_log
from storage import storage


class Moderation(commands.Cog):
    """Ban, kick, timeout, and moderation history commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------------- ban
    @app_commands.command(name="ban", description="Permanently bans a member.")
    @app_commands.describe(member="The member to ban", reason="Reason for the ban", delete_days="Days of messages to delete (0-7)")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = None, delete_days: app_commands.Range[int, 0, 7] = 0):
        if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("You cannot ban a member with an equal or higher role than you.", ephemeral=True)
            return
        await interaction.guild.ban(member, reason=reason, delete_message_days=delete_days)
        storage.add_history(interaction.guild.id, member.id, "ban", interaction.user.id, reason)
        embed = action_embed("Member Banned", member, interaction.user, reason)
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)

    # ------------------------------------------------------------ tempban
    @app_commands.command(name="tempban", description="Bans a member for a specified duration.")
    @app_commands.describe(member="The member to ban", duration="e.g. 10m, 2h, 1d, 1w", reason="Reason for the ban")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def tempban(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = None):
        from helpers import parse_duration
        try:
            seconds = parse_duration(duration)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        guild = interaction.guild
        await guild.ban(member, reason=reason)
        storage.add_history(guild.id, member.id, f"tempban ({duration})", interaction.user.id, reason)
        embed = action_embed(f"Member Temp-Banned ({duration})", member, interaction.user, reason)
        await interaction.response.send_message(embed=embed)
        await send_log(guild, embed)

        async def _unban_later():
            await asyncio.sleep(seconds)
            try:
                await guild.unban(discord.Object(id=member.id), reason="Temporary ban expired")
            except discord.NotFound:
                pass
            except discord.HTTPException:
                pass

        self.bot.loop.create_task(_unban_later())

    # ------------------------------------------------------------ softban
    @app_commands.command(name="softban", description="Bans then immediately unbans a member to delete recent messages.")
    @app_commands.describe(member="The member to softban", reason="Reason", delete_days="Days of messages to delete (0-7)")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def softban(self, interaction: discord.Interaction, member: discord.Member, reason: str = None, delete_days: app_commands.Range[int, 1, 7] = 1):
        guild = interaction.guild
        await guild.ban(member, reason=reason, delete_message_days=delete_days)
        await guild.unban(discord.Object(id=member.id), reason="Softban")
        storage.add_history(guild.id, member.id, "softban", interaction.user.id, reason)
        embed = action_embed("Member Softbanned", member, interaction.user, reason)
        await interaction.response.send_message(embed=embed)
        await send_log(guild, embed)

    # --------------------------------------------------------------- unban
    @app_commands.command(name="unban", description="Unbans a member.")
    @app_commands.describe(user_id="The user ID to unban", reason="Reason for the unban")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = None):
        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message("That doesn't look like a valid user ID.", ephemeral=True)
            return
        try:
            user = await self.bot.fetch_user(uid)
            await interaction.guild.unban(user, reason=reason)
        except discord.NotFound:
            await interaction.response.send_message("That user is not banned.", ephemeral=True)
            return
        storage.add_history(interaction.guild.id, uid, "unban", interaction.user.id, reason)
        embed = action_embed("Member Unbanned", user, interaction.user, reason)
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)

    # ---------------------------------------------------------------- kick
    @app_commands.command(name="kick", description="Kicks a member from the server.")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("You cannot kick a member with an equal or higher role than you.", ephemeral=True)
            return
        await member.kick(reason=reason)
        storage.add_history(interaction.guild.id, member.id, "kick", interaction.user.id, reason)
        embed = action_embed("Member Kicked", member, interaction.user, reason)
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)

    # ------------------------------------------------------------- timeout
    @app_commands.command(name="timeout", description="Times out a member.")
    @app_commands.describe(member="The member to time out", duration="e.g. 10m, 2h, 1d", reason="Reason")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = None):
        from helpers import parse_duration
        try:
            seconds = parse_duration(duration)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        if seconds > 2419200:  # Discord's 28 day max
            await interaction.response.send_message("Timeouts cannot exceed 28 days.", ephemeral=True)
            return
        await member.timeout(timedelta(seconds=seconds), reason=reason)
        storage.add_history(interaction.guild.id, member.id, f"timeout ({duration})", interaction.user.id, reason)
        embed = action_embed(f"Member Timed Out ({duration})", member, interaction.user, reason)
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)

    # ----------------------------------------------------------- untimeout
    @app_commands.command(name="untimeout", description="Removes a timeout.")
    @app_commands.describe(member="The member to remove a timeout from", reason="Reason")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        await member.timeout(None, reason=reason)
        storage.add_history(interaction.guild.id, member.id, "untimeout", interaction.user.id, reason)
        embed = action_embed("Timeout Removed", member, interaction.user, reason)
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)

    # ------------------------------------------------------------- history


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
