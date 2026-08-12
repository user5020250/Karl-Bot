import logging

import discord
from discord import app_commands
from discord.ext import commands

from helpers import (
    LOG_CATEGORIES,
    get_log_channels,
    set_log_channel,
    clear_log_channel,
    send_log,
    make_embed,
)

log = logging.getLogger("bot")


def build_panel_embed(guild_id: int) -> discord.Embed:
    settings = get_log_channels(guild_id)
    lines = []
    for key, label in LOG_CATEGORIES.items():
        channel_id = settings.get(key)
        status = f"<#{channel_id}>" if channel_id else "Not set"
        lines.append(f"**{label}** — {status}")
    return make_embed("Logs Panel", "\n".join(lines))


# ============================================================
# PANEL VIEW (category select + channel select + disable button)
# ============================================================

class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=label, value=key)
            for key, label in LOG_CATEGORIES.items()
        ]
        super().__init__(placeholder="Choose a log category to configure", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: LogsPanelView = self.view
        view.selected = self.values[0]
        view.refresh()
        await interaction.response.edit_message(embed=build_panel_embed(view.guild_id), view=view)


class LogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="Select a category first",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            disabled=True,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        view: LogsPanelView = self.view
        if view.selected is None:
            await interaction.response.send_message("Select a category first.", ephemeral=True)
            return

        channel = self.values[0]
        set_log_channel(view.guild_id, view.selected, channel.id)
        view.refresh()
        await interaction.response.edit_message(embed=build_panel_embed(view.guild_id), view=view)


class DisableButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Disable", style=discord.ButtonStyle.danger, disabled=True, row=2)

    async def callback(self, interaction: discord.Interaction):
        view: LogsPanelView = self.view
        clear_log_channel(view.guild_id, view.selected)
        view.refresh()
        await interaction.response.edit_message(embed=build_panel_embed(view.guild_id), view=view)


class LogsPanelView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.selected: str | None = None

        self.category_select = CategorySelect()
        self.channel_select = LogChannelSelect()
        self.disable_btn = DisableButton()

        self.add_item(self.category_select)
        self.add_item(self.channel_select)
        self.add_item(self.disable_btn)

    def refresh(self):
        if self.selected is None:
            self.channel_select.disabled = True
            self.channel_select.placeholder = "Select a category first"
            self.disable_btn.disabled = True
            return

        label = LOG_CATEGORIES[self.selected]
        channel_id = get_log_channels(self.guild_id).get(self.selected)

        self.channel_select.disabled = False
        self.channel_select.placeholder = f"Set channel for {label}"
        self.disable_btn.disabled = channel_id is None
        self.category_select.placeholder = f"Category: {label}"


# ============================================================
# COG
# ============================================================

class Logs(commands.Cog):
    """Configurable per-category logging: /logs panel + automatic event logging."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --------------------------------------------------------
    # PANEL
    # --------------------------------------------------------

    @app_commands.command(name="logs", description="Open the logging control panel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs(self, interaction: discord.Interaction):
        view = LogsPanelView(interaction.guild.id)
        view.refresh()
        await interaction.response.send_message(embed=build_panel_embed(interaction.guild.id), view=view)

    # --------------------------------------------------------
    # MESSAGES
    # --------------------------------------------------------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author == self.bot.user:
            return
        embed = make_embed(
            "Message Deleted",
            f"**Author:** {message.author.mention}\n**Channel:** {message.channel.mention}",
        )
        content = message.content or "*No text content*"
        embed.add_field(name="Content", value=content[:1024], inline=False)
        await send_log(message.guild, embed, category="messages")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author == self.bot.user or before.content == after.content:
            return
        embed = make_embed(
            "Message Edited",
            f"**Author:** {before.author.mention}\n**Channel:** {before.channel.mention}",
        )
        embed.add_field(name="Before", value=(before.content or "*No text content*")[:1024], inline=False)
        embed.add_field(name="After", value=(after.content or "*No text content*")[:1024], inline=False)
        await send_log(before.guild, embed, category="messages")

    # --------------------------------------------------------
    # MEMBERS
    # --------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = make_embed(
            "Member Joined",
            f"{member.mention} ({member.id})\nAccount created: {discord.utils.format_dt(member.created_at, 'R')}",
        )
        await send_log(member.guild, embed, category="members")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = make_embed(
            "Member Left",
            f"{member} ({member.id})",
        )
        await send_log(member.guild, embed, category="members")

    # --------------------------------------------------------
    # CHANNELS & ROLES
    # --------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        embed = make_embed("Channel Created", f"{channel.mention} (`{channel.type}`)")
        await send_log(channel.guild, embed, category="channels_roles")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        embed = make_embed("Channel Deleted", f"#{channel.name} (`{channel.type}`)")
        await send_log(channel.guild, embed, category="channels_roles")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        embed = make_embed("Role Created", f"{role.mention} ({role.id})")
        await send_log(role.guild, embed, category="channels_roles")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        embed = make_embed("Role Deleted", f"{role.name} ({role.id})")
        await send_log(role.guild, embed, category="channels_roles")

    # --------------------------------------------------------
    # SERVER
    # --------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** {before.name} → {after.name}")
        if before.icon != after.icon:
            changes.append("**Icon:** changed")
        if not changes:
            return
        embed = make_embed("Server Updated", "\n".join(changes))
        await send_log(after, embed, category="server")

    # --------------------------------------------------------
    # VOICE
    # --------------------------------------------------------

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        if before.channel == after.channel:
            return

        if before.channel is None and after.channel is not None:
            embed = make_embed("Voice Join", f"{member.mention} joined {after.channel.mention}")
        elif before.channel is not None and after.channel is None:
            embed = make_embed("Voice Leave", f"{member.mention} left {before.channel.mention}")
        else:
            embed = make_embed(
                "Voice Move",
                f"{member.mention} moved from {before.channel.mention} to {after.channel.mention}",
            )

        await send_log(member.guild, embed, category="voice")


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
