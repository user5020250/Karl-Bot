import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DB_PATH = os.getenv("DB_PATH", "data/database.db")

CURRENCY = "₱"
EMBED_COLOR = 0x000000  # black, per spec

# Economy tuning ---------------------------------------------------------
STARTING_BALANCE = 0

# Bank capacity is no longer tied to player level. It starts at a flat
# amount, grows only through `/bank upg` purchases and automatically on
# every prestige, and never resets.
BANK_STARTING_CAPACITY = 500_000
BANK_UPG_CAPACITY_INCREASE = 500_000  # capacity gained per /bank upg purchase
BANK_CAPACITY_PRESTIGE_INCREASE = 500_000  # capacity gained automatically per prestige
BANK_DAILY_INTEREST_RATE = 0.02  # 2%

DAILY_REWARD = (1_000, 3_000)
WEEKLY_REWARD = (10_000, 20_000)
MONTHLY_REWARD = (50_000, 100_000)
YEARLY_REWARD = (500_000, 1_000_000)

WORK_REWARD = (1_000, 5_000)
OVERTIME_REWARD = (5_000, 10_000)
BEG_REWARD = (1_000, 5_000)
COOK_REWARD = (1_000, 5_000)
FISH_REWARD = (1_000, 5_000)
FARM_REWARD = (1_000, 5_000)
HARVEST_REWARD = (1_000, 5_000)

COOLDOWNS = {
    "work": 120,
    "overtime": 600,
    "beg": 120,
    "cook": 120,
    "fish": 120,
    "farm": 120,
    "harvest": 120,
    "rob": 3600,
    "daily": 86400,
    "weekly": 604800,
    "monthly": 2_592_000,
    "yearly": 31_536_000,
    "feed": 600,
    "interest": 86400,
}

ROB_SUCCESS_CHANCE = 0.45
ROB_MIN_TARGET_BALANCE = 500
ROB_STEAL_PERCENT = (0.10, 0.30)  # steal 10-30% of target's cash on hand

JOB_STOCK_REFRESH_SECONDS = 1800  # 30 minutes

MAX_PETS_OWNED = 5
PET_FEED_COOLDOWN = 600
PET_HUNGER_DECAY_HOURS = 24  # hunger drops once per this many hours if not fed
PET_DEATH_HUNGER_THRESHOLD = 0  # pet dies when hunger hits 0 and stays there

# Prestige & bank-upgrade tier pricing -----------------------------------
# Both prestiging and /bank upg share the same tiered price ladder:
# tier 0 -> 1 costs 1,000,000; every tier after that costs 5,000,000 * tier
# (1m, 5m, 10m, 15m, 20m, ...).
TIER_COST_FIRST = 1_000_000
TIER_COST_STEP = 5_000_000
PRESTIGE_MAX_LEVEL = 10
PRESTIGE_INCOME_BONUS_PER_LEVEL = 0.05  # +5% income per prestige level

GAMBLING_GAMES = ["scatter", "colorgame", "tongits", "sabong"]
GAMBLING_MIN_BET = 100

# Leveling / EXP ----------------------------------------------------------
EXP_PER_COMMAND = 10          # base exp gained for using any command
EXP_PER_LEVEL = 1_000         # flat exp needed per level (no level cap)
EXP_PET_BONUS_PER_PET = 0.10  # +10% exp gain per pet owned (alive)
