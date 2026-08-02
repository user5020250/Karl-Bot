import asyncio
import json
import os
import re

import discord
from discord import app_commands
from discord.ext import commands


BLACK = discord.Color.from_str("#000000")

ROLE_MENTION_RE = re.compile(r"^<@&(\d+)>$")
ROLE_MENTION_GLOBAL_RE = re.compile(r"<@&\d+>")

REACTIONROLE_DATA_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "reactionrole_data.json"
)


def load_reactionrole_data() -> dict:
    if not os.path.exists(REACTIONROLE_DATA_FILE):
        return {}
    with open(REACTIONROLE_DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_reactionrole_data(data: dict) -> None:
    with open(REACTIONROLE_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def resolve_role(guild: discord.Guild, token: str):
    """Resolve a role from a mention, raw ID, or name (case-insensitive,
    with or without a leading @)."""
    match = ROLE_MENTION_RE.match(token)
    if match:
        return guild.get_role(int(match.group(1)))

    if token.isdigit():
        return guild.get_role(int(token))

    name = token[1:] if token.startswith("@") else token

    return discord.utils.find(
        lambda r: r.name.lower() == name.lower(), guild.roles
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

    async def _send_ephemeral(self, interaction: discord.Interaction, content: str, delay: float = 5):
        """Send an ephemeral reply and schedule it to auto-delete shortly after,
        without blocking whatever the caller does next."""
        await interaction.response.send_message(content, ephemeral=True)
        asyncio.create_task(self._delete_after(interaction, delay))

    async def _delete_after(self, interaction: discord.Interaction, delay: float):
        await asyncio.sleep(delay)
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass

    # --------------------
    # SAY
    # --------------------

    @say_group.command(
        name="send",
        description="Sends a message as the bot."
    )
    @app_commands.describe(
        description="The message content (optional).",
        title="Optional title (sent as an embed if provided).",
        footer="Optional footer text (sent as an embed if provided).",
        img="Optional image URL (sent as an embed if provided)."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def say_send(
        self,
        interaction: discord.Interaction,
        description: str = None,
        title: str = None,
        footer: str = None,
        img: str = None
    ):

        if not any([description, title, footer, img]):
            await self._send_ephemeral(
                interaction,
                "Provide at least one of: description, title, footer, or img."
            )
            return

        await self._send_ephemeral(interaction, "Message sent.")

        if title or footer or img:
            embed = discord.Embed(color=BLACK)

            if description:
                embed.description = description

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
        description="The new message content (optional).",
        title="Optional title (sent as an embed if provided).",
        footer="Optional footer text (sent as an embed if provided).",
        img="Optional image URL (sent as an embed if provided)."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def say_edit(
        self,
        interaction: discord.Interaction,
        message_id: str,
        description: str = None,
        title: str = None,
        footer: str = None,
        img: str = None
    ):

        try:
            msg = await interaction.channel.fetch_message(
                int(message_id)
            )
        except:
            await self._send_ephemeral(interaction, "Invalid message ID.")
            return

        if msg.author.id != self.bot.user.id:
            await self._send_ephemeral(
                interaction, "I can only edit my own messages."
            )
            return

        if not any([description, title, footer, img]):
            await self._send_ephemeral(
                interaction,
                "Provide at least one of: description, title, footer, or img."
            )
            return

        if title or footer or img:
            embed = discord.Embed(color=BLACK)

            if description:
                embed.description = description

            if title:
                embed.title = title

            if footer:
                embed.set_footer(text=footer)

            if img:
                embed.set_image(url=img)

            await msg.edit(content=None, embed=embed)
        else:
            await msg.edit(content=description, embed=None)

        await self._send_ephemeral(interaction, "Message edited.")


    # --------------------
    # EMBED
    # --------------------

    @embed_group.command(
        name="send",
        description="Sends a custom embed."
    )
    @app_commands.describe(
        description="The embed description (optional).",
        title="Optional title.",
        footer="Optional footer text.",
        img="Optional image URL."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed_send(
        self,
        interaction: discord.Interaction,
        description: str = None,
        title: str = None,
        footer: str = None,
        img: str = None
    ):

        if not any([description, title, footer, img]):
            await self._send_ephemeral(
                interaction,
                "Provide at least one of: description, title, footer, or img."
            )
            return

        embed = discord.Embed(color=BLACK)

        if description:
            embed.description = description

        if title:
            embed.title = title

        if footer:
            embed.set_footer(text=footer)

        if img:
            embed.set_image(url=img)

        await self._send_ephemeral(interaction, "Embed sent.")

        await interaction.channel.send(embed=embed)


    @embed_group.command(
        name="edit",
        description="Edits an embed previously sent by the bot."
    )
    @app_commands.describe(
        message_id="The ID of the embed message to edit.",
        description="The new embed description (optional).",
        title="Optional title.",
        footer="Optional footer text.",
        img="Optional image URL."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed_edit(
        self,
        interaction: discord.Interaction,
        message_id: str,
        description: str = None,
        title: str = None,
        footer: str = None,
        img: str = None
    ):

        try:
            msg = await interaction.channel.fetch_message(
                int(message_id)
            )
        except:
            await self._send_ephemeral(interaction, "Invalid message ID.")
            return

        if msg.author.id != self.bot.user.id:
            await self._send_ephemeral(
                interaction, "I can only edit my own messages."
            )
            return

        if not any([description, title, footer, img]):
            await self._send_ephemeral(
                interaction,
                "Provide at least one of: description, title, footer, or img."
            )
            return

        embed = discord.Embed(color=BLACK)

        if description:
            embed.description = description

        if title:
            embed.title = title

        if footer:
            embed.set_footer(text=footer)

        if img:
            embed.set_image(url=img)

        await msg.edit(embed=embed)

        await self._send_ephemeral(interaction, "Embed edited.")


    # --------------------
    # ANNOUNCE
    # --------------------

    @app_commands.command(
        name="announce",
        description="Posts an announcement."
    )
    @app_commands.describe(
        type="Plain text message or a styled embed.",
        description="The announcement content (optional for embed type).",
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
        description: str = None,
        title: str = None,
        footer: str = None,
        img: str = None
    ):

        if type.value == "message":
            if not description:
                await self._send_ephemeral(
                    interaction,
                    "A plain message announcement needs a description."
                )
                return

            await self._send_ephemeral(interaction, "Announcement posted.")

            await interaction.channel.send(description)
            return

        if not any([description, title, footer, img]):
            await self._send_ephemeral(
                interaction,
                "Provide at least one of: description, title, footer, or img."
            )
            return

        embed = discord.Embed(
            title=title if title else "Announcement",
            color=BLACK
        )

        if description:
            embed.description = description

        embed.set_footer(
            text=footer if footer else f"Posted by {interaction.user}"
        )

        if img:
            embed.set_image(url=img)

        await self._send_ephemeral(interaction, "Announcement posted.")

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
        message_id="The ID of the message (in this channel) to attach buttons to.",
        type="How members can select roles from this button group.",
        roles="Roles, comma-separated (mention, ID, or exact name). No limit."
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="single role", value="single"),
        app_commands.Choice(name="multiple role", value="multiple"),
        app_commands.Choice(name="unique", value="unique"),
    ])
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reactionrole(
        self,
        interaction: discord.Interaction,
        message_id: str,
        type: app_commands.Choice[str],
        roles: str
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

        if message.author.id != self.bot.user.id:
            await interaction.response.send_message(
                "I can only attach reaction role buttons to a message "
                "I sent myself (Discord doesn't allow bots to add "
                "components to someone else's message). Post the message "
                "with `/say send` or `/embed send` first, then run "
                "`/reactionrole` on that message's ID.",
                ephemeral=True
            )
            return

        guild = interaction.guild

        mentions = ROLE_MENTION_GLOBAL_RE.findall(roles)
        remainder = ROLE_MENTION_GLOBAL_RE.sub(",", roles)

        tokens = mentions + [
            token.strip()
            for line in remainder.splitlines()
            for token in line.split(",")
        ]
        tokens = [t for t in tokens if t]

        if not tokens:
            await interaction.response.send_message(
                "No roles were provided.",
                ephemeral=True
            )
            return

        view = discord.ui.View(timeout=None)
        added = []
        errors = []
        role_ids = []

        for token in tokens:
            role = resolve_role(guild, token)

            if role is None:
                errors.append(f"Role `{token}` not found.")
                continue

            if role.id in role_ids:
                continue  # skip duplicate

            if role >= guild.me.top_role:
                errors.append(
                    f"My role is below `{role.name}`, can't assign it."
                )
                continue

            button = discord.ui.Button(
                label=role.name,
                style=discord.ButtonStyle.secondary,
                custom_id=f"reactionrole:{role.id}",
            )

            try:
                view.add_item(button)
            except ValueError:
                errors.append(
                    "Stopped here — Discord allows a maximum of 25 "
                    "buttons on one message."
                )
                break

            role_ids.append(role.id)
            added.append(role.mention)

        if added:
            await message.edit(view=view)

            data = load_reactionrole_data()
            data[str(message.id)] = {
                "type": type.value,
                "roles": role_ids,
            }
            save_reactionrole_data(data)

        summary = ""
        if added:
            summary += "**Added:**\n" + ", ".join(added) + "\n"
        if errors:
            summary += "**Errors:**\n" + "\n".join(errors)
        if not summary:
            summary = "Nothing was added."

        await interaction.response.send_message(summary, ephemeral=True)


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

        data = load_reactionrole_data()
        config = data.get(str(interaction.message.id), {})
        rr_type = config.get("type", "multiple")
        group_role_ids = set(config.get("roles", [role_id]))

        member = interaction.user
        has_role = role in member.roles

        if rr_type == "multiple":
            if has_role:
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
            return

        if rr_type == "single":
            if has_role:
                await member.remove_roles(role)
                await interaction.response.send_message(
                    f"Removed role `{role.name}`",
                    ephemeral=True
                )
                return

            to_remove = [
                r for r in member.roles
                if r.id in group_role_ids and r.id != role_id
            ]
            if to_remove:
                await member.remove_roles(*to_remove)
            await member.add_roles(role)
            await interaction.response.send_message(
                f"Added role `{role.name}`",
                ephemeral=True
            )
            return

        if rr_type == "unique":
            if has_role:
                await interaction.response.send_message(
                    f"You already have `{role.name}`.",
                    ephemeral=True
                )
                return

            to_remove = [
                r for r in member.roles
                if r.id in group_role_ids and r.id != role_id
            ]
            if to_remove:
                await member.remove_roles(*to_remove)
            await member.add_roles(role)
            await interaction.response.send_message(
                f"Added role `{role.name}`",
                ephemeral=True
            )
            return


    # --------------------
    # STICKY
    # --------------------

    @sticky_group.command(
        name="set",
        description="Creates a sticky message in this channel."
    )
    @app_commands.describe(
        type="Plain text message or a styled embed.",
        description="The main sticky text (optional for embed type).",
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
        description: str = None,
        title: str = None,
        footer: str = None,
        img: str = None
    ):

        if type.value == "message":
            if not description:
                await self._send_ephemeral(
                    interaction,
                    "A plain sticky message needs a description."
                )
                return

            self.sticky_messages[interaction.channel.id] = {
                "type": "text",
                "content": description,
            }

            await self._send_ephemeral(interaction, "Sticky message enabled.")

            await interaction.channel.send(description)
            return

        if not any([description, title, footer, img]):
            await self._send_ephemeral(
                interaction,
                "Provide at least one of: description, title, footer, or img."
            )
            return

        embed = discord.Embed(color=BLACK)

        if description:
            embed.description = description

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

        await self._send_ephemeral(interaction, "Sticky message enabled.")

        await interaction.channel.send(embed=embed)


    @sticky_group.command(
        name="edit",
        description="Edits an existing sticky message."
    )
    @app_commands.describe(
        message_id="The ID of the sticky message to edit.",
        type="Plain text message or a styled embed.",
        description="The new sticky text (optional for embed type).",
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
        description: str = None,
        title: str = None,
        footer: str = None,
        img: str = None
    ):

        try:
            msg = await interaction.channel.fetch_message(
                int(message_id)
            )
        except:
            await self._send_ephemeral(interaction, "Invalid message ID.")
            return

        if msg.author.id != self.bot.user.id:
            await self._send_ephemeral(
                interaction, "I can only edit my own messages."
            )
            return

        if type.value == "message":
            if not description:
                await self._send_ephemeral(
                    interaction,
                    "A plain sticky message needs a description."
                )
                return

            await msg.edit(content=description, embed=None)

            self.sticky_messages[interaction.channel.id] = {
                "type": "text",
                "content": description,
            }

            await self._send_ephemeral(interaction, "Sticky message edited.")
            return

        if not any([description, title, footer, img]):
            await self._send_ephemeral(
                interaction,
                "Provide at least one of: description, title, footer, or img."
            )
            return

        embed = discord.Embed(color=BLACK)

        if description:
            embed.description = description

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

        await self._send_ephemeral(interaction, "Sticky message edited.")


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
