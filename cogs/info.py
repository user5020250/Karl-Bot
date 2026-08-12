import discord
from discord import app_commands
from discord.ext import commands

from helpers import make_embed


class Info(commands.Cog):
    """Read-only information commands. No special permissions required."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="userinfo", description="View member information.")
    @app_commands.describe(member="The member to look up (defaults to you)")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        embed = make_embed(f"User Info — {member}")
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
        embed.add_field(name="Bot", value="Yes" if member.bot else "No", inline=True)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, style="F"), inline=False)
        if member.joined_at:
            embed.add_field(name="Joined Server", value=discord.utils.format_dt(member.joined_at, style="F"), inline=False)
        role_list = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
        embed.add_field(name=f"Roles ({len(role_list)})", value=", ".join(role_list) if role_list else "None", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Display a user's avatar.")
    @app_commands.describe(member="The member to look up (defaults to you)")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        embed = make_embed(f"{member}'s Avatar")
        embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="banner", description="Display a user's banner.")
    @app_commands.describe(member="The member to look up (defaults to you)")
    async def banner(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        user = await self.bot.fetch_user(member.id)
        embed = make_embed(f"{member}'s Banner")
        if user.banner:
            embed.set_image(url=user.banner.url)
        else:
            embed.description = "This user doesn't have a banner set."
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roles", description="View a member's roles.")
    @app_commands.describe(member="The member to look up (defaults to you)")
    async def roles(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        role_list = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
        embed = make_embed(f"Roles — {member}", ", ".join(role_list) if role_list else "This member has no roles.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="permissions", description="View a member's permissions.")
    @app_commands.describe(member="The member to look up (defaults to you)")
    async def permissions(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        perms = [name.replace("_", " ").title() for name, value in member.guild_permissions if value]
        embed = make_embed(f"Permissions — {member}", ", ".join(perms) if perms else "This member has no notable permissions.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="joined", description="See when a member joined.")
    @app_commands.describe(member="The member to look up (defaults to you)")
    async def joined(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        if member.joined_at:
            value = discord.utils.format_dt(member.joined_at, style="F") + " (" + discord.utils.format_dt(member.joined_at, style="R") + ")"
        else:
            value = "Unknown"
        embed = make_embed(f"{member} Joined", value)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="created", description="See when a Discord account was created.")
    @app_commands.describe(member="The member to look up (defaults to you)")
    async def created(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        value = discord.utils.format_dt(member.created_at, style="F") + " (" + discord.utils.format_dt(member.created_at, style="R") + ")"
        embed = make_embed(f"{member}'s Account Created", value)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="View server information.")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = make_embed(f"Server Info — {guild.name}")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="ID", value=str(guild.id), inline=True)
        embed.add_field(name="Owner", value=str(guild.owner), inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Text Channels", value=str(len(guild.text_channels)), inline=True)
        embed.add_field(name="Voice Channels", value=str(len(guild.voice_channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, style="F"), inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="channelinfo", description="View channel information.")
    @app_commands.describe(channel="The channel to look up (defaults to this channel)")
    async def channelinfo(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel = None):
        channel = channel or interaction.channel
        embed = make_embed(f"Channel Info — #{channel.name}")
        embed.add_field(name="ID", value=str(channel.id), inline=True)
        embed.add_field(name="Type", value=str(channel.type).title(), inline=True)
        embed.add_field(name="Category", value=channel.category.name if channel.category else "None", inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(channel.created_at, style="F"), inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roleinfo", description="View role information.")
    @app_commands.describe(role="The role to look up")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        embed = make_embed(f"Role Info — {role.name}")
        embed.add_field(name="ID", value=str(role.id), inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Members", value=str(len(role.members)), inline=True)
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        embed.add_field(name="Hoisted", value="Yes" if role.hoist else "No", inline=True)
        embed.add_field(name="Position", value=str(role.position), inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(role.created_at, style="F"), inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
