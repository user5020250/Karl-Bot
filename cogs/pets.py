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

# ---------------------------------------------------------------------------
# NOTE ON ASSUMPTIONS
# I only had this one file to work from, not your db.py/config.py/utils/*.
# Everything below matches patterns already used in the original file
# (db.fetchall(query), db.update_pet(pet_id, **kwargs), db.add_balance,
# db.get_user, db.get_pet(s), db.add_pet, db.remove_pet, track_activity,
# make_embed, money, check_cooldown).
#
# ONE NEW ASSUMPTION: `self.db.execute(sql)` exists as an async method that
# runs raw SQL (used once below, in ensure_schema, to add new pet columns).
# If your db wrapper names this differently, just rename that one call.
#
# NEW CONFIG VALUES (both have safe fallbacks via getattr, so nothing
# breaks if you haven't added them to config.py yet):
#   config.RENAME_COST          -> cash cost to rename a pet (default 250)
#   config.RACE_CHALLENGE_TIMEOUT -> seconds a race challenge stays open (default 120)
# ---------------------------------------------------------------------------

_PETS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "pets.json")
_FOOD_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "food.json")

with open(_PETS_PATH, "r", encoding="utf-8") as f:
    PET_SHOP = json.load(f)
PET_SHOP_BY_SPECIES = {p["species"].lower(): p for p in PET_SHOP}

with open(_FOOD_PATH, "r", encoding="utf-8") as f:
    FOOD_SHOP = json.load(f)
FOOD_BY_NAME = {item["name"].lower(): item for item in FOOD_SHOP}
FOOD_CHOICES = [app_commands.Choice(name=item["name"], value=item["name"]) for item in FOOD_SHOP][:25]

DEATH_DAYS = 7  # fully unfed for this many days -> pet dies
RENAME_COST = getattr(config, "RENAME_COST", 250)
RACE_CHALLENGE_TIMEOUT = getattr(config, "RACE_CHALLENGE_TIMEOUT", 120)


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


# ---------------------------------------------------------------------------
# EXP / Leveling
# ---------------------------------------------------------------------------

def exp_needed(level: int) -> int:
    """EXP required to go from `level` to `level + 1`."""
    return 100 + (level - 1) * 50


def add_pet_exp(pet: dict, amount: int):
    """Apply EXP gain to a pet dict, returns (new_exp, new_level, leveled_up)."""
    exp = pet.get("exp", 0) + amount
    level = pet.get("level", 1)
    leveled_up = False
    while exp >= exp_needed(level):
        exp -= exp_needed(level)
        level += 1
        leveled_up = True
    return exp, level, leveled_up


# ---------------------------------------------------------------------------
# Bet parsing (supports "all", "half", plain numbers, "5k"/"2m" shorthand)
# ---------------------------------------------------------------------------

def parse_bet(balance: int, raw: str) -> int:
    cleaned = raw.strip().lower().replace(",", "").replace("$", "")

    if cleaned in ("all", "max", "everything"):
        amount = balance
    elif cleaned == "half":
        amount = balance // 2
    else:
        multiplier = 1
        if cleaned.endswith("k"):
            multiplier = 1_000
            cleaned = cleaned[:-1]
        elif cleaned.endswith("m"):
            multiplier = 1_000_000
            cleaned = cleaned[:-1]
        try:
            amount = int(float(cleaned) * multiplier)
        except ValueError:
            raise ValueError("Enter a valid amount, `all`, or `half`.")

    if amount <= 0:
        raise ValueError("Bet must be greater than zero.")
    if amount > balance:
        raise ValueError("You don't have that much cash on hand.")
    return amount


# ---------------------------------------------------------------------------
# Shop embeds + category dropdown
# ---------------------------------------------------------------------------

def build_pet_shop_embed() -> discord.Embed:
    lines = [f"**{p['species']}** — {money(p['cost'])}\n{p['description']}" for p in PET_SHOP]
    return make_embed("Pet Shop — Pets", "\n\n".join(lines))


def build_food_shop_embed() -> discord.Embed:
    lines = [
        f"**{item['name']}** — {money(item['cost'])} "
        f"(+{item['hunger']} hunger, +{item['exp']} EXP)\n{item['description']}"
        for item in FOOD_SHOP
    ]
    return make_embed("Pet Shop — Food", "\n\n".join(lines))


class ShopCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Pets", description="Adoptable household pets", value="pets", emoji="🐾"),
            discord.SelectOption(label="Food", description="Food & treats to feed your pets", value="food", emoji="🍖"),
        ]
        super().__init__(placeholder="Choose a category...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        embed = build_pet_shop_embed() if self.values[0] == "pets" else build_food_shop_embed()
        await interaction.response.edit_message(embed=embed, view=self.view)


class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(ShopCategorySelect())


# ---------------------------------------------------------------------------
# /pet group
# ---------------------------------------------------------------------------

class RaceGroup(app_commands.Group):
    def __init__(self, cog: "PetsCog"):
        super().__init__(name="race", description="Challenge another player to a pet race")
        self.cog = cog

    @app_commands.command(name="challenge", description="Challenge another player to a pet race")
    @app_commands.describe(
        opponent="Who you want to race",
        pet_id="The ID of your pet to race (see /profile Pets)",
        bet="Amount to bet — a number, 'all', 'half', or shorthand like 5k",
    )
    async def challenge_cmd(self, interaction: discord.Interaction, opponent: discord.Member, pet_id: int, bet: str):
        db = self.cog.db
        challenger = interaction.user

        if opponent.bot or opponent.id == challenger.id:
            await interaction.response.send_message(embed=make_embed("Error", "You can't race yourself or a bot."), ephemeral=True)
            return

        pet = await db.get_pet(pet_id)
        if not pet or pet["owner_id"] != challenger.id or not pet["alive"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not own that pet."), ephemeral=True)
            return

        user = await db.get_user(challenger.id)
        try:
            amount = parse_bet(user["balance"], bet)
        except ValueError as e:
            await interaction.response.send_message(embed=make_embed("Error", str(e)), ephemeral=True)
            return

        existing = self.cog.pending_races.get(opponent.id)
        if existing and time.time() - existing["created"] < RACE_CHALLENGE_TIMEOUT:
            await interaction.response.send_message(embed=make_embed("Error", f"{opponent.display_name} already has a pending race challenge."), ephemeral=True)
            return

        self.cog.pending_races[opponent.id] = {
            "challenger": challenger.id,
            "challenger_pet": pet_id,
            "bet": amount,
            "created": time.time(),
        }

        embed = make_embed(
            "Race Challenge!",
            f"{challenger.mention} challenges {opponent.mention} to a pet race with "
            f"**{pet['name'] or pet['species']}** for {money(amount)}!\n\n"
            f"{opponent.mention}, use `/pet race accept pet_id:<id>` with a matching bet of {money(amount)} "
            f"on hand, or `/pet race decline` to turn it down. Expires in {format_seconds(RACE_CHALLENGE_TIMEOUT)}.",
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="accept", description="Accept a pending race challenge")
    @app_commands.describe(pet_id="The ID of your pet to race (see /profile Pets)")
    async def accept_cmd(self, interaction: discord.Interaction, pet_id: int):
        db = self.cog.db
        acceptor = interaction.user

        challenge = self.cog.pending_races.get(acceptor.id)
        if not challenge:
            await interaction.response.send_message(embed=make_embed("Error", "You have no pending race challenges."), ephemeral=True)
            return

        if time.time() - challenge["created"] > RACE_CHALLENGE_TIMEOUT:
            del self.cog.pending_races[acceptor.id]
            await interaction.response.send_message(embed=make_embed("Error", "That challenge has expired."), ephemeral=True)
            return

        acceptor_pet = await db.get_pet(pet_id)
        if not acceptor_pet or acceptor_pet["owner_id"] != acceptor.id or not acceptor_pet["alive"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not own that pet."), ephemeral=True)
            return

        challenger_id = challenge["challenger"]
        challenger_pet = await db.get_pet(challenge["challenger_pet"])
        if not challenger_pet or not challenger_pet["alive"] or challenger_pet["owner_id"] != challenger_id:
            del self.cog.pending_races[acceptor.id]
            await interaction.response.send_message(embed=make_embed("Error", "The challenger's pet is no longer available."), ephemeral=True)
            return

        bet = challenge["bet"]
        challenger_user = await db.get_user(challenger_id)
        acceptor_user = await db.get_user(acceptor.id)
        if challenger_user["balance"] < bet:
            del self.cog.pending_races[acceptor.id]
            await interaction.response.send_message(embed=make_embed("Error", "The challenger can no longer cover the bet. Challenge cancelled."), ephemeral=True)
            return
        if acceptor_user["balance"] < bet:
            await interaction.response.send_message(embed=make_embed("Error", f"You need {money(bet)} on hand to accept this race."), ephemeral=True)
            return

        del self.cog.pending_races[acceptor.id]

        # Escrow both bets
        await db.add_balance(challenger_id, -bet)
        await db.add_balance(acceptor.id, -bet)

        winner_pet, loser_pet, winner_id, loser_id = self.cog._resolve_race(
            challenger_pet, acceptor_pet, challenger_id, acceptor.id
        )

        pot = bet * 2
        await db.add_balance(winner_id, pot)

        # Winner: EXP, win, some exertion
        w_exp, w_level, w_leveled = add_pet_exp(winner_pet, 40)
        await db.update_pet(
            winner_pet["pet_id"],
            exp=w_exp, level=w_level,
            wins=winner_pet.get("wins", 0) + 1,
            hunger=max(0, winner_pet["hunger"] - 15),
            happiness=min(100, winner_pet["happiness"] + 5),
        )

        # Loser: participation EXP, loss, some exertion
        l_exp, l_level, l_leveled = add_pet_exp(loser_pet, 10)
        await db.update_pet(
            loser_pet["pet_id"],
            exp=l_exp, level=l_level,
            losses=loser_pet.get("losses", 0) + 1,
            hunger=max(0, loser_pet["hunger"] - 15),
            happiness=max(0, loser_pet["happiness"] - 5),
        )

        await track_activity(db, challenger_id)
        await track_activity(db, acceptor.id)

        winner_member = interaction.guild.get_member(winner_id) if interaction.guild else None
        winner_name = winner_member.mention if winner_member else f"<@{winner_id}>"

        desc = (
            f"🏁 **{winner_pet['name'] or winner_pet['species']}** wins the race and takes home {money(pot)}!\n"
            f"Winner: {winner_name}"
        )
        if w_leveled:
            desc += f"\n{winner_pet['name'] or winner_pet['species']} leveled up to **level {w_level}**!"
        if l_leveled:
            desc += f"\n{loser_pet['name'] or loser_pet['species']} leveled up to **level {l_level}**!"

        await interaction.response.send_message(embed=make_embed("Race Results", desc))

    @app_commands.command(name="decline", description="Decline a pending race challenge")
    async def decline_cmd(self, interaction: discord.Interaction):
        challenge = self.cog.pending_races.pop(interaction.user.id, None)
        if not challenge:
            await interaction.response.send_message(embed=make_embed("Error", "You have no pending race challenges."), ephemeral=True)
            return
        await interaction.response.send_message(embed=make_embed("Race Declined", "You declined the race challenge."))


class PetGroup(app_commands.Group):
    def __init__(self, cog: "PetsCog"):
        super().__init__(name="pet", description="Manage your pets")
        self.cog = cog
        self.race_group = RaceGroup(cog)
        self.add_command(self.race_group)

    @app_commands.command(name="rename", description="Rename a pet (has a fee)")
    @app_commands.describe(pet_id="The ID of the pet to rename (see /profile Pets)", new_name="The new name")
    async def rename_cmd(self, interaction: discord.Interaction, pet_id: int, new_name: str):
        pet = await self.cog.db.get_pet(pet_id)
        if not pet or pet["owner_id"] != interaction.user.id or not pet["alive"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not own that pet."), ephemeral=True)
            return

        user = await self.cog.db.get_user(interaction.user.id)
        if user["balance"] < RENAME_COST:
            await interaction.response.send_message(
                embed=make_embed("Error", f"Renaming costs {money(RENAME_COST)} and you don't have enough cash on hand."),
                ephemeral=True,
            )
            return

        await self.cog.db.add_balance(interaction.user.id, -RENAME_COST)
        await self.cog.db.update_pet(pet_id, name=new_name)
        leveled_up = await track_activity(self.cog.db, interaction.user.id)
        desc = f"Renamed to **{new_name}** for {money(RENAME_COST)}."
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

    @app_commands.command(name="info", description="View a pet's stats")
    @app_commands.describe(pet_id="The ID of the pet to inspect (see /profile Pets)")
    async def info_cmd(self, interaction: discord.Interaction, pet_id: int):
        pet = await self.cog.db.get_pet(pet_id)
        if not pet or pet["owner_id"] != interaction.user.id:
            await interaction.response.send_message(embed=make_embed("Error", "You do not own that pet."), ephemeral=True)
            return

        hunger = compute_hunger(pet["last_fed"])
        level = pet.get("level", 1)
        exp = pet.get("exp", 0)
        desc = (
            f"**Species:** {pet['species']}\n"
            f"**Status:** {'Alive' if pet['alive'] else 'Deceased'}\n"
            f"**Hunger:** {hunger}/100 ({hunger_status(hunger)})\n"
            f"**Happiness:** {pet['happiness']}/100\n"
            f"**Level:** {level} ({exp}/{exp_needed(level)} EXP)\n"
            f"**Race Record:** {pet.get('wins', 0)}W - {pet.get('losses', 0)}L"
        )
        await interaction.response.send_message(embed=make_embed(pet["name"] or pet["species"], desc))


class PetsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.pending_races = {}  # opponent_id -> {challenger, challenger_pet, bet, created}
        self.pet_group = PetGroup(self)
        bot.tree.add_command(self.pet_group)
        self.pet_decay_loop.start()

    async def cog_load(self):
        await self.ensure_schema()

    async def ensure_schema(self):
        # New columns for the EXP/leveling and racing systems. Wrapped in
        # try/except since ALTER TABLE ADD COLUMN fails if it already exists
        # (sqlite has no IF NOT EXISTS for columns).
        for col, decl in [
            ("exp", "INTEGER NOT NULL DEFAULT 0"),
            ("level", "INTEGER NOT NULL DEFAULT 1"),
            ("wins", "INTEGER NOT NULL DEFAULT 0"),
            ("losses", "INTEGER NOT NULL DEFAULT 0"),
        ]:
            try:
                await self.db.execute(f"ALTER TABLE pets ADD COLUMN {col} {decl}")
            except Exception:
                pass

    def cog_unload(self):
        self.pet_decay_loop.cancel()

    def _resolve_race(self, pet_a: dict, pet_b: dict, owner_a: int, owner_b: int):
        """Weighted race outcome based on species speed, level, happiness, hunger + randomness."""
        def score(pet):
            base_speed = PET_SHOP_BY_SPECIES.get(pet["species"].lower(), {}).get("speed", 5)
            return (
                base_speed * 10
                + pet.get("level", 1) * 5
                + pet["happiness"] / 2
                + pet["hunger"] / 5
                + random.randint(1, 30)
            )

        score_a = score(pet_a)
        score_b = score(pet_b)

        if score_a >= score_b:
            return pet_a, pet_b, owner_a, owner_b
        return pet_b, pet_a, owner_b, owner_a

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

    @app_commands.command(name="petshop", description="Browse the pet shop")
    async def petshop_cmd(self, interaction: discord.Interaction):
        await track_activity(self.db, interaction.user.id)
        embed = build_pet_shop_embed()
        await interaction.response.send_message(embed=embed, view=ShopView())

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
    @app_commands.describe(pet_id="The ID of the pet to feed (see /profile Pets)", food="What to feed it")
    @app_commands.choices(food=FOOD_CHOICES)
    async def feed_cmd(self, interaction: discord.Interaction, pet_id: int, food: str):
        if not await check_cooldown(interaction, self.db, "feed", config.COOLDOWNS["feed"]):
            return

        pet = await self.db.get_pet(pet_id)
        if not pet or pet["owner_id"] != interaction.user.id or not pet["alive"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not own that pet."), ephemeral=True)
            return

        food_item = FOOD_BY_NAME.get(food.lower())
        if not food_item:
            await interaction.response.send_message(embed=make_embed("Error", "That food isn't sold in the shop."), ephemeral=True)
            return

        user = await self.db.get_user(interaction.user.id)
        if user["balance"] < food_item["cost"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not have enough cash on hand."), ephemeral=True)
            return

        await self.db.add_balance(interaction.user.id, -food_item["cost"])

        new_hunger = min(100, pet["hunger"] + food_item["hunger"])
        new_exp, new_level, leveled = add_pet_exp(pet, food_item["exp"])
        await self.db.update_pet(pet_id, last_fed=time.time(), hunger=new_hunger, exp=new_exp, level=new_level)

        leveled_up_owner = await track_activity(self.db, interaction.user.id)
        desc = f"You fed **{pet['name'] or pet['species']}** some {food_item['name']}. Hunger: `{new_hunger}/100`."
        if leveled:
            desc += f"\n{pet['name'] or pet['species']} leveled up to **level {new_level}**!"
        if leveled_up_owner:
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
        exp_gain = random.randint(5, 12)
        new_exp, new_level, leveled = add_pet_exp(pet, exp_gain)
        await self.db.update_pet(pet_id, happiness=new_happiness, exp=new_exp, level=new_level)

        leveled_up_owner = await track_activity(self.db, interaction.user.id)
        desc = f"You played with **{pet['name'] or pet['species']}**. Happiness: `{new_happiness}/100` (+{exp_gain} EXP)."
        if leveled:
            desc += f"\n{pet['name'] or pet['species']} leveled up to **level {new_level}**!"
        if leveled_up_owner:
            desc += "\nYou leveled up!"
        embed = make_embed("Playtime", desc)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(PetsCog(bot))
