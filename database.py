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
    guild_id INTEGER NOT NULL,
    job_key TEXT NOT NULL,
    name TEXT NOT NULL,
    pay_min INTEGER NOT NULL,
    pay_max INTEGER NOT NULL,
    stock INTEGER NOT NULL,
    max_stock INTEGER NOT NULL,
    next_refresh REAL NOT NULL,
    PRIMARY KEY (guild_id, job_key)
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

CREATE TABLE IF NOT EXISTS jackpot (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    amount INTEGER NOT NULL DEFAULT 0
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
        await self.conn.execute("INSERT OR IGNORE INTO jackpot (id, amount) VALUES (1, 0)")
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

        # The jobs table used to be keyed globally by job_key alone, which meant
        # job stock (e.g. "only 1 Programmer slot") was shared across every
        # Discord server the bot is in instead of being per-server. Rebuild it
        # with a (guild_id, job_key) key. Job stock is regenerating/ephemeral
        # data (it refills on a timer), so it's safe to reset rather than try
        # to guess which guild old rows belonged to.
        cur = await self.conn.execute("PRAGMA table_info(jobs)")
        cols = [row[1] for row in await cur.fetchall()]
        if "guild_id" not in cols:
            await self.conn.executescript(
                """
                DROP TABLE IF EXISTS jobs;
                CREATE TABLE jobs (
                    guild_id INTEGER NOT NULL,
                    job_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    pay_min INTEGER NOT NULL,
                    pay_max INTEGER NOT NULL,
                    stock INTEGER NOT NULL,
                    max_stock INTEGER NOT NULL,
                    next_refresh REAL NOT NULL,
                    PRIMARY KEY (guild_id, job_key)
                );
                """
            )
            await self.conn.commit()

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

    # -- jobs (per-guild) ------------------------------------------------------
    async def get_job(self, guild_id: int, job_key: str):
        return await self.fetchone(
            "SELECT * FROM jobs WHERE guild_id = ? AND job_key = ?", (guild_id, job_key)
        )

    async def get_all_jobs(self, guild_id: int):
        return await self.fetchall("SELECT * FROM jobs WHERE guild_id = ?", (guild_id,))

    async def upsert_job(self, guild_id, job_key, name, pay_min, pay_max, stock, max_stock, next_refresh):
        await self.execute(
            "INSERT INTO jobs (guild_id, job_key, name, pay_min, pay_max, stock, max_stock, next_refresh) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, job_key) DO NOTHING",
            (guild_id, job_key, name, pay_min, pay_max, stock, max_stock, next_refresh),
        )

    async def reset_job_stock(self, guild_id, job_key, max_stock, next_refresh):
        """Used by the periodic refresh loop to reset a job back to full stock."""
        await self.execute(
            "UPDATE jobs SET stock = ?, next_refresh = ? WHERE guild_id = ? AND job_key = ?",
            (max_stock, next_refresh, guild_id, job_key),
        )

    async def clamp_job_stock(self, guild_id, job_key, max_stock):
        """Used when jobs.json lowers max_stock; clamps existing stock down
        immediately instead of waiting for the next scheduled refresh."""
        await self.execute(
            "UPDATE jobs SET stock = MIN(stock, ?), max_stock = ? WHERE guild_id = ? AND job_key = ?",
            (max_stock, max_stock, guild_id, job_key),
        )

    async def try_take_job(self, guild_id: int, job_key: str) -> bool:
        """Atomically claim one open slot for a job, if any are available.

        Returns True if a slot was claimed, False if the job was already
        full. This is a single conditional UPDATE (not a read-then-write),
        so two users applying for the last slot at the same instant cannot
        both succeed - only one UPDATE will affect a row."""
        cur = await self.conn.execute(
            "UPDATE jobs SET stock = stock - 1 WHERE guild_id = ? AND job_key = ? AND stock > 0",
            (guild_id, job_key),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def release_job(self, guild_id: int, job_key: str):
        """Atomically give back one slot for a job (e.g. on resign), capped
        at the job's max_stock so it can never overflow."""
        await self.conn.execute(
            "UPDATE jobs SET stock = MIN(stock + 1, max_stock) WHERE guild_id = ? AND job_key = ?",
            (guild_id, job_key),
        )
        await self.conn.commit()

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

    # -- jackpot pool ------------------------------------------------------
    async def get_jackpot(self) -> int:
        row = await self.fetchone("SELECT amount FROM jackpot WHERE id = 1")
        return row["amount"] if row else 0

    async def add_to_jackpot(self, amount: int):
        """Feed lost gambling bets into the shared jackpot pool."""
        if amount <= 0:
            return
        await self.execute(
            "UPDATE jackpot SET amount = amount + ? WHERE id = 1", (amount,)
        )

    async def take_jackpot(self) -> int:
        """Atomically empty the jackpot pool and return what was taken.

        Uses a compare-and-swap (read the current amount, then UPDATE only if
        it hasn't changed) so two simultaneous /777 wins can't both drain the
        same pool. In the astronomically rare case of a genuine race, the
        loser of the race gets 0 back rather than risking a double payout."""
        row = await self.fetchone("SELECT amount FROM jackpot WHERE id = 1")
        current = row["amount"] if row else 0
        if current <= 0:
            return 0
        cur = await self.conn.execute(
            "UPDATE jackpot SET amount = 0 WHERE id = 1 AND amount = ?", (current,)
        )
        await self.conn.commit()
        return current if cur.rowcount > 0 else 0

    # -- leaderboard -----------------------------------------------------
    async def get_leaderboard(self, limit: int = 10):
        return await self.fetchall(
            "SELECT user_id, balance, bank, (balance + bank) AS net "
            "FROM users ORDER BY net DESC LIMIT ?",
            (limit,),
        )
