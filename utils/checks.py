import discord
from utils.embeds import make_embed, format_seconds


async def check_cooldown(interaction: discord.Interaction, db, command: str, seconds: int) -> bool:
    """Returns True if the command may proceed. Sends a reply and returns False if on cooldown."""
    remaining = await db.get_cooldown_remaining(interaction.user.id, command)
    if remaining > 0:
        embed = make_embed(
            "Cooldown Active",
            f"You must wait `{format_seconds(remaining)}` before using this command again.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    await db.set_cooldown(interaction.user.id, command, seconds)
    return True
