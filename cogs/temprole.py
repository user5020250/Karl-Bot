import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from helpers import make_embed, send_log
from storage import storage


_DURATION_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>mo|y|w|d|h|m|s)", re.IGNORECASE)
UNIT_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
    "w": 7 * 24 * 60 * 60,
    "mo": 30 * 24 * 60 * 60,
    "y": 365 * 24 * 60 * 60,
}


def parse_duration(value: str) -> int:
    """Parse strings such as 30m, 2h, 7d, 1w, 1mo, 1y, 1h30m."""
    if not value:
        raise ValueError("Duration cannot be empty.")

    value = value.strip().lower().replace(" ", "")
    if value.startswith("-"):
        raise ValueError("Duration cannot be negative.")

    position = 0
    total = 0.0

    for match in _DURATION_RE.finditer(value):
        if match.start() != position:
            raise ValueError("Invalid duration format.")

        amount = float(match.group("value"))
        unit = match.group("unit").lower()
        total += amount * UNIT_SECONDS[unit]
        position = match.end()

    if position != len(value):
        raise ValueError("Invalid duration format.")

    seconds = int(total)
    if seconds <= 0:
        raise ValueError("Duration must be greater than 0.")

    # Discord's role expiration is handled by the bot, so keep an explicit
    # upper bound to prevent accidental absurdly long values.
    if seconds > 10 * 365 * 24 * 60 * 60:
        raise ValueError("Duration cannot be longer than 10 years.")

    return seconds


def format_duration(seconds: int) -> str:
    parts = []
    units = (
        (365 * 24 * 60 * 60, "y"),
        (30 * 24 * 60 * 60, "mo"),
        (7 * 24 * 60 * 60, "w"),
        (24 * 60 * 60, "d"),
        (60 * 60, "h"),
        (60, "m"),
        (1, "s"),
    )

    remaining = int(seconds)
    for size, suffix in units:
        if remaining >= size:
            amount, remaining = divmod(remaining, size)
            parts.append(f"{amount}{suffix}")

    return " ".join(parts) or "0s"


class TempRole(commands.Cog):
    """Persistent temporary roles with human-readable durations."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.expiration_loop.start()

    def cog_unload(self):
        self.expiration_loop.cancel()

    async def _remove_expired(self):
        expired = storage.get_expired_temp_roles()
        for item in expired:
            guild = self.bot.get_guild(item["guild_id"])
            if guild is not None:
                role = guild.get_role(item["role_id"])
                member = guild.get_member(item["user_id"])
                if role is not None and member is not None and role in member.roles:
                    try:
                        await member.remove_roles(role, reason="Temporary role expired")
                    except (discord.Forbidden, discord.HTTPException):
                        # Keep the record so a later pass can retry it.
                        continue

                    embed = make_embed(
                        "Temporary Role Expired",
                        f"{role.mention} was automatically removed from {member.mention}."
                    )
                    await send_log(guild, embed, category="channels_roles")

            # The guild/member/role may no longer exist; in that case there is
            # nothing useful left to retry, so clean up the persistent record.
            storage.delete_temp_role(item["guild_id"], item["user_id"], item["role_id"])

    @tasks.loop(seconds=15)
    async def expiration_loop(self):
        await self._remove_expired()

    @expiration_loop.before_loop
    async def before_expiration_loop(self):
        await self.bot.wait_until_ready()

    temp_group = app_commands.Group(
        name="temprole",
        description="Manage roles that automatically expire after a duration.",
    )

    @temp_group.command(name="add", description="Give a member a temporary role.")
    @app_commands.describe(
        member="The member to give the temporary role to",
        role="The role to give",
        duration="Duration, e.g. 30m, 2h, 7d, 1w, 1mo, 1y, or 1h30m",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def temprole_add(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
        duration: str,
    ):
        guild = interaction.guild

        if role.is_default():
            await interaction.response.send_message("I cannot temporarily assign the @everyone role.", ephemeral=True)
            return
        if role.managed:
            await interaction.response.send_message("I cannot manually assign a managed integration role.", ephemeral=True)
            return
        if role >= guild.me.top_role:
            await interaction.response.send_message(
                "I cannot assign a role higher than or equal to my own top role.", ephemeral=True
            )
            return
        if interaction.user.id != guild.owner_id and role >= interaction.user.top_role:
            await interaction.response.send_message(
                "You cannot assign a role higher than or equal to your own top role.", ephemeral=True
            )
            return

        try:
            seconds = parse_duration(duration)
        except ValueError as exc:
            await interaction.response.send_message(
                f"Invalid duration: {exc}\nExamples: `30m`, `2h`, `7d`, `1w`, `1mo`, `1h30m`.",
                ephemeral=True,
            )
            return

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)

        try:
            await member.add_roles(role, reason=f"Temporary role by {interaction.user} for {duration}")
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to assign that role.", ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.response.send_message("Discord rejected the role assignment. Please try again.", ephemeral=True)
            return

        storage.set_temp_role(
            guild.id,
            member.id,
            role.id,
            expires_at.isoformat(),
            interaction.user.id,
        )

        embed = make_embed(
            "Temporary Role Added",
            f"**Member:** {member.mention}\n"
            f"**Role:** {role.mention}\n"
            f"**Duration:** `{format_duration(seconds)}`\n"
            f"**Expires:** {discord.utils.format_dt(expires_at, 'R')}\n"
            f"**Moderator:** {interaction.user.mention}",
        )
        await interaction.response.send_message(embed=embed)
        await send_log(guild, embed, category="channels_roles")

    @temp_group.command(name="remove", description="Remove temporary roles from a member.")
    @app_commands.describe(member="The member whose temporary roles should be removed")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def temprole_remove(self, interaction: discord.Interaction, member: discord.Member):
        records = storage.get_temp_roles_for_member(interaction.guild.id, member.id)
        if not records:
            await interaction.response.send_message(
                f"{member.mention} has no active temporary roles.", ephemeral=True
            )
            return

        removed = []
        failed = []
        for item in records:
            role = interaction.guild.get_role(item["role_id"])
            if role is None:
                storage.delete_temp_role(interaction.guild.id, member.id, item["role_id"])
                continue

            try:
                if role in member.roles:
                    await member.remove_roles(role, reason=f"Temporary role removed by {interaction.user}")
                removed.append(role.mention)
                storage.delete_temp_role(interaction.guild.id, member.id, role.id)
            except (discord.Forbidden, discord.HTTPException):
                failed.append(role.mention)

        description = f"Removed: {', '.join(removed) if removed else 'None'}"
        if failed:
            description += f"\nFailed: {', '.join(failed)}"

        embed = make_embed("Temporary Roles Removed", f"**Member:** {member.mention}\n{description}")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed, category="channels_roles")


async def setup(bot: commands.Bot):
    await bot.add_cog(TempRole(bot))
