import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed, send_log


class Roles(commands.Cog):
    """Role and nickname management commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="addrole", description="Gives a role.")
    @app_commands.describe(member="The member to give the role to", role="The role to give")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def addrole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("I cannot assign a role higher than or equal to my own top role.", ephemeral=True)
            return
        if role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("You cannot assign a role higher than or equal to your own top role.", ephemeral=True)
            return
        await member.add_roles(role, reason=f"Added by {interaction.user}")
        embed = make_embed("Role Added", f"Gave {role.mention} to {member.mention}.")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed, category="channels_roles")

    @app_commands.command(name="removerole", description="Removes a role.")
    @app_commands.describe(member="The member to remove the role from", role="The role to remove")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def removerole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("I cannot remove a role higher than or equal to my own top role.", ephemeral=True)
            return
        if role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("You cannot remove a role higher than or equal to your own top role.", ephemeral=True)
            return
        await member.remove_roles(role, reason=f"Removed by {interaction.user}")
        embed = make_embed("Role Removed", f"Removed {role.mention} from {member.mention}.")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed, category="channels_roles")

    @app_commands.command(name="nickname", description="Changes nickname.")
    @app_commands.describe(member="The member to rename", new_nickname="The new nickname (leave blank to reset)")
    @app_commands.checks.has_permissions(manage_nicknames=True)
    @app_commands.checks.bot_has_permissions(manage_nicknames=True)
    async def nickname(self, interaction: discord.Interaction, member: discord.Member, new_nickname: str = None):
        old_nick = member.display_name
        await member.edit(nick=new_nickname, reason=f"Changed by {interaction.user}")
        new_display = new_nickname or member.name
        embed = make_embed("Nickname Changed", f"Changed {member.mention}'s nickname from '{old_nick}' to '{new_display}'.")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed, category="members")


async def setup(bot: commands.Bot):
    await bot.add_cog(Roles(bot))
