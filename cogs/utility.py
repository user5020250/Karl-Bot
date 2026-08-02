import re

import discord
from discord import app_commands
from discord.ext import commands


BLACK = discord.Color.from_str("#000000")

ROLE_MENTION_RE = re.compile(r"^<@&(\d+)>$")


def resolve_role(guild: discord.Guild, token: str):
    """Resolve a role from a mention, raw ID, or exact name (case-insensitive)."""
    match = ROLE_MENTION_RE.match(token)
    if match:
        return guild.get_role(int(match.group(1)))

    if token.isdigit():
        return guild.get_role(int(token))

    return discord.utils.find(
        lambda r: r.name.lower() == token.lower(), guild.roles
    )


class ReactionRoleModal(discord.ui.Modal, title="Reaction Roles"):
    roles_input = discord.ui.TextInput(
        label="Emoji + Role, one pair per line",
        style=discord.TextStyle.paragraph,
        placeholder="🎮 Gamers\n🎨 Artists\n@Musicians\n987654321098765432",
        required=True,
        max_length=4000,
    )

    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild

        lines = [
            ln.strip() for ln in self.roles_input.value.splitlines() if ln.strip()
        ]

        if not lines:
            await interaction.response.send_message(
                "No roles were provided.",
                ephemeral=True
            )
            return

        view = discord.ui.View(timeout=None)
        added = []
        errors = []

        for line_num, line in enumerate(lines, start=1):
            parts = line.split(maxsplit=1)

            if len(parts) == 2:
                emoji_token, role_token = parts
            else:
                emoji_token, role_token = None, parts[0]

            role = resolve_role(guild, role_token)

            # in case the "emoji" token was actually part of a multi-word role name
            if role is None and emoji_token is not None:
                whole_line_role = resolve_role(guild, line)
                if whole_line_role is not None:
                    role = whole_line_role
                    emoji_token = None

            if role is None:
                errors.append(f"Line {line_num}: role `{role_token}` not found.")
                continue

            if role >= guild.me.top_role:
                errors.append(
                    f"Line {line_num}: my role is below `{role.name}`, "
                    f"can't assign it."
                )
                continue

            emoji = None
            if emoji_token:
                try:
                    emoji = discord.PartialEmoji.from_str(emoji_token)
                except Exception:
                    errors.append(
                        f"Line {line_num}: `{emoji_token}` isn't a valid emoji, "
                        f"added button without it."
                    )
                    emoji_token = None

            button = discord.ui.Button(
                label=role.name,
                style=discord.ButtonStyle.secondary,
                custom_id=f"reactionrole:{role.id}",
                emoji=emoji,
            )

            try:
                view.add_item(button)
            except ValueError:
                errors.append(
                    f"Line {line_num}: stopped here — Discord allows a "
                    f"maximum of 25 buttons on one message."
                )
                break

            added.append(f"{(emoji_token + ' ') if emoji_token else ''}{role.mention}")

        if added:
            await self.message.edit(view=view)

        summary = ""
        if added:
            summary += "**Added:**\n" + "\n".join(added) + "\n"
        if errors:
            summary += "**Errors:**\n" + "\n".join(errors)
        if not summary:
            summary = "Nothing was added."

        await interaction.response.send_message(summary, ephemeral=True)


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
        description="Attach reaction role buttons to an existing message."
    )
    @app_commands.describe(
        message_id="The ID of the message (in this channel) to attach buttons to."
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reactionrole(
        self,
        interaction: discord.Interaction,
        message_id: str
    ):

        if not message_id.isdigit():
            await interaction.response.send_message(
                "Invalid message ID.",
                ephemeral=True
            )
            return

        try:
            message = await interaction.channel.fetch_message(
                int(message_id)
            )
        except:
            await interaction.response.send_message(
                "Invalid message ID.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(ReactionRoleModal(message))


    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):

        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")

        if not custom_id.startswith("reactionrole:"):
            return

        role_id = int(custom_id.split(":", 1)[1])
        guild = interaction.guild
        role = guild.get_role(role_id) if guild else None

        if role is None:
            await interaction.response.send_message(
                "That role no longer exists.",
                ephemeral=True
            )
            return

        member = interaction.user

        if role in member.roles:
            await member.remove_roles(role)
            await interaction.response.send_message(
                f"Removed role `{role.name}`",
                ephemeral=True
            )
        else:
            await member.add_roles(role)
            await interaction.response.send_message(
                f"Added role `{role.name}`",
                ephemeral=True
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
