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

EMOJI_RE = re.compile(
    r"<a?:\w+:\d+>|"
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "]"
)


DEFAULTS = {
    "spam": {"enabled": False, "limit": 5, "seconds": 5},
    "mentions": {"enabled": False, "limit": 5},
    "raid": {"enabled": False, "joins": 10, "seconds": 30},
    "emoji": {"enabled": False, "limit": 10},
    "caps": {"enabled": False, "percent": 70},
}

SETTINGS_KEY = "automod3"  # fresh storage key, keeps old data out of the way


# ============================================================
# FILTER METADATA (drives the panel: labels + which ones have
# configurable numeric limits and what those fields are)
# ============================================================

FILTER_INFO = {
    "links": {"label": "Links", "fields": None},
    "invites": {"label": "Invites", "fields": None},
    "gif": {"label": "GIFs", "fields": None},
    "duplicate": {"label": "Duplicate Messages", "fields": None},
    "bot": {"label": "Anti Bot", "fields": None},
    "profanity": {"label": "Profanity", "fields": None},
    "spam": {
        "label": "Anti Spam",
        "fields": [
            ("limit", "Max messages allowed", "e.g. 5"),
            ("seconds", "Time window (seconds)", "e.g. 5"),
        ],
    },
    "mentions": {
        "label": "Mention Limit",
        "fields": [("limit", "Max mentions per message", "e.g. 5")],
    },
    "raid": {
        "label": "Raid Protection",
        "fields": [
            ("joins", "Joins to trigger an alert", "e.g. 10"),
            ("seconds", "Time window (seconds)", "e.g. 30"),
        ],
    },
    "emoji": {
        "label": "Emoji Limit",
        "fields": [("limit", "Max emoji per message", "e.g. 10")],
    },
    "caps": {
        "label": "Caps Filter",
        "fields": [("percent", "Max uppercase percent (0-100)", "e.g. 70")],
    },
}


def default_cfg(key: str) -> dict:
    if key in DEFAULTS:
        return dict(DEFAULTS[key])
    if key == "profanity":
        return {"enabled": False, "words": []}
    return {"enabled": False}


# ============================================================
# SETTINGS HELPERS
# ============================================================

def get_settings(guild_id: int) -> dict:
    settings = storage.get_guild_setting(SETTINGS_KEY, guild_id, {})
    if not settings:
        settings = {}
        storage.set_guild_setting(SETTINGS_KEY, guild_id, settings)
    return settings


def update_setting(guild_id: int, key: str, value) -> None:
    settings = get_settings(guild_id)
    settings[key] = value
    storage.set_guild_setting(SETTINGS_KEY, guild_id, settings)


def set_enabled(guild_id: int, key: str, enabled: bool, defaults: dict | None = None) -> dict:
    settings = get_settings(guild_id)
    cfg = settings.get(key, dict(defaults) if defaults else {})
    cfg["enabled"] = enabled
    update_setting(guild_id, key, cfg)
    return cfg


def status_embed(filter_name: str, cfg: dict) -> discord.Embed:
    enabled = cfg.get("enabled", False)
    status = "Enabled" if enabled else "Disabled"

    extras = {k: v for k, v in cfg.items() if k != "enabled" and k != "words"}
    if extras:
        status += "\n" + ", ".join(f"{k}: `{v}`" for k, v in extras.items())

    return make_embed(filter_name, status)


def build_panel_embed(guild_id: int) -> discord.Embed:
    settings = get_settings(guild_id)
    lines = []
    for key, info in FILTER_INFO.items():
        cfg = settings.get(key, {})
        enabled = cfg.get("enabled", False)
        status = "Enabled" if enabled else "Disabled"

        extras = ""
        if info["fields"]:
            parts = [f"{fkey}: {cfg.get(fkey, dict(DEFAULTS[key])[fkey])}" for fkey, _, _ in info["fields"]]
            extras = " (" + ", ".join(parts) + ")"

        lines.append(f"**{info['label']}** — {status}{extras}")

    return make_embed("AutoMod Panel", "\n".join(lines))


def _parse_int(raw: str, field_label: str) -> int:
    """Raises ValueError with a friendly message if raw isn't a valid non-negative int."""
    try:
        value = int(raw.strip())
    except (ValueError, AttributeError):
        raise ValueError(f"`{field_label}` must be a whole number.")
    if value < 0:
        raise ValueError(f"`{field_label}` must be zero or greater.")
    return value


# ============================================================
# LIMIT CONFIG MODAL (generic — used for spam/mentions/raid/emoji/caps)
# ============================================================

class LimitConfigModal(discord.ui.Modal):
    def __init__(
        self,
        key: str,
        label: str,
        fields: list,
        current: dict,
        guild_id: int,
        panel_message: discord.Message | None = None,
        panel_view: "AutoModPanelView | None" = None,
    ):
        super().__init__(title=f"Configure {label}")
        self.key = key
        self.label = label
        self.fields_meta = fields
        self.guild_id = guild_id
        self.panel_message = panel_message
        self.panel_view = panel_view
        self.inputs = {}

        for field_key, field_label, placeholder in fields:
            text_input = discord.ui.TextInput(
                label=field_label,
                placeholder=placeholder,
                default=str(current.get(field_key, "")),
                required=True,
                max_length=6,
            )
            self.inputs[field_key] = text_input
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction):
        parsed = {}
        for field_key, field_label, _ in self.fields_meta:
            try:
                parsed[field_key] = _parse_int(self.inputs[field_key].value, field_label)
            except ValueError as e:
                await interaction.response.send_message(str(e), ephemeral=True)
                return

        if self.key == "caps" and parsed.get("percent", 0) > 100:
            await interaction.response.send_message(
                "`Max uppercase percent` must be between 0 and 100.", ephemeral=True
            )
            return

        settings = get_settings(self.guild_id)
        cfg = settings.get(self.key, default_cfg(self.key))
        cfg.update(parsed)
        update_setting(self.guild_id, self.key, cfg)

        if self.panel_message is not None:
            try:
                await self.panel_message.edit(embed=build_panel_embed(self.guild_id), view=self.panel_view)
            except discord.HTTPException:
                pass

        await interaction.response.send_message(embed=status_embed(self.label, cfg), ephemeral=True)


# ============================================================
# PANEL VIEW (select + enable/disable/configure buttons)
# ============================================================

class FilterSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=info["label"], value=key)
            for key, info in FILTER_INFO.items()
        ]
        super().__init__(placeholder="Choose a filter to manage", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: AutoModPanelView = self.view
        view.selected = self.values[0]
        view.refresh()
        await interaction.response.edit_message(embed=build_panel_embed(view.guild_id), view=view)


class EnableButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Enable", style=discord.ButtonStyle.success, disabled=True, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: AutoModPanelView = self.view
        key = view.selected
        set_enabled(view.guild_id, key, True, default_cfg(key))
        view.refresh()
        await interaction.response.edit_message(embed=build_panel_embed(view.guild_id), view=view)


class DisableButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Disable", style=discord.ButtonStyle.danger, disabled=True, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: AutoModPanelView = self.view
        key = view.selected
        set_enabled(view.guild_id, key, False, default_cfg(key))
        view.refresh()
        await interaction.response.edit_message(embed=build_panel_embed(view.guild_id), view=view)


class ConfigureButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Configure Limits", style=discord.ButtonStyle.primary, disabled=True, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: AutoModPanelView = self.view
        key = view.selected
        info = FILTER_INFO[key]

        if not info["fields"]:
            await interaction.response.send_message("This filter has no configurable limits.", ephemeral=True)
            return

        settings = get_settings(view.guild_id)
        current = settings.get(key, default_cfg(key))
        modal = LimitConfigModal(
            key, info["label"], info["fields"], current, view.guild_id,
            panel_message=interaction.message, panel_view=view,
        )
        await interaction.response.send_modal(modal)


class AutoModPanelView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.selected: str | None = None

        self.select = FilterSelect()
        self.enable_btn = EnableButton()
        self.disable_btn = DisableButton()
        self.configure_btn = ConfigureButton()

        self.add_item(self.select)
        self.add_item(self.enable_btn)
        self.add_item(self.disable_btn)
        self.add_item(self.configure_btn)

    def refresh(self):
        if self.selected is None:
            self.enable_btn.disabled = True
            self.disable_btn.disabled = True
            self.configure_btn.disabled = True
            return

        info = FILTER_INFO[self.selected]
        settings = get_settings(self.guild_id)
        cfg = settings.get(self.selected, {})
        enabled = cfg.get("enabled", False)

        self.enable_btn.disabled = enabled
        self.disable_btn.disabled = not enabled
        self.configure_btn.disabled = info["fields"] is None
        self.select.placeholder = f"Filter: {info['label']}"


# ============================================================
# COMMAND GROUPS
# ============================================================

automod_group = app_commands.Group(
    name="automod",
    description="Configure AutoMod protections"
)

profanity_group = app_commands.Group(name="profanity", description="Profanity filter", parent=automod_group)
whitelist_group = app_commands.Group(name="whitelist", description="Manage AutoMod whitelist", parent=automod_group)
blacklist_group = app_commands.Group(name="blacklist", description="Manage AutoMod blacklist", parent=automod_group)
ignore_group = app_commands.Group(name="ignore", description="Manage ignored channels/roles", parent=automod_group)


# ============================================================
# COG
# ============================================================

class AutoMod(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.recent_messages = defaultdict(lambda: defaultdict(deque))
        self.last_message_content = defaultdict(dict)
        self.recent_joins = defaultdict(deque)

    # --------------------------------------------------------
    # HELPERS
    # --------------------------------------------------------

    def _is_ignored(self, guild_id, member, channel) -> bool:
        ignored = storage.get_list("ignore", guild_id)

        if channel.id in ignored:
            return True

        for role in getattr(member, "roles", []):
            if role.id in ignored:
                return True

        return False

    def _is_whitelisted(self, guild_id, member) -> bool:
        whitelist = storage.get_list("whitelist", guild_id)

        if member.id in whitelist:
            return True

        for role in getattr(member, "roles", []):
            if role.id in whitelist:
                return True

        if member.guild_permissions.administrator:
            return True

        return False

    async def _violation(self, message, reason):
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        embed = make_embed(
            "AutoMod Action",
            f"Deleted message from {message.author.mention}\n\nReason: {reason}",
        )
        await send_log(message.guild, embed)

    # --------------------------------------------------------
    # PANEL
    # --------------------------------------------------------

    @automod_group.command(name="panel", description="Open the AutoMod control panel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_panel(self, interaction: discord.Interaction):
        view = AutoModPanelView(interaction.guild.id)
        view.refresh()
        await interaction.response.send_message(embed=build_panel_embed(interaction.guild.id), view=view)

    # --------------------------------------------------------
    # PROFANITY (word list management stays as commands)
    # --------------------------------------------------------

    @profanity_group.command(name="add", description="Add a word to the profanity filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_add(self, interaction: discord.Interaction, word: str):
        settings = get_settings(interaction.guild.id)
        profanity = settings.get("profanity", {"enabled": False, "words": []})

        word = word.lower()
        if word not in profanity.get("words", []):
            profanity.setdefault("words", []).append(word)

        update_setting(interaction.guild.id, "profanity", profanity)
        await interaction.response.send_message(
            embed=make_embed("Profanity Added", f"Blocked: `{word}`"), ephemeral=True
        )

    @profanity_group.command(name="remove", description="Remove a word from the profanity filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_remove(self, interaction: discord.Interaction, word: str):
        settings = get_settings(interaction.guild.id)
        profanity = settings.get("profanity", {"enabled": False, "words": []})

        word = word.lower()
        if word in profanity.get("words", []):
            profanity["words"].remove(word)

        update_setting(interaction.guild.id, "profanity", profanity)
        await interaction.response.send_message(
            embed=make_embed("Profanity Removed", f"Removed: `{word}`"), ephemeral=True
        )

    @profanity_group.command(name="list", description="List all blocked words.")
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_list(self, interaction: discord.Interaction):
        settings = get_settings(interaction.guild.id)
        words = settings.get("profanity", {}).get("words", [])

        await interaction.response.send_message(
            embed=make_embed("Blocked Words", ", ".join(words) if words else "No blocked words"),
            ephemeral=True,
        )

    # --------------------------------------------------------
    # WHITELIST
    # --------------------------------------------------------

    @whitelist_group.command(name="add", description="Whitelist a user or role from AutoMod.")
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelist_add(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
        role: discord.Role = None,
    ):
        target = user or role
        if target is None:
            await interaction.response.send_message("Provide a user or role.", ephemeral=True)
            return

        storage.add_to_list("whitelist", interaction.guild.id, target.id)
        await interaction.response.send_message(
            embed=make_embed("Whitelist Updated", f"Added {target.mention}")
        )

    @whitelist_group.command(name="remove", description="Remove a user or role from the whitelist.")
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelist_remove(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
        role: discord.Role = None,
    ):
        target = user or role
        if target is None:
            await interaction.response.send_message("Provide a user or role.", ephemeral=True)
            return

        storage.remove_from_list("whitelist", interaction.guild.id, target.id)
        await interaction.response.send_message(
            embed=make_embed("Whitelist Updated", f"Removed {target.mention}")
        )

    # --------------------------------------------------------
    # BLACKLIST
    # --------------------------------------------------------

    @blacklist_group.command(name="add", description="Blacklist a user or role.")
    @app_commands.checks.has_permissions(administrator=True)
    async def blacklist_add(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
        role: discord.Role = None,
    ):
        target = user or role
        if target is None:
            await interaction.response.send_message("Provide a user or role.", ephemeral=True)
            return

        storage.add_to_list("blacklist", interaction.guild.id, target.id)
        await interaction.response.send_message(
            embed=make_embed("Blacklist Updated", f"Added {target.mention}")
        )

    @blacklist_group.command(name="remove", description="Remove a user or role from the blacklist.")
    @app_commands.checks.has_permissions(administrator=True)
    async def blacklist_remove(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
        role: discord.Role = None,
    ):
        target = user or role
        if target is None:
            await interaction.response.send_message("Provide a user or role.", ephemeral=True)
            return

        storage.remove_from_list("blacklist", interaction.guild.id, target.id)
        await interaction.response.send_message(
            embed=make_embed("Blacklist Updated", f"Removed {target.mention}")
        )

    # --------------------------------------------------------
    # IGNORE
    # --------------------------------------------------------

    @ignore_group.command(name="add", description="Ignore a channel or role for AutoMod.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ignore_add(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
        role: discord.Role = None,
    ):
        target = channel or role
        if target is None:
            await interaction.response.send_message("Provide channel or role.", ephemeral=True)
            return

        storage.add_to_list("ignore", interaction.guild.id, target.id)
        await interaction.response.send_message(
            embed=make_embed("Ignore Updated", f"Ignoring {target.mention}")
        )

    @ignore_group.command(name="remove", description="Remove a channel or role from the ignore list.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ignore_remove(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
        role: discord.Role = None,
    ):
        target = channel or role
        if target is None:
            await interaction.response.send_message("Provide channel or role.", ephemeral=True)
            return

        storage.remove_from_list("ignore", interaction.guild.id, target.id)
        await interaction.response.send_message(
            embed=make_embed("Ignore Updated", f"Removed {target.mention}")
        )

    # --------------------------------------------------------
    # MESSAGE FILTER
    # --------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if (
            message.author.bot
            or not message.guild
            or not isinstance(message.author, discord.Member)
        ):
            return

        if self._is_whitelisted(message.guild.id, message.author):
            return

        if self._is_ignored(message.guild.id, message.author, message.channel):
            return

        settings = get_settings(message.guild.id)

        # LINKS
        cfg = settings.get("links", {})
        if cfg.get("enabled") and LINK_RE.search(message.content):
            await self._violation(message, "Links are not allowed.")
            return

        # INVITES
        cfg = settings.get("invites", {})
        if cfg.get("enabled") and INVITE_RE.search(message.content):
            await self._violation(message, "Discord invites are not allowed.")
            return

        # GIF
        cfg = settings.get("gif", {})
        if cfg.get("enabled") and GIF_RE.search(message.content):
            await self._violation(message, "GIFs are disabled.")
            return

        # PROFANITY
        cfg = settings.get("profanity", {})
        if cfg.get("enabled"):
            content = message.content.lower()
            for word in cfg.get("words", []):
                if word in content:
                    await self._violation(message, "Profanity detected.")
                    return

        # DUPLICATE
        cfg = settings.get("duplicate", {})
        if cfg.get("enabled"):
            previous = self.last_message_content[message.guild.id].get(message.author.id)
            self.last_message_content[message.guild.id][message.author.id] = message.content

            if previous == message.content:
                await self._violation(message, "Duplicate message.")
                return

        # MENTIONS
        cfg = settings.get("mentions", {})
        if cfg.get("enabled"):
            mention_count = len(message.mentions) + len(message.role_mentions)
            if mention_count > cfg.get("limit", 5):
                await self._violation(message, "Too many mentions.")
                return

        # EMOJI
        cfg = settings.get("emoji", {})
        if cfg.get("enabled"):
            emoji_count = len(EMOJI_RE.findall(message.content))
            if emoji_count > cfg.get("limit", 10):
                await self._violation(message, "Too many emoji.")
                return

        # CAPS
        cfg = settings.get("caps", {})
        if cfg.get("enabled"):
            letters = [c for c in message.content if c.isalpha()]
            if len(letters) >= 8:
                caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters) * 100
                if caps_ratio > cfg.get("percent", 70):
                    await self._violation(message, "Excessive caps.")
                    return

        # SPAM
        cfg = settings.get("spam", {})
        if cfg.get("enabled"):
            now = time.time()
            messages = self.recent_messages[message.guild.id][message.author.id]
            messages.append(now)

            while messages and now - messages[0] > cfg.get("seconds", 5):
                messages.popleft()

            if len(messages) > cfg.get("limit", 5):
                await self._violation(message, "Spam detected.")

    # --------------------------------------------------------
    # MEMBER JOIN PROTECTION
    # --------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        settings = get_settings(guild.id)

        cfg = settings.get("bot", {})
        if (
            cfg.get("enabled")
            and member.bot
            and not self._is_whitelisted(guild.id, member)
        ):
            try:
                await member.kick(reason="Unauthorized bot")
            except discord.HTTPException:
                pass

        cfg = settings.get("raid", {})
        if cfg.get("enabled"):
            now = time.time()
            joins = self.recent_joins[guild.id]
            joins.append(now)

            while joins and now - joins[0] > cfg.get("seconds", 30):
                joins.popleft()

            if len(joins) >= cfg.get("joins", 10):
                await send_log(
                    guild,
                    make_embed("Raid Alert", f"{len(joins)} users joined quickly."),
                )


# ============================================================
# SETUP
# ============================================================

async def setup(bot: commands.Bot):
    cog = AutoMod(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(automod_group)
