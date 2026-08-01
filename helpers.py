"""Shared helper functions used across cogs."""

import discord
from storage import storage


BLACK = discord.Color.from_str("#000000")


def make_embed(title: str, description: str = None, color: discord.Color = None):
    embed = discord.Embed(title=title, description=description, color=color or BLACK)
    return embed


async def get_log_channel(guild: discord.Guild):
    """Return the configured mod-log channel for a guild, if any."""
    channel_id = storage.get_guild_setting("logs", guild.id)
    if not channel_id:
        return None
    return guild.get_channel(int(channel_id))


async def send_log(guild: discord.Guild, embed: discord.Embed):
    channel = await get_log_channel(guild)
    if channel:
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass


def action_embed(action: str, target: discord.abc.User, moderator: discord.abc.User, reason: str = None, color=None):
    embed = discord.Embed(title=action, color=color or BLACK)
    embed.add_field(name="User", value=f"{target} ({target.id})", inline=False)
    embed.add_field(name="Moderator", value=f"{moderator} ({moderator.id})", inline=False)
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
    embed.timestamp = discord.utils.utcnow()
    return embed


def parse_duration(duration: str) -> int:
    """Parse strings like '10m', '2h', '1d' into a number of seconds.

    Raises ValueError if the string can't be parsed.
    """
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    duration = duration.strip().lower()
    if not duration:
        raise ValueError("Empty duration")
    unit = duration[-1]
    if unit not in units:
        raise ValueError(f"Unknown duration unit '{unit}'. Use s/m/h/d/w, e.g. 10m, 2h, 1d.")
    number = duration[:-1]
    if not number.isdigit():
        raise ValueError("Duration must be a number followed by s/m/h/d/w, e.g. 10m.")
    return int(number) * units[unit]
