import json
import os

_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "achievements.json")

with open(_DATA_PATH, "r", encoding="utf-8") as f:
    ACHIEVEMENTS = json.load(f)

ACHIEVEMENTS_BY_KEY = {a["key"]: a for a in ACHIEVEMENTS}


async def check_and_award(db, user_id: int, context: dict | None = None):
    """
    Checks all non-secret + secret achievements against the user's current state
    and unlocks any newly met ones, applying their reward.
    `context` can carry event-specific flags like {"gamble_won": True} or
    {"just_went_bankrupt": True}.
    Returns a list of achievement dicts that were newly unlocked.
    """
    context = context or {}
    user = await db.get_user(user_id)
    net_worth = user["balance"] + user["bank"]
    unlocked_keys = set(await db.get_unlocked_achievements(user_id))
    newly_unlocked = []

    for ach in ACHIEVEMENTS:
        key = ach["key"]
        if key in unlocked_keys:
            continue

        met = False
        cond = ach["condition"]

        if cond == "work_count" and user["work_count"] >= ach["value"]:
            met = True
        elif cond == "lifetime_earned" and user["lifetime_earned"] >= ach["value"]:
            met = True
        elif cond == "net_worth" and net_worth >= ach["value"]:
            met = True
        elif cond == "first_gamble_win" and context.get("gamble_won") and user["gambling_won"] > 0:
            met = True
        elif cond == "comeback" and user["has_gone_bankrupt"] and net_worth >= ach["value"]:
            met = True
        elif cond == "exact_balance" and user["balance"] == ach["value"] and context.get("balance_checked"):
            met = True

        if met:
            await db.unlock_achievement(user_id, key)
            if ach["reward_type"] == "money":
                await db.add_balance(user_id, ach["reward_value"])
            elif ach["reward_type"] == "title":
                await db.unlock_title(user_id, ach["reward_value"])
            newly_unlocked.append(ach)

    return newly_unlocked


async def mark_bankrupt_if_needed(db, user_id: int):
    user = await db.get_user(user_id)
    if user["balance"] + user["bank"] <= 0 and not user["has_gone_bankrupt"]:
        await db.set_field(user_id, "has_gone_bankrupt", 1)
