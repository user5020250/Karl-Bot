import io
import json

import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed
from storage import storage


class ModLogs(commands.Cog):
    """Viewing and exporting moderation logs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="modlogs", description="View moderation logs.")
    @app_commands.describe(member="Only show entries for this member (optional)")
    @app_commands.checks.has_permissions(view_audit_log=True)
    async def modlogs(self, interaction: discord.Interaction, member: discord.Member = None):
        guild_history = storage.section("history").get(str(interaction.guild.id), {})

        entries = []
        if member is not None:
            for entry in guild_history.get(str(member.id), []):
                entries.append((member.id, entry))
        else:
            for user_id, user_entries in guild_history.items():
                for entry in user_entries:
                    entries.append((int(user_id), entry))

        entries.sort(key=lambda e: e[1]["timestamp"], reverse=True)
        entries = entries[:10]

        embed = make_embed("Moderation Logs" if member is None else f"Moderation Logs for {member}")
        if not entries:
            embed.description = "No moderation log entries found."
        else:
            for user_id, entry in entries:
                target = interaction.guild.get_member(user_id)
                target_display = target.mention if target else f"ID {user_id}"
                embed.add_field(
                    name=f"{entry['type']} — {entry['timestamp'][:19].replace('T', ' ')} UTC",
                    value=f"Target: {target_display}\nReason: {entry['reason']}",
                    inline=False,
                )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="exportlogs", description="Export moderation logs.")
    @app_commands.checks.has_permissions(administrator=True)
    async def exportlogs(self, interaction: discord.Interaction):
        guild_history = storage.section("history").get(str(interaction.guild.id), {})
        payload = json.dumps(guild_history, indent=2)
        buffer = io.BytesIO(payload.encode("utf-8"))
        file = discord.File(buffer, filename=f"modlogs_{interaction.guild.id}.json")
        embed = make_embed("Moderation Logs Export", "Attached is the full moderation log export for this server.")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModLogs(bot))
