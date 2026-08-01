import re

import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed

BLACK = discord.Color.from_str("#000000")

MENTION_RE = re.compile(r"<@!?(\d+)>")


# ============================================================
# PURGE FILTER DEFINITIONS
# ============================================================
# key -> (button label, needs a "member" text field, needs a "text" field)

PURGE_FILTERS = {
    "user": ("By User", True, False),
    "bots": ("Bots", False, False),
    "links": ("Links", False, False),
    "invites": ("Invites", False, False),
    "images": ("Images", False, False),
    "embeds": ("Embeds", False, False),
    "files": ("Files/Attachments", False, False),
    "mentions": ("Mentions", False, False),
    "contains": ("Contains Text", False, True),
}


async def _resolve_member(guild: discord.Guild, raw: str):

    raw = raw.strip()

    match = MENTION_RE.match(raw)

    user_id = match.group(1) if match else raw

    if not user_id.isdigit():
        return None

    member = guild.get_member(int(user_id))

    if member is not None:
        return member

    try:
        return await guild.fetch_member(int(user_id))
    except discord.HTTPException:
        return None


def _build_check(key: str, *, member: discord.Member = None, text: str = None):

    if key == "user":
        return lambda m: m.author.id == member.id

    if key == "bots":
        return lambda m: m.author.bot

    if key == "links":
        return lambda m: "http://" in m.content or "https://" in m.content

    if key == "invites":
        invite_markers = ("discord.gg/", "discord.com/invite/", "discordapp.com/invite/")
        return lambda m: any(marker in m.content.lower() for marker in invite_markers)

    if key == "images":
        image_exts = (".png", ".jpg", ".jpeg", ".gif", ".webp")
        return lambda m: any(a.filename.lower().endswith(image_exts) for a in m.attachments)

    if key == "embeds":
        return lambda m: len(m.embeds) > 0

    if key == "files":
        return lambda m: len(m.attachments) > 0

    if key == "mentions":
        return lambda m: len(m.mentions) > 0 or len(m.role_mentions) > 0

    if key == "contains":
        return lambda m: text.lower() in m.content.lower()

    raise ValueError(f"Unknown purge filter: {key}")


# ============================================================
# MODALS
# ============================================================

class PurgeAmountModal(discord.ui.Modal):
    """Used for filters that only need an amount (bots, links, invites, images, embeds, files, mentions)."""

    def __init__(self, key: str, label: str):

        super().__init__(title=f"Purge: {label}")

        self.key = key

        self.amount = discord.ui.TextInput(
            label="Messages to scan (1-200)",
            default="100",
        )

        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):

        try:
            amount = int(self.amount.value)
        except ValueError:
            await interaction.response.send_message("Amount must be a number.", ephemeral=True)
            return

        amount = max(1, min(amount, 200))

        await interaction.response.defer(ephemeral=True)

        check = _build_check(self.key)

        deleted = await interaction.channel.purge(limit=amount, check=check)

        await interaction.followup.send(f"Deleted {len(deleted)} matching messages.", ephemeral=True)


class PurgeUserModal(discord.ui.Modal, title="Purge: By User"):

    def __init__(self):

        super().__init__()

        self.member_input = discord.ui.TextInput(
            label="User (mention or ID)",
        )
        self.amount = discord.ui.TextInput(
            label="Messages to scan (1-200)",
            default="100",
        )

        self.add_item(self.member_input)
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):

        try:
            amount = int(self.amount.value)
        except ValueError:
            await interaction.response.send_message("Amount must be a number.", ephemeral=True)
            return

        amount = max(1, min(amount, 200))

        member = await _resolve_member(interaction.guild, self.member_input.value)

        if member is None:
            await interaction.response.send_message(
                "Couldn't find that user. Provide a mention or a valid user ID.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        check = _build_check("user", member=member)

        deleted = await interaction.channel.purge(limit=amount, check=check)

        await interaction.followup.send(f"Deleted {len(deleted)} matching messages.", ephemeral=True)


class PurgeContainsModal(discord.ui.Modal, title="Purge: Contains Text"):

    def __init__(self):

        super().__init__()

        self.text_input = discord.ui.TextInput(
            label="Text to search for",
        )
        self.amount = discord.ui.TextInput(
            label="Messages to scan (1-200)",
            default="100",
        )

        self.add_item(self.text_input)
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):

        try:
            amount = int(self.amount.value)
        except ValueError:
            await interaction.response.send_message("Amount must be a number.", ephemeral=True)
            return

        amount = max(1, min(amount, 200))

        await interaction.response.defer(ephemeral=True)

        check = _build_check("contains", text=self.text_input.value)

        deleted = await interaction.channel.purge(limit=amount, check=check)

        await interaction.followup.send(f"Deleted {len(deleted)} matching messages.", ephemeral=True)


# ============================================================
# PANEL VIEW
# ============================================================

class PurgeButton(discord.ui.Button):

    def __init__(self, key: str, label: str):

        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
        )

        self.key = key

    async def callback(self, interaction: discord.Interaction):

        label, needs_member, needs_text = PURGE_FILTERS[self.key]

        if needs_member:
            modal = PurgeUserModal()
        elif needs_text:
            modal = PurgeContainsModal()
        else:
            modal = PurgeAmountModal(self.key, label)

        await interaction.response.send_modal(modal)


class PurgePanelView(discord.ui.View):

    def __init__(self, timeout: int = 180):

        super().__init__(timeout=timeout)

        for key, (label, _, _) in PURGE_FILTERS.items():
            self.add_item(PurgeButton(key, label))


def build_purge_embed() -> discord.Embed:

    embed = discord.Embed(
        title="Purge Messages",
        description="Pick a filter below. You'll be asked for an amount (and any extra details) before anything is deleted.",
        color=BLACK,
    )

    return embed


class Messages(commands.Cog):
    """Message clearing, purge, and snipe commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # channel_id -> deleted message data
        self.snipes: dict[int, dict] = {}
        # channel_id -> edited message data
        self.edit_snipes: dict[int, dict] = {}

    # ---------------------------------------------------------------------
    # Snipe caching
    # ---------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot:
            return
        self.snipes[message.channel.id] = {
            "content": message.content,
            "author": message.author,
            "created_at": message.created_at,
            "attachment_url": message.attachments[0].url if message.attachments else None,
        }

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or before.content == after.content:
            return
        self.edit_snipes[before.channel.id] = {
            "before": before.content,
            "after": after.content,
            "author": before.author,
            "created_at": before.created_at,
        }

    @app_commands.command(name="snipe", description="Shows the last deleted message.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def snipe(self, interaction: discord.Interaction):
        data = self.snipes.get(interaction.channel.id)
        if not data:
            await interaction.response.send_message("There is nothing to snipe in this channel.", ephemeral=True)
            return
        embed = discord.Embed(
            description=data["content"] or "*No text content*",
            color=BLACK,
            timestamp=data["created_at"],
        )
        embed.set_author(name=str(data["author"]), icon_url=data["author"].display_avatar.url)
        if data["attachment_url"]:
            embed.set_image(url=data["attachment_url"])
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="editsnipe", description="Shows the last edited message.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def editsnipe(self, interaction: discord.Interaction):
        data = self.edit_snipes.get(interaction.channel.id)
        if not data:
            await interaction.response.send_message("There is nothing to editsnipe in this channel.", ephemeral=True)
            return
        embed = discord.Embed(color=BLACK, timestamp=data["created_at"])
        embed.set_author(name=str(data["author"]), icon_url=data["author"].display_avatar.url)
        embed.add_field(name="Before", value=data["before"] or "*No text content*", inline=False)
        embed.add_field(name="After", value=data["after"] or "*No text content*", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clear", description="Deletes recent messages.")
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)

    # ---------------------------------------------------------------------
    # Purge panel
    # ---------------------------------------------------------------------
    @app_commands.command(name="purge", description="Delete messages matching a filter.")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction):
        embed = build_purge_embed()
        view = PurgePanelView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Messages(bot))
