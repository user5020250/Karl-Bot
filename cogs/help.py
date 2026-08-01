import discord
from discord import app_commands
from discord.ext import commands


# ---------------------------------------------------------------------------
# Command data: category -> list of (command, description, required permission)
# ---------------------------------------------------------------------------
CATEGORIES = {
    "Moderation": [
        ("/ban", "Permanently bans a member.", "Ban Members"),
        ("/tempban", "Bans a member for a specified duration.", "Ban Members"),
        ("/softban", "Bans then immediately unbans a member to delete recent messages.", "Ban Members"),
        ("/unban", "Unbans a member.", "Ban Members"),
        ("/kick", "Kicks a member from the server.", "Kick Members"),
        ("/timeout", "Times out a member.", "Moderate Members"),
        ("/untimeout", "Removes a timeout.", "Moderate Members"),
        ("/history", "Displays a member's moderation history.", "Moderate Members"),
    ],
    "Messages": [
        ("/clear", "Deletes recent messages.", "Manage Messages"),
        ("/purge user", "Deletes messages from a specific user.", "Manage Messages"),
        ("/purge bots", "Deletes bot messages.", "Manage Messages"),
        ("/purge links", "Deletes messages containing links.", "Manage Messages"),
        ("/purge invites", "Deletes Discord invite links.", "Manage Messages"),
        ("/purge images", "Deletes image messages.", "Manage Messages"),
        ("/purge embeds", "Deletes embedded messages.", "Manage Messages"),
        ("/purge files", "Deletes messages with attachments.", "Manage Messages"),
        ("/purge mentions", "Deletes messages containing mentions.", "Manage Messages"),
        ("/purge contains", "Deletes messages containing text.", "Manage Messages"),
        ("/snipe", "Shows the last deleted message.", "Manage Messages"),
        ("/editsnipe", "Shows the last edited message.", "Manage Messages"),
    ],
    "Channels": [
        ("/lock", "Locks a channel.", "Manage Channels"),
        ("/unlock", "Unlocks a channel.", "Manage Channels"),
        ("/slowmode", "Sets channel slowmode.", "Manage Channels"),
        ("/clone", "Clones a channel.", "Manage Channels"),
        ("/nuke", "Deletes all messages by recreating the channel.", "Manage Channels"),
        ("/archive", "Archives a channel.", "Manage Channels"),
        ("/renamechannel", "Renames a channel.", "Manage Channels"),
    ],
    "Voice": [
        ("/voicekick", "Disconnects a user from voice.", "Move Members"),
        ("/move", "Moves a member.", "Move Members"),
        ("/moveall", "Moves everyone in a voice channel.", "Move Members"),
        ("/mutevoice", "Server mutes a member.", "Mute Members"),
        ("/unmutevoice", "Removes server mute.", "Mute Members"),
        ("/deafen", "Server deafens a member.", "Deafen Members"),
        ("/undeafen", "Removes server deafening.", "Deafen Members"),
    ],
    "Roles & Nicknames": [
        ("/addrole", "Gives a role.", "Manage Roles"),
        ("/removerole", "Removes a role.", "Manage Roles"),
        ("/nickname", "Changes nickname.", "Manage Nicknames"),
    ],
    "AutoMod": [
        ("/automod", "Opens the AutoMod panel to toggle and configure filters.", "Administrator"),
        ("/profanity add", "Add a word to the profanity filter.", "Administrator"),
        ("/profanity remove", "Remove a word from the profanity filter.", "Administrator"),
        ("/profanity list", "List all blocked words.", "Administrator"),
        ("/whitelist add", "Whitelist a user or role from AutoMod.", "Administrator"),
        ("/whitelist remove", "Remove a user or role from the whitelist.", "Administrator"),
        ("/blacklist add", "Blacklist a user or role.", "Administrator"),
        ("/blacklist remove", "Remove a user or role from the blacklist.", "Administrator"),
        ("/ignore add", "Ignore a channel or role for AutoMod.", "Administrator"),
        ("/ignore remove", "Remove a channel or role from the ignore list.", "Administrator"),
    ],
    "Server Config": [
        ("/lockdown", "Lock every channel.", "Administrator"),
        ("/unlockdown", "End lockdown.", "Administrator"),
        ("/autorole add", "Add a role to be given automatically to new members.", "Manage Roles"),
        ("/autorole remove", "Remove a role from the autorole list.", "Manage Roles"),
        ("/autorole list", "List autoroles.", "Manage Roles"),
        ("/logs", "Configure log channels.", "Manage Server"),
    ],
    "Welcome & Goodbye": [
        ("/welcome message", "Welcome new members with a plain text message.", "Manage Server"),
        ("/welcome embed", "Welcome new members with a custom embed.", "Manage Server"),
        ("/goodbye message", "Announce members leaving with a plain text message.", "Manage Server"),
        ("/goodbye embed", "Announce members leaving with a custom embed.", "Manage Server"),
        ("/greet test", "Send a test welcome or goodbye message.", "Manage Server"),
    ],
    "Jail": [
        ("/jail", "Moves a member into jail, removing their other roles.", "Moderate Members"),
        ("/unjail", "Releases a member from jail and restores their previous roles.", "Moderate Members"),
        ("/setjail", "Configure the jail role and channel.", "Administrator"),
        ("/createjail", "Creates a jail role + channel with the correct permissions, and configures jail.", "Administrator"),
    ],
    "Mod Logs": [
        ("/modlogs", "View moderation logs.", "View Audit Log"),
        ("/exportlogs", "Export moderation logs.", "Administrator"),
    ],
    "Messaging Tools": [
        ("/say", "Sends a message as the bot.", "Manage Messages"),
        ("/embed", "Sends a custom embed.", "Manage Messages"),
        ("/announce", "Posts an announcement.", "Manage Messages"),
        ("/poll", "Creates a poll.", "Manage Messages"),
        ("/reactionrole", "Creates a reaction role message.", "Manage Roles"),
        ("/sticky", "Pins a message to the bottom by reposting it.", "Manage Messages"),
        ("/pin", "Pins a message.", "Manage Messages"),
        ("/unpin", "Unpins a message.", "Manage Messages"),
    ],
    "Info": [
        ("/userinfo", "View member information.", "None"),
        ("/avatar", "Display a user's avatar.", "None"),
        ("/banner", "Display a user's banner.", "None"),
        ("/roles", "View a member's roles.", "None"),
        ("/permissions", "View a member's permissions.", "None"),
        ("/joined", "See when a member joined.", "None"),
        ("/created", "See when a Discord account was created.", "None"),
        ("/serverinfo", "View server information.", "None"),
        ("/channelinfo", "View channel information.", "None"),
        ("/roleinfo", "View role information.", "None"),
    ],
    "Social": [
        ("/hug", "Hug another user.", "None"),
        ("/kiss", "Kiss another user.", "None"),
        ("/pat", "Pat another user.", "None"),
        ("/slap", "Slap another user.", "None"),
        ("/poke", "Poke another user.", "None"),
        ("/highfive", "High five another user.", "None"),
        ("/bonk", "Bonk another user.", "None"),
        ("/wave", "Wave at another user.", "None"),
        ("/cuddle", "Cuddle another user.", "None"),
        ("/dance", "Dance with another user.", "None"),
    ],
    "Games": [
        ("/connect4", "Play Connect Four with another user.", "None"),
        ("/rps", "Rock Paper Scissors battle.", "None"),
        ("/checkers", "Play checkers against another player.", "None"),
        ("/chess", "Play chess against another player.", "None"),
        ("/battleship", "Guess and destroy the opponent's ships.", "None"),
    ],
    "Misc": [
        ("/afk", "Sets your AFK status with an optional reason. Removed automatically when you send a message.", "None"),
    ],
}

BLACK = discord.Color.from_str("#000000")


def build_category_embed(category: str) -> discord.Embed:
    commands_list = CATEGORIES[category]
    lines = [f"`{cmd}` \u2014 {desc} \u2014 `{perm}`" for cmd, desc, perm in commands_list]
    embed = discord.Embed(
        title=category,
        description="\n".join(lines),
        color=BLACK,
    )
    embed.set_footer(text=f"{len(commands_list)} command(s) in this category")
    return embed


def build_overview_embed() -> discord.Embed:
    total = sum(len(v) for v in CATEGORIES.values())
    embed = discord.Embed(
        title="Help",
        description=(
            f"Use the dropdown below to browse commands by category.\n"
            f"`{total}` commands across `{len(CATEGORIES)}` categories."
        ),
        color=BLACK,
    )
    for category, cmds in CATEGORIES.items():
        embed.add_field(name=category, value=f"`{len(cmds)}` command(s)", inline=True)
    return embed


class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=category, description=f"{len(cmds)} command(s)")
            for category, cmds in CATEGORIES.items()
        ]
        super().__init__(placeholder="Select a category", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        embed = build_category_embed(self.values[0])
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.message: discord.Message = None
        self.add_item(HelpSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This help menu isn't yours. Run /help to get your own.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class Help(commands.Cog):
    """Displays all bot commands and their required permissions, grouped by category."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Shows all commands and required permissions.")
    async def help(self, interaction: discord.Interaction):
        embed = build_overview_embed()
        view = HelpView(author_id=interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
