import re
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed, send_log
from storage import storage


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


def update_setting(guild_id: int, key: str, value):
    settings = get_settings(guild_id)
    settings[key] = value

    storage.set_guild_setting(
        "automod",
        guild_id,
        settings
    )


# ============================================================
# AUTOMOD COG
# ============================================================

class AutoMod(commands.Cog):

    automod_group = app_commands.Group(
        name="automod",
        description="Configure AutoMod"
    )


    filter_group = app_commands.Group(
        name="filter",
        description="Configure AutoMod filters",
        parent=automod_group
    )


    profanity_group = app_commands.Group(
        name="profanity",
        description="Manage profanity filter",
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
        description="Ignore channels or roles",
        parent=automod_group
    )


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

    def is_ignored(
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



    def is_whitelisted(
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



    async def violation(
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



    # ========================================================
    # /automod status
    # ========================================================

    @automod_group.command(
        name="status",
        description="View AutoMod settings"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def status(
        self,
        interaction: discord.Interaction
    ):

        settings = get_settings(
            interaction.guild.id
        )


        embed = make_embed(
            "AutoMod Status"
        )


        filters = [
            "spam",
            "links",
            "invites",
            "mentions",
            "raid",
            "bot",
            "emoji",
            "gif",
            "caps",
            "duplicate"
        ]


        for item in filters:

            data = settings.get(
                item,
                {}
            )

            enabled = data.get(
                "enabled",
                False
            )

            embed.add_field(
                name=item,
                value=(
                    "Enabled"
                    if enabled
                    else
                    "Disabled"
                ),
                inline=True
            )


        await interaction.response.send_message(
            embed=embed
        )


    # ========================================================
    # FILTER COMMANDS
    # ========================================================


    @filter_group.command(
        name="spam",
        description="Configure anti spam"
    )
    @app_commands.describe(
        enabled="Enable spam protection",
        limit="Messages allowed",
        seconds="Time window"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def filter_spam(
        self,
        interaction,
        enabled: bool,
        limit: int = 5,
        seconds: int = 5
    ):

        update_setting(
            interaction.guild.id,
            "spam",
            {
                "enabled": enabled,
                "limit": limit,
                "seconds": seconds
            }
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Spam Filter Updated",
                f"Enabled: {enabled}\nLimit: {limit}\nWindow: {seconds}s"
            )
        )



    @filter_group.command(
        name="links",
        description="Configure link filter"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def filter_links(
        self,
        interaction,
        enabled: bool
    ):

        update_setting(
            interaction.guild.id,
            "links",
            {
                "enabled": enabled
            }
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Link Filter Updated",
                f"Enabled: {enabled}"
            )
        )



    @filter_group.command(
        name="invites",
        description="Configure invite filter"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def filter_invites(
        self,
        interaction,
        enabled: bool
    ):

        update_setting(
            interaction.guild.id,
            "invites",
            {
                "enabled": enabled
            }
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Invite Filter Updated",
                f"Enabled: {enabled}"
            )
        )

    # ========================================================
    # MORE FILTER COMMANDS
    # ========================================================

    @filter_group.command(
        name="mentions",
        description="Configure mention limit"
    )
    @app_commands.describe(
        enabled="Enable mention filter",
        limit="Maximum mentions"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def filter_mentions(
        self,
        interaction,
        enabled: bool,
        limit: int = 5
    ):

        update_setting(
            interaction.guild.id,
            "mentions",
            {
                "enabled": enabled,
                "limit": limit
            }
        )

        await interaction.response.send_message(
            embed=make_embed(
                "Mention Filter Updated",
                f"Enabled: {enabled}\nLimit: {limit}"
            )
        )



    @filter_group.command(
        name="raid",
        description="Configure raid protection"
    )
    @app_commands.describe(
        enabled="Enable raid protection",
        joins="Join limit",
        seconds="Time window"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def filter_raid(
        self,
        interaction,
        enabled: bool,
        joins: int = 10,
        seconds: int = 30
    ):

        update_setting(
            interaction.guild.id,
            "raid",
            {
                "enabled": enabled,
                "joins": joins,
                "seconds": seconds
            }
        )

        await interaction.response.send_message(
            embed=make_embed(
                "Raid Protection Updated",
                f"Enabled: {enabled}\nJoins: {joins}\nWindow: {seconds}s"
            )
        )



    @filter_group.command(
        name="bot",
        description="Configure anti bot"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def filter_bot(
        self,
        interaction,
        enabled: bool
    ):

        update_setting(
            interaction.guild.id,
            "bot",
            {
                "enabled": enabled
            }
        )

        await interaction.response.send_message(
            embed=make_embed(
                "Anti Bot Updated",
                f"Enabled: {enabled}"
            )
        )



    @filter_group.command(
        name="emoji",
        description="Configure emoji filter"
    )
    @app_commands.describe(
        enabled="Enable emoji filter",
        limit="Maximum emojis"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def filter_emoji(
        self,
        interaction,
        enabled: bool,
        limit: int = 10
    ):

        update_setting(
            interaction.guild.id,
            "emoji",
            {
                "enabled": enabled,
                "limit": limit
            }
        )

        await interaction.response.send_message(
            embed=make_embed(
                "Emoji Filter Updated",
                f"Enabled: {enabled}\nLimit: {limit}"
            )
        )



    @filter_group.command(
        name="gif",
        description="Configure GIF filter"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def filter_gif(
        self,
        interaction,
        enabled: bool
    ):

        update_setting(
            interaction.guild.id,
            "gif",
            {
                "enabled": enabled
            }
        )

        await interaction.response.send_message(
            embed=make_embed(
                "GIF Filter Updated",
                f"Enabled: {enabled}"
            )
        )



    @filter_group.command(
        name="caps",
        description="Configure caps filter"
    )
    @app_commands.describe(
        enabled="Enable caps filter",
        percent="Allowed uppercase percentage"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def filter_caps(
        self,
        interaction,
        enabled: bool,
        percent: int = 70
    ):

        update_setting(
            interaction.guild.id,
            "caps",
            {
                "enabled": enabled,
                "percent": percent
            }
        )

        await interaction.response.send_message(
            embed=make_embed(
                "Caps Filter Updated",
                f"Enabled: {enabled}\nLimit: {percent}%"
            )
        )



    @filter_group.command(
        name="duplicate",
        description="Configure duplicate message filter"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def filter_duplicate(
        self,
        interaction,
        enabled: bool
    ):

        update_setting(
            interaction.guild.id,
            "duplicate",
            {
                "enabled": enabled
            }
        )

        await interaction.response.send_message(
            embed=make_embed(
                "Duplicate Filter Updated",
                f"Enabled: {enabled}"
            )
        )



    # ========================================================
    # PROFANITY GROUP
    # ========================================================


    @profanity_group.command(
        name="enable",
        description="Enable profanity filter"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def profanity_enable(
        self,
        interaction,
        enabled: bool
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


        profanity["enabled"] = enabled


        update_setting(
            interaction.guild.id,
            "profanity",
            profanity
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Profanity Filter Updated",
                f"Enabled: {enabled}"
            )
        )



    @profanity_group.command(
        name="add",
        description="Add blocked word"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def profanity_add(
        self,
        interaction,
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


        if word not in profanity["words"]:
            profanity["words"].append(word)


        update_setting(
            interaction.guild.id,
            "profanity",
            profanity
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Word Added",
                f"`{word}` added"
            ),
            ephemeral=True
        )



    @profanity_group.command(
        name="remove",
        description="Remove blocked word"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def profanity_remove(
        self,
        interaction,
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


        if word in profanity["words"]:
            profanity["words"].remove(word)


        update_setting(
            interaction.guild.id,
            "profanity",
            profanity
        )


        await interaction.response.send_message(
            embed=make_embed(
                "Word Removed",
                f"`{word}` removed"
            ),
            ephemeral=True
        )



    @profanity_group.command(
        name="list",
        description="List blocked words"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def profanity_list(
        self,
        interaction
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

    # ------------------------------------------------------------
    # PROFANITY GROUP
    # ------------------------------------------------------------

    profanity_group = app_commands.Group(
        name="profanity",
        description="Manage profanity filter."
    )

    @profanity_group.command(
        name="enable",
        description="Enable or disable profanity filtering."
    )
    @app_commands.describe(enabled="Enable profanity filter")
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_enable(
        self,
        interaction: discord.Interaction,
        enabled: bool
    ):
        settings = get_settings(interaction.guild.id)

        profanity = settings.get(
            "profanity",
            {
                "enabled": False,
                "words": []
            }
        )

        profanity["enabled"] = enabled

        update_setting(
            interaction.guild.id,
            "profanity",
            profanity
        )

        await interaction.response.send_message(
            embed=make_embed(
                "Profanity Filter",
                f"Status: {'Enabled' if enabled else 'Disabled'}"
            )
        )


    @profanity_group.command(
        name="add",
        description="Add a blocked word."
    )
    @app_commands.describe(word="Word to block")
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_add(
        self,
        interaction: discord.Interaction,
        word: str
    ):
        settings = get_settings(interaction.guild.id)

        profanity = settings.get(
            "profanity",
            {
                "enabled": False,
                "words": []
            }
        )

        word = word.lower()

        if word not in profanity["words"]:
            profanity["words"].append(word)

        update_setting(
            interaction.guild.id,
            "profanity",
            profanity
        )

        await interaction.response.send_message(
            embed=make_embed(
                "Profanity Added",
                f"Blocked word added: `{word}`"
            )
        )


    @profanity_group.command(
        name="remove",
        description="Remove a blocked word."
    )
    @app_commands.describe(word="Word to remove")
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_remove(
        self,
        interaction: discord.Interaction,
        word: str
    ):
        settings = get_settings(interaction.guild.id)

        profanity = settings.get(
            "profanity",
            {
                "enabled": False,
                "words": []
            }
        )

        word = word.lower()

        if word in profanity["words"]:
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
            )
        )


    @profanity_group.command(
        name="list",
        description="View blocked words."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def profanity_list(
        self,
        interaction: discord.Interaction
    ):
        settings = get_settings(interaction.guild.id)

        profanity = settings.get(
            "profanity",
            {
                "enabled": False,
                "words": []
            }
        )

        words = ", ".join(
            profanity["words"]
        )

        if not words:
            words = "No blocked words."

        await interaction.response.send_message(
            embed=make_embed(
                "Blocked Words",
                words
            ),
            ephemeral=True
        )


    # ------------------------------------------------------------
    # WHITELIST GROUP
    # ------------------------------------------------------------

    whitelist_group = app_commands.Group(
        name="whitelist",
        description="Manage AutoMod whitelist."
    )


    @whitelist_group.command(
        name="add",
        description="Whitelist a user or role."
    )
    @app_commands.describe(
        user="User to whitelist",
        role="Role to whitelist"
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
        description="Remove a user or role from whitelist."
    )
    @app_commands.describe(
        user="User to remove",
        role="Role to remove"
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


    # ------------------------------------------------------------
    # BLACKLIST GROUP
    # ------------------------------------------------------------

    blacklist_group = app_commands.Group(
        name="blacklist",
        description="Manage AutoMod blacklist."
    )


    @blacklist_group.command(
        name="add",
        description="Blacklist user or role."
    )
    @app_commands.describe(
        user="User to blacklist",
        role="Role to blacklist"
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
        description="Remove user or role from blacklist."
    )
    @app_commands.describe(
        user="User to remove",
        role="Role to remove"
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
            # ------------------------------------------------------------
    # IGNORE GROUP
    # ------------------------------------------------------------

    ignore_group = app_commands.Group(
        name="ignore",
        description="Ignore channels or roles from AutoMod."
    )


    @ignore_group.command(
        name="add",
        description="Ignore a channel or role."
    )
    @app_commands.describe(
        channel="Channel to ignore",
        role="Role to ignore"
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
                "Provide a channel or role.",
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
        description="Remove ignored channel or role."
    )
    @app_commands.describe(
        channel="Channel to remove",
        role="Role to remove"
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
                "Provide a channel or role.",
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


    # ------------------------------------------------------------
    # MESSAGE FILTER LISTENER
    # ------------------------------------------------------------

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


        # ---------------- LINK FILTER

        cfg = settings.get(
            "antilink",
            {}
        )

        if cfg.get("enabled"):

            if LINK_RE.search(
                message.content
            ):

                await self._violation(
                    message,
                    "Links are not allowed."
                )
                return



        # ---------------- INVITE FILTER

        cfg = settings.get(
            "antiinvite",
            {}
        )

        if cfg.get("enabled"):

            if INVITE_RE.search(
                message.content
            ):

                await self._violation(
                    message,
                    "Discord invites are not allowed."
                )
                return



        # ---------------- GIF FILTER

        cfg = settings.get(
            "antigif",
            {}
        )

        if cfg.get("enabled"):

            if GIF_RE.search(
                message.content
            ):

                await self._violation(
                    message,
                    "GIFs are disabled."
                )
                return



        # ---------------- DUPLICATE FILTER

        cfg = settings.get(
            "duplicatefilter",
            {}
        )

        if cfg.get("enabled"):

            previous = (
                self.last_message_content
                [message.guild.id]
                .get(message.author.id)
            )


            self.last_message_content[
                message.guild.id
            ][
                message.author.id
            ] = message.content


            if (
                previous
                and previous == message.content
            ):

                await self._violation(
                    message,
                    "Duplicate message."
                )
                return



        # ---------------- SPAM FILTER

        cfg = settings.get(
            "antispam",
            {}
        )


        if cfg.get("enabled"):

            now = time.time()

            timestamps = (
                self.recent_messages
                [message.guild.id]
                [message.author.id]
            )


            timestamps.append(now)


            while (
                timestamps
                and now - timestamps[0] > cfg.get(
                    "seconds",
                    5
                )
            ):

                timestamps.popleft()


            if len(timestamps) > cfg.get(
                "limit",
                5
            ):

                await self._violation(
                    message,
                    "Spam detected."
                )
                return



    # ------------------------------------------------------------
    # RAID / BOT JOIN PROTECTION
    # ------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_join(
        self,
        member: discord.Member
    ):

        guild = member.guild

        settings = get_settings(
            guild.id
        )


        # Anti bot

        cfg = settings.get(
            "antibot",
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

                await send_log(
                    guild,
                    make_embed(
                        "Anti Bot",
                        f"Kicked {member}"
                    )
                )

            except discord.HTTPException:
                pass



        # Anti raid

        cfg = settings.get(
            "antiraid",
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
                and now - joins[0]
                > cfg.get(
                    "seconds",
                    30
                )
            ):
                joins.popleft()



            if len(joins) >= cfg.get(
                "join_limit",
                10
            ):

                await send_log(
                    guild,
                    make_embed(
                        "Raid Alert",
                        f"{len(joins)} users joined quickly."
                    )
                )



# ------------------------------------------------------------
# SETUP
# ------------------------------------------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
