"""Shared helper functions used across cogs."""
import discord

from storage import storage

BLACK = discord.Color.from_str("#000000")

# ============================================================
# LOG CATEGORIES
# Each maps to its own configurable channel via the /logs panel
# (cogs/logs.py). Anything that calls send_log() without a
# category falls back to "moderation" for backward compatibility
# with cogs that predate this system.
# ============================================================

LOG_CATEGORIES = {
    "messages": "Messages",
    "members": "Members",
    "moderation": "Moderation",
    "voice": "Voice",
    "channels_roles": "Channels & Roles",
    "server": "Server",
}

LOG_SETTINGS_KEY = "logchannels"


def make_embed(title: str, description: str = None, color: discord.Color = None):
    embed = discord.Embed(title=title, description=description, color=color or BLACK)
    return embed



def _parse_embed_fields(raw: str, inline: bool = False):
    """Parse fields from `name | value; name | value` syntax."""
    if not raw:
        return []
    fields = []
    for item in raw.split(";"):
        item = item.strip()
        if not item or "|" not in item:
            continue
        name, value = item.split("|", 1)
        name, value = name.strip(), value.strip()
        if name and value:
            fields.append((name[:256], value[:1024], inline))
    return fields[:25]


def build_custom_embed(*, author=None, author_icon=None, title=None, title_url=None, description=None,
                       fields=None, inline_fields=None, thumbnail=None, image=None, footer=None,
                       footer_icon=None, timestamp=False, color=None):
    """Build a Discord embed from the bot's standard embed creator options."""
    embed = discord.Embed(color=color or BLACK)
    if author:
        kwargs = {"name": author}
        if author_icon:
            kwargs["icon_url"] = author_icon
        embed.set_author(**kwargs)
    if title:
        embed.title = title
        if title_url:
            embed.url = title_url
    if description:
        embed.description = description
    parsed_fields = _parse_embed_fields(fields, False) + _parse_embed_fields(inline_fields, True)
    for name, value, inline in parsed_fields[:25]:
        embed.add_field(name=name, value=value, inline=inline)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    if footer:
        kwargs = {"text": footer}
        if footer_icon:
            kwargs["icon_url"] = footer_icon
        embed.set_footer(**kwargs)
    if timestamp:
        embed.timestamp = discord.utils.utcnow()
    return embed


def parse_embed_color(value: str = None):
    """Parse a hex embed color, defaulting to black."""
    if not value:
        return BLACK
    value = value.strip().lstrip("#")
    try:
        return discord.Color(int(value, 16))
    except ValueError:
        raise ValueError("Color must be a valid hex value such as #000000 or FFFFFF.")

def get_log_channels(guild_id: int) -> dict:
    """Returns the full {category: channel_id} mapping for a guild."""
    return storage.get_guild_setting(LOG_SETTINGS_KEY, guild_id, {}) or {}


def set_log_channel(guild_id: int, category: str, channel_id: int):
    settings = get_log_channels(guild_id)
    settings[category] = channel_id
    storage.set_guild_setting(LOG_SETTINGS_KEY, guild_id, settings)


def clear_log_channel(guild_id: int, category: str):
    settings = get_log_channels(guild_id)
    settings.pop(category, None)
    storage.set_guild_setting(LOG_SETTINGS_KEY, guild_id, settings)


async def get_log_channel(guild: discord.Guild, category: str = "moderation"):
    """Return the configured log channel for a guild/category, if any."""
    channel_id = get_log_channels(guild.id).get(category)
    if not channel_id:
        return None
    return guild.get_channel(int(channel_id))


async def send_log(guild: discord.Guild, embed: discord.Embed, category: str = "moderation"):
    channel = await get_log_channel(guild, category)
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
