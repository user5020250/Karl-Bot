import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed, send_log
from storage import storage

BLACK = discord.Color.from_str("#000000")


# ============================================================
# GREETING HELPERS (shared by welcome + goodbye)
# ============================================================

def _fill_placeholders(text: str, member: discord.Member, guild: discord.Guild, mention: bool) -> str:

    who = member.mention if mention else str(member)

    return (
        text
        .replace("{member}", who)
        .replace("{user}", who)
        .replace("{server}", guild.name)
    )


def _build_greet_payload(cfg: dict, member: discord.Member, guild: discord.Guild, mention: bool) -> dict:
    """Turns a welcome/goodbye config into kwargs for channel.send()."""

    mode = cfg.get("mode", "message")

    if mode == "embed":

        edata = cfg.get("embed", {}) or {}

        embed = discord.Embed(color=BLACK)

        if edata.get("title"):
            embed.title = _fill_placeholders(edata["title"], member, guild, mention)

        if edata.get("description"):
            embed.description = _fill_placeholders(edata["description"], member, guild, mention)

        if edata.get("footer"):
            embed.set_footer(text=_fill_placeholders(edata["footer"], member, guild, mention))

        if edata.get("image"):
            embed.set_image(url=edata["image"])

        return {"embed": embed}

    message = cfg.get("message", "Welcome {member} to {server}!")

    return {"content": _fill_placeholders(message, member, guild, mention)}


class Server(commands.Cog):
    """Server-wide configuration: lockdown, autorole, welcome/goodbye.

    Log channel configuration lives in cogs/logs.py (/logs panel).
    """

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
        await send_log(interaction.guild, embed, category="moderation")

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
        await send_log(guild, embed, category="moderation")

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

    # ---------------------------------------------------------------------
    # Join / leave listeners: autorole + welcome/goodbye
    # ---------------------------------------------------------------------
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
                payload = _build_greet_payload(welcome_cfg, member, member.guild, mention=True)
                try:
                    await channel.send(**payload)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        goodbye_cfg = storage.get_guild_setting("goodbye", member.guild.id)
        if goodbye_cfg and goodbye_cfg.get("channel_id"):
            channel = member.guild.get_channel(int(goodbye_cfg["channel_id"]))
            if channel is not None:
                payload = _build_greet_payload(goodbye_cfg, member, member.guild, mention=False)
                try:
                    await channel.send(**payload)
                except discord.HTTPException:
                    pass

    # ---------------------------------------------------------------------
    # Welcome configuration
    # ---------------------------------------------------------------------
    welcome_group = app_commands.Group(name="welcome", description="Configure welcome messages.")

    @welcome_group.command(name="message", description="Welcome new members with a plain text message.")
    @app_commands.describe(
        channel="Channel to post welcome messages in",
        message="Message text. Use {member} (or {user}) and {server} as placeholders",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_message(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str = "Welcome {member} to {server}!",
    ):
        cfg = storage.get_guild_setting("welcome", interaction.guild.id) or {}
        cfg["channel_id"] = channel.id
        cfg["mode"] = "message"
        cfg["message"] = message
        storage.set_guild_setting("welcome", interaction.guild.id, cfg)
        embed = make_embed("Welcome Messages Configured", f"New members will be welcomed in {channel.mention} with a plain message.")
        await interaction.response.send_message(embed=embed)

    @welcome_group.command(name="embed", description="Welcome new members with a custom embed.")
    @app_commands.describe(
        channel="Channel to post welcome messages in",
        title="Embed title (optional). Supports {member}/{user} and {server}",
        description="Embed description. Supports {member}/{user} and {server}",
        footer="Embed footer text (optional). Supports {member}/{user} and {server}",
        image="Image URL to display in the embed (optional)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_embed(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        description: str = "Welcome {member} to {server}!",
        title: str = None,
        footer: str = None,
        image: str = None,
    ):
        cfg = storage.get_guild_setting("welcome", interaction.guild.id) or {}
        cfg["channel_id"] = channel.id
        cfg["mode"] = "embed"
        cfg["embed"] = {
            "title": title,
            "description": description,
            "footer": footer,
            "image": image,
        }
        storage.set_guild_setting("welcome", interaction.guild.id, cfg)
        embed = make_embed("Welcome Messages Configured", f"New members will be welcomed in {channel.mention} with an embed.")
        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------------------
    # Goodbye configuration
    # ---------------------------------------------------------------------
    goodbye_group = app_commands.Group(name="goodbye", description="Configure leave messages.")

    @goodbye_group.command(name="message", description="Announce members leaving with a plain text message.")
    @app_commands.describe(
        channel="Channel to post leave messages in",
        message="Message text. Use {member} (or {user}) and {server} as placeholders",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def goodbye_message(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str = "{member} has left {server}.",
    ):
        cfg = storage.get_guild_setting("goodbye", interaction.guild.id) or {}
        cfg["channel_id"] = channel.id
        cfg["mode"] = "message"
        cfg["message"] = message
        storage.set_guild_setting("goodbye", interaction.guild.id, cfg)
        embed = make_embed("Goodbye Messages Configured", f"Leave messages will be posted in {channel.mention} as a plain message.")
        await interaction.response.send_message(embed=embed)

    @goodbye_group.command(name="embed", description="Announce members leaving with a custom embed.")
    @app_commands.describe(
        channel="Channel to post leave messages in",
        title="Embed title (optional). Supports {member}/{user} and {server}",
        description="Embed description. Supports {member}/{user} and {server}",
        footer="Embed footer text (optional). Supports {member}/{user} and {server}",
        image="Image URL to display in the embed (optional)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def goodbye_embed(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        description: str = "{member} has left {server}.",
        title: str = None,
        footer: str = None,
        image: str = None,
    ):
        cfg = storage.get_guild_setting("goodbye", interaction.guild.id) or {}
        cfg["channel_id"] = channel.id
        cfg["mode"] = "embed"
        cfg["embed"] = {
            "title": title,
            "description": description,
            "footer": footer,
            "image": image,
        }
        storage.set_guild_setting("goodbye", interaction.guild.id, cfg)
        embed = make_embed("Goodbye Messages Configured", f"Leave messages will be posted in {channel.mention} as an embed.")
        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------------------
    # Greet testing (welcome + goodbye combined)
    # ---------------------------------------------------------------------
    greet_group = app_commands.Group(name="greet", description="Test greeting messages.")

    @greet_group.command(name="test", description="Send a test welcome or goodbye message.")
    @app_commands.describe(type="Which greeting to test")
    @app_commands.choices(type=[
        app_commands.Choice(name="Welcome", value="welcome"),
        app_commands.Choice(name="Goodbye", value="goodbye"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def greet_test(self, interaction: discord.Interaction, type: app_commands.Choice[str]):

        key = type.value
        label = type.name

        cfg = storage.get_guild_setting(key, interaction.guild.id)

        if not cfg or not cfg.get("channel_id"):
            await interaction.response.send_message(
                f"{label} messages aren't configured yet. Use /{key} message or /{key} embed first.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(int(cfg["channel_id"]))

        if channel is None:
            await interaction.response.send_message(f"The configured {key} channel no longer exists.", ephemeral=True)
            return

        mention = key == "welcome"

        payload = _build_greet_payload(cfg, interaction.user, interaction.guild, mention=mention)

        await channel.send(**payload)

        await interaction.response.send_message(f"Sent a test {key} message in {channel.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Server(bot))
