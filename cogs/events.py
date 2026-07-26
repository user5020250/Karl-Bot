import time
import random
import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.embeds import make_embed, money
from utils.achievements import check_and_award
from utils.economy import track_activity

# type_key: (display name, min amount, max amount, claim window seconds, weight)
EVENT_TYPES = {
    "lost_wallet": ("Lost Wallet", 10_000, 30_000, None, 40),
    "cash_rain": ("Cash Rain", 5_000, 10_000, None, 35),
    "treasure_chest": ("Treasure Chest", 10_000, 100_000, None, 18),
    "atm_glitch": ("ATM Glitch", 10_000, 10_000, 30, 5),
    "jackpot_event": ("Jackpot Event", 100_000, 2_000_000, None, 2),
}

EVENT_FLAVOR = {
    "lost_wallet": "Someone dropped a wallet in chat.",
    "cash_rain": "It's raining money!",
    "treasure_chest": "A treasure chest has appeared.",
    "atm_glitch": "An ATM is glitching out. You have 30 seconds to claim it.",
    "jackpot_event": "A jackpot event has appeared. This is extremely rare.",
}

SPAWN_CHECK_INTERVAL_MINUTES = 15
SPAWN_CHANCE_PER_CHECK = 0.35
DEFAULT_CLAIM_WINDOW = 300  # 5 minutes for events without a fixed window


class EventGroup(app_commands.Group):
    def __init__(self, cog: "EventsCog"):
        super().__init__(name="event", description="Configure random money-drop events")
        self.cog = cog

    @app_commands.command(name="setchannel", description="Set the channel for random events")
    @app_commands.describe(channel="The channel events will be posted in")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.cog.db.set_event_channel(interaction.guild.id, channel.id)
        await track_activity(self.cog.db, interaction.user.id)
        embed = make_embed("Event Channel Set", f"Random events will now be posted in {channel.mention}.")
        await interaction.response.send_message(embed=embed)


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.event_group = EventGroup(self)
        bot.tree.add_command(self.event_group)
        self.event_spawner_loop.start()

    def cog_unload(self):
        self.event_spawner_loop.cancel()

    @tasks.loop(minutes=SPAWN_CHECK_INTERVAL_MINUTES)
    async def event_spawner_loop(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            channel_id = await self.db.get_event_channel(guild.id)
            if not channel_id:
                continue
            if random.random() > SPAWN_CHANCE_PER_CHECK:
                continue

            channel = guild.get_channel(channel_id)
            if channel is None:
                continue

            await self._spawn_event(channel)

    async def _spawn_event(self, channel: discord.TextChannel):
        type_key = random.choices(
            list(EVENT_TYPES.keys()),
            weights=[v[4] for v in EVENT_TYPES.values()],
        )[0]
        name, lo, hi, window, _ = EVENT_TYPES[type_key]
        amount = random.randint(lo, hi)
        claim_window = window or DEFAULT_CLAIM_WINDOW
        expires_at = time.time() + claim_window

        event_id = await self.db.create_event(channel.guild.id, channel.id, type_key, amount, expires_at)

        embed = make_embed(
            name,
            f"{EVENT_FLAVOR[type_key]}\nPrize: {money(amount)}\n"
            f"Use `/claim` within `{claim_window}` seconds to win it.",
        )
        message = await channel.send(embed=embed)
        await self.db.set_event_message(event_id, message.id)

    @app_commands.command(name="claim", description="Claim an active event reward")
    async def claim_cmd(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(embed=make_embed("Error", "This command only works in a server."), ephemeral=True)
            return

        event = await self.db.get_active_event_in_channel(interaction.channel.id)
        if not event:
            await interaction.response.send_message(embed=make_embed("No Active Event", "There is no active event to claim right now."), ephemeral=True)
            return

        if event["expires_at"] and time.time() > event["expires_at"]:
            await self.db.expire_event(event["event_id"])
            await interaction.response.send_message(embed=make_embed("Too Late", "That event has already expired."), ephemeral=True)
            return

        won = await self.db.claim_event(event["event_id"], interaction.user.id)
        if not won:
            await interaction.response.send_message(embed=make_embed("Too Late", "Someone else already claimed this event."), ephemeral=True)
            return

        await self.db.earn(interaction.user.id, event["amount"])
        leveled_up = await track_activity(self.db, interaction.user.id)
        name = EVENT_TYPES[event["type"]][0]
        desc = f"You claimed the **{name}** event and won {money(event['amount'])}."
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("Event Claimed", desc)
        await interaction.response.send_message(embed=embed)

        newly = await check_and_award(self.db, interaction.user.id)
        for ach in newly:
            await interaction.followup.send(embed=make_embed("Achievement Unlocked", f"**{ach['name']}** - {ach['description']}"))


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))
