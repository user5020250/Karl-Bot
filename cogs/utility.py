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


# ============================================================
# STICKY COMMAND GROUP
# ============================================================

sticky_group = app_commands.Group(
    name="sticky",
    description="Manage sticky messages in this channel."
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
    @app_commands.checks.has_permissions(manage_messages=True)
    async def say(
        self,
        interaction: discord.Interaction,
        message: str
    ):

        await interaction.response.send_message(
            "Message sent.",
            ephemeral=True
        )

        await interaction.channel.send(message)


    # --------------------
    # EMBED
    # --------------------

    @app_commands.command(
        name="embed",
        description="Sends a custom embed."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str
    ):

        embed = discord.Embed(
            title=title,
            description=description,
            color=BLACK
        )

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

    @sticky_group.command(
        name="message",
        description="Creates a sticky plain text message."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_message(
        self,
        interaction: discord.Interaction,
        description: str
    ):

        self.sticky_messages[interaction.channel.id] = {
            "type": "text",
            "content": description,
        }

        await interaction.response.send_message(
            "Sticky message enabled.",
            ephemeral=True
        )

        await interaction.channel.send(description)

    @sticky_group.command(
        name="embed",
        description="Creates a sticky embed message."
    )
    @app_commands.describe(
        description="The main sticky text (required).",
        title="Optional embed title.",
        footer="Optional embed footer text.",
        image="Optional image to attach to the embed."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_embed(
        self,
        interaction: discord.Interaction,
        description: str,
        title: str = None,
        footer: str = None,
        image: discord.Attachment = None
    ):

        embed = discord.Embed(
            description=description,
            color=BLACK
        )

        if title:
            embed.title = title

        if footer:
            embed.set_footer(text=footer)

        if image:
            embed.set_image(url=image.url)

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
    cog = Utility(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(sticky_group)
