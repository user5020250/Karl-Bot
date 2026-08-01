import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed, send_log
from storage import storage


class Server(commands.Cog):
    """Server-wide configuration: lockdown, maintenance, verification, autorole, welcome/goodbye, logs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------------------
    # Lockdown
    # ---------------------------------------------------------------------
    @app_commands.command(name="lockdown", description="Lock every channel.")
    @app_commands.describe(reason="Reason for the lockdown")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def lockdown(self, interaction: discord.Interaction, reason: str = None):
        await interaction.response.defer()
        guild = interaction.guild
        locked = 0
        for channel in guild.text_channels:
            try:
                overwrite = channel.overwrites_for(guild.default_role)
                overwrite.send_messages = False
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason or "Server lockdown")
                locked += 1
            except discord.HTTPException:
                continue
        embed = make_embed("Server Lockdown", f"Locked {locked} channel(s).\nReason: {reason or 'No reason provided'}")
        await interaction.followup.send(embed=embed)
        await send_log(guild, embed)

    @app_commands.command(name="unlockdown", description="End lockdown.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def unlockdown(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        unlocked = 0
        for channel in guild.text_channels:
            try:
                overwrite = channel.overwrites_for(guild.default_role)
                overwrite.send_messages = None
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Lockdown lifted")
                unlocked += 1
            except discord.HTTPException:
                continue
        embed = make_embed("Lockdown Lifted", f"Unlocked {unlocked} channel(s).")
        await interaction.followup.send(embed=embed)
        await send_log(guild, embed)

    # ---------------------------------------------------------------------
    # Maintenance
    # ---------------------------------------------------------------------
    @app_commands.command(name="maintenance", description="Toggle maintenance mode.")
    @app_commands.describe(enabled="Turn maintenance mode on or off")
    @app_commands.checks.has_permissions(administrator=True)
    async def maintenance(self, interaction: discord.Interaction, enabled: bool):
        storage.set_guild_setting("maintenance", interaction.guild.id, enabled)
        embed = make_embed(
            "Maintenance Mode",
            f"Maintenance mode is now {'enabled' if enabled else 'disabled'}. "
            + ("Only administrators can use commands while enabled." if enabled else "All commands are available again."),
        )
        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------------------
    # Verification
    # ---------------------------------------------------------------------
    @app_commands.command(name="verify", description="Verify a member.")
    @app_commands.describe(member="The member to verify")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def verify(self, interaction: discord.Interaction, member: discord.Member):
        config = storage.get_guild_setting("verify", interaction.guild.id)
        if not config or not config.get("role_id"):
            await interaction.response.send_message("No verification role is configured. Set one up with /setverifyrole.", ephemeral=True)
            return
        role = interaction.guild.get_role(int(config["role_id"]))
        if role is None:
            await interaction.response.send_message("The configured verification role no longer exists.", ephemeral=True)
            return
        await member.add_roles(role, reason=f"Verified by {interaction.user}")
        embed = make_embed("Member Verified", f"{member.mention} has been verified.")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)

    @app_commands.command(name="unverify", description="Remove verification.")
    @app_commands.describe(member="The member to unverify")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def unverify(self, interaction: discord.Interaction, member: discord.Member):
        config = storage.get_guild_setting("verify", interaction.guild.id)
        if not config or not config.get("role_id"):
            await interaction.response.send_message("No verification role is configured.", ephemeral=True)
            return
        role = interaction.guild.get_role(int(config["role_id"]))
        if role is None:
            await interaction.response.send_message("The configured verification role no longer exists.", ephemeral=True)
            return
        await member.remove_roles(role, reason=f"Unverified by {interaction.user}")
        embed = make_embed("Verification Removed", f"{member.mention} is no longer verified.")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)

    @app_commands.command(name="setverifyrole", description="Set the role given to verified members.")
    @app_commands.describe(role="The verification role")
    @app_commands.checks.has_permissions(administrator=True)
    async def setverifyrole(self, interaction: discord.Interaction, role: discord.Role):
        storage.set_guild_setting("verify", interaction.guild.id, {"role_id": role.id})
        embed = make_embed("Verification Role Set", f"{role.mention} will now be given by /verify.")
        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------------------
    # Autorole
    # ---------------------------------------------------------------------
    autorole_group = app_commands.Group(name="autorole", description="Configure automatic roles given to new members.")

    @autorole_group.command(name="add", description="Add a role to be given automatically to new members.")
    @app_commands.describe(role="The role to add")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole_add(self, interaction: discord.Interaction, role: discord.Role):
        storage.add_to_list("autorole", interaction.guild.id, role.id)
        embed = make_embed("Autorole Added", f"{role.mention} will now be given automatically to new members.")
        await interaction.response.send_message(embed=embed)

    @autorole_group.command(name="remove", description="Remove a role from the autorole list.")
    @app_commands.describe(role="The role to remove")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole_remove(self, interaction: discord.Interaction, role: discord.Role):
        storage.remove_from_list("autorole", interaction.guild.id, role.id)
        embed = make_embed("Autorole Removed", f"{role.mention} will no longer be given automatically.")
        await interaction.response.send_message(embed=embed)

    @autorole_group.command(name="list", description="List autoroles.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole_list(self, interaction: discord.Interaction):
        role_ids = storage.get_list("autorole", interaction.guild.id)
        roles = [interaction.guild.get_role(rid) for rid in role_ids]
        roles = [r for r in roles if r is not None]
        embed = make_embed("Autoroles", ", ".join(r.mention for r in roles) if roles else "No autoroles configured.")
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        role_ids = storage.get_list("autorole", member.guild.id)
        for rid in role_ids:
            role = member.guild.get_role(rid)
            if role is not None:
                try:
                    await member.add_roles(role, reason="Autorole")
                except discord.HTTPException:
                    continue

        welcome_cfg = storage.get_guild_setting("welcome", member.guild.id)
        if welcome_cfg and welcome_cfg.get("channel_id"):
            channel = member.guild.get_channel(int(welcome_cfg["channel_id"]))
            if channel is not None:
                message = welcome_cfg.get("message", "Welcome {member} to {server}!")
                message = message.replace("{member}", member.mention).replace("{server}", member.guild.name)
                try:
                    await channel.send(message)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        goodbye_cfg = storage.get_guild_setting("goodbye", member.guild.id)
        if goodbye_cfg and goodbye_cfg.get("channel_id"):
            channel = member.guild.get_channel(int(goodbye_cfg["channel_id"]))
            if channel is not None:
                message = goodbye_cfg.get("message", "{member} has left {server}.")
                message = message.replace("{member}", str(member)).replace("{server}", member.guild.name)
                try:
                    await channel.send(message)
                except discord.HTTPException:
                    pass

    # ---------------------------------------------------------------------
    # Welcome / goodbye / logs configuration
    # ---------------------------------------------------------------------
    @app_commands.command(name="welcome", description="Configure welcome messages.")
    @app_commands.describe(channel="Channel to post welcome messages in", message="Message text. Use {member} and {server} as placeholders")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = "Welcome {member} to {server}!"):
        storage.set_guild_setting("welcome", interaction.guild.id, {"channel_id": channel.id, "message": message})
        embed = make_embed("Welcome Messages Configured", f"New members will be welcomed in {channel.mention}.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="goodbye", description="Configure leave messages.")
    @app_commands.describe(channel="Channel to post leave messages in", message="Message text. Use {member} and {server} as placeholders")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def goodbye(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = "{member} has left {server}."):
        storage.set_guild_setting("goodbye", interaction.guild.id, {"channel_id": channel.id, "message": message})
        embed = make_embed("Goodbye Messages Configured", f"Leave messages will be posted in {channel.mention}.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="logs", description="Configure log channels.")
    @app_commands.describe(channel="Channel to send moderation logs to")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs(self, interaction: discord.Interaction, channel: discord.TextChannel):
        storage.set_guild_setting("logs", interaction.guild.id, channel.id)
        embed = make_embed("Log Channel Set", f"Moderation actions will now be logged in {channel.mention}.")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Server(bot))
