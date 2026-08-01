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

    def __init__(self, bot):
        self.bot = bot
        self.sticky_messages = {}

    # --------------------
    # SAY
    # --------------------

    @app_commands.command(
        name="say",
        description="Sends a message as the bot."
    )
    @app_commands.describe(
        description="The message content (required).",
        title="Optional title (sent as an embed if provided).",
        footer="Optional footer text (sent as an embed if provided).",
        img="Optional image attachment (sent as an embed if provided)."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def say(
        self,
        interaction: discord.Interaction,
        description: str,
        title: str = None,
        footer: str = None,
        img: discord.Attachment = None
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
                embed.set_image(url=img.url)

            await interaction.channel.send(embed=embed)
        else:
            await interaction.channel.send(description)


    # --------------------
    # EMBED
    # --------------------

    @app_commands.command(
        name="embed",
        description="Sends a custom embed."
    )
    @app_commands.describe(
        description="The embed description (required).",
        title="Optional title.",
        footer="Optional footer text.",
        img="Optional image attachment."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed(
        self,
        interaction: discord.Interaction,
        description: str,
        title: str = None,
        footer: str = None,
        img: discord.Attachment = None
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
            embed.set_image(url=img.url)

        await interaction.response.send_message(
            "Embed sent.",
            ephemeral=True
        )

        await interaction.channel.send(embed=embed)


    # --------------------
    # ANNOUNCE
    # --------------------

    @app_commands.command(
        name="announce",
        description="Posts an announcement."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def announce(
        self,
        interaction: discord.Interaction,
        message: str
    ):

        embed = discord.Embed(
            title="Announcement",
            description=message,
            color=BLACK
        )

        embed.set_footer(
            text=f"Posted by {interaction.user}"
        )

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

    @app_commands.command(
        name="sticky",
        description="Creates a sticky message in this channel."
    )
    @app_commands.describe(
        type="Plain text message or a styled embed.",
        description="The main sticky text (required).",
        title="Optional title (embed only).",
        footer="Optional footer text (embed only).",
        img="Optional image attachment (embed only)."
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="message", value="message"),
        app_commands.Choice(name="embed", value="embed"),
    ])
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],
        description: str,
        title: str = None,
        footer: str = None,
        img: discord.Attachment = None
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
            embed.set_image(url=img.url)

        self.sticky_messages[interaction.channel.id] = {
            "type": "embed",
            "embed": embed,
        }

        await interaction.response.send_message(
            "Sticky message enabled.",
            ephemeral=True
        )

        await interaction.channel.send(embed=embed)


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
