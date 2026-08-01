import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed, send_log
from storage import storage


class Jail(commands.Cog):
    """Moves members into a restricted 'jail' role and channel, removing their other roles until released."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setjail", description="Configure the jail role and channel.")
    @app_commands.describe(role="The restricted role given to jailed members", channel="The channel jailed members can see")
    @app_commands.checks.has_permissions(administrator=True)
    async def setjail(self, interaction: discord.Interaction, role: discord.Role, channel: discord.TextChannel):
        storage.set_guild_setting("jail", interaction.guild.id, {"role_id": role.id, "channel_id": channel.id, "members": {}})
        embed = make_embed("Jail Configured", f"Role: {role.mention}\nChannel: {channel.mention}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="jail", description="Moves a member into jail, removing their other roles.")
    @app_commands.describe(member="The member to jail", reason="Reason for jailing")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def jail(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        config = storage.get_guild_setting("jail", interaction.guild.id)
        if not config or not config.get("role_id"):
            await interaction.response.send_message("Jail is not configured yet. Use /setjail first.", ephemeral=True)
            return

        jail_role = interaction.guild.get_role(int(config["role_id"]))
        if jail_role is None:
            await interaction.response.send_message("The configured jail role no longer exists.", ephemeral=True)
            return

        if jail_role >= interaction.guild.me.top_role:
            await interaction.response.send_message("The jail role is higher than or equal to my top role. Move my role above it.", ephemeral=True)
            return

        current_roles = [r.id for r in member.roles if r.name != "@everyone" and r.id != jail_role.id]
        config.setdefault("members", {})[str(member.id)] = current_roles
        storage.set_guild_setting("jail", interaction.guild.id, config)

        roles_to_remove = [r for r in member.roles if r.name != "@everyone"]
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason=f"Jailed by {interaction.user}: {reason or 'No reason provided'}")
        await member.add_roles(jail_role, reason=f"Jailed by {interaction.user}")

        embed = make_embed("Member Jailed", f"{member.mention} has been jailed.\nReason: {reason or 'No reason provided'}")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)

    @app_commands.command(name="unjail", description="Releases a member from jail and restores their previous roles.")
    @app_commands.describe(member="The member to release", reason="Reason for releasing")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def unjail(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        config = storage.get_guild_setting("jail", interaction.guild.id)
        if not config or not config.get("role_id"):
            await interaction.response.send_message("Jail is not configured yet. Use /setjail first.", ephemeral=True)
            return

        jail_role = interaction.guild.get_role(int(config["role_id"]))
        saved_role_ids = config.get("members", {}).pop(str(member.id), [])
        storage.set_guild_setting("jail", interaction.guild.id, config)

        if jail_role is not None and jail_role in member.roles:
            await member.remove_roles(jail_role, reason=f"Unjailed by {interaction.user}")

        restored = []
        for rid in saved_role_ids:
            role = interaction.guild.get_role(rid)
            if role is not None:
                restored.append(role)
        if restored:
            await member.add_roles(*restored, reason=f"Unjailed by {interaction.user}: restoring previous roles")

        embed = make_embed("Member Released", f"{member.mention} has been released from jail.\nReason: {reason or 'No reason provided'}")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Jail(bot))
