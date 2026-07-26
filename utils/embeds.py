import discord
import config


def make_embed(title: str, description: str = None, footer: str = None) -> discord.Embed:
    """Standard embed: black color, bold title, no emojis."""
    embed = discord.Embed(
        title=f"**{title}**",
        description=description,
        color=config.EMBED_COLOR,
    )
    if footer:
        embed.set_footer(text=footer)
    return embed


def error_embed(message: str) -> discord.Embed:
    return make_embed("Error", message)


def money(amount: int) -> str:
    return f"`{config.CURRENCY}{amount:,}`"


def raw(value) -> str:
    return f"`{value}`"


def progress_bar(fraction: float, length: int = 10) -> str:
    """Renders a text progress bar, e.g. '▓▓▓▓░░░░░░ 40%'."""
    fraction = max(0.0, min(1.0, fraction))
    filled = round(length * fraction)
    bar = "▓" * filled + "░" * (length - filled)
    return f"`{bar}` {fraction * 100:.0f}%"


def format_seconds(seconds: float) -> str:
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)
