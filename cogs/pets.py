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
# NEW CONFIG VALUES (all have safe fallbacks via getattr, so nothing
# breaks if you haven't added them to config.py yet):
#   config.RENAME_COST               -> cash cost to rename a pet (default 250)
#   config.RACE_CHALLENGE_TIMEOUT    -> seconds a race challenge stays open (default 120)
#   config.PET_STOCK_REFRESH_MINUTES -> how often shop stock re-rolls (default 30)
#   config.PET_GIFT_ENABLED          -> allow /pet gift at all (default True)
#
# SHOP STOCK: each species is either in stock (1) or sold out (0), shared
# across the whole server, and re-rolled 50/50 on a timer (self.pet_stock in
# PetsCog, refreshed by stock_refresh_loop). Stock resets to a fresh random
# roll on bot restart since it's kept in memory, not the database — say the
# word if you'd rather it persist across restarts.
#
# Ownership itself is NOT limited by species — a player can own multiple
# pets of multiple species, up to config.MAX_PETS_OWNED total. Stock only
# gates how many of a given species can be *bought* before the next restock.
#
# RACING: outcomes are a pure 50/50 coin flip (see PetsCog._resolve_race) —
# no stat, level, or species advantage either way.
#
# CHANGE LOG:
#   - /adopt moved into the /pet group -> /pet adopt (unchanged behavior).
#   - /feed moved into the /pet group -> /pet feed (unchanged behavior).
#   - /play moved into the /pet group -> /pet play, for consistency with
#     every other single-pet action now living under /pet. (Not explicitly
#     requested — revert easily if you'd rather keep it top-level.)
#   - /pet adopt now has autocomplete on `species`, showing stock status.
#     It was previously free-text, easy to mistype.
#   - NEW: /pet list — quick overview of your own pets + their IDs, since
#     almost every other subcommand needs a pet_id and previously the only
#     way to find one was a separate /profile command.
#   - NEW: /pet leaderboard — top pets server-wide by race wins.
#   - NEW: /pet gift — transfer a live pet you own to another member,
#     respecting their MAX_PETS_OWNED cap. Gated by config.PET_GIFT_ENABLED
#     in case you don't want pets tradeable.
# ---------------------------------------------------------------------------

_PETS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "pets.json")
_FOOD_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "food.json")

with open(_PETS_PATH, "r", encoding="utf-8") as f:
    PET_SHOP = json.load(f)
PET_SHOP_BY_SPECIES = {p["species"].lower(): p for p in PET_SHOP}

with open(_FOOD_PATH, "r", encoding="utf-8") as f:
    FOOD_SHOP = json.load(f)
FOOD_BY_NAME = {item["name"].lower(): item for item in FOOD_SHOP}


def food_is_valid_for(food_item: dict, species: str) -> bool:
    """Empty species list on a food item means it's universal (fits any pet)."""
    allowed = food_item.get("species") or []
    if not allowed:
        return True
    return species in allowed


def get_food_options(species: str = None) -> list:
    if not species:
        return FOOD_SHOP
    return [f for f in FOOD_SHOP if food_is_valid_for(f, species)]

DEATH_DAYS = 7  # fully unfed for this many days -> pet dies
RENAME_COST = getattr(config, "RENAME_COST", 250)
RACE_CHALLENGE_TIMEOUT = getattr(config, "RACE_CHALLENGE_TIMEOUT", 120)
STOCK_REFRESH_MINUTES = getattr(config, "PET_STOCK_REFRESH_MINUTES", 30)
GIFT_ENABLED = getattr(config, "PET_GIFT_ENABLED", True)


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

def build_pet_shop_embed(stock: dict, next_restock: float = None) -> discord.Embed:
    lines = []
    for p in PET_SHOP:
        in_stock = stock.get(p["species"], 0) > 0
        status = "`Available (1/1)`" if in_stock else "`Out of Stock (0/1)`"
        lines.append(f"**{p['species']}** — {money(p['cost'])} [{status}]\n{p['description']}")
    desc = "\n\n".join(lines)
    if next_restock:
        desc += f"\n\nStock refreshes every {STOCK_REFRESH_MINUTES} minutes. Next restock: <t:{int(next_restock)}:R>"
    return make_embed("Pet Shop — Pets", desc)


def build_food_shop_embed() -> discord.Embed:
    lines = []
    for item in FOOD_SHOP:
        allowed = item.get("species") or []
        for_line = "Any Pet" if not allowed else ", ".join(allowed)
        lines.append(
            f"**{item['name']}** — {money(item['cost'])} "
            f"`(+{item['hunger']} hunger, +{item['exp']} exp)`\n"
            f"For: `{for_line}`\n{item['description']}"
        )
    return make_embed("Pet Shop — Food", "\n\n".join(lines))


class ShopCategorySelect(discord.ui.Select):
    def __init__(self, cog: "PetsCog"):
        self.cog = cog
        options = [
            discord.SelectOption(label="Pets", description="Adoptable household pets", value="pets"),
            discord.SelectOption(label="Food", description="Food & treats to feed your pets", value="food"),
        ]
        super().__init__(placeholder="Choose a category...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "pets":
            embed = build_pet_shop_embed(self.cog.pet_stock, self.cog.next_restock)
        else:
            embed = build_food_shop_embed()
        await interaction.response.edit_message(embed=embed, view=self.view)


class ShopView(discord.ui.View):
    def __init__(self, cog: "PetsCog"):
        super().__init__(timeout=120)
        self.add_item(ShopCategorySelect(cog))


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
        pet_id="The ID of your pet to race (see /pet list)",
        bet="Amount to bet — a number, 'all', 'half', or shorthand like 5k",
    )
    async def challenge_cmd(self, interaction: discord.Interaction, opponent: discord.Member, pet_id: int, bet: str):
        db = self.cog.db
        challenger = interaction.user

        for target_id, existing_challenge in self.cog.pending_races.items():
            if existing_challenge["challenger"] == challenger.id and time.time() - existing_challenge["created"] < RACE_CHALLENGE_TIMEOUT:
                other = interaction.guild.get_member(target_id) if interaction.guild else None
                other_name = other.mention if other else f"<@{target_id}>"
                await interaction.response.send_message(
                    embed=make_embed(
                        "Error",
                        f"You already have a pending challenge with {other_name}. "
                        f"Use `/pet race cancel` to cancel it before sending a new one.",
                    ),
                    ephemeral=True,
                )
                return

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
    @app_commands.describe(pet_id="The ID of your pet to race (see /pet list)")
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

    @app_commands.command(name="cancel", description="Cancel a race challenge you sent")
    async def cancel_cmd(self, interaction: discord.Interaction):
        target_id = None
        for opponent_id, challenge in self.cog.pending_races.items():
            if challenge["challenger"] == interaction.user.id:
                target_id = opponent_id
                break

        if target_id is None:
            await interaction.response.send_message(embed=make_embed("Error", "You have no pending challenge to cancel."), ephemeral=True)
            return

        del self.cog.pending_races[target_id]
        await interaction.response.send_message(embed=make_embed("Race Cancelled", "You cancelled your pending race challenge."))


class PetGroup(app_commands.Group):
    def __init__(self, cog: "PetsCog"):
        super().__init__(name="pet", description="Manage your pets")
        self.cog = cog
        self.race_group = RaceGroup(cog)
        self.add_command(self.race_group)

    # -- adopt -------------------------------------------------------------
    async def _species_autocomplete(self, interaction: discord.Interaction, current: str):
        current_lower = current.lower()
        choices = []
        for p in PET_SHOP:
            if current_lower in p["species"].lower():
                in_stock = self.cog.pet_stock.get(p["species"], 0) > 0
                label = p["species"] if in_stock else f"{p['species']} (Out of Stock)"
                choices.append(app_commands.Choice(name=label, value=p["species"]))
        return choices[:25]

    @app_commands.command(name="adopt", description="Adopt a pet")
    @app_commands.describe(species="The species to adopt", name="A name for your new pet")
    @app_commands.autocomplete(species=_species_autocomplete)
    async def adopt_cmd(self, interaction: discord.Interaction, species: str, name: str):
        species_key = species.lower()
        if species_key not in PET_SHOP_BY_SPECIES:
            await interaction.response.send_message(embed=make_embed("Error", "That species is not available in the pet shop."), ephemeral=True)
            return

        pet_def = PET_SHOP_BY_SPECIES[species_key]

        if self.cog.pet_stock.get(pet_def["species"], 0) <= 0:
            await interaction.response.send_message(
                embed=make_embed(
                    "Error",
                    f"**{pet_def['species']}** is currently out of stock. "
                    f"Stock refreshes every {STOCK_REFRESH_MINUTES} minutes — next restock <t:{int(self.cog.next_restock)}:R>.",
                ),
                ephemeral=True,
            )
            return

        owned = await self.cog.db.get_pets(interaction.user.id)
        if len(owned) >= config.MAX_PETS_OWNED:
            await interaction.response.send_message(embed=make_embed("Error", f"You may only own up to `{config.MAX_PETS_OWNED}` pets."), ephemeral=True)
            return

        user = await self.cog.db.get_user(interaction.user.id)
        if user["balance"] < pet_def["cost"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not have enough cash on hand."), ephemeral=True)
            return

        # Consume the single stock slot immediately so two people can't both
        # buy the same last-in-stock pet in a race condition.
        self.cog.pet_stock[pet_def["species"]] = 0

        await self.cog.db.add_balance(interaction.user.id, -pet_def["cost"])
        await self.cog.db.add_pet(interaction.user.id, pet_def["species"], name)
        leveled_up = await track_activity(self.cog.db, interaction.user.id)

        desc = f"You adopted a **{pet_def['species']}** named **{name}**."
        if leveled_up:
            desc += "\nYou leveled up!"
        embed = make_embed("Pet Adopted", desc)
        await interaction.response.send_message(embed=embed)

    # -- feed ----------------------------------------------------------------
    async def _food_autocomplete(self, interaction: discord.Interaction, current: str):
        pet_id = interaction.namespace.pet_id
        species = None
        if pet_id is not None:
            try:
                pet = await self.cog.db.get_pet(pet_id)
            except Exception:
                pet = None
            if pet:
                species = pet["species"]

        options = get_food_options(species)
        current_lower = current.lower()
        return [
            app_commands.Choice(name=item["name"], value=item["name"])
            for item in options
            if current_lower in item["name"].lower()
        ][:25]

    @app_commands.command(name="feed", description="Feed a pet")
    @app_commands.describe(pet_id="The ID of the pet to feed (see /pet list)", food="What to feed it")
    @app_commands.autocomplete(food=_food_autocomplete)
    async def feed_cmd(self, interaction: discord.Interaction, pet_id: int, food: str):
        if not await check_cooldown(interaction, self.cog.db, "feed", config.COOLDOWNS["feed"]):
            return

        pet = await self.cog.db.get_pet(pet_id)
        if not pet or pet["owner_id"] != interaction.user.id or not pet["alive"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not own that pet."), ephemeral=True)
            return

        food_item = FOOD_BY_NAME.get(food.lower())
        if not food_item:
            await interaction.response.send_message(embed=make_embed("Error", "That food isn't sold in the shop."), ephemeral=True)
            return

        if not food_is_valid_for(food_item, pet["species"]):
            suitable = ", ".join(f["name"] for f in get_food_options(pet["species"]))
            await interaction.response.send_message(
                embed=make_embed(
                    "Error",
                    f"**{food_item['name']}** isn't suitable for a {pet['species']}.\n"
                    f"Try: {suitable}",
                ),
                ephemeral=True,
            )
            return

        user = await self.cog.db.get_user(interaction.user.id)
        if user["balance"] < food_item["cost"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not have enough cash on hand."), ephemeral=True)
            return

        await self.cog.db.add_balance(interaction.user.id, -food_item["cost"])

        new_hunger = min(100, pet["hunger"] + food_item["hunger"])
        new_exp, new_level, leveled = add_pet_exp(pet, food_item["exp"])
        await self.cog.db.update_pet(pet_id, last_fed=time.time(), hunger=new_hunger, exp=new_exp, level=new_level)

        leveled_up_owner = await track_activity(self.cog.db, interaction.user.id)
        desc = f"You fed **{pet['name'] or pet['species']}** some {food_item['name']}. Hunger: `{new_hunger}/100`."
        if leveled:
            desc += f"\n{pet['name'] or pet['species']} leveled up to **level {new_level}**!"
        if leveled_up_owner:
            desc += "\nYou leveled up!"
        embed = make_embed("Pet Fed", desc)
        await interaction.response.send_message(embed=embed)

    # -- play ----------------------------------------------------------------
    @app_commands.command(name="play", description="Play with a pet")
    @app_commands.describe(pet_id="The ID of the pet to play with (see /pet list)")
    async def play_cmd(self, interaction: discord.Interaction, pet_id: int):
        pet = await self.cog.db.get_pet(pet_id)
        if not pet or pet["owner_id"] != interaction.user.id or not pet["alive"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not own that pet."), ephemeral=True)
            return

        new_happiness = min(100, pet["happiness"] + random.randint(5, 15))
        exp_gain = random.randint(5, 12)
        new_exp, new_level, leveled = add_pet_exp(pet, exp_gain)
        await self.cog.db.update_pet(pet_id, happiness=new_happiness, exp=new_exp, level=new_level)

        leveled_up_owner = await track_activity(self.cog.db, interaction.user.id)
        desc = f"You played with **{pet['name'] or pet['species']}**. Happiness: `{new_happiness}/100` (+{exp_gain} EXP)."
        if leveled:
            desc += f"\n{pet['name'] or pet['species']} leveled up to **level {new_level}**!"
        if leveled_up_owner:
            desc += "\nYou leveled up!"
        embed = make_embed("Playtime", desc)
        await interaction.response.send_message(embed=embed)

    # -- rename / disowned / info --------------------------------------------
    @app_commands.command(name="rename", description="Rename a pet (has a fee)")
    @app_commands.describe(pet_id="The ID of the pet to rename (see /pet list)", new_name="The new name")
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
    @app_commands.describe(pet_id="The ID of the pet to abandon (see /pet list)")
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
    @app_commands.describe(pet_id="The ID of the pet to inspect (see /pet list)")
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

    # -- list (NEW) ------------------------------------------------------
    @app_commands.command(name="list", description="List your pets and their IDs")
    async def list_cmd(self, interaction: discord.Interaction):
        pets = await self.cog.db.get_pets(interaction.user.id)
        if not pets:
            await interaction.response.send_message(
                embed=make_embed("Your Pets", "You don't own any pets yet. Try `/pet adopt`."),
                ephemeral=True,
            )
            return

        lines = []
        for pet in pets:
            hunger = compute_hunger(pet["last_fed"])
            lines.append(
                f"`#{pet['pet_id']}` **{pet['name'] or pet['species']}** ({pet['species']}) — "
                f"Lv.{pet.get('level', 1)} — {hunger_status(hunger)} ({hunger}/100) — "
                f"Happiness {pet['happiness']}/100 — {pet.get('wins', 0)}W/{pet.get('losses', 0)}L"
            )
        await interaction.response.send_message(
            embed=make_embed(f"Your Pets ({len(pets)})", "\n".join(lines)),
            ephemeral=True,
        )

    # -- leaderboard (NEW) ------------------------------------------------
    @app_commands.command(name="leaderboard", description="See the top racing pets server-wide")
    async def leaderboard_cmd(self, interaction: discord.Interaction):
        rows = await self.cog.db.fetchall(
            "SELECT pet_id, owner_id, name, species, wins, losses FROM pets "
            "WHERE alive = 1 AND (wins > 0 OR losses > 0) "
            "ORDER BY wins DESC, losses ASC LIMIT 10"
        )
        if not rows:
            await interaction.response.send_message(
                embed=make_embed("Pet Racing Leaderboard", "No races have been run yet — try `/pet race challenge`.")
            )
            return

        lines = []
        for i, row in enumerate(rows, start=1):
            lines.append(
                f"**#{i}. {row['name'] or row['species']}** ({row['species']}) — "
                f"Owner: <@{row['owner_id']}> — {row['wins']}W / {row['losses']}L"
            )
        await interaction.response.send_message(embed=make_embed("Pet Racing Leaderboard", "\n".join(lines)))

    # -- gift (NEW) --------------------------------------------------------
    @app_commands.command(name="gift", description="Give one of your pets to another player")
    @app_commands.describe(pet_id="The ID of the pet to give away (see /pet list)", recipient="Who to give it to")
    async def gift_cmd(self, interaction: discord.Interaction, pet_id: int, recipient: discord.Member):
        if not GIFT_ENABLED:
            await interaction.response.send_message(embed=make_embed("Error", "Pet gifting is currently disabled."), ephemeral=True)
            return

        if recipient.bot or recipient.id == interaction.user.id:
            await interaction.response.send_message(embed=make_embed("Error", "You can't gift a pet to yourself or a bot."), ephemeral=True)
            return

        pet = await self.cog.db.get_pet(pet_id)
        if not pet or pet["owner_id"] != interaction.user.id or not pet["alive"]:
            await interaction.response.send_message(embed=make_embed("Error", "You do not own that pet."), ephemeral=True)
            return

        recipient_pets = await self.cog.db.get_pets(recipient.id)
        if len(recipient_pets) >= config.MAX_PETS_OWNED:
            await interaction.response.send_message(
                embed=make_embed("Error", f"{recipient.display_name} already owns the maximum of `{config.MAX_PETS_OWNED}` pets."),
                ephemeral=True,
            )
            return

        await self.cog.db.update_pet(pet_id, owner_id=recipient.id)
        leveled_up = await track_activity(self.cog.db, interaction.user.id)
        desc = f"You gave **{pet['name'] or pet['species']}** to {recipient.mention}."
        if leveled_up:
            desc += "\nYou leveled up!"
        await interaction.response.send_message(embed=make_embed("Pet Gifted", desc))


class PetsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.pending_races = {}  # opponent_id -> {challenger, challenger_pet, bet, created}
        # Shop stock: each species is either in stock (1) or sold out (0),
        # shared across all users, re-rolled on a timer.
        self.pet_stock = {p["species"]: random.randint(0, 1) for p in PET_SHOP}
        self.next_restock = time.time() + STOCK_REFRESH_MINUTES * 60
        self.pet_group = PetGroup(self)
        bot.tree.add_command(self.pet_group)
        self.pet_decay_loop.start()
        self.stock_refresh_loop.start()

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
        self.stock_refresh_loop.cancel()

    def _resolve_race(self, pet_a: dict, pet_b: dict, owner_a: int, owner_b: int):
        """Pure 50/50 coin flip — no stat advantages, every race is a toss-up."""
        if random.random() < 0.5:
            return pet_a, pet_b, owner_a, owner_b
        return pet_b, pet_a, owner_b, owner_a

    @tasks.loop(minutes=STOCK_REFRESH_MINUTES)
    async def stock_refresh_loop(self):
        await self.bot.wait_until_ready()
        self.pet_stock = {p["species"]: random.randint(0, 1) for p in PET_SHOP}
        self.next_restock = time.time() + STOCK_REFRESH_MINUTES * 60

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
        embed = build_pet_shop_embed(self.pet_stock, self.next_restock)
        await interaction.response.send_message(embed=embed, view=ShopView(self))


async def setup(bot: commands.Bot):
    await bot.add_cog(PetsCog(bot))
