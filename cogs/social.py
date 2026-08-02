import discord
from discord import app_commands
from discord.ext import commands
import aiohttp

BLACK = discord.Color.from_str("#000000")
GIF_API = "https://api.otakugifs.xyz/gif"

# command name -> (API reaction key, verb used in the message)
# NOTE: "highfive" and "bonk" are not valid reaction keys on otakugifs.xyz.
# Mapped to the closest valid keys ("brofist" and "smack") so the command
# names/verbs stay the same but the API call actually succeeds.
REACTIONS = {
    "hug": ("hug", "hugs"),
    "kiss": ("kiss", "kisses"),
    "pat": ("pat", "pats"),
    "slap": ("slap", "slaps"),
    "poke": ("poke", "pokes"),
    "highfive": ("brofist", "high fives"),
    "bonk": ("smack", "bonks"),
    "wave": ("wave", "waves at"),
    "cuddle": ("cuddle", "cuddles"),
    "dance": ("dance", "dances with"),
    "punch": ("punch", "punches"),
}

SELF_MESSAGES = {
    "hug": "{author} hugs themselves.",
    "kiss": "{author} kisses their own reflection.",
    "pat": "{author} pats themselves on the head.",
    "slap": "{author} slaps themselves.",
    "poke": "{author} pokes themselves.",
    "highfive": "{author} tries to high five themselves.",
    "bonk": "{author} bonks themselves.",
    "wave": "{author} waves at themselves.",
    "cuddle": "{author} cuddles themselves.",
    "dance": "{author} dances alone.",
    "punch": "{author} punches themselves.",
}


class Social(commands.Cog):
    """Social interaction commands with reaction GIFs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Reuse a single session instead of opening a new one per request.
        self._session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        self._session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _fetch_gif(self, reaction: str) -> str | None:
        try:
            assert self._session is not None
            async with self._session.get(
                GIF_API,
                params={"reaction": reaction, "format": "gif"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("url")
        except (aiohttp.ClientError, discord.HTTPException, TimeoutError):
            return None

    async def _send_action(self, interaction: discord.Interaction, member: discord.Member, action: str):
        # Defer immediately so the network round trip can't blow past
        # Discord's 3-second initial-response window.
        await interaction.response.defer()

        reaction_key, verb = REACTIONS[action]

        if member.id == interaction.user.id:
            description = SELF_MESSAGES[action].format(author=interaction.user.mention)
        else:
            description = f"{interaction.user.mention} {verb} {member.mention}!"

        gif_url = await self._fetch_gif(reaction_key)

        embed = discord.Embed(description=description, color=BLACK)
        if gif_url:
            embed.set_image(url=gif_url)
        else:
            embed.set_footer(text="Couldn't fetch a gif right now, sorry!")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="hug", description="Hug another user.")
    @app_commands.describe(member="The user to hug")
    async def hug(self, interaction: discord.Interaction, member: discord.Member):
        await self._send_action(interaction, member, "hug")

    @app_commands.command(name="kiss", description="Kiss another user.")
    @app_commands.describe(member="The user to kiss")
    async def kiss(self, interaction: discord.Interaction, member: discord.Member):
        await self._send_action(interaction, member, "kiss")

    @app_commands.command(name="pat", description="Pat another user.")
    @app_commands.describe(member="The user to pat")
    async def pat(self, interaction: discord.Interaction, member: discord.Member):
        await self._send_action(interaction, member, "pat")

    @app_commands.command(name="slap", description="Slap another user.")
    @app_commands.describe(member="The user to slap")
    async def slap(self, interaction: discord.Interaction, member: discord.Member):
        await self._send_action(interaction, member, "slap")

    @app_commands.command(name="poke", description="Poke another user.")
    @app_commands.describe(member="The user to poke")
    async def poke(self, interaction: discord.Interaction, member: discord.Member):
        await self._send_action(interaction, member, "poke")

    @app_commands.command(name="highfive", description="High five another user.")
    @app_commands.describe(member="The user to high five")
    async def highfive(self, interaction: discord.Interaction, member: discord.Member):
        await self._send_action(interaction, member, "highfive")

    @app_commands.command(name="bonk", description="Bonk another user.")
    @app_commands.describe(member="The user to bonk")
    async def bonk(self, interaction: discord.Interaction, member: discord.Member):
        await self._send_action(interaction, member, "bonk")

    @app_commands.command(name="wave", description="Wave at another user.")
    @app_commands.describe(member="The user to wave at")
    async def wave(self, interaction: discord.Interaction, member: discord.Member):
        await self._send_action(interaction, member, "wave")

    @app_commands.command(name="cuddle", description="Cuddle another user.")
    @app_commands.describe(member="The user to cuddle")
    async def cuddle(self, interaction: discord.Interaction, member: discord.Member):
        await self._send_action(interaction, member, "cuddle")

    @app_commands.command(name="dance", description="Dance with another user.")
    @app_commands.describe(member="The user to dance with")
    async def dance(self, interaction: discord.Interaction, member: discord.Member):
        await self._send_action(interaction, member, "dance")

    @app_commands.command(name="punch", description="Punch another user.")
    @app_commands.describe(member="The user to punch")
    async def punch(self, interaction: discord.Interaction, member: discord.Member):
        await self._send_action(interaction, member, "punch")


async def setup(bot: commands.Bot):
    await bot.add_cog(Social(bot))
