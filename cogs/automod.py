import re
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed, send_log
from storage import storage


# ============================================================
# REGEX
# ============================================================

INVITE_RE = re.compile(
    r"(discord\.gg/|discord(app)?\.com/invite/)",
    re.IGNORECASE
)

LINK_RE = re.compile(
    r"https?://",
    re.IGNORECASE
)

GIF_RE = re.compile(
    r"\.gif($|\?)|tenor\.com|giphy\.com",
    re.IGNORECASE
)


# ============================================================
# FILTER DEFINITIONS
# ============================================================
# Every filter that only has an on/off switch gets a toggle button.
# Every filter that also has numeric settings gets a "Configure"
# entry in the select menu, which opens a modal.

TOGGLE_FILTERS = {
    "links": "Links",
    "invites": "Invites",
    "gif": "GIFs",
    "duplicate": "Duplicate Messages",
    "bot": "Anti Bot",
    "profanity": "Profanity",
}

CONFIGURABLE_FILTERS = {
    "spam": "Anti Spam",
    "mentions": "Mention Limit",
    "raid": "Raid Protection",
    "emoji": "Emoji Limit",
    "caps": "Caps Filter",
}

ALL_FILTERS = {**TOGGLE_FILTERS, **CONFIGURABLE_FILTERS}

DEFAULTS = {
    "spam": {"enabled": False, "limit": 5, "seconds": 5},
    "mentions": {"enabled": False, "limit": 5},
    "raid": {"enabled": False, "joins": 10, "seconds": 30},
    "emoji": {"enabled": False, "limit": 10},
    "caps": {"enabled": False, "percent": 70},
}


# ============================================================
# SETTINGS
# ============================================================

def get_settings(guild_id: int):

    settings = storage.get_guild_setting(
        "automod",
        guild_id,
        {}
    )

    if not settings:
        settings = {}

        storage.set_guild_setting(
            "automod",
            guild_id,
            settings
        )

    return settings



def update_setting(
    guild_id: int,
    key: str,
    value
):

    settings = get_settings(guild_id)

    settings[key] = value

    storage.set_guild_setting(
        "automod",
        guild_id,
        settings
    )



def build_panel_embed(guild_id: int) -> discord.Embed:

    settings = get_settings(guild_id)

    embed = make_embed("AutoMod Panel")

    for key, label in ALL_FILTERS.items():

        cfg = settings.get(key, {})
        enabled = cfg.get("enabled", False)

        status = "🟢 Enabled" if enabled else "🔴 Disabled"

        if key in CONFIGURABLE_FILTERS:

            extras = {
                k: v
                for k, v in {**DEFAULTS.get(key, {}), **cfg}.items()
                if k != "enabled"
            }

            if extras:
                extra_text = ", ".join(
                    f"{k}: `{v}`" for k, v in extras.items()
                )
                status += f"\n{extra_text}"

        embed.add_field(
            name=label,
            value=status,
            inline=True
        )

    embed.set_footer(
        text="Use the buttons to toggle filters, or the dropdown to configure limits."
    )

    return embed



# ============================================================
# MODALS (for filters with numeric settings)
# ============================================================

class SpamModal(discord.ui.Modal, title="Configure Anti Spam"):

    def __init__(self, cog, guild_id, current):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id

        self.limit = discord.ui.TextInput(
            label="Message limit",
            default=str(current.get("limit", 5)),
        )
        self.seconds = discord.ui.TextInput(
            label="Time window (seconds)",
            default=str(current.get("seconds", 5)),
        )

        self.add_item(self.limit)
        self.add_item(self.seconds)

    async def on_submit(self, interaction: discord.Interaction):

        settings = get_settings(self.guild_id)
        cfg = settings.get("spam", dict(DEFAULTS["spam"]))

        try:
            cfg["limit"] = int(self.limit.value)
            cfg["seconds"] = int(self.seconds.value)
        except ValueError:
            await interaction.response.send_message(
                "Limit and seconds must be numbers.",
                ephemeral=True
            )
            return

        update_setting(self.guild_id, "spam", cfg)

        await self.cog.refresh_panel(interaction)


class MentionsModal(discord.ui.Modal, title="Configure Mention Limit"):

    def __init__(self, cog, guild_id, current):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id

        self.limit = discord.ui.TextInput(
            label="Mention limit",
            default=str(current.get("limit", 5)),
        )

        self.add_item(self.limit)

    async def on_submit(self, interaction: discord.Interaction):

        settings = get_settings(self.guild_id)
        cfg = settings.get("mentions", dict(DEFAULTS["mentions"]))

        try:
            cfg["limit"] = int(self.limit.value)
        except ValueError:
            await interaction.response.send_message(
                "Limit must be a number.",
                ephemeral=True
            )
            return

        update_setting(self.guild_id, "mentions", cfg)

        await self.cog.refresh_panel(interaction)


class RaidModal(discord.ui.Modal, title="Configure Raid Protection"):

    def __init__(self, cog, guild_id, current):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id

        self.joins = discord.ui.TextInput(
            label="Join count",
            default=str(current.get("joins", 10)),
        )
        self.seconds = discord.ui.TextInput(
            label="Time window (seconds)",
            default=str(current.get("seconds", 30)),
        )

        self.add_item(self.joins)
        self.add_item(self.seconds)

    async def on_submit(self, interaction: discord.Interaction):

        settings = get_settings(self.guild_id)
        cfg = settings.get("raid", dict(DEFAULTS["raid"]))

        try:
            cfg["joins"] = int(self.joins.value)
            cfg["seconds"] = int(self.seconds.value)
        except ValueError:
            await interaction.response.send_message(
                "Joins and seconds must be numbers.",
                ephemeral=True
            )
            return

        update_setting(self.guild_id, "raid", cfg)

        await self.cog.refresh_panel(interaction)


class EmojiModal(discord.ui.Modal, title="Configure Emoji Limit"):

    def __init__(self, cog, guild_id, current):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id

        self.limit = discord.ui.TextInput(
            label="Emoji limit",
            default=str(current.get("limit", 10)),
        )

        self.add_item(self.limit)

    async def on_submit(self, interaction: discord.Interaction):

        settings = get_settings(self.guild_id)
        cfg = settings.get("emoji", dict(DEFAULTS["emoji"]))

        try:
            cfg["limit"] = int(self.limit.value)
        except ValueError:
            await interaction.response.send_message(
                "Limit must be a number.",
                ephemeral=True
            )
            return

        update_setting(self.guild_id, "emoji", cfg)

        await self.cog.refresh_panel(interaction)


class CapsModal(discord.ui.Modal, title="Configure Caps Filter"):

    def __init__(self, cog, guild_id, current):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id

        self.percent = discord.ui.TextInput(
            label="Max caps percentage",
            default=str(current.get("percent", 70)),
        )

        self.add_item(self.percent)

    async def on_submit(self, interaction: discord.Interaction):

        settings = get_settings(self.guild_id)
        cfg = settings.get("caps", dict(DEFAULTS["caps"]))

        try:
            cfg["percent"] = int(self.percent.value)
        except ValueError:
            await interaction.response.send_message(
                "Percentage must be a number.",
                ephemeral=True
            )
            return

        update_setting(self.guild_id, "caps", cfg)

        await self.cog.refresh_panel(interaction)


MODALS = {
    "spam": SpamModal,
    "mentions": MentionsModal,
    "raid": RaidModal,
    "emoji": EmojiModal,
    "caps": CapsModal,
}


# ============================================================
# PANEL VIEW
# ============================================================

class ConfigureSelect(discord.ui.Select):

    def __init__(self, cog, guild_id):

        options = [
            discord.SelectOption(
                label=f"Configure {label}",
                value=key
            )
            for key, label in CONFIGURABLE_FILTERS.items()
        ]

        super().__init__(
            placeholder="Configure a filter's settings...",
            options=options,
            min_values=1,
            max_values=1
        )

        self.cog = cog
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):

        key = self.values[0]

        settings = get_settings(self.guild_id)
        current = settings.get(key, dict(DEFAULTS.get(key, {})))

        modal = MODALS[key](self.cog, self.guild_id, current)

        await interaction.response.send_modal(modal)


class ToggleButton(discord.ui.Button):

    def __init__(self, cog, guild_id, key, label):

        settings = get_settings(guild_id)
        enabled = settings.get(key, {}).get("enabled", False)

        super().__init__(
            label=label,
            style=(
                discord.ButtonStyle.success
                if enabled
                else discord.ButtonStyle.danger
            ),
            emoji="🟢" if enabled else "🔴"
        )

        self.cog = cog
        self.guild_id = guild_id
        self.key = key

    async def callback(self, interaction: discord.Interaction):

        settings = get_settings(self.guild_id)
        cfg = settings.get(self.key, {})

        cfg["enabled"] = not cfg.get("enabled", False)

        update_setting(self.guild_id, self.key, cfg)

        await self.cog.refresh_panel(interaction)


class AutoModPanelView(discord.ui.View):

    def __init__(self, cog, guild_id):

        super().__init__(timeout=None)

        self.cog = cog
        self.guild_id = guild_id

        for key, label in ALL_FILTERS.items():
            self.add_item(ToggleButton(cog, guild_id, key, label))

        self.add_item(ConfigureSelect(cog, guild_id))



# ============================================================
# GROUPS
# ============================================================
# Everything lives under /automod: the dashboard is "/automod panel",
# and list management is nested as subgroups underneath it.

automod_group = app_commands.Group(
    name="automod",
    description="Configure AutoMod"
)

profanity_group = app_commands.Group(
    name="profanity",
    description="Manage profanity filter words",
    parent=automod_group
)

whitelist_group = app_commands.Group(
    name="whitelist",
    description="Manage AutoMod whitelist",
    parent=automod_group
)

blacklist_group = app_commands.Group(
    name="blacklist",
    description="Manage AutoMod blacklist",
    parent=automod_group
)

ignore_group = app_commands.Group(
    name="ignore",
    description="Manage ignored channels/roles",
    parent=automod_group
)


# ============================================================
# AUTOMOD COG
# ============================================================

class AutoMod(commands.Cog):


    def __init__(self, bot):

        self.bot = bot


        self.recent_messages = defaultdict(
            lambda: defaultdict(deque)
        )


        self.last_message_content = defaultdict(dict)


        self.recent_joins = defaultdict(deque)



    # ========================================================
    # HELPERS
    # ========================================================


    def _is_ignored(
        self,
        guild_id,
        member,
        channel
    ):

        ignored = storage.get_list(
            "ignore",
            guild_id
        )


        if channel.id in ignored:
            return True


        for role in getattr(member, "roles", []):

            if role.id in ignored:
                return True


        return False



    def _is_whitelisted(
        self,
        guild_id,
        member
    ):

        whitelist = storage.get_list(
            "whitelist",
            guild_id
        )


        if member.id in whitelist:
            return True


        for role in getattr(member, "roles", []):

            if role.id in whitelist:
                return True


        if member.guild_permissions.administrator:
            return True


        return False



    async def _violation(
        self,
        message,
        reason
    ):

        try:
            await message.delete()

        except discord.HTTPException:
            pass


        embed = make_embed(
            "AutoMod Action",
            (
                f"Deleted message from "
                f"{message.author.mention}\n\n"
                f"Reason: {reason}"
            )
        )


        await send_log(
            message.guild,
            embed
        )



    async def refresh_panel(self, interaction: discord.Interaction):
        """Rebuild and edit the panel message after a button/modal action."""

        embed = build_panel_embed(interaction.guild.id)
        view = AutoModPanelView(self, interaction.guild.id)

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)



    # ========================================================
    # PANEL COMMAND
    # ========================================================


    @automod_group.command(
        name="panel",
        description="Opens the AutoMod panel to toggle and configure filters."
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def automod_panel(
        self,
        interaction: discord.Interaction
    ):

        embed = build_panel_embed(interaction.guild.id)
        view = AutoModPanelView(self, interaction.guild.id)

        await interaction.response.send_message(
            embed=embed,
            view=view
        )



    # ========================================================
    # PROFANITY (word list management)
    # ========================================================


    @profanity_group.command(
        name="add",
        description="Add a word to the profanity filter."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_add(
        self,
        interaction: discord.Interaction,
        word: str
    ):

        settings = get_settings(
            interaction.guild.id
        )


        profanity = settings.get(
            "profanity",
            {
                "enabled": False,
                "words": []
            }
        )


        word = word.lower()


        if word not in profanity.get("words", []):
            profanity.setdefault("words", []).append(word)


        update_setting(
            interaction.guild.id,
            "profanity",
            profanity
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Profanity Added",
                f"Blocked: `{word}`"
            ),
            ephemeral=True
        )



    @profanity_group.command(
        name="remove",
        description="Remove a word from the profanity filter."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_remove(
        self,
        interaction: discord.Interaction,
        word: str
    ):

        settings = get_settings(
            interaction.guild.id
        )


        profanity = settings.get(
            "profanity",
            {
                "enabled": False,
                "words": []
            }
        )


        word = word.lower()


        if word in profanity.get("words", []):
            profanity["words"].remove(word)


        update_setting(
            interaction.guild.id,
            "profanity",
            profanity
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Profanity Removed",
                f"Removed: `{word}`"
            ),
            ephemeral=True
        )



    @profanity_group.command(
        name="list",
        description="List all blocked words."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_list(
        self,
        interaction: discord.Interaction
    ):

        settings = get_settings(
            interaction.guild.id
        )


        words = settings.get(
            "profanity",
            {}
        ).get(
            "words",
            []
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Blocked Words",
                ", ".join(words)
                if words
                else "No blocked words"
            ),
            ephemeral=True
        )



    # ========================================================
    # WHITELIST
    # ========================================================


    @whitelist_group.command(
        name="add",
        description="Whitelist a user or role from AutoMod."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelist_add(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
        role: discord.Role = None
    ):

        target = user or role


        if target is None:
            await interaction.response.send_message(
                "Provide a user or role.",
                ephemeral=True
            )
            return


        storage.add_to_list(
            "whitelist",
            interaction.guild.id,
            target.id
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Whitelist Updated",
                f"Added {target.mention}"
            )
        )



    @whitelist_group.command(
        name="remove",
        description="Remove a user or role from the whitelist."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelist_remove(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
        role: discord.Role = None
    ):

        target = user or role


        if target is None:
            await interaction.response.send_message(
                "Provide a user or role.",
                ephemeral=True
            )
            return


        storage.remove_from_list(
            "whitelist",
            interaction.guild.id,
            target.id
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Whitelist Updated",
                f"Removed {target.mention}"
            )
        )



    # ========================================================
    # BLACKLIST
    # ========================================================


    @blacklist_group.command(
        name="add",
        description="Blacklist a user or role."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def blacklist_add(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
        role: discord.Role = None
    ):

        target = user or role


        if target is None:
            await interaction.response.send_message(
                "Provide a user or role.",
                ephemeral=True
            )
            return


        storage.add_to_list(
            "blacklist",
            interaction.guild.id,
            target.id
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Blacklist Updated",
                f"Added {target.mention}"
            )
        )



    @blacklist_group.command(
        name="remove",
        description="Remove a user or role from the blacklist."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def blacklist_remove(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
        role: discord.Role = None
    ):

        target = user or role


        if target is None:
            await interaction.response.send_message(
                "Provide a user or role.",
                ephemeral=True
            )
            return


        storage.remove_from_list(
            "blacklist",
            interaction.guild.id,
            target.id
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Blacklist Updated",
                f"Removed {target.mention}"
            )
        )



    # ========================================================
    # IGNORE
    # ========================================================


    @ignore_group.command(
        name="add",
        description="Ignore a channel or role for AutoMod."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def ignore_add(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
        role: discord.Role = None
    ):

        target = channel or role


        if target is None:
            await interaction.response.send_message(
                "Provide channel or role.",
                ephemeral=True
            )
            return


        storage.add_to_list(
            "ignore",
            interaction.guild.id,
            target.id
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Ignore Updated",
                f"Ignoring {target.mention}"
            )
        )



    @ignore_group.command(
        name="remove",
        description="Remove a channel or role from the ignore list."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def ignore_remove(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
        role: discord.Role = None
    ):

        target = channel or role


        if target is None:
            await interaction.response.send_message(
                "Provide channel or role.",
                ephemeral=True
            )
            return


        storage.remove_from_list(
            "ignore",
            interaction.guild.id,
            target.id
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Ignore Updated",
                f"Removed {target.mention}"
            )
        )



    # ========================================================
    # MESSAGE FILTER
    # ========================================================


    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message
    ):

        if (
            message.author.bot
            or not message.guild
            or not isinstance(message.author, discord.Member)
        ):
            return


        if self._is_whitelisted(
            message.guild.id,
            message.author
        ):
            return


        if self._is_ignored(
            message.guild.id,
            message.author,
            message.channel
        ):
            return



        settings = get_settings(
            message.guild.id
        )



        # LINKS

        cfg = settings.get("links", {})

        if cfg.get("enabled"):

            if LINK_RE.search(message.content):

                await self._violation(
                    message,
                    "Links are not allowed."
                )
                return



        # INVITES

        cfg = settings.get("invites", {})

        if cfg.get("enabled"):

            if INVITE_RE.search(message.content):

                await self._violation(
                    message,
                    "Discord invites are not allowed."
                )
                return



        # GIF

        cfg = settings.get("gif", {})

        if cfg.get("enabled"):

            if GIF_RE.search(message.content):

                await self._violation(
                    message,
                    "GIFs are disabled."
                )
                return



        # PROFANITY

        cfg = settings.get(
            "profanity",
            {}
        )

        if cfg.get("enabled"):

            content = message.content.lower()

            for word in cfg.get("words", []):

                if word in content:

                    await self._violation(
                        message,
                        "Profanity detected."
                    )
                    return



        # DUPLICATE

        cfg = settings.get(
            "duplicate",
            {}
        )

        if cfg.get("enabled"):

            previous = self.last_message_content[
                message.guild.id
            ].get(
                message.author.id
            )


            self.last_message_content[
                message.guild.id
            ][
                message.author.id
            ] = message.content


            if previous == message.content:

                await self._violation(
                    message,
                    "Duplicate message."
                )
                return



        # SPAM

        cfg = settings.get(
            "spam",
            {}
        )


        if cfg.get("enabled"):

            now = time.time()


            messages = self.recent_messages[
                message.guild.id
            ][
                message.author.id
            ]


            messages.append(now)


            while (
                messages
                and now - messages[0] > cfg.get(
                    "seconds",
                    5
                )
            ):
                messages.popleft()



            if len(messages) > cfg.get(
                "limit",
                5
            ):

                await self._violation(
                    message,
                    "Spam detected."
                )



    # ========================================================
    # MEMBER JOIN PROTECTION
    # ========================================================


    @commands.Cog.listener()
    async def on_member_join(
        self,
        member: discord.Member
    ):

        guild = member.guild


        settings = get_settings(
            guild.id
        )


        cfg = settings.get(
            "bot",
            {}
        )


        if (
            cfg.get("enabled")
            and member.bot
            and not self._is_whitelisted(
                guild.id,
                member
            )
        ):

            try:

                await member.kick(
                    reason="Unauthorized bot"
                )


            except discord.HTTPException:
                pass



        cfg = settings.get(
            "raid",
            {}
        )


        if cfg.get("enabled"):

            now = time.time()


            joins = self.recent_joins[
                guild.id
            ]


            joins.append(now)


            while (
                joins
                and now - joins[0] > cfg.get(
                    "seconds",
                    30
                )
            ):
                joins.popleft()



            if len(joins) >= cfg.get(
                "joins",
                10
            ):

                await send_log(
                    guild,
                    make_embed(
                        "Raid Alert",
                        f"{len(joins)} users joined quickly."
                    )
                )



# ============================================================
# SETUP
# ============================================================


async def setup(
    bot: commands.Bot
):

    cog = AutoMod(bot)

    await bot.add_cog(cog)

    bot.tree.add_command(automod_group)
