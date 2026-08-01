import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed
from storage import storage


class Afk(commands.Cog):
    """Lets members set an AFK status that is automatically cleared when they next speak."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="afk", description="Sets your AFK status with an optional reason.")
    @app_commands.describe(reason="Why you're AFK (optional)")
    async def afk(self, interaction: discord.Interaction, reason: str = None):
        storage.set_afk(interaction.guild.id, interaction.user.id, reason or "No reason given")
        embed = make_embed(f"{interaction.user.mention} is now afk, {reason or 'no reason given'}.")
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        # Clear the sender's own AFK status when they send a message.
        was_afk = storage.clear_afk(message.guild.id, message.author.id)
        if was_afk:
            try:
                await message.channel.send(f"Welcome back, {message.author.mention}. Your AFK status has been removed.", delete_after=8)
            except discord.HTTPException:
                pass

        # Notify if the message mentions someone who is currently AFK.
        for mentioned in message.mentions:
            afk_entry = storage.get_afk(message.guild.id, mentioned.id)
            if afk_entry:
                try:
                    await message.channel.send(f"{mentioned.display_name} is AFK: {afk_entry['reason']}")
                except discord.HTTPException:
                    pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Afk(bot))
