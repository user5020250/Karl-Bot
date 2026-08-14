import discord
from discord import app_commands
from discord.ext import commands
from helpers import make_embed
from storage import storage


class AfkNotifyView(discord.ui.View):
    """Buttons shown when someone mentions an AFK user."""

    def __init__(self, cog: "Afk", guild_id: int, afk_user_id: int):
        # timeout=None so the buttons keep working even if this specific
        # message stays up a while (not persistent across bot restarts
        # unless you also register a template view in setup()).
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.afk_user_id = afk_user_id

    @discord.ui.button(label="Leave a message", style=discord.ButtonStyle.secondary)
    async def leave_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Guard: only useful if the target is still AFK.
        if not storage.get_afk(self.guild_id, self.afk_user_id):
            await interaction.response.send_message("They're not AFK anymore.", ephemeral=True)
            return
        await interaction.response.send_modal(LeaveMessageModal(self.cog, self.guild_id, self.afk_user_id))

    @discord.ui.button(label="Notify me when they are back", style=discord.ButtonStyle.secondary)
    async def notify_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not storage.get_afk(self.guild_id, self.afk_user_id):
            await interaction.response.send_message("They're not AFK anymore.", ephemeral=True)
            return

        self.cog.add_watcher(self.guild_id, self.afk_user_id, interaction.user.id)
        embed = make_embed("", "Got it! I'll ping you when they're back.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class LeaveMessageModal(discord.ui.Modal, title="Leave a message"):
    message = discord.ui.TextInput(
        label="Message",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True,
    )

    def __init__(self, cog: "Afk", guild_id: int, afk_user_id: int):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.afk_user_id = afk_user_id

    async def on_submit(self, interaction: discord.Interaction):
        self.cog.add_left_message(self.guild_id, self.afk_user_id, interaction.user.id, str(self.message))
        embed = make_embed("", "Your message will be passed along when they're back.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Afk(commands.Cog):
    """Lets members set an AFK status that is automatically cleared when they next speak."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # (guild_id, afk_user_id) -> set of watcher user ids to ping when they're back
        self.watchers: dict[tuple[int, int], set[int]] = {}
        # (guild_id, afk_user_id) -> list of (author_id, message_text)
        self.left_messages: dict[tuple[int, int], list[tuple[int, str]]] = {}

    def add_watcher(self, guild_id: int, afk_user_id: int, watcher_id: int):
        key = (guild_id, afk_user_id)
        self.watchers.setdefault(key, set()).add(watcher_id)

    def add_left_message(self, guild_id: int, afk_user_id: int, author_id: int, text: str):
        key = (guild_id, afk_user_id)
        self.left_messages.setdefault(key, []).append((author_id, text))

    def pop_watchers(self, guild_id: int, afk_user_id: int) -> set[int]:
        return self.watchers.pop((guild_id, afk_user_id), set())

    def pop_left_messages(self, guild_id: int, afk_user_id: int) -> list[tuple[int, str]]:
        return self.left_messages.pop((guild_id, afk_user_id), [])

    @app_commands.command(name="afk", description="Sets your AFK status with an optional reason.")
    @app_commands.describe(reason="Why you're afk")
    async def afk(self, interaction: discord.Interaction, reason: str = None):
        storage.set_afk(interaction.guild.id, interaction.user.id, reason or "No reason given")
        embed = make_embed("AFK", f"{interaction.user.mention} is now afk, reason: {reason or 'No reason given'}.")
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        # Clear the sender's own AFK status when they send a message.
        was_afk = storage.clear_afk(message.guild.id, message.author.id)
        if was_afk:
            try:
                await message.channel.send(
                    f"Welcome back, {message.author.mention}. Your AFK status has been removed.",
                    delete_after=8,
                )
            except discord.HTTPException:
                pass

            # Deliver any messages left for them while they were away.
            left = self.pop_left_messages(message.guild.id, message.author.id)
            if left:
                lines = [f"<@{author_id}>: {text}" for author_id, text in left]
                embed = make_embed(
                    "Messages while you were away",
                    "\n".join(lines),
                )
                try:
                    await message.channel.send(content=message.author.mention, embed=embed)
                except discord.HTTPException:
                    pass

            # Ping everyone who asked to be notified.
            watchers = self.pop_watchers(message.guild.id, message.author.id)
            if watchers:
                pings = " ".join(f"<@{watcher_id}>" for watcher_id in watchers)
                try:
                    await message.channel.send(f"{pings}, {message.author.mention} is back.")
                except discord.HTTPException:
                    pass

        # Notify if the message mentions someone who is currently AFK.
        for mentioned in message.mentions:
            afk_entry = storage.get_afk(message.guild.id, mentioned.id)
            if afk_entry:
                embed = make_embed(
                    "",
                    f"`{mentioned}` is AFK: {afk_entry['reason']}",
                )
                view = AfkNotifyView(self, message.guild.id, mentioned.id)
                try:
                    await message.channel.send(embed=embed, view=view)
                except discord.HTTPException:
                    pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Afk(bot))
