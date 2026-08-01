import discord
from discord import app_commands
from discord.ext import commands


BLACK = discord.Color.from_str("#000000")


class ReactionRoleView(discord.ui.View):
    def __init__(self, role: discord.Role):
        super().__init__(timeout=None)
        self.role = role

    @discord.ui.button(
        label="Get Role",
        style=discord.ButtonStyle.secondary,
        custom_id="reaction_role_button"
    )
    async def role_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        member = interaction.user

        if self.role in member.roles:
            await member.remove_roles(self.role)
            await interaction.response.send_message(
                f"Removed role `{self.role.name}`",
                ephemeral=True
            )

        else:
            await member.add_roles(self.role)
            await interaction.response.send_message(
                f"Added role `{self.role.name}`",
                ephemeral=True
            )


class Utility(commands.Cog):

    say_group = app_commands.Group(
        name="say",
        description="Send or edit a message as the bot."
    )
    embed_group = app_commands.Group(
        name="embed",
        description="Send or edit a custom embed."
    )
    sticky_group = app_commands.Group(
        name="sticky",
        description="Create or edit a sticky message in this channel."
    )

    def __init__(self, bot):
        self.bot = bot
        self.sticky_messages = {}

    # --------------------
    # SAY
    # --------------------

    @say_group.command(
        name="send",
        description="Sends a message as the bot."
    )
    @app_commands.describe(
        description="The message content (required).",
        title="Optional title (sent as an embed if provided).",
        footer="Optional footer text (sent as an embed if provided).",
        img="Optional image URL (sent as an embed if provided)."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def say_send(
        self,
        interaction: discord.Interaction,
        description: str,
        title: str = None,
        footer: str = None,
        img: str = None
    ):

        await interaction.response.send_message(
            "Message sent.",
            ephemeral=True
        )

        if title or footer or img:
            embed = discord.Embed(
                description=description,
                color=BLACK
            )

            if title:
                embed.title = title

            if footer:
                embed.set_footer(text=footer)

            if img:
                embed.set_image(url=img)

            await interaction.channel.send(embed=embed)
        else:
            await interaction.channel.send(description)


    @say_group.command(
        name="edit",
        description="Edits a message previously sent by the bot."
    )
    @app_commands.describe(
        message_id="The ID of the message to edit.",
        description="The new message content (required).",
        title="Optional title (sent as an embed if provided).",
        footer="Optional footer text (sent as an embed if provided).",
        img="Optional image URL (sent as an embed if provided)."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def say_edit(
        self,
        interaction: discord.Interaction,
        message_id: str,
        description: str,
        title: str = None,
        footer: str = None,
        img: str = None
    ):

        try:
            msg = await interaction.channel.fetch_message(
                int(message_id)
            )
        except:
            await interaction.response.send_message(
                "Invalid message ID.",
                ephemeral=True
            )
            return

        if msg.author.id != self.bot.user.id:
            await interaction.response.send_message(
                "I can only edit my own messages.",
                ephemeral=True
            )
            return

        if title or footer or img:
            embed = discord.Embed(
                description=description,
                color=BLACK
            )

            if title:
                embed.title = title

            if footer:
                embed.set_footer(text=footer)

            if img:
                embed.set_image(url=img)

            await msg.edit(content=None, embed=embed)
        else:
            await msg.edit(content=description, embed=None)

        await interaction.response.send_message(
            "Message edited.",
            ephemeral=True
        )


    # --------------------
    # EMBED
    # --------------------

    @embed_group.command(
        name="send",
        description="Sends a custom embed."
    )
    @app_commands.describe(
        description="The embed description (required).",
        title="Optional title.",
        footer="Optional footer text.",
        img="Optional image URL."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed_send(
        self,
        interaction: discord.Interaction,
        description: str,
        title: str = None,
        footer: str = None,
        img: str = None
    ):

        embed = discord.Embed(
            description=description,
            color=BLACK
        )

        if title:
            embed.title = title

        if footer:
            embed.set_footer(text=footer)

        if img:
            embed.set_image(url=img)

        await interaction.response.send_message(
            "Embed sent.",
            ephemeral=True
        )

        await interaction.channel.send(embed=embed)


    @embed_group.command(
        name="edit",
        description="Edits an embed previously sent by the bot."
    )
    @app_commands.describe(
        message_id="The ID of the embed message to edit.",
        description="The new embed description (required).",
        title="Optional title.",
        footer="Optional footer text.",
        img="Optional image URL."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed_edit(
        self,
        interaction: discord.Interaction,
        message_id: str,
        description: str,
        title: str = None,
        footer: str = None,
        img: str = None
    ):

        try:
            msg = await interaction.channel.fetch_message(
                int(message_id)
            )
        except:
            await interaction.response.send_message(
                "Invalid message ID.",
                ephemeral=True
            )
            return

        if msg.author.id != self.bot.user.id:
            await interaction.response.send_message(
                "I can only edit my own messages.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            description=description,
            color=BLACK
        )

        if title:
            embed.title = title

        if footer:
            embed.set_footer(text=footer)

        if img:
            embed.set_image(url=img)

        await msg.edit(embed=embed)

        await interaction.response.send_message(
            "Embed edited.",
            ephemeral=True
        )


    # --------------------
    # ANNOUNCE
    # --------------------

    @app_commands.command(
        name="announce",
        description="Posts an announcement."
    )
    @app_commands.describe(
        type="Plain text message or a styled embed.",
        description="The announcement content (required).",
        title="Optional title (embed only).",
        footer="Optional footer text (embed only).",
        img="Optional image URL (embed only)."
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="message", value="message"),
        app_commands.Choice(name="embed", value="embed"),
    ])
    @app_commands.checks.has_permissions(manage_messages=True)
    async def announce(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],
        description: str,
        title: str = None,
        footer: str = None,
        img: str = None
    ):

        if type.value == "message":
            await interaction.response.send_message(
                "Announcement posted.",
                ephemeral=True
            )

            await interaction.channel.send(description)
            return

        embed = discord.Embed(
            title=title if title else "Announcement",
            description=description,
            color=BLACK
        )

        embed.set_footer(
            text=footer if footer else f"Posted by {interaction.user}"
        )

        if img:
            embed.set_image(url=img)

        await interaction.response.send_message(
            "Announcement posted.",
            ephemeral=True
        )

        await interaction.channel.send(embed=embed)


    # --------------------
    # POLL
    # --------------------

    @app_commands.command(
        name="poll",
        description="Creates a poll."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str
    ):

        embed = discord.Embed(
            title="Poll",
            description=(
                f"**{question}**\n\n"
                f"1️⃣ {option1}\n"
                f"2️⃣ {option2}"
            ),
            color=BLACK
        )

        await interaction.response.send_message(
            "Poll created.",
            ephemeral=True
        )

        msg = await interaction.channel.send(embed=embed)

        await msg.add_reaction("1️⃣")
        await msg.add_reaction("2️⃣")


    # --------------------
    # REACTION ROLE
    # --------------------

    @app_commands.command(
        name="reactionrole",
        description="Creates a reaction role button."
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reactionrole(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        message: str
    ):

        embed = discord.Embed(
            title="Role Selection",
            description=message,
            color=BLACK
        )

        await interaction.response.send_message(
            "Reaction role created.",
            ephemeral=True
        )

        await interaction.channel.send(
            embed=embed,
            view=ReactionRoleView(role)
        )


    # --------------------
    # STICKY
    # --------------------

    @sticky_group.command(
        name="set",
        description="Creates a sticky message in this channel."
    )
    @app_commands.describe(
        type="Plain text message or a styled embed.",
        description="The main sticky text (required).",
        title="Optional title (embed only).",
        footer="Optional footer text (embed only).",
        img="Optional image URL (embed only)."
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="message", value="message"),
        app_commands.Choice(name="embed", value="embed"),
    ])
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_set(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],
        description: str,
        title: str = None,
        footer: str = None,
        img: str = None
    ):

        if type.value == "message":
            self.sticky_messages[interaction.channel.id] = {
                "type": "text",
                "content": description,
            }

            await interaction.response.send_message(
                "Sticky message enabled.",
                ephemeral=True
            )

            await interaction.channel.send(description)
            return

        embed = discord.Embed(
            description=description,
            color=BLACK
        )

        if title:
            embed.title = title

        if footer:
            embed.set_footer(text=footer)

        if img:
            embed.set_image(url=img)

        self.sticky_messages[interaction.channel.id] = {
            "type": "embed",
            "embed": embed,
        }

        await interaction.response.send_message(
            "Sticky message enabled.",
            ephemeral=True
        )

        await interaction.channel.send(embed=embed)


    @sticky_group.command(
        name="edit",
        description="Edits an existing sticky message."
    )
    @app_commands.describe(
        message_id="The ID of the sticky message to edit.",
        type="Plain text message or a styled embed.",
        description="The new sticky text (required).",
        title="Optional title (embed only).",
        footer="Optional footer text (embed only).",
        img="Optional image URL (embed only)."
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="message", value="message"),
        app_commands.Choice(name="embed", value="embed"),
    ])
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_edit(
        self,
        interaction: discord.Interaction,
        message_id: str,
        type: app_commands.Choice[str],
        description: str,
        title: str = None,
        footer: str = None,
        img: str = None
    ):

        try:
            msg = await interaction.channel.fetch_message(
                int(message_id)
            )
        except:
            await interaction.response.send_message(
                "Invalid message ID.",
                ephemeral=True
            )
            return

        if msg.author.id != self.bot.user.id:
            await interaction.response.send_message(
                "I can only edit my own messages.",
                ephemeral=True
            )
            return

        if type.value == "message":
            await msg.edit(content=description, embed=None)

            self.sticky_messages[interaction.channel.id] = {
                "type": "text",
                "content": description,
            }

            await interaction.response.send_message(
                "Sticky message edited.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            description=description,
            color=BLACK
        )

        if title:
            embed.title = title

        if footer:
            embed.set_footer(text=footer)

        if img:
            embed.set_image(url=img)

        await msg.edit(content=None, embed=embed)

        self.sticky_messages[interaction.channel.id] = {
            "type": "embed",
            "embed": embed,
        }

        await interaction.response.send_message(
            "Sticky message edited.",
            ephemeral=True
        )


    @commands.Cog.listener()
    async def on_message(self, message):

        if message.author.bot:
            return

        if message.channel.id in self.sticky_messages:

            sticky = self.sticky_messages[message.channel.id]

            if sticky["type"] == "text":
                await message.channel.send(sticky["content"])
            else:
                await message.channel.send(embed=sticky["embed"])

    # --------------------
    # PIN
    # --------------------

    @app_commands.command(
        name="pin",
        description="Pins a message."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def pin(
        self,
        interaction: discord.Interaction,
        message_id: str
    ):

        try:
            msg = await interaction.channel.fetch_message(
                int(message_id)
            )

            await msg.pin()

            await interaction.response.send_message(
                "Message pinned.",
                ephemeral=True
            )

        except:
            await interaction.response.send_message(
                "Invalid message ID.",
                ephemeral=True
            )


    # --------------------
    # UNPIN
    # --------------------

    @app_commands.command(
        name="unpin",
        description="Unpins a message."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def unpin(
        self,
        interaction: discord.Interaction,
        message_id: str
    ):

        try:
            msg = await interaction.channel.fetch_message(
                int(message_id)
            )

            await msg.unpin()

            await interaction.response.send_message(
                "Message unpinned.",
                ephemeral=True
            )

        except:
            await interaction.response.send_message(
                "Invalid message ID.",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Utility(bot))
