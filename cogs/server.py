import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed, send_log
from storage import storage

BLACK = discord.Color.from_str("#000000")


class Server(commands.Cog):
    """Server-wide configuration: lockdown, maintenance, verification, autorole, welcome/goodbye, logs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------------------
    # Lockdown
    # ---------------------------------------------------------------------
    def _lockable_channels(self, guild: discord.Guild):
        """Every channel type that actually has a send/post permission to lock."""
        return [
            c for c in guild.channels
            if isinstance(c, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.ForumChannel))
        ]

    async def _set_channel_lock(self, channel: discord.abc.GuildChannel, locked: bool, reason: str):
        overwrite = channel.overwrites_for(channel.guild.default_role)
        value = False if locked else None
        if isinstance(channel, discord.ForumChannel):
            overwrite.create_forum_threads = value
            overwrite.send_messages_in_threads = value
        else:
            overwrite.send_messages = value
        await channel.set_permissions(channel.guild.default_role, overwrite=overwrite, reason=reason)

    async def _lock_all_channels(self, guild: discord.Guild, reason: str) -> discord.Embed:
        locked = 0
        failed = []
        for channel in self._lockable_channels(guild):
            try:
                await self._set_channel_lock(channel, locked=True, reason=reason)
                locked += 1
            except discord.Forbidden:
                failed.append(channel.mention)
            except discord.HTTPException:
                failed.append(channel.mention)
        description = f"Locked {locked} channel(s).\nReason: {reason}"
        if failed:
            shown = ", ".join(failed[:10]) + (f" (+{len(failed) - 10} more)" if len(failed) > 10 else "")
            description += f"\n\nCould not lock {len(failed)} channel(s) (missing permission overwrite there): {shown}"
        return make_embed("Server Lockdown", description)

    @app_commands.command(name="lockdown", description="Lock every channel.")
    @app_commands.describe(reason="Reason for the lockdown")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def lockdown(self, interaction: discord.Interaction, reason: str = None):
        await interaction.response.defer()
        embed = await self._lock_all_channels(interaction.guild, reason or "Server lockdown")
        await interaction.followup.send(embed=embed)
        await send_log(interaction.guild, embed)

    @app_commands.command(name="unlockdown", description="End lockdown.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def unlockdown(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        unlocked = 0
        failed = []
        for channel in self._lockable_channels(guild):
            try:
                await self._set_channel_lock(channel, locked=False, reason="Lockdown lifted")
                unlocked += 1
            except (discord.Forbidden, discord.HTTPException):
                failed.append(channel.mention)
        description = f"Unlocked {unlocked} channel(s)."
        if failed:
            shown = ", ".join(failed[:10]) + (f" (+{len(failed) - 10} more)" if len(failed) > 10 else "")
            description += f"\n\nCould not unlock {len(failed)} channel(s): {shown}"
        embed = make_embed("Lockdown Lifted", description)
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
                message = (
                    message.replace("{member}", member.mention)
                    .replace("{user}", member.mention)
                    .replace("{server}", member.guild.name)
                )
                try:
                    if welcome_cfg.get("embed"):
                        await channel.send(embed=discord.Embed(description=message, color=BLACK))
                    else:
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
                message = (
                    message.replace("{member}", str(member))
                    .replace("{user}", str(member))
                    .replace("{server}", member.guild.name)
                )
                try:
                    if goodbye_cfg.get("embed"):
                        await channel.send(embed=discord.Embed(description=message, color=BLACK))
                    else:
                        await channel.send(message)
                except discord.HTTPException:
                    pass

    # ---------------------------------------------------------------------
    # Welcome configuration
    # ---------------------------------------------------------------------
    welcome_group = app_commands.Group(name="welcome", description="Configure welcome messages.")

    @welcome_group.command(name="set", description="Configure welcome messages.")
    @app_commands.describe(channel="Channel to post welcome messages in", message="Message text. Use {member} (or {user}) and {server} as placeholders")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_set(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = "Welcome {member} to {server}!"):
        cfg = storage.get_guild_setting("welcome", interaction.guild.id) or {}
        cfg["channel_id"] = channel.id
        cfg["message"] = message
        storage.set_guild_setting("welcome", interaction.guild.id, cfg)
        embed = make_embed("Welcome Messages Configured", f"New members will be welcomed in {channel.mention}.")
        await interaction.response.send_message(embed=embed)

    @welcome_group.command(name="embed", description="Toggle embed welcome.")
    @app_commands.describe(enabled="Send welcome messages as an embed instead of plain text")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_embed(self, interaction: discord.Interaction, enabled: bool):
        cfg = storage.get_guild_setting("welcome", interaction.guild.id) or {}
        cfg["embed"] = enabled
        storage.set_guild_setting("welcome", interaction.guild.id, cfg)
        embed = make_embed("Welcome Embed Toggled", f"Embed welcome messages are now {'enabled' if enabled else 'disabled'}.")
        await interaction.response.send_message(embed=embed)

    @welcome_group.command(name="test", description="Send a test welcome.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_test(self, interaction: discord.Interaction):
        cfg = storage.get_guild_setting("welcome", interaction.guild.id)
        if not cfg or not cfg.get("channel_id"):
            await interaction.response.send_message("Welcome messages aren't configured yet. Use /welcome set first.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(int(cfg["channel_id"]))
        if channel is None:
            await interaction.response.send_message("The configured welcome channel no longer exists.", ephemeral=True)
            return
        message = cfg.get("message", "Welcome {member} to {server}!")
        message = (
            message.replace("{member}", interaction.user.mention)
            .replace("{user}", interaction.user.mention)
            .replace("{server}", interaction.guild.name)
        )
        if cfg.get("embed"):
            await channel.send(embed=discord.Embed(description=message, color=BLACK))
        else:
            await channel.send(message)
        await interaction.response.send_message(f"Sent a test welcome message in {channel.mention}.", ephemeral=True)

    # ---------------------------------------------------------------------
    # Goodbye configuration
    # ---------------------------------------------------------------------
    goodbye_group = app_commands.Group(name="goodbye", description="Configure leave messages.")

    @goodbye_group.command(name="set", description="Configure leave messages.")
    @app_commands.describe(channel="Channel to post leave messages in", message="Message text. Use {member} (or {user}) and {server} as placeholders")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def goodbye_set(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = "{member} has left {server}."):
        cfg = storage.get_guild_setting("goodbye", interaction.guild.id) or {}
        cfg["channel_id"] = channel.id
        cfg["message"] = message
        storage.set_guild_setting("goodbye", interaction.guild.id, cfg)
        embed = make_embed("Goodbye Messages Configured", f"Leave messages will be posted in {channel.mention}.")
        await interaction.response.send_message(embed=embed)

    @goodbye_group.command(name="embed", description="Toggle embed goodbye.")
    @app_commands.describe(enabled="Send leave messages as an embed instead of plain text")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def goodbye_embed(self, interaction: discord.Interaction, enabled: bool):
        cfg = storage.get_guild_setting("goodbye", interaction.guild.id) or {}
        cfg["embed"] = enabled
        storage.set_guild_setting("goodbye", interaction.guild.id, cfg)
        embed = make_embed("Goodbye Embed Toggled", f"Embed goodbye messages are now {'enabled' if enabled else 'disabled'}.")
        await interaction.response.send_message(embed=embed)

    @goodbye_group.command(name="test", description="Send a test goodbye.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def goodbye_test(self, interaction: discord.Interaction):
        cfg = storage.get_guild_setting("goodbye", interaction.guild.id)
        if not cfg or not cfg.get("channel_id"):
            await interaction.response.send_message("Goodbye messages aren't configured yet. Use /goodbye set first.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(int(cfg["channel_id"]))
        if channel is None:
            await interaction.response.send_message("The configured goodbye channel no longer exists.", ephemeral=True)
            return
        message = cfg.get("message", "{member} has left {server}.")
        message = (
            message.replace("{member}", str(interaction.user))
            .replace("{user}", str(interaction.user))
            .replace("{server}", interaction.guild.name)
        )
        if cfg.get("embed"):
            await channel.send(embed=discord.Embed(description=message, color=BLACK))
        else:
            await channel.send(message)
        await interaction.response.send_message(f"Sent a test goodbye message in {channel.mention}.", ephemeral=True)

    # ---------------------------------------------------------------------
    # Logs configuration
    # ---------------------------------------------------------------------
    @app_commands.command(name="logs", description="Configure log channels.")
    @app_commands.describe(channel="Channel to send moderation logs to")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs(self, interaction: discord.Interaction, channel: discord.TextChannel):
        storage.set_guild_setting("logs", interaction.guild.id, channel.id)
        embed = make_embed("Log Channel Set", f"Moderation actions will now be logged in {channel.mention}.")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Server(bot))
