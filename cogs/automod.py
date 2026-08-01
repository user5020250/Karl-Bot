import re
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed, send_log
from storage import storage

INVITE_RE = re.compile(r"(discord\.gg/|discord(app)?\.com/invite/)", re.IGNORECASE)
LINK_RE = re.compile(r"https?://", re.IGNORECASE)
GIF_RE = re.compile(r"\.gif($|\?)|tenor\.com|giphy\.com", re.IGNORECASE)


def get_settings(guild_id: int) -> dict:
    settings = storage.get_guild_setting("automod", guild_id, {})
    if not settings:
        settings = {}
        storage.set_guild_setting("automod", guild_id, settings)
    return settings


def update_setting(guild_id: int, key: str, value: dict):
    settings = get_settings(guild_id)
    settings[key] = value
    storage.set_guild_setting("automod", guild_id, settings)


class AutoMod(commands.Cog):
    """AutoMod configuration commands and the message/member listeners that enforce them."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.recent_messages = defaultdict(lambda: defaultdict(deque))  # guild_id -> user_id -> deque[timestamps]
        self.last_message_content = defaultdict(dict)  # guild_id -> user_id -> last content
        self.recent_joins = defaultdict(deque)  # guild_id -> deque[timestamps]

    # ------------------------------------------------------------ helpers
    def _is_ignored(self, guild_id: int, member: discord.Member, channel: discord.abc.GuildChannel) -> bool:
        ignore_list = storage.get_list("ignore", guild_id)
        if channel.id in ignore_list:
            return True
        if any(role.id in ignore_list for role in getattr(member, "roles", [])):
            return True
        return False

    def _is_whitelisted(self, guild_id: int, member: discord.Member) -> bool:
        whitelist = storage.get_list("whitelist", guild_id)
        if member.id in whitelist:
            return True
        if any(role.id in whitelist for role in getattr(member, "roles", [])):
            return True
        if member.guild_permissions.administrator:
            return True
        return False

    async def _violation(self, message: discord.Message, reason: str):
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        embed = make_embed("AutoMod Action", f"Deleted a message from {message.author.mention} in {message.channel.mention}.\nReason: {reason}")
        await send_log(message.guild, embed)

    # ------------------------------------------------------------- /automod
    @app_commands.command(name="automod", description="Configure AutoMod.")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod(self, interaction: discord.Interaction):
        settings = get_settings(interaction.guild.id)
        embed = make_embed("AutoMod Overview")
        keys = [
            "antispam", "antilink", "antiinvite", "antimention", "antiraid",
            "antibot", "antiemoji", "antigif", "duplicatefilter", "capsfilter", "profanity",
        ]
        for key in keys:
            state = settings.get(key, {})
            status = "Enabled" if state.get("enabled") else "Disabled"
            embed.add_field(name=key, value=status, inline=True)
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------ antispam
    @app_commands.command(name="antispam", description="Anti-spam settings.")
    @app_commands.describe(enabled="Turn anti-spam on or off", limit="Max messages allowed", seconds="Time window in seconds")
    @app_commands.checks.has_permissions(administrator=True)
    async def antispam(self, interaction: discord.Interaction, enabled: bool, limit: app_commands.Range[int, 2, 30] = 5, seconds: app_commands.Range[int, 2, 60] = 5):
        update_setting(interaction.guild.id, "antispam", {"enabled": enabled, "limit": limit, "seconds": seconds})
        embed = make_embed("Anti-Spam Updated", f"Anti-spam is now {'enabled' if enabled else 'disabled'}. Limit: {limit} messages per {seconds}s.")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------ antilink
    @app_commands.command(name="antilink", description="Anti-link settings.")
    @app_commands.describe(enabled="Turn link filtering on or off")
    @app_commands.checks.has_permissions(administrator=True)
    async def antilink(self, interaction: discord.Interaction, enabled: bool):
        update_setting(interaction.guild.id, "antilink", {"enabled": enabled})
        embed = make_embed("Anti-Link Updated", f"Anti-link is now {'enabled' if enabled else 'disabled'}.")
        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------- antiinvite
    @app_commands.command(name="antiinvite", description="Block Discord invites.")
    @app_commands.describe(enabled="Turn invite blocking on or off")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiinvite(self, interaction: discord.Interaction, enabled: bool):
        update_setting(interaction.guild.id, "antiinvite", {"enabled": enabled})
        embed = make_embed("Anti-Invite Updated", f"Anti-invite is now {'enabled' if enabled else 'disabled'}.")
        await interaction.response.send_message(embed=embed)

    # --------------------------------------------------------- antimention
    @app_commands.command(name="antimention", description="Limit mass mentions.")
    @app_commands.describe(enabled="Turn mention limiting on or off", limit="Max mentions allowed per message")
    @app_commands.checks.has_permissions(administrator=True)
    async def antimention(self, interaction: discord.Interaction, enabled: bool, limit: app_commands.Range[int, 1, 50] = 5):
        update_setting(interaction.guild.id, "antimention", {"enabled": enabled, "limit": limit})
        embed = make_embed("Anti-Mention Updated", f"Anti-mention is now {'enabled' if enabled else 'disabled'}. Limit: {limit} mentions.")
        await interaction.response.send_message(embed=embed)

    # ----------------------------------------------------------- antiraid
    @app_commands.command(name="antiraid", description="Raid protection.")
    @app_commands.describe(enabled="Turn raid protection on or off", join_limit="Max joins allowed", seconds="Time window in seconds")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid(self, interaction: discord.Interaction, enabled: bool, join_limit: app_commands.Range[int, 2, 50] = 10, seconds: app_commands.Range[int, 2, 300] = 30):
        update_setting(interaction.guild.id, "antiraid", {"enabled": enabled, "join_limit": join_limit, "seconds": seconds})
        embed = make_embed("Anti-Raid Updated", f"Anti-raid is now {'enabled' if enabled else 'disabled'}. Alerts when {join_limit}+ joins happen within {seconds}s.")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------ antibot
    @app_commands.command(name="antibot", description="Prevent unauthorized bot joins.")
    @app_commands.describe(enabled="Turn bot-join blocking on or off")
    @app_commands.checks.has_permissions(administrator=True)
    async def antibot(self, interaction: discord.Interaction, enabled: bool):
        update_setting(interaction.guild.id, "antibot", {"enabled": enabled})
        embed = make_embed("Anti-Bot Updated", f"Anti-bot is now {'enabled' if enabled else 'disabled'}. Unwhitelisted bots will be kicked on join.")
        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------- antiemoji
    @app_commands.command(name="antiemoji", description="Limit emoji spam.")
    @app_commands.describe(enabled="Turn emoji limiting on or off", limit="Max emoji allowed per message")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiemoji(self, interaction: discord.Interaction, enabled: bool, limit: app_commands.Range[int, 1, 50] = 10):
        update_setting(interaction.guild.id, "antiemoji", {"enabled": enabled, "limit": limit})
        embed = make_embed("Anti-Emoji Updated", f"Anti-emoji is now {'enabled' if enabled else 'disabled'}. Limit: {limit} emoji per message.")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------ antigif
    @app_commands.command(name="antigif", description="Block GIF spam.")
    @app_commands.describe(enabled="Turn GIF blocking on or off")
    @app_commands.checks.has_permissions(administrator=True)
    async def antigif(self, interaction: discord.Interaction, enabled: bool):
        update_setting(interaction.guild.id, "antigif", {"enabled": enabled})
        embed = make_embed("Anti-GIF Updated", f"Anti-GIF is now {'enabled' if enabled else 'disabled'}.")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------ duplicatefilter
    @app_commands.command(name="duplicatefilter", description="Remove duplicate messages.")
    @app_commands.describe(enabled="Turn duplicate message filtering on or off")
    @app_commands.checks.has_permissions(administrator=True)
    async def duplicatefilter(self, interaction: discord.Interaction, enabled: bool):
        update_setting(interaction.guild.id, "duplicatefilter", {"enabled": enabled})
        embed = make_embed("Duplicate Filter Updated", f"Duplicate message filtering is now {'enabled' if enabled else 'disabled'}.")
        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------- capsfilter
    @app_commands.command(name="capsfilter", description="Limit excessive capital letters.")
    @app_commands.describe(enabled="Turn caps filtering on or off", percent="Max percentage of capital letters allowed (1-100)")
    @app_commands.checks.has_permissions(administrator=True)
    async def capsfilter(self, interaction: discord.Interaction, enabled: bool, percent: app_commands.Range[int, 10, 100] = 70):
        update_setting(interaction.guild.id, "capsfilter", {"enabled": enabled, "percent": percent})
        embed = make_embed("Caps Filter Updated", f"Caps filter is now {'enabled' if enabled else 'disabled'}. Limit: {percent}% capital letters.")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------ profanity
    profanity_group = app_commands.Group(name="profanity", description="Manage blocked words.")

    @profanity_group.command(name="enable", description="Enable or disable the profanity filter.")
    @app_commands.describe(enabled="Turn the profanity filter on or off")
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_enable(self, interaction: discord.Interaction, enabled: bool):
        settings = get_settings(interaction.guild.id)
        current = settings.get("profanity", {"enabled": False, "words": []})
        current["enabled"] = enabled
        update_setting(interaction.guild.id, "profanity", current)
        embed = make_embed("Profanity Filter Updated", f"Profanity filter is now {'enabled' if enabled else 'disabled'}.")
        await interaction.response.send_message(embed=embed)

    @profanity_group.command(name="add", description="Add a word to the blocked word list.")
    @app_commands.describe(word="The word to block")
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_add(self, interaction: discord.Interaction, word: str):
        settings = get_settings(interaction.guild.id)
        current = settings.get("profanity", {"enabled": False, "words": []})
        word = word.lower().strip()
        if word not in current["words"]:
            current["words"].append(word)
        update_setting(interaction.guild.id, "profanity", current)
        embed = make_embed("Word Blocked", f"Added '{word}' to the blocked word list.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @profanity_group.command(name="remove", description="Remove a word from the blocked word list.")
    @app_commands.describe(word="The word to unblock")
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_remove(self, interaction: discord.Interaction, word: str):
        settings = get_settings(interaction.guild.id)
        current = settings.get("profanity", {"enabled": False, "words": []})
        word = word.lower().strip()
        if word in current["words"]:
            current["words"].remove(word)
        update_setting(interaction.guild.id, "profanity", current)
        embed = make_embed("Word Unblocked", f"Removed '{word}' from the blocked word list.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @profanity_group.command(name="list", description="List blocked words.")
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_list(self, interaction: discord.Interaction):
        settings = get_settings(interaction.guild.id)
        current = settings.get("profanity", {"enabled": False, "words": []})
        words = ", ".join(current["words"]) or "No words are blocked."
        embed = make_embed("Blocked Words", words)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ----------------------------------------------------------- whitelist
    whitelist_group = app_commands.Group(name="whitelist", description="Whitelist users or roles from AutoMod.")

    @whitelist_group.command(name="add", description="Add a user or role to the whitelist.")
    @app_commands.describe(user="A user to whitelist", role="A role to whitelist")
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelist_add(self, interaction: discord.Interaction, user: discord.Member = None, role: discord.Role = None):
        target = user or role
        if target is None:
            await interaction.response.send_message("Provide a user or a role.", ephemeral=True)
            return
        storage.add_to_list("whitelist", interaction.guild.id, target.id)
        embed = make_embed("Whitelisted", f"{target.mention} is now whitelisted from AutoMod.")
        await interaction.response.send_message(embed=embed)

    @whitelist_group.command(name="remove", description="Remove a user or role from the whitelist.")
    @app_commands.describe(user="A user to remove", role="A role to remove")
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelist_remove(self, interaction: discord.Interaction, user: discord.Member = None, role: discord.Role = None):
        target = user or role
        if target is None:
            await interaction.response.send_message("Provide a user or a role.", ephemeral=True)
            return
        storage.remove_from_list("whitelist", interaction.guild.id, target.id)
        embed = make_embed("Whitelist Updated", f"{target.mention} was removed from the whitelist.")
        await interaction.response.send_message(embed=embed)

    # ----------------------------------------------------------- blacklist
    blacklist_group = app_commands.Group(name="blacklist", description="Blacklist users or roles.")

    @blacklist_group.command(name="add", description="Add a user or role to the blacklist.")
    @app_commands.describe(user="A user to blacklist", role="A role to blacklist")
    @app_commands.checks.has_permissions(administrator=True)
    async def blacklist_add(self, interaction: discord.Interaction, user: discord.Member = None, role: discord.Role = None):
        target = user or role
        if target is None:
            await interaction.response.send_message("Provide a user or a role.", ephemeral=True)
            return
        storage.add_to_list("blacklist", interaction.guild.id, target.id)
        embed = make_embed("Blacklisted", f"{target.mention} is now blacklisted.")
        await interaction.response.send_message(embed=embed)

    @blacklist_group.command(name="remove", description="Remove a user or role from the blacklist.")
    @app_commands.describe(user="A user to remove", role="A role to remove")
    @app_commands.checks.has_permissions(administrator=True)
    async def blacklist_remove(self, interaction: discord.Interaction, user: discord.Member = None, role: discord.Role = None):
        target = user or role
        if target is None:
            await interaction.response.send_message("Provide a user or a role.", ephemeral=True)
            return
        storage.remove_from_list("blacklist", interaction.guild.id, target.id)
        embed = make_embed("Blacklist Updated", f"{target.mention} was removed from the blacklist.")
        await interaction.response.send_message(embed=embed)

    # --------------------------------------------------------------- ignore
    ignore_group = app_commands.Group(name="ignore", description="Ignore channels or roles for AutoMod.")

    @ignore_group.command(name="add", description="Ignore a channel or role.")
    @app_commands.describe(channel="A channel to ignore", role="A role to ignore")
    @app_commands.checks.has_permissions(administrator=True)
    async def ignore_add(self, interaction: discord.Interaction, channel: discord.TextChannel = None, role: discord.Role = None):
        target = channel or role
        if target is None:
            await interaction.response.send_message("Provide a channel or a role.", ephemeral=True)
            return
        storage.add_to_list("ignore", interaction.guild.id, target.id)
        embed = make_embed("Ignore List Updated", f"{target.mention} is now ignored by AutoMod.")
        await interaction.response.send_message(embed=embed)

    @ignore_group.command(name="remove", description="Stop ignoring a channel or role.")
    @app_commands.describe(channel="A channel to stop ignoring", role="A role to stop ignoring")
    @app_commands.checks.has_permissions(administrator=True)
    async def ignore_remove(self, interaction: discord.Interaction, channel: discord.TextChannel = None, role: discord.Role = None):
        target = channel or role
        if target is None:
            await interaction.response.send_message("Provide a channel or a role.", ephemeral=True)
            return
        storage.remove_from_list("ignore", interaction.guild.id, target.id)
        embed = make_embed("Ignore List Updated", f"{target.mention} is no longer ignored.")
        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------------------
    # Listeners that enforce the settings above
    # ---------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None or not isinstance(message.author, discord.Member):
            return
        if self._is_whitelisted(message.guild.id, message.author):
            return
        if self._is_ignored(message.guild.id, message.author, message.channel):
            return

        settings = get_settings(message.guild.id)

        # antilink
        link_cfg = settings.get("antilink", {})
        if link_cfg.get("enabled") and LINK_RE.search(message.content or ""):
            await self._violation(message, "Links are not allowed here.")
            return

        # antiinvite
        invite_cfg = settings.get("antiinvite", {})
        if invite_cfg.get("enabled") and INVITE_RE.search(message.content or ""):
            await self._violation(message, "Discord invite links are not allowed here.")
            return

        # antigif
        gif_cfg = settings.get("antigif", {})
        if gif_cfg.get("enabled"):
            has_gif_attachment = any(a.filename.lower().endswith(".gif") for a in message.attachments)
            if has_gif_attachment or GIF_RE.search(message.content or ""):
                await self._violation(message, "GIFs are not allowed here.")
                return

        # antimention
        mention_cfg = settings.get("antimention", {})
        if mention_cfg.get("enabled"):
            total_mentions = len(message.mentions) + len(message.role_mentions)
            if total_mentions > mention_cfg.get("limit", 5):
                await self._violation(message, "Too many mentions in one message.")
                return

        # antiemoji
        emoji_cfg = settings.get("antiemoji", {})
        if emoji_cfg.get("enabled"):
            custom_emoji_count = len(re.findall(r"<a?:\w+:\d+>", message.content or ""))
            unicode_emoji_count = len(re.findall(
                "[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F000-\U0001F0FF]", message.content or ""
            ))
            if (custom_emoji_count + unicode_emoji_count) > emoji_cfg.get("limit", 10):
                await self._violation(message, "Too many emoji in one message.")
                return

        # capsfilter
        caps_cfg = settings.get("capsfilter", {})
        if caps_cfg.get("enabled"):
            letters = [c for c in (message.content or "") if c.isalpha()]
            if len(letters) >= 8:
                upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters) * 100
                if upper_ratio > caps_cfg.get("percent", 70):
                    await self._violation(message, "Excessive use of capital letters.")
                    return

        # profanity
        profanity_cfg = settings.get("profanity", {})
        if profanity_cfg.get("enabled") and profanity_cfg.get("words"):
            content_lower = (message.content or "").lower()
            if any(word in content_lower for word in profanity_cfg["words"]):
                await self._violation(message, "Message contained a blocked word.")
                return

        # duplicatefilter
        dup_cfg = settings.get("duplicatefilter", {})
        if dup_cfg.get("enabled"):
            last = self.last_message_content[message.guild.id].get(message.author.id)
            self.last_message_content[message.guild.id][message.author.id] = message.content
            if last is not None and last == message.content and message.content:
                await self._violation(message, "Duplicate message.")
                return

        # antispam
        spam_cfg = settings.get("antispam", {})
        if spam_cfg.get("enabled"):
            now = time.time()
            window = spam_cfg.get("seconds", 5)
            limit = spam_cfg.get("limit", 5)
            timestamps = self.recent_messages[message.guild.id][message.author.id]
            timestamps.append(now)
            while timestamps and now - timestamps[0] > window:
                timestamps.popleft()
            if len(timestamps) > limit:
                await self._violation(message, "Sending messages too quickly.")
                return

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        settings = get_settings(guild.id)

        # antibot
        bot_cfg = settings.get("antibot", {})
        if bot_cfg.get("enabled") and member.bot and not self._is_whitelisted(guild.id, member):
            try:
                await member.kick(reason="Unauthorized bot join (antibot)")
                embed = make_embed("Anti-Bot Action", f"Kicked bot {member} for joining without whitelist approval.")
                await send_log(guild, embed)
            except discord.HTTPException:
                pass
            return

        # antiraid
        raid_cfg = settings.get("antiraid", {})
        if raid_cfg.get("enabled"):
            now = time.time()
            window = raid_cfg.get("seconds", 30)
            limit = raid_cfg.get("join_limit", 10)
            joins = self.recent_joins[guild.id]
            joins.append(now)
            while joins and now - joins[0] > window:
                joins.popleft()
            if len(joins) >= limit:
                embed = make_embed(
                    "Raid Alert",
                    f"{len(joins)} members joined within {window} seconds. Consider using /lockdown while you investigate.",
                )
                await send_log(guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
