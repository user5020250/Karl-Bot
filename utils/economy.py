import random
import config


def apply_prestige_bonus(user, amount: int) -> int:
    """Applies the permanent +5%-per-prestige-level income bonus."""
    prestige = user["prestige"] if user else 0
    bonus = 1 + (prestige * config.PRESTIGE_INCOME_BONUS_PER_LEVEL)
    return round(amount * bonus)


def roll(range_tuple) -> int:
    lo, hi = range_tuple
    return random.randint(lo, hi)


def tier_cost(tier: int) -> int:
    """Shared price ladder used by both /prestige and /bank upg.

    Tier 0 -> 1 costs 1,000,000. Every tier after that costs
    5,000,000 * tier (1m, 5m, 10m, 15m, 20m, ...).
    """
    if tier <= 0:
        return config.TIER_COST_FIRST
    return config.TIER_COST_STEP * tier


def bank_capacity_for(user) -> int:
    """Reads the user's current bank capacity (persists across prestige,
    grows via /bank upg and automatically on prestige)."""
    if user is None:
        return config.BANK_STARTING_CAPACITY
    try:
        return user["bank_capacity"]
    except (IndexError, KeyError):
        return config.BANK_STARTING_CAPACITY


# -- Leveling / EXP --------------------------------------------------------

def level_for_exp(exp: int) -> int:
    return exp // config.EXP_PER_LEVEL + 1


def exp_progress(exp: int):
    """Returns (level, exp_into_level, exp_needed_for_level, fraction 0-1)."""
    level = level_for_exp(exp)
    into_level = exp % config.EXP_PER_LEVEL
    needed = config.EXP_PER_LEVEL
    fraction = into_level / needed if needed else 0.0
    return level, into_level, needed, fraction


async def add_exp_and_level(db, user_id: int, exp_gain: int = 10) -> bool:
    user = await db.get_user(user_id)
    new_exp = user["exp"] + exp_gain
    new_level = level_for_exp(new_exp)
    await db.execute(
        "UPDATE users SET exp = ?, level = ? WHERE user_id = ?",
        (new_exp, new_level, user_id),
    )
    return new_level > user["level"]


def pet_exp_multiplier(pet_count: int) -> float:
    """Owning pets increases exp gain (+EXP_PET_BONUS_PER_PET per pet owned)."""
    return 1 + pet_count * config.EXP_PET_BONUS_PER_PET


async def track_activity(db, user_id: int, base_exp: int = None) -> bool:
    """Central helper called by (almost) every command: bumps the total
    commands-used counter and grants exp (boosted by owned pets).
    Returns True if the user leveled up from this gain.
    """
    base_exp = config.EXP_PER_COMMAND if base_exp is None else base_exp
    await db.increment_field(user_id, "total_commands", 1)
    pets = await db.get_pets(user_id)
    gain = round(base_exp * pet_exp_multiplier(len(pets)))
    return await add_exp_and_level(db, user_id, gain)
