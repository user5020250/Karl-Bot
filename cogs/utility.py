import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed
from storage import storage


class Utility(commands.Cog):
    """Messaging utilities: say, embed, announce, poll, reaction roles, sticky, pin/unpin."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="say", description="Sends a message as the bot.")
    @app_commands.describe(message="The message to send", channel="Channel to send it in (defaults to this channel)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def say(self, interaction: discord.Interaction, message: str, channel: discord.TextChannel = None):
        channel = channel or interaction.channel
        await channel.send(message)
        await interaction.response.send_message(f"Message sent in {channel.mention}.", ephemeral=True)

    @app_commands.command(name="embed", description="Sends a custom embed.")
    @app_commands.describe(title="Embed title", description="Embed description", channel="Channel to send it in (defaults to this channel)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed(self, interaction: discord.Interaction, title: str, description: str, channel: discord.TextChannel = None):
        channel = channel or interaction.channel
        embed = make_embed(title, description)
        await channel.send(embed=embed)
        await interaction.response.send_message(f"Embed sent in {channel.mention}.", ephemeral=True)

    @app_commands.command(name="announce", description="Posts an announcement.")
    @app_commands.describe(message="The announcement text", channel="Channel to announce in", mention_everyone="Whether to ping @everyone")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(mention_everyone=True)
    async def announce(self, interaction: discord.Interaction, message: str, channel: discord.TextChannel = None, mention_everyone: bool = False):
        channel = channel or interaction.channel
        embed = make_embed("Announcement", message)
        content = "@everyone" if mention_everyone else None
        allowed = discord.AllowedMentions(everyone=mention_everyone)
        await channel.send(content=content, embed=embed, allowed_mentions=allowed)
        await interaction.response.send_message(f"Announcement posted in {channel.mention}.", ephemeral=True)

    @app_commands.command(name="poll", description="Creates a poll.")
    @app_commands.describe(question="The poll question", option1="First option", option2="Second option", option3="Third option (optional)", option4="Fourth option (optional)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def poll(self, interaction: discord.Interaction, question: str, option1: str, option2: str, option3: str = None, option4: str = None):
        options = [option1, option2]
        if option3:
            options.append(option3)
        if option4:
            options.append(option4)
        number_emojis = ["1\N{combining enclosing keycap}", "2\N{combining enclosing keycap}", "3\N{combining enclosing keycap}", "4\N{combining enclosing keycap}"]
        description = "\n".join(f"{number_emojis[i]} {opt}" for i, opt in enumerate(options))
        embed = make_embed(question, description)
        await interaction.response.send_message(embed=embed)
        sent = await interaction.original_response()
        for i in range(len(options)):
            await sent.add_reaction(number_emojis[i])

    @app_commands.command(name="reactionrole", description="Creates a reaction role message.")
    @app_commands.describe(channel="Channel to post the message in", message="The message content", emoji="The emoji members react with", role="The role given for that reaction")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def reactionrole(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str, emoji: str, role: discord.Role):
        embed = make_embed("Reaction Role", message)
        sent = await channel.send(embed=embed)
        try:
            await sent.add_reaction(emoji)
        except discord.HTTPException:
            await interaction.response.send_message("I couldn't react with that emoji. Make sure it's a standard or server emoji.", ephemeral=True)
            return
        storage.add_reaction_role(sent.id, emoji, role.id)
        await interaction.response.send_message(f"Reaction role message created in {channel.mention}.", ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member is None or payload.member.bot:
            return
        role_map = storage.get_reaction_roles(payload.message_id)
        if not role_map:
            return
        emoji_key = str(payload.emoji)
        role_id = role_map.get(emoji_key)
        if role_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        role = guild.get_role(int(role_id)) if guild else None
        if role is not None:
            try:
                await payload.member.add_roles(role, reason="Reaction role")
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        role_map = storage.get_reaction_roles(payload.message_id)
        if not role_map:
            return
        emoji_key = str(payload.emoji)
        role_id = role_map.get(emoji_key)
        if role_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(int(role_id))
        if member is not None and role is not None:
            try:
                await member.remove_roles(role, reason="Reaction role removed")
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------- sticky
    @app_commands.command(name="sticky", description="Pins a message to the bottom by reposting it.")
    @app_commands.describe(message="The sticky message content. Leave blank to clear the sticky in this channel.")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def sticky(self, interaction: discord.Interaction, message: str = None):
        channel = interaction.channel
        sticky_section = storage.section("sticky")
        if message is None:
            existing = sticky_section.get(str(channel.id))
            if existing and existing.get("message_id"):
                try:
                    old = await channel.fetch_message(int(existing["message_id"]))
                    await old.delete()
                except discord.HTTPException:
                    pass
            sticky_section.pop(str(channel.id), None)
            storage.save()
            await interaction.response.send_message("Sticky message cleared for this channel.", ephemeral=True)
            return

        embed = make_embed("Sticky Message", message)
        sent = await channel.send(embed=embed)
        sticky_section[str(channel.id)] = {"content": message, "message_id": sent.id}
        storage.save()
        await interaction.response.send_message("Sticky message set for this channel.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        sticky_section = storage.section("sticky")
        entry = sticky_section.get(str(message.channel.id))
        if not entry:
            return
        try:
            old = await message.channel.fetch_message(int(entry["message_id"]))
            await old.delete()
        except discord.HTTPException:
            pass
        embed = make_embed("Sticky Message", entry["content"])
        try:
            sent = await message.channel.send(embed=embed)
            entry["message_id"] = sent.id
            storage.save()
        except discord.HTTPException:
            pass

    # --------------------------------------------------------------- pin
    @app_commands.command(name="pin", description="Pins a message.")
    @app_commands.describe(message_id="The ID of the message to pin (defaults to the most recent message)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def pin(self, interaction: discord.Interaction, message_id: str = None):
        channel = interaction.channel
        if message_id:
            try:
                target = await channel.fetch_message(int(message_id))
            except (discord.NotFound, ValueError):
                await interaction.response.send_message("Couldn't find that message in this channel.", ephemeral=True)
                return
        else:
            history = [m async for m in channel.history(limit=2)]
            target = history[1] if len(history) > 1 else None
            if target is None:
                await interaction.response.send_message("No previous message found to pin.", ephemeral=True)
                return
        await target.pin(reason=f"Pinned by {interaction.user}")
        await interaction.response.send_message("Message pinned.", ephemeral=True)

    @app_commands.command(name="unpin", description="Unpins a message.")
    @app_commands.describe(message_id="The ID of the message to unpin")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def unpin(self, interaction: discord.Interaction, message_id: str):
        channel = interaction.channel
        try:
            target = await channel.fetch_message(int(message_id))
        except (discord.NotFound, ValueError):
            await interaction.response.send_message("Couldn't find that message in this channel.", ephemeral=True)
            return
        await target.unpin(reason=f"Unpinned by {interaction.user}")
        await interaction.response.send_message("Message unpinned.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
