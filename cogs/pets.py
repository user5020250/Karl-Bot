import time
import json
import os
import random
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from utils.embeds import make_embed, money, format_seconds
from utils.checks import check_cooldown
from utils.economy import track_activity

_PETS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "pets.json")
with open(_PETS_PATH, "r", encoding="utf-8") as f:
    PET_SHOP = json.load(f)
PET_SHOP_BY_SPECIES = {p["species"].lower(): p for p in PET_SHOP}

DEATH_DAYS = 7  # fully unfed for this many days -> pet dies


def compute_hunger(last_fed: float) -> int:
    days_unfed = (time.time() - last_fed) / 86400
    return max(0, round(100 - days_unfed * 20))


def hunger_status(hunger: int) -> str:
    if hunger >= 70:
        return "Well Fed"
    if hunger >= 40:
        return "Hungry"
    if hunger > 0:
        return "Weak"
    return "Starving"


class PetGroup(app_commands.Group):
    def __init__(self, cog: "PetsCog"):
        super().__init__(name="pet", description="Manage your pets")
        self.cog = cog

    @app_commands.command(name="rename", description="Rename a pet")
    @app_commands.describe(pet_id="The ID of the pet to rename (see /profile Pets)", new_name="The new name")
    async def rename_cmd(self, interaction: discord.Interaction, pet_id: int, new_name: str):
        pet = await self.cog.db.get_pet(pet_id)
        if not pet or pet["owner_id"] != interaction.user.id or not pet["alive"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not own that pet."), ephemeral=True)
            return
        await self.cog.db.update_pet(pet_id, name=new_name)
        leveled_up = await track_activity(self.cog.db, interaction.user.id)
        desc = f"Renamed to **{new_name}**."
        if leveled_up:
            desc += "\nYou leveled up!"
        await interaction.response.send_message(embed=make_embed("Pet Renamed", desc))

    @app_commands.command(name="disowned", description="Abandon a pet")
    @app_commands.describe(pet_id="The ID of the pet to abandon (see /profile Pets)")
    async def disowned_cmd(self, interaction: discord.Interaction, pet_id: int):
        pet = await self.cog.db.get_pet(pet_id)
        if not pet or pet["owner_id"] != interaction.user.id:
            await interaction.response.send_message(embed=make_embed("Error", "You do not own that pet."), ephemeral=True)
            return
        await self.cog.db.remove_pet(pet_id)
        leveled_up = await track_activity(self.cog.db, interaction.user.id)
        desc = f"You abandoned **{pet['name'] or pet['species']}**."
        if leveled_up:
            desc += "\nYou leveled up!"
        await interaction.response.send_message(embed=make_embed("Pet Abandoned", desc))


class PetsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.pet_group = PetGroup(self)
        bot.tree.add_command(self.pet_group)
        self.pet_decay_loop.start()

    def cog_unload(self):
        self.pet_decay_loop.cancel()

    @tasks.loop(hours=1)
    async def pet_decay_loop(self):
        await self.bot.wait_until_ready()
        rows = await self.db.fetchall("SELECT * FROM pets WHERE alive = 1")
        for pet in rows:
            hunger = compute_hunger(pet["last_fed"])
            days_unfed = (time.time() - pet["last_fed"]) / 86400
            if days_unfed >= DEATH_DAYS:
                await self.db.update_pet(pet["pet_id"], alive=0, hunger=0)
            else:
                await self.db.update_pet(pet["pet_id"], hunger=hunger)

    @app_commands.command(name="petshop", description="Show the pet shop")
    async def petshop_cmd(self, interaction: discord.Interaction):
        await track_activity(self.db, interaction.user.id)
        lines = [f"**{p['species']}** - {money(p['cost'])} - {p['description']}" for p in PET_SHOP]
        embed = make_embed("Pet Shop", "\n".join(lines))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="adopt", description="Adopt a pet")
    @app_commands.describe(species="The species to adopt", name="A name for your new pet")
    async def adopt_cmd(self, interaction: discord.Interaction, species: str, name: str):
        species_key = species.lower()
        if species_key not in PET_SHOP_BY_SPECIES:
            await interaction.response.send_message(embed=make_embed("Error", "That species is not available in the pet shop."), ephemeral=True)
            return

        owned = await self.db.get_pets(interaction.user.id)
        if len(owned) >= config.MAX_PETS_OWNED:
            await interaction.response.send_message(embed=make_embed("Error", f"You may only own up to `{config.MAX_PETS_OWNED}` pets."), ephemeral=True)
            return

        pet_def = PET_SHOP_BY_SPECIES[species_key]
        user = await self.db.get_user(interaction.user.id)
        if user["balance"] < pet_def["cost"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not have enough cash on hand."), ephemeral=True)
            return

        await self.db.add_balance(interaction.user.id, -pet_def["cost"])
        await self.db.add_pet(interaction.user.id, pet_def["species"], name)
        leveled_up = await track_activity(self.db, interaction.user.id)

        desc = f"You adopted a **{pet_def['species']}** named **{name}**."
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("Pet Adopted", desc)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="feed", description="Feed a pet")
    @app_commands.describe(pet_id="The ID of the pet to feed (see /profile Pets)")
    async def feed_cmd(self, interaction: discord.Interaction, pet_id: int):
        if not await check_cooldown(interaction, self.db, "feed", config.COOLDOWNS["feed"]):
            return

        pet = await self.db.get_pet(pet_id)
        if not pet or pet["owner_id"] != interaction.user.id or not pet["alive"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not own that pet."), ephemeral=True)
            return

        await self.db.update_pet(pet_id, last_fed=time.time(), hunger=100)
        leveled_up = await track_activity(self.db, interaction.user.id)
        desc = f"You fed **{pet['name'] or pet['species']}**. It is now full."
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("Pet Fed", desc)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="play", description="Play with a pet")
    @app_commands.describe(pet_id="The ID of the pet to play with (see /profile Pets)")
    async def play_cmd(self, interaction: discord.Interaction, pet_id: int):
        pet = await self.db.get_pet(pet_id)
        if not pet or pet["owner_id"] != interaction.user.id or not pet["alive"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not own that pet."), ephemeral=True)
            return

        new_happiness = min(100, pet["happiness"] + random.randint(5, 15))
        await self.db.update_pet(pet_id, happiness=new_happiness)
        leveled_up = await track_activity(self.db, interaction.user.id)
        desc = f"You played with **{pet['name'] or pet['species']}**. Happiness: `{new_happiness}/100`."
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("Playtime", desc)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(PetsCog(bot))
