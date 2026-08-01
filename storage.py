"""
Simple JSON-file backed storage for the bot.

This is intentionally lightweight so the bot can run on a single Railway
service with no external database. Every guild's settings and history are
kept in one data.json file on disk.

NOTE: Railway's filesystem is ephemeral on redeploy unless you attach a
volume. For anything you want to survive redeploys, either attach a
Railway volume mounted at this project's working directory, or swap this
module out for a real database (Postgres, Redis, etc).
"""

import json
import os
import threading
from datetime import datetime, timezone

DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")

_lock = threading.Lock()

DEFAULTS = {
    "history": {},      # guild_id -> user_id -> [ {type, moderator_id, reason, timestamp} ]
    "afk": {},          # guild_id -> user_id -> {reason, since}
    "automod": {},      # guild_id -> settings dict
    "sticky": {},       # channel_id -> content
    "reactionroles": {},# message_id -> {emoji: role_id}
    "jail": {},         # guild_id -> {role_id, channel_id}
    "verify": {},       # guild_id -> {role_id}
    "autorole": {},     # guild_id -> [role_id, ...]
    "welcome": {},      # guild_id -> {channel_id, message}
    "goodbye": {},      # guild_id -> {channel_id, message}
    "logs": {},         # guild_id -> channel_id
    "whitelist": {},    # guild_id -> [id, ...]
    "blacklist": {},    # guild_id -> [id, ...]
    "ignore": {},       # guild_id -> [id, ...]
    "maintenance": {},  # guild_id -> bool
}


def _read():
    if not os.path.exists(DATA_FILE):
        return json.loads(json.dumps(DEFAULTS))
    with open(DATA_FILE, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}
    for k, v in DEFAULTS.items():
        data.setdefault(k, json.loads(json.dumps(v)))
    return data


def _write(data):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, DATA_FILE)


class Storage:
    """Thread-safe accessor around the JSON data file."""

    def __init__(self):
        with _lock:
            self.data = _read()

    def save(self):
        with _lock:
            _write(self.data)

    # -- generic helpers -------------------------------------------------
    def section(self, name):
        return self.data.setdefault(name, {})

    # -- history / moderation log ----------------------------------------
    def add_history(self, guild_id: int, user_id: int, action: str, moderator_id: int, reason: str = None):
        guild_hist = self.section("history").setdefault(str(guild_id), {})
        user_hist = guild_hist.setdefault(str(user_id), [])
        user_hist.append({
            "type": action,
            "moderator_id": moderator_id,
            "reason": reason or "No reason provided",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.save()

    def get_history(self, guild_id: int, user_id: int):
        return self.section("history").get(str(guild_id), {}).get(str(user_id), [])

    # -- afk ---------------------------------------------------------------
    def set_afk(self, guild_id: int, user_id: int, reason: str):
        g = self.section("afk").setdefault(str(guild_id), {})
        g[str(user_id)] = {"reason": reason, "since": datetime.now(timezone.utc).isoformat()}
        self.save()

    def clear_afk(self, guild_id: int, user_id: int):
        g = self.section("afk").setdefault(str(guild_id), {})
        if str(user_id) in g:
            del g[str(user_id)]
            self.save()
            return True
        return False

    def get_afk(self, guild_id: int, user_id: int):
        return self.section("afk").get(str(guild_id), {}).get(str(user_id))

    # -- per-guild settings (automod, jail, verify, welcome, goodbye, logs)
    def get_guild_setting(self, section: str, guild_id: int, default=None):
        return self.section(section).get(str(guild_id), default)

    def set_guild_setting(self, section: str, guild_id: int, value):
        self.section(section)[str(guild_id)] = value
        self.save()

    # -- sticky messages -----------------------------------------------
    def set_sticky(self, channel_id: int, content: str):
        self.section("sticky")[str(channel_id)] = content
        self.save()

    def clear_sticky(self, channel_id: int):
        s = self.section("sticky")
        if str(channel_id) in s:
            del s[str(channel_id)]
            self.save()

    def get_sticky(self, channel_id: int):
        return self.section("sticky").get(str(channel_id))

    # -- reaction roles --------------------------------------------------
    def add_reaction_role(self, message_id: int, emoji: str, role_id: int):
        rr = self.section("reactionroles").setdefault(str(message_id), {})
        rr[emoji] = role_id
        self.save()

    def get_reaction_roles(self, message_id: int):
        return self.section("reactionroles").get(str(message_id), {})

    # -- list-style settings (whitelist/blacklist/ignore/autorole) ------
    def add_to_list(self, section: str, guild_id: int, item_id: int):
        lst = self.section(section).setdefault(str(guild_id), [])
        if item_id not in lst:
            lst.append(item_id)
            self.save()

    def remove_from_list(self, section: str, guild_id: int, item_id: int):
        lst = self.section(section).setdefault(str(guild_id), [])
        if item_id in lst:
            lst.remove(item_id)
            self.save()

    def get_list(self, section: str, guild_id: int):
        return self.section(section).get(str(guild_id), [])


storage = Storage()
