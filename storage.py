"""
SQLite-backed storage for the bot.

Compatible with:
- moderation.py
- automod.py
- utility.py
- jail.py
- server.py
- modlogs.py
- reaction roles
- sticky messages
- AFK system

Keeps the old JSON storage API compatibility while using SQLite.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone


DB_PATH = os.environ.get(
    "BOT_DB_PATH",
    os.path.join(os.path.dirname(__file__), "bot.db")
)

_lock = threading.Lock()


class Storage:
    """Thread-safe SQLite storage manager."""

    def __init__(self, db_path: str = DB_PATH):
        folder = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(folder, exist_ok=True)

        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False
        )

        self._conn.execute(
            "PRAGMA journal_mode=WAL"
        )

        self._init_schema()


    def _init_schema(self):
        with _lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS guild_settings (
                    section TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY(section, guild_id)
                );


                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    moderator_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );


                CREATE TABLE IF NOT EXISTS afk (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    since TEXT NOT NULL,
                    PRIMARY KEY(guild_id, user_id)
                );


                CREATE TABLE IF NOT EXISTS sticky (
                    channel_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL
                );


                CREATE TABLE IF NOT EXISTS reactionroles (
                    message_id TEXT NOT NULL,
                    emoji TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    PRIMARY KEY(message_id, emoji)
                );
                """
            )

            self._conn.commit()


    # ============================================================
    # MODERATION HISTORY
    # ============================================================

    def add_history(
        self,
        guild_id: int,
        user_id: int,
        action: str,
        moderator_id: int,
        reason: str = None
    ):

        with _lock:
            self._conn.execute(
                """
                INSERT INTO history
                (guild_id,user_id,type,moderator_id,reason,timestamp)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    str(guild_id),
                    str(user_id),
                    action,
                    str(moderator_id),
                    reason or "No reason provided",
                    datetime.now(timezone.utc).isoformat()
                )
            )

            self._conn.commit()



    def get_history(
        self,
        guild_id: int,
        user_id: int
    ):

        with _lock:
            rows = self._conn.execute(
                """
                SELECT type,moderator_id,reason,timestamp
                FROM history
                WHERE guild_id=? AND user_id=?
                ORDER BY id ASC
                """,
                (
                    str(guild_id),
                    str(user_id)
                )
            ).fetchall()


        return [
            {
                "type": row[0],
                "moderator_id": int(row[1]),
                "reason": row[2],
                "timestamp": row[3],
            }
            for row in rows
        ]



    # ============================================================
    # AFK SYSTEM
    # ============================================================


    def set_afk(
        self,
        guild_id: int,
        user_id: int,
        reason: str
    ):

        with _lock:
            self._conn.execute(
                """
                INSERT INTO afk
                (guild_id,user_id,reason,since)
                VALUES(?,?,?,?)

                ON CONFLICT(guild_id,user_id)
                DO UPDATE SET
                reason=excluded.reason,
                since=excluded.since
                """,
                (
                    str(guild_id),
                    str(user_id),
                    reason,
                    datetime.now(timezone.utc).isoformat()
                )
            )

            self._conn.commit()



    def clear_afk(
        self,
        guild_id: int,
        user_id: int
    ):

        with _lock:
            cur = self._conn.execute(
                """
                DELETE FROM afk
                WHERE guild_id=? AND user_id=?
                """,
                (
                    str(guild_id),
                    str(user_id)
                )
            )

            self._conn.commit()

        return cur.rowcount > 0



    def get_afk(
        self,
        guild_id: int,
        user_id: int
    ):

        with _lock:
            row = self._conn.execute(
                """
                SELECT reason,since
                FROM afk
                WHERE guild_id=? AND user_id=?
                """,
                (
                    str(guild_id),
                    str(user_id)
                )
            ).fetchone()


        if not row:
            return None


        return {
            "reason": row[0],
            "since": row[1]
        }

    # ============================================================
    # GUILD SETTINGS
    # ============================================================

    def get_guild_setting(
        self,
        section: str,
        guild_id: int,
        default=None
    ):

        with _lock:
            row = self._conn.execute(
                """
                SELECT value
                FROM guild_settings
                WHERE section=? AND guild_id=?
                """,
                (
                    section,
                    str(guild_id)
                )
            ).fetchone()


        if row is None:
            return default


        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return default



    def set_guild_setting(
        self,
        section: str,
        guild_id: int,
        value
    ):

        payload = json.dumps(value)


        with _lock:
            self._conn.execute(
                """
                INSERT INTO guild_settings
                (section,guild_id,value)

                VALUES(?,?,?)

                ON CONFLICT(section,guild_id)
                DO UPDATE SET value=excluded.value
                """,
                (
                    section,
                    str(guild_id),
                    payload
                )
            )

            self._conn.commit()



    # ============================================================
    # OLD JSON STORAGE COMPATIBILITY
    # Fixes:
    # storage.section("name")
    # ============================================================


    def section(self, name: str):

        storage = self


        class Section:

            def __init__(self, section_name):
                self.name = section_name



            def get(self, guild_id, default=None):

                return storage.get_guild_setting(
                    self.name,
                    guild_id,
                    default
                )



            def set(self, guild_id, value):

                storage.set_guild_setting(
                    self.name,
                    guild_id,
                    value
                )



            def delete(self, guild_id):

                with _lock:
                    storage._conn.execute(
                        """
                        DELETE FROM guild_settings
                        WHERE section=? AND guild_id=?
                        """,
                        (
                            self.name,
                            str(guild_id)
                        )
                    )

                    storage._conn.commit()


        return Section(name)



    # ============================================================
    # STICKY MESSAGES
    # ============================================================


    def set_sticky(
        self,
        channel_id: int,
        content: str
    ):

        with _lock:
            self._conn.execute(
                """
                INSERT INTO sticky
                (channel_id,content)

                VALUES(?,?)

                ON CONFLICT(channel_id)
                DO UPDATE SET content=excluded.content
                """,
                (
                    str(channel_id),
                    content
                )
            )

            self._conn.commit()



    def clear_sticky(
        self,
        channel_id: int
    ):

        with _lock:
            self._conn.execute(
                """
                DELETE FROM sticky
                WHERE channel_id=?
                """,
                (
                    str(channel_id),
                )
            )

            self._conn.commit()



    def get_sticky(
        self,
        channel_id: int
    ):

        with _lock:
            row = self._conn.execute(
                """
                SELECT content
                FROM sticky
                WHERE channel_id=?
                """,
                (
                    str(channel_id),
                )
            ).fetchone()


        return row[0] if row else None



    # ============================================================
    # REACTION ROLES
    # ============================================================


    def add_reaction_role(
        self,
        message_id: int,
        emoji: str,
        role_id: int
    ):

        with _lock:
            self._conn.execute(
                """
                INSERT INTO reactionroles
                (message_id,emoji,role_id)

                VALUES(?,?,?)

                ON CONFLICT(message_id,emoji)
                DO UPDATE SET role_id=excluded.role_id
                """,
                (
                    str(message_id),
                    emoji,
                    str(role_id)
                )
            )

            self._conn.commit()



    def get_reaction_roles(
        self,
        message_id: int
    ):

        with _lock:
            rows = self._conn.execute(
                """
                SELECT emoji,role_id
                FROM reactionroles
                WHERE message_id=?
                """,
                (
                    str(message_id),
                )
            ).fetchall()


        return {
            emoji: int(role_id)
            for emoji, role_id in rows
        }



    # ============================================================
    # LIST STORAGE
    # whitelist / blacklist / ignore / autorole
    # ============================================================


    def add_to_list(
        self,
        section: str,
        guild_id: int,
        item_id: int
    ):

        current = self.get_guild_setting(
            section,
            guild_id,
            []
        )


        if item_id not in current:
            current.append(item_id)

            self.set_guild_setting(
                section,
                guild_id,
                current
            )



    def remove_from_list(
        self,
        section: str,
        guild_id: int,
        item_id: int
    ):

        current = self.get_guild_setting(
            section,
            guild_id,
            []
        )


        if item_id in current:
            current.remove(item_id)

            self.set_guild_setting(
                section,
                guild_id,
                current
            )



    def get_list(
        self,
        section: str,
        guild_id: int
    ):

        return self.get_guild_setting(
            section,
            guild_id,
            []
        )



# ============================================================
# GLOBAL STORAGE INSTANCE
# ============================================================

storage = Storage()
