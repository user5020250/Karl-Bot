import discord
from discord import app_commands
from discord.ext import commands

BLACK = discord.Color.from_str("#000000")



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
    # PURGE COMMANDS
    # ---------------------------------------------------------------------
    purge_group = app_commands.Group(name="purge", description="Delete messages matching a filter.")

    @purge_group.command(name="user", description="Delete messages sent by a specific user.")
    @app_commands.describe(member="The user whose messages should be deleted", amount="Number of recent messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_user(self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1, 200] = 100):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount, check=lambda m: m.author.id == member.id)
        await interaction.followup.send(f"Deleted {len(deleted)} message(s) from {member.mention}.", ephemeral=True)

    @purge_group.command(name="bots", description="Delete messages sent by bots.")
    @app_commands.describe(amount="Number of recent messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_bots(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 100):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount, check=lambda m: m.author.bot)
        await interaction.followup.send(f"Deleted {len(deleted)} bot message(s).", ephemeral=True)

    @purge_group.command(name="links", description="Delete messages containing links.")
    @app_commands.describe(amount="Number of recent messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_links(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 100):
        await interaction.response.defer(ephemeral=True)
        check = lambda m: "http://" in m.content.lower() or "https://" in m.content.lower()
        deleted = await interaction.channel.purge(limit=amount, check=check)
        await interaction.followup.send(f"Deleted {len(deleted)} message(s) containing links.", ephemeral=True)

    @purge_group.command(name="invites", description="Delete Discord invite messages.")
    @app_commands.describe(amount="Number of recent messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_invites(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 100):
        await interaction.response.defer(ephemeral=True)
        markers = ("discord.gg/", "discord.com/invite/", "discordapp.com/invite/")
        deleted = await interaction.channel.purge(limit=amount, check=lambda m: any(x in m.content.lower() for x in markers))
        await interaction.followup.send(f"Deleted {len(deleted)} invite message(s).", ephemeral=True)

    @purge_group.command(name="images", description="Delete messages with image attachments.")
    @app_commands.describe(amount="Number of recent messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_images(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 100):
        await interaction.response.defer(ephemeral=True)
        image_exts = (".png", ".jpg", ".jpeg", ".gif", ".webp")
        check = lambda m: any(a.filename.lower().endswith(image_exts) for a in m.attachments)
        deleted = await interaction.channel.purge(limit=amount, check=check)
        await interaction.followup.send(f"Deleted {len(deleted)} message(s) with images.", ephemeral=True)

    @purge_group.command(name="embeds", description="Delete messages containing embeds.")
    @app_commands.describe(amount="Number of recent messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_embeds(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 100):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount, check=lambda m: len(m.embeds) > 0)
        await interaction.followup.send(f"Deleted {len(deleted)} message(s) containing embeds.", ephemeral=True)

    @purge_group.command(name="files", description="Delete messages with file attachments.")
    @app_commands.describe(amount="Number of recent messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_files(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 100):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount, check=lambda m: len(m.attachments) > 0)
        await interaction.followup.send(f"Deleted {len(deleted)} message(s) with attachments.", ephemeral=True)

    @purge_group.command(name="mentions", description="Delete messages containing user or role mentions.")
    @app_commands.describe(amount="Number of recent messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_mentions(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 100):
        await interaction.response.defer(ephemeral=True)
        check = lambda m: len(m.mentions) > 0 or len(m.role_mentions) > 0
        deleted = await interaction.channel.purge(limit=amount, check=check)
        await interaction.followup.send(f"Deleted {len(deleted)} message(s) containing mentions.", ephemeral=True)

    @purge_group.command(name="contains", description="Delete messages containing specific text.")
    @app_commands.describe(text="Text to search for", amount="Number of recent messages to scan (1-200)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_contains(self, interaction: discord.Interaction, text: str, amount: app_commands.Range[int, 1, 200] = 100):
        await interaction.response.defer(ephemeral=True)
        needle = text.lower()
        deleted = await interaction.channel.purge(limit=amount, check=lambda m: needle in m.content.lower())
        await interaction.followup.send(f"Deleted {len(deleted)} message(s) containing `{text}`.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Messages(bot))
