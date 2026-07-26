import time
import os
import aiosqlite

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER NOT NULL DEFAULT 0,
    bank INTEGER NOT NULL DEFAULT 0,
    bank_capacity INTEGER NOT NULL DEFAULT 500000,
    lifetime_earned INTEGER NOT NULL DEFAULT 0,
    exp INTEGER NOT NULL DEFAULT 0,
    level INTEGER NOT NULL DEFAULT 1,
    prestige INTEGER NOT NULL DEFAULT 0,
    title TEXT,
    job TEXT,
    total_commands INTEGER NOT NULL DEFAULT 0,
    work_count INTEGER NOT NULL DEFAULT 0,
    gambling_won INTEGER NOT NULL DEFAULT 0,
    gambling_lost INTEGER NOT NULL DEFAULT 0,
    gambling_count INTEGER NOT NULL DEFAULT 0,
    has_gone_bankrupt INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS gambling_stats (
    user_id INTEGER NOT NULL,
    game TEXT NOT NULL,
    won INTEGER NOT NULL DEFAULT 0,
    lost INTEGER NOT NULL DEFAULT 0,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, game)
);

CREATE TABLE IF NOT EXISTS cooldowns (
    user_id INTEGER NOT NULL,
    command TEXT NOT NULL,
    expires_at REAL NOT NULL,
    PRIMARY KEY (user_id, command)
);

CREATE TABLE IF NOT EXISTS achievements_unlocked (
    user_id INTEGER NOT NULL,
    achievement_key TEXT NOT NULL,
    unlocked_at REAL NOT NULL,
    PRIMARY KEY (user_id, achievement_key)
);

CREATE TABLE IF NOT EXISTS titles_unlocked (
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    PRIMARY KEY (user_id, title)
);

CREATE TABLE IF NOT EXISTS pets (
    pet_id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    species TEXT NOT NULL,
    name TEXT,
    level INTEGER NOT NULL DEFAULT 1,
    hunger INTEGER NOT NULL DEFAULT 100,
    happiness INTEGER NOT NULL DEFAULT 100,
    alive INTEGER NOT NULL DEFAULT 1,
    last_fed REAL NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    job_key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    pay_min INTEGER NOT NULL,
    pay_max INTEGER NOT NULL,
    stock INTEGER NOT NULL,
    max_stock INTEGER NOT NULL,
    next_refresh REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER,
    type TEXT NOT NULL,
    amount INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    claimed_by INTEGER,
    expires_at REAL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,
    event_channel_id INTEGER
);
"""


class Database:
    def __init__(self, path: str = config.DB_PATH):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()
        await self._migrate()

    async def _migrate(self):
        """Add columns introduced after the initial release to any pre-existing
        database file. Safe to run every startup; errors from an already-present
        column are ignored."""
        migrations = [
            ("users", "bank_capacity", f"INTEGER NOT NULL DEFAULT {config.BANK_STARTING_CAPACITY}"),
        ]
        for table, column, coltype in migrations:
            try:
                await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
                await self.conn.commit()
            except Exception:
                pass  # column already exists

    async def close(self):
        if self.conn:
            await self.conn.close()

    # -- generic helpers ---------------------------------------------------
    async def execute(self, query: str, params: tuple = ()):
        await self.conn.execute(query, params)
        await self.conn.commit()

    async def fetchone(self, query: str, params: tuple = ()):
        async with self.conn.execute(query, params) as cur:
            return await cur.fetchone()

    async def fetchall(self, query: str, params: tuple = ()):
        async with self.conn.execute(query, params) as cur:
            return await cur.fetchall()

    # -- users ---------------------------------------------------------------
    async def ensure_user(self, user_id: int):
        await self.execute(
            "INSERT OR IGNORE INTO users (user_id, created_at) VALUES (?, ?)",
            (user_id, time.time()),
        )

    async def get_user(self, user_id: int):
        await self.ensure_user(user_id)
        return await self.fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))

    async def add_balance(self, user_id: int, amount: int):
        await self.ensure_user(user_id)
        await self.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id),
        )

    async def earn(self, user_id: int, amount: int):
        """Add balance from an income source and track lifetime earnings for achievements."""
        await self.ensure_user(user_id)
        await self.execute(
            "UPDATE users SET balance = balance + ?, lifetime_earned = lifetime_earned + ? "
            "WHERE user_id = ?",
            (amount, amount, user_id),
        )

    async def add_bank(self, user_id: int, amount: int):
        await self.ensure_user(user_id)
        await self.execute(
            "UPDATE users SET bank = bank + ? WHERE user_id = ?",
            (amount, user_id),
        )

    async def set_field(self, user_id: int, field: str, value):
        await self.ensure_user(user_id)
        await self.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))

    async def increment_field(self, user_id: int, field: str, amount=1):
        await self.ensure_user(user_id)
        await self.execute(
            f"UPDATE users SET {field} = {field} + ? WHERE user_id = ?", (amount, user_id)
        )

    # -- cooldowns -------------------------------------------------------
    async def get_cooldown_remaining(self, user_id: int, command: str) -> float:
        row = await self.fetchone(
            "SELECT expires_at FROM cooldowns WHERE user_id = ? AND command = ?",
            (user_id, command),
        )
        if not row:
            return 0.0
        remaining = row["expires_at"] - time.time()
        return max(0.0, remaining)

    async def set_cooldown(self, user_id: int, command: str, seconds: float):
        expires_at = time.time() + seconds
        await self.execute(
            "INSERT INTO cooldowns (user_id, command, expires_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, command) DO UPDATE SET expires_at = excluded.expires_at",
            (user_id, command, expires_at),
        )

    async def get_all_cooldowns(self, user_id: int):
        rows = await self.fetchall(
            "SELECT command, expires_at FROM cooldowns WHERE user_id = ? AND expires_at > ?",
            (user_id, time.time()),
        )
        return rows

    # -- achievements / titles -------------------------------------------
    async def has_achievement(self, user_id: int, key: str) -> bool:
        row = await self.fetchone(
            "SELECT 1 FROM achievements_unlocked WHERE user_id = ? AND achievement_key = ?",
            (user_id, key),
        )
        return row is not None

    async def unlock_achievement(self, user_id: int, key: str):
        await self.execute(
            "INSERT OR IGNORE INTO achievements_unlocked (user_id, achievement_key, unlocked_at) "
            "VALUES (?, ?, ?)",
            (user_id, key, time.time()),
        )

    async def get_unlocked_achievements(self, user_id: int):
        rows = await self.fetchall(
            "SELECT achievement_key FROM achievements_unlocked WHERE user_id = ?", (user_id,)
        )
        return [r["achievement_key"] for r in rows]

    async def unlock_title(self, user_id: int, title: str):
        await self.execute(
            "INSERT OR IGNORE INTO titles_unlocked (user_id, title) VALUES (?, ?)",
            (user_id, title),
        )

    async def get_titles(self, user_id: int):
        rows = await self.fetchall("SELECT title FROM titles_unlocked WHERE user_id = ?", (user_id,))
        return [r["title"] for r in rows]

    # -- gambling stats (per-game) ----------------------------------------
    async def record_gamble(self, user_id: int, game: str, won: int, lost: int):
        await self.execute(
            "INSERT INTO gambling_stats (user_id, game, won, lost, count) VALUES (?, ?, ?, ?, 1) "
            "ON CONFLICT(user_id, game) DO UPDATE SET "
            "won = won + excluded.won, lost = lost + excluded.lost, count = count + 1",
            (user_id, game, won, lost),
        )

    async def get_gambling_stats(self, user_id: int):
        return await self.fetchall(
            "SELECT game, won, lost, count FROM gambling_stats WHERE user_id = ?", (user_id,)
        )

    async def get_gambling_stat(self, user_id: int, game: str):
        return await self.fetchone(
            "SELECT game, won, lost, count FROM gambling_stats WHERE user_id = ? AND game = ?",
            (user_id, game),
        )

    # -- bank capacity -------------------------------------------------------
    async def add_bank_capacity(self, user_id: int, amount: int):
        await self.ensure_user(user_id)
        await self.execute(
            "UPDATE users SET bank_capacity = bank_capacity + ? WHERE user_id = ?",
            (amount, user_id),
        )

    # -- pets --------------------------------------------------------------
    async def get_pets(self, owner_id: int, alive_only: bool = True):
        if alive_only:
            return await self.fetchall(
                "SELECT * FROM pets WHERE owner_id = ? AND alive = 1", (owner_id,)
            )
        return await self.fetchall("SELECT * FROM pets WHERE owner_id = ?", (owner_id,))

    async def add_pet(self, owner_id: int, species: str, name: str):
        await self.execute(
            "INSERT INTO pets (owner_id, species, name, last_fed, created_at) VALUES (?, ?, ?, ?, ?)",
            (owner_id, species, name, time.time(), time.time()),
        )

    async def get_pet(self, pet_id: int):
        return await self.fetchone("SELECT * FROM pets WHERE pet_id = ?", (pet_id,))

    async def update_pet(self, pet_id: int, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [pet_id]
        await self.execute(f"UPDATE pets SET {cols} WHERE pet_id = ?", tuple(values))

    async def remove_pet(self, pet_id: int):
        await self.execute("DELETE FROM pets WHERE pet_id = ?", (pet_id,))

    # -- jobs ----------------------------------------------------------------
    async def get_job(self, job_key: str):
        return await self.fetchone("SELECT * FROM jobs WHERE job_key = ?", (job_key,))

    async def get_all_jobs(self):
        return await self.fetchall("SELECT * FROM jobs")

    async def upsert_job(self, job_key, name, pay_min, pay_max, stock, max_stock, next_refresh):
        await self.execute(
            "INSERT INTO jobs (job_key, name, pay_min, pay_max, stock, max_stock, next_refresh) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(job_key) DO NOTHING",
            (job_key, name, pay_min, pay_max, stock, max_stock, next_refresh),
        )

    async def set_job_stock(self, job_key, stock, next_refresh):
        await self.execute(
            "UPDATE jobs SET stock = ?, next_refresh = ? WHERE job_key = ?",
            (stock, next_refresh, job_key),
        )

    # -- events --------------------------------------------------------------
    async def set_event_channel(self, guild_id: int, channel_id: int):
        await self.execute(
            "INSERT INTO guild_config (guild_id, event_channel_id) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET event_channel_id = excluded.event_channel_id",
            (guild_id, channel_id),
        )

    async def get_event_channel(self, guild_id: int):
        row = await self.fetchone(
            "SELECT event_channel_id FROM guild_config WHERE guild_id = ?", (guild_id,)
        )
        return row["event_channel_id"] if row else None

    async def create_event(self, guild_id, channel_id, type_, amount, expires_at):
        cur = await self.conn.execute(
            "INSERT INTO events (guild_id, channel_id, type, amount, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, channel_id, type_, amount, expires_at, time.time()),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def set_event_message(self, event_id, message_id):
        await self.execute(
            "UPDATE events SET message_id = ? WHERE event_id = ?", (message_id, event_id)
        )

    async def get_event(self, event_id: int):
        return await self.fetchone("SELECT * FROM events WHERE event_id = ?", (event_id,))

    async def claim_event(self, event_id: int, user_id: int) -> bool:
        """Atomically claim an event. Returns True if this user won the claim race."""
        await self.conn.execute(
            "UPDATE events SET status = 'claimed', claimed_by = ? "
            "WHERE event_id = ? AND status = 'active'",
            (user_id, event_id),
        )
        await self.conn.commit()
        row = await self.fetchone("SELECT claimed_by FROM events WHERE event_id = ?", (event_id,))
        return row is not None and row["claimed_by"] == user_id

    async def expire_event(self, event_id: int):
        await self.execute(
            "UPDATE events SET status = 'expired' WHERE event_id = ? AND status = 'active'",
            (event_id,),
        )

    async def get_active_event_in_channel(self, channel_id: int):
        return await self.fetchone(
            "SELECT * FROM events WHERE channel_id = ? AND status = 'active' "
            "ORDER BY event_id DESC LIMIT 1",
            (channel_id,),
        )

    # -- leaderboard -----------------------------------------------------
    async def get_leaderboard(self, limit: int = 10):
        return await self.fetchall(
            "SELECT user_id, balance, bank, (balance + bank) AS net "
            "FROM users ORDER BY net DESC LIMIT ?",
            (limit,),
        )
