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
    status = "🟢 Enabled" if enabled else "🔴 Disabled"

    extras = {k: v for k, v in cfg.items() if k != "enabled"}
    if extras:
        status += "\n" + ", ".join(f"{k}: `{v}`" for k, v in extras.items())

    return make_embed(filter_name, status)


# ============================================================
# COMMAND GROUPS
# ============================================================

automod_group = app_commands.Group(
    name="automod",
    description="Configure AutoMod protections"
)

links_group = app_commands.Group(name="links", description="Link filter", parent=automod_group)
invites_group = app_commands.Group(name="invites", description="Discord invite filter", parent=automod_group)
gif_group = app_commands.Group(name="gif", description="GIF filter", parent=automod_group)
duplicate_group = app_commands.Group(name="duplicate", description="Duplicate message filter", parent=automod_group)
antibot_group = app_commands.Group(name="antibot", description="Unauthorized bot filter", parent=automod_group)
profanity_group = app_commands.Group(name="profanity", description="Profanity filter", parent=automod_group)
spam_group = app_commands.Group(name="spam", description="Anti-spam filter", parent=automod_group)
mentions_group = app_commands.Group(name="mentions", description="Mention limit filter", parent=automod_group)
raid_group = app_commands.Group(name="raid", description="Raid protection", parent=automod_group)
emoji_group = app_commands.Group(name="emoji", description="Emoji limit filter", parent=automod_group)
caps_group = app_commands.Group(name="caps", description="Caps filter", parent=automod_group)
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
    # LINKS
    # --------------------------------------------------------

    @links_group.command(name="enable", description="Enable the link filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def links_enable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "links", True)
        await interaction.response.send_message(embed=status_embed("Links", cfg), ephemeral=True)

    @links_group.command(name="disable", description="Disable the link filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def links_disable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "links", False)
        await interaction.response.send_message(embed=status_embed("Links", cfg), ephemeral=True)

    # --------------------------------------------------------
    # INVITES
    # --------------------------------------------------------

    @invites_group.command(name="enable", description="Enable the Discord invite filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def invites_enable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "invites", True)
        await interaction.response.send_message(embed=status_embed("Invites", cfg), ephemeral=True)

    @invites_group.command(name="disable", description="Disable the Discord invite filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def invites_disable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "invites", False)
        await interaction.response.send_message(embed=status_embed("Invites", cfg), ephemeral=True)

    # --------------------------------------------------------
    # GIF
    # --------------------------------------------------------

    @gif_group.command(name="enable", description="Enable the GIF filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def gif_enable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "gif", True)
        await interaction.response.send_message(embed=status_embed("GIFs", cfg), ephemeral=True)

    @gif_group.command(name="disable", description="Disable the GIF filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def gif_disable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "gif", False)
        await interaction.response.send_message(embed=status_embed("GIFs", cfg), ephemeral=True)

    # --------------------------------------------------------
    # DUPLICATE
    # --------------------------------------------------------

    @duplicate_group.command(name="enable", description="Enable the duplicate message filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def duplicate_enable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "duplicate", True)
        await interaction.response.send_message(embed=status_embed("Duplicate Messages", cfg), ephemeral=True)

    @duplicate_group.command(name="disable", description="Disable the duplicate message filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def duplicate_disable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "duplicate", False)
        await interaction.response.send_message(embed=status_embed("Duplicate Messages", cfg), ephemeral=True)

    # --------------------------------------------------------
    # ANTI BOT
    # --------------------------------------------------------

    @antibot_group.command(name="enable", description="Enable kicking unauthorized bots on join.")
    @app_commands.checks.has_permissions(administrator=True)
    async def antibot_enable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "bot", True)
        await interaction.response.send_message(embed=status_embed("Anti Bot", cfg), ephemeral=True)

    @antibot_group.command(name="disable", description="Disable kicking unauthorized bots on join.")
    @app_commands.checks.has_permissions(administrator=True)
    async def antibot_disable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "bot", False)
        await interaction.response.send_message(embed=status_embed("Anti Bot", cfg), ephemeral=True)

    # --------------------------------------------------------
    # PROFANITY
    # --------------------------------------------------------

    @profanity_group.command(name="enable", description="Enable the profanity filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_enable(self, interaction: discord.Interaction):
        settings = get_settings(interaction.guild.id)
        cfg = settings.get("profanity", {"words": []})
        cfg["enabled"] = True
        update_setting(interaction.guild.id, "profanity", cfg)
        await interaction.response.send_message(embed=status_embed("Profanity", cfg), ephemeral=True)

    @profanity_group.command(name="disable", description="Disable the profanity filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_disable(self, interaction: discord.Interaction):
        settings = get_settings(interaction.guild.id)
        cfg = settings.get("profanity", {"words": []})
        cfg["enabled"] = False
        update_setting(interaction.guild.id, "profanity", cfg)
        await interaction.response.send_message(embed=status_embed("Profanity", cfg), ephemeral=True)

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
    # SPAM
    # --------------------------------------------------------

    @spam_group.command(name="enable", description="Enable the anti-spam filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def spam_enable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "spam", True, DEFAULTS["spam"])
        await interaction.response.send_message(embed=status_embed("Anti Spam", cfg), ephemeral=True)

    @spam_group.command(name="disable", description="Disable the anti-spam filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def spam_disable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "spam", False, DEFAULTS["spam"])
        await interaction.response.send_message(embed=status_embed("Anti Spam", cfg), ephemeral=True)

    @spam_group.command(name="configure", description="Configure anti-spam message limit and time window.")
    @app_commands.describe(limit="Max messages allowed", seconds="Time window in seconds")
    @app_commands.checks.has_permissions(administrator=True)
    async def spam_configure(self, interaction: discord.Interaction, limit: int, seconds: int):
        settings = get_settings(interaction.guild.id)
        cfg = settings.get("spam", dict(DEFAULTS["spam"]))
        cfg["limit"] = limit
        cfg["seconds"] = seconds
        update_setting(interaction.guild.id, "spam", cfg)
        await interaction.response.send_message(embed=status_embed("Anti Spam", cfg), ephemeral=True)

    # --------------------------------------------------------
    # MENTIONS
    # --------------------------------------------------------

    @mentions_group.command(name="enable", description="Enable the mention limit filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def mentions_enable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "mentions", True, DEFAULTS["mentions"])
        await interaction.response.send_message(embed=status_embed("Mention Limit", cfg), ephemeral=True)

    @mentions_group.command(name="disable", description="Disable the mention limit filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def mentions_disable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "mentions", False, DEFAULTS["mentions"])
        await interaction.response.send_message(embed=status_embed("Mention Limit", cfg), ephemeral=True)

    @mentions_group.command(name="configure", description="Configure the max mentions allowed per message.")
    @app_commands.describe(limit="Max mentions allowed per message")
    @app_commands.checks.has_permissions(administrator=True)
    async def mentions_configure(self, interaction: discord.Interaction, limit: int):
        settings = get_settings(interaction.guild.id)
        cfg = settings.get("mentions", dict(DEFAULTS["mentions"]))
        cfg["limit"] = limit
        update_setting(interaction.guild.id, "mentions", cfg)
        await interaction.response.send_message(embed=status_embed("Mention Limit", cfg), ephemeral=True)

    # --------------------------------------------------------
    # RAID
    # --------------------------------------------------------

    @raid_group.command(name="enable", description="Enable raid protection.")
    @app_commands.checks.has_permissions(administrator=True)
    async def raid_enable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "raid", True, DEFAULTS["raid"])
        await interaction.response.send_message(embed=status_embed("Raid Protection", cfg), ephemeral=True)

    @raid_group.command(name="disable", description="Disable raid protection.")
    @app_commands.checks.has_permissions(administrator=True)
    async def raid_disable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "raid", False, DEFAULTS["raid"])
        await interaction.response.send_message(embed=status_embed("Raid Protection", cfg), ephemeral=True)

    @raid_group.command(name="configure", description="Configure raid protection join count and time window.")
    @app_commands.describe(joins="Number of joins to trigger an alert", seconds="Time window in seconds")
    @app_commands.checks.has_permissions(administrator=True)
    async def raid_configure(self, interaction: discord.Interaction, joins: int, seconds: int):
        settings = get_settings(interaction.guild.id)
        cfg = settings.get("raid", dict(DEFAULTS["raid"]))
        cfg["joins"] = joins
        cfg["seconds"] = seconds
        update_setting(interaction.guild.id, "raid", cfg)
        await interaction.response.send_message(embed=status_embed("Raid Protection", cfg), ephemeral=True)

    # --------------------------------------------------------
    # EMOJI
    # --------------------------------------------------------

    @emoji_group.command(name="enable", description="Enable the emoji limit filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def emoji_enable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "emoji", True, DEFAULTS["emoji"])
        await interaction.response.send_message(embed=status_embed("Emoji Limit", cfg), ephemeral=True)

    @emoji_group.command(name="disable", description="Disable the emoji limit filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def emoji_disable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "emoji", False, DEFAULTS["emoji"])
        await interaction.response.send_message(embed=status_embed("Emoji Limit", cfg), ephemeral=True)

    @emoji_group.command(name="configure", description="Configure the max emoji allowed per message.")
    @app_commands.describe(limit="Max emoji allowed per message")
    @app_commands.checks.has_permissions(administrator=True)
    async def emoji_configure(self, interaction: discord.Interaction, limit: int):
        settings = get_settings(interaction.guild.id)
        cfg = settings.get("emoji", dict(DEFAULTS["emoji"]))
        cfg["limit"] = limit
        update_setting(interaction.guild.id, "emoji", cfg)
        await interaction.response.send_message(embed=status_embed("Emoji Limit", cfg), ephemeral=True)

    # --------------------------------------------------------
    # CAPS
    # --------------------------------------------------------

    @caps_group.command(name="enable", description="Enable the caps filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def caps_enable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "caps", True, DEFAULTS["caps"])
        await interaction.response.send_message(embed=status_embed("Caps Filter", cfg), ephemeral=True)

    @caps_group.command(name="disable", description="Disable the caps filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def caps_disable(self, interaction: discord.Interaction):
        cfg = set_enabled(interaction.guild.id, "caps", False, DEFAULTS["caps"])
        await interaction.response.send_message(embed=status_embed("Caps Filter", cfg), ephemeral=True)

    @caps_group.command(name="configure", description="Configure the max caps percentage allowed per message.")
    @app_commands.describe(percent="Max percentage of uppercase letters allowed (0-100)")
    @app_commands.checks.has_permissions(administrator=True)
    async def caps_configure(self, interaction: discord.Interaction, percent: int):
        settings = get_settings(interaction.guild.id)
        cfg = settings.get("caps", dict(DEFAULTS["caps"]))
        cfg["percent"] = percent
        update_setting(interaction.guild.id, "caps", cfg)
        await interaction.response.send_message(embed=status_embed("Caps Filter", cfg), ephemeral=True)

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
