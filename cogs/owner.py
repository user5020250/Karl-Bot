"""
owner.py
--------
Owner-only administration cog for the economy bot.

ASSUMPTIONS (adjust to match your real schema/setup):
- You're using aiosqlite against a file called `economy.db`.
- There is a single table called `users` with (at least) these columns:
    user_id           INTEGER PRIMARY KEY
    balance           INTEGER DEFAULT 0      -- cash
    bank              INTEGER DEFAULT 0
    bank_capacity     INTEGER DEFAULT 10000
    level             INTEGER DEFAULT 1
    xp                INTEGER DEFAULT 0
    prestige          INTEGER DEFAULT 0
    title             TEXT    DEFAULT ''
    job               TEXT    DEFAULT 'Unemployed'
    commands_used     INTEGER DEFAULT 0
    daily_cd          INTEGER DEFAULT 0      -- unix timestamps, 0 = ready
    work_cd           INTEGER DEFAULT 0
    rob_cd            INTEGER DEFAULT 0
    crime_cd          INTEGER DEFAULT 0
    weekly_cd         INTEGER DEFAULT 0
    monthly_cd        INTEGER DEFAULT 0
    stats             TEXT    DEFAULT '{}'   -- JSON blob
    achievements      TEXT    DEFAULT '[]'   -- JSON blob

- self.bot.db is an aiosqlite.Connection already open elsewhere in your bot.
  If instead you open a new connection per-call, swap DB_PATH usage in below.

If your real schema differs, the column names in COOLDOWN_COLUMNS / the
INSERT-OR-IGNORE statement / userinfo formatting are the places to edit.
"""

import json
import os
import shutil
import time
from datetime import datetime

import discord
from discord.ext import commands

DB_PATH = "economy.db"
BACKUP_DIR = "backups"

COOLDOWN_COLUMNS = [
    "daily_cd", "work_cd", "rob_cd", "crime_cd", "weekly_cd", "monthly_cd",
]

DEFAULT_ROW = {
    "balance": 0,
    "bank": 0,
    "bank_capacity": 10000,
    "level": 1,
    "xp": 0,
    "prestige": 0,
    "title": "",
    "job": "Unemployed",
    "commands_used": 0,
    "stats": "{}",
    "achievements": "[]",
    **{c: 0 for c in COOLDOWN_COLUMNS},
}


def fmt_money(n: int) -> str:
    return f"₱{n:,}"


class ConfirmView(discord.ui.View):
    """Simple Yes/No confirmation, only usable by the invoking owner."""

    def __init__(self, author_id: int, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This confirmation isn't for you.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.edit_message(content="✅ Confirmed.", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.edit_message(content="❌ Cancelled.", view=None)
        self.stop()


class Owner(commands.Cog):
    """Owner-only commands for managing the economy database and bot internals."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------ #
    # Cog-wide guard: belt and suspenders on top of @commands.is_owner()
    # ------------------------------------------------------------------ #
    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    async def _db(self):
        """Return the bot's shared aiosqlite connection."""
        return self.bot.db  # assumes bot.db is an open aiosqlite.Connection

    async def _ensure_user(self, user_id: int):
        db = await self._db()
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, balance, bank, bank_capacity, "
            "level, xp, prestige, title, job, commands_used, daily_cd, work_cd, "
            "rob_cd, crime_cd, weekly_cd, monthly_cd, stats, achievements) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                DEFAULT_ROW["balance"], DEFAULT_ROW["bank"], DEFAULT_ROW["bank_capacity"],
                DEFAULT_ROW["level"], DEFAULT_ROW["xp"], DEFAULT_ROW["prestige"],
                DEFAULT_ROW["title"], DEFAULT_ROW["job"], DEFAULT_ROW["commands_used"],
                DEFAULT_ROW["daily_cd"], DEFAULT_ROW["work_cd"], DEFAULT_ROW["rob_cd"],
                DEFAULT_ROW["crime_cd"], DEFAULT_ROW["weekly_cd"], DEFAULT_ROW["monthly_cd"],
                DEFAULT_ROW["stats"], DEFAULT_ROW["achievements"],
            ),
        )
        await db.commit()

    async def _get_row(self, user_id: int):
        await self._ensure_user(user_id)
        db = await self._db()
        db.row_factory = None
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        cols = [d[0] for d in cur.description]
        await cur.close()
        return dict(zip(cols, row))

    async def _set_column(self, user_id: int, column: str, value):
        await self._ensure_user(user_id)
        db = await self._db()
        await db.execute(f"UPDATE users SET {column} = ? WHERE user_id = ?", (value, user_id))
        await db.commit()

    async def _add_column(self, user_id: int, column: str, delta):
        await self._ensure_user(user_id)
        db = await self._db()
        await db.execute(
            f"UPDATE users SET {column} = {column} + ? WHERE user_id = ?", (delta, user_id)
        )
        await db.commit()

    async def _confirm(self, ctx: commands.Context, message: str) -> bool:
        view = ConfirmView(author_id=ctx.author.id)
        msg = await ctx.send(message, view=view)
        await view.wait()
        if view.value is None:
            await msg.edit(content="⌛ Confirmation timed out, action cancelled.", view=None)
            return False
        return bool(view.value)

    def _resolve_target(self, ctx: commands.Context, user: discord.User = None) -> discord.abc.User:
        return user or ctx.author

    # ==================================================================
    # ECONOMY MANAGEMENT
    # ==================================================================
    @commands.command(name="give")
    @commands.is_owner()
    async def give(self, ctx: commands.Context, amount: int, user: discord.User = None):
        """Give money (cash) to yourself or another user."""
        target = self._resolve_target(ctx, user)
        if amount <= 0:
            return await ctx.send("Amount must be positive.")
        await self._add_column(target.id, "balance", amount)
        await ctx.send(f"💸 Gave {fmt_money(amount)} to **{target}**.")

    @commands.command(name="take")
    @commands.is_owner()
    async def take(self, ctx: commands.Context, amount: int, user: discord.User):
        """Remove money (cash) from a user."""
        if amount <= 0:
            return await ctx.send("Amount must be positive.")
        row = await self._get_row(user.id)
        new_bal = max(0, row["balance"] - amount)
        await self._set_column(user.id, "balance", new_bal)
        await ctx.send(f"🧹 Took {fmt_money(amount)} from **{user}**. New balance: {fmt_money(new_bal)}")

    @commands.command(name="setbal")
    @commands.is_owner()
    async def setbal(self, ctx: commands.Context, amount: int, user: discord.User = None):
        """Set a user's cash balance."""
        target = self._resolve_target(ctx, user)
        if amount < 0:
            return await ctx.send("Amount cannot be negative.")
        await self._set_column(target.id, "balance", amount)
        await ctx.send(f"⚙️ Set **{target}**'s balance to {fmt_money(amount)}.")

    @commands.command(name="addbal")
    @commands.is_owner()
    async def addbal(self, ctx: commands.Context, amount: int, user: discord.User = None):
        """Add cash to a user's balance without replacing it."""
        target = self._resolve_target(ctx, user)
        await self._add_column(target.id, "balance", amount)
        await ctx.send(f"➕ Added {fmt_money(amount)} to **{target}**'s balance.")

    @commands.command(name="setbank")
    @commands.is_owner()
    async def setbank(self, ctx: commands.Context, amount: int, user: discord.User = None):
        """Set a user's bank balance."""
        target = self._resolve_target(ctx, user)
        if amount < 0:
            return await ctx.send("Amount cannot be negative.")
        await self._set_column(target.id, "bank", amount)
        await ctx.send(f"⚙️ Set **{target}**'s bank balance to {fmt_money(amount)}.")

    @commands.command(name="addbank")
    @commands.is_owner()
    async def addbank(self, ctx: commands.Context, amount: int, user: discord.User = None):
        """Add money directly to a user's bank."""
        target = self._resolve_target(ctx, user)
        await self._add_column(target.id, "bank", amount)
        await ctx.send(f"🏦 Added {fmt_money(amount)} to **{target}**'s bank.")

    @commands.command(name="setbankcap")
    @commands.is_owner()
    async def setbankcap(self, ctx: commands.Context, amount: int, user: discord.User = None):
        """Set a user's bank capacity."""
        target = self._resolve_target(ctx, user)
        if amount < 0:
            return await ctx.send("Amount cannot be negative.")
        await self._set_column(target.id, "bank_capacity", amount)
        await ctx.send(f"⚙️ Set **{target}**'s bank capacity to {fmt_money(amount)}.")

    @commands.command(name="addbankcap")
    @commands.is_owner()
    async def addbankcap(self, ctx: commands.Context, amount: int, user: discord.User = None):
        """Increase a user's bank capacity."""
        target = self._resolve_target(ctx, user)
        await self._add_column(target.id, "bank_capacity", amount)
        await ctx.send(f"📈 Increased **{target}**'s bank capacity by {fmt_money(amount)}.")

    # ==================================================================
    # PROGRESSION
    # ==================================================================
    @commands.command(name="setlevel")
    @commands.is_owner()
    async def setlevel(self, ctx: commands.Context, level: int, user: discord.User = None):
        target = self._resolve_target(ctx, user)
        if level < 0:
            return await ctx.send("Level cannot be negative.")
        await self._set_column(target.id, "level", level)
        await ctx.send(f"⚙️ Set **{target}**'s level to {level}.")

    @commands.command(name="setxp")
    @commands.is_owner()
    async def setxp(self, ctx: commands.Context, xp: int, user: discord.User = None):
        target = self._resolve_target(ctx, user)
        if xp < 0:
            return await ctx.send("XP cannot be negative.")
        await self._set_column(target.id, "xp", xp)
        await ctx.send(f"⚙️ Set **{target}**'s XP to {xp:,}.")

    @commands.command(name="addxp")
    @commands.is_owner()
    async def addxp(self, ctx: commands.Context, xp: int, user: discord.User = None):
        target = self._resolve_target(ctx, user)
        await self._add_column(target.id, "xp", xp)
        await ctx.send(f"➕ Added {xp:,} XP to **{target}**.")

    @commands.command(name="setprestige")
    @commands.is_owner()
    async def setprestige(self, ctx: commands.Context, level: int, user: discord.User = None):
        target = self._resolve_target(ctx, user)
        if level < 0:
            return await ctx.send("Prestige cannot be negative.")
        await self._set_column(target.id, "prestige", level)
        await ctx.send(f"⚙️ Set **{target}**'s prestige to {level}.")

    @commands.command(name="settitle")
    @commands.is_owner()
    async def settitle(self, ctx: commands.Context, title: str, user: discord.User = None):
        target = self._resolve_target(ctx, user)
        await self._set_column(target.id, "title", title)
        await ctx.send(f"🏷️ Set **{target}**'s title to \"{title}\".")

    # ==================================================================
    # RESET COMMANDS
    # ==================================================================
    @commands.group(name="reset", invoke_without_command=True)
    @commands.is_owner()
    async def reset(self, ctx: commands.Context):
        await ctx.send(
            "Usage: `!reset cooldown|economy|achievements|stats|all [user]`"
        )

    @reset.command(name="cooldown")
    @commands.is_owner()
    async def reset_cooldown(self, ctx: commands.Context, user: discord.User = None):
        """Resets every cooldown column for a user."""
        target = self._resolve_target(ctx, user)
        await self._ensure_user(target.id)
        db = await self._db()
        set_clause = ", ".join(f"{c} = 0" for c in COOLDOWN_COLUMNS)
        await db.execute(f"UPDATE users SET {set_clause} WHERE user_id = ?", (target.id,))
        await db.commit()
        await ctx.send(f"⏱️ Reset all cooldowns for **{target}**.")

    @reset.command(name="economy")
    @commands.is_owner()
    async def reset_economy(self, ctx: commands.Context, user: discord.User = None):
        """Resets cash, bank, capacity, prestige, level, XP, titles, stats, jobs, cooldowns."""
        target = self._resolve_target(ctx, user)
        ok = await self._confirm(
            ctx, f"⚠️ This will reset **all economy data** for {target}. Continue?"
        )
        if not ok:
            return
        db = await self._db()
        await self._ensure_user(target.id)
        await db.execute(
            "UPDATE users SET balance = ?, bank = ?, bank_capacity = ?, prestige = ?, "
            "level = ?, xp = ?, title = ?, job = ?, stats = ?, "
            + ", ".join(f"{c} = 0" for c in COOLDOWN_COLUMNS)
            + " WHERE user_id = ?",
            (
                DEFAULT_ROW["balance"], DEFAULT_ROW["bank"], DEFAULT_ROW["bank_capacity"],
                DEFAULT_ROW["prestige"], DEFAULT_ROW["level"], DEFAULT_ROW["xp"],
                DEFAULT_ROW["title"], DEFAULT_ROW["job"], DEFAULT_ROW["stats"],
                target.id,
            ),
        )
        await db.commit()
        await ctx.send(f"♻️ Economy data reset for **{target}**.")

    @reset.command(name="achievements")
    @commands.is_owner()
    async def reset_achievements(self, ctx: commands.Context, user: discord.User = None):
        target = self._resolve_target(ctx, user)
        await self._set_column(target.id, "achievements", "[]")
        await ctx.send(f"🏆 Cleared achievements for **{target}**.")

    @reset.command(name="stats")
    @commands.is_owner()
    async def reset_stats(self, ctx: commands.Context, user: discord.User = None):
        target = self._resolve_target(ctx, user)
        await self._set_column(target.id, "stats", "{}")
        await ctx.send(f"📊 Cleared stats for **{target}**.")

    @reset.command(name="all")
    @commands.is_owner()
    async def reset_all(self, ctx: commands.Context, user: discord.User = None):
        """Completely wipes a player's data (row deleted, recreated fresh)."""
        target = self._resolve_target(ctx, user)
        ok = await self._confirm(
            ctx, f"🚨 This will **completely wipe** all data for {target}. This cannot be undone. Continue?"
        )
        if not ok:
            return
        db = await self._db()
        await db.execute("DELETE FROM users WHERE user_id = ?", (target.id,))
        await db.commit()
        await self._ensure_user(target.id)
        await ctx.send(f"🗑️ **{target}**'s data has been completely wiped and reset to defaults.")

    # ==================================================================
    # INFORMATION
    # ==================================================================
    @commands.command(name="userinfo")
    @commands.is_owner()
    async def userinfo(self, ctx: commands.Context, user: discord.User = None):
        """Shows every database field for a user."""
        target = self._resolve_target(ctx, user)
        row = await self._get_row(target.id)

        lines = [
            f"ID: {row['user_id']}",
            f"Balance: {fmt_money(row['balance'])}",
            f"Bank: {fmt_money(row['bank'])}",
            f"Capacity: {fmt_money(row['bank_capacity'])}",
            f"Prestige: {row['prestige']}",
            f"Level: {row['level']}",
            f"XP: {row['xp']:,}",
            f"Job: {row['job']}",
            f"Title: {row['title']}",
            f"Commands Used: {row['commands_used']:,}",
        ]
        for c in COOLDOWN_COLUMNS:
            ts = row.get(c, 0)
            ready = "Ready" if not ts or ts <= time.time() else f"<t:{int(ts)}:R>"
            lines.append(f"{c}: {ready}")

        embed = discord.Embed(
            title=f"User Info — {target}",
            description="```\n" + "\n".join(lines) + "\n```",
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    # ==================================================================
    # BOT UTILITIES
    # ==================================================================
    @commands.command(name="reload")
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, cog: str):
        try:
            await self.bot.reload_extension(cog)
            await ctx.send(f"🔄 Reloaded `{cog}`.")
        except Exception as e:
            await ctx.send(f"❌ Failed to reload `{cog}`: `{e}`")

    @commands.command(name="reloadall")
    @commands.is_owner()
    async def reloadall(self, ctx: commands.Context):
        results = []
        for ext in list(self.bot.extensions.keys()):
            try:
                await self.bot.reload_extension(ext)
                results.append(f"✅ {ext}")
            except Exception as e:
                results.append(f"❌ {ext}: `{e}`")
        await ctx.send("**Reload results:**\n" + "\n".join(results))

    @commands.command(name="load")
    @commands.is_owner()
    async def load(self, ctx: commands.Context, cog: str):
        try:
            await self.bot.load_extension(cog)
            await ctx.send(f"📦 Loaded `{cog}`.")
        except Exception as e:
            await ctx.send(f"❌ Failed to load `{cog}`: `{e}`")

    @commands.command(name="unload")
    @commands.is_owner()
    async def unload(self, ctx: commands.Context, cog: str):
        try:
            await self.bot.unload_extension(cog)
            await ctx.send(f"📤 Unloaded `{cog}`.")
        except Exception as e:
            await ctx.send(f"❌ Failed to unload `{cog}`: `{e}`")

    @commands.command(name="sync")
    @commands.is_owner()
    async def sync(self, ctx: commands.Context):
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"🔗 Synced {len(synced)} slash command(s).")
        except Exception as e:
            await ctx.send(f"❌ Sync failed: `{e}`")

    # ==================================================================
    # DATABASE
    # ==================================================================
    @commands.command(name="sql")
    @commands.is_owner()
    async def sql(self, ctx: commands.Context, *, query: str):
        """Execute raw SQL. Auto-backs up before any non-SELECT statement."""
        db = await self._db()
        is_select = query.strip().lower().startswith("select")

        if not is_select:
            ok = await self._confirm(
                ctx,
                "⚠️ This is a **write** query. A backup will be made first, "
                "but this can still corrupt data. Continue?",
            )
            if not ok:
                return
            await self._backup()

        try:
            cur = await db.execute(query)
            if is_select:
                rows = await cur.fetchall()
                cols = [d[0] for d in cur.description] if cur.description else []
                await cur.close()
                if not rows:
                    return await ctx.send("Query returned no rows.")
                preview = "\n".join(str(dict(zip(cols, r))) for r in rows[:15])
                if len(preview) > 1900:
                    preview = preview[:1900] + "\n... (truncated)"
                await ctx.send(f"```\n{preview}\n```")
            else:
                await db.commit()
                await ctx.send(f"✅ Query executed. Rows affected: {cur.rowcount}")
        except Exception as e:
            await ctx.send(f"❌ SQL error: `{e}`")

    async def _backup(self) -> str:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(BACKUP_DIR, f"economy_{timestamp}.db")
        db = await self._db()
        await db.commit()  # flush pending writes first
        shutil.copyfile(DB_PATH, dest)
        return dest

    @commands.command(name="backup")
    @commands.is_owner()
    async def backup(self, ctx: commands.Context):
        """Creates a backup of economy.db."""
        dest = await self._backup()
        await ctx.send(f"💾 Backup created: `{dest}`")

    @commands.command(name="restore")
    @commands.is_owner()
    async def restore(self, ctx: commands.Context, backup: str):
        """Restore economy.db from a backup file in the backups/ folder."""
        path = os.path.join(BACKUP_DIR, backup)
        if not os.path.isfile(path):
            return await ctx.send(f"❌ Backup file not found: `{path}`")

        ok = await self._confirm(
            ctx,
            f"🚨 This will **overwrite the live database** with `{backup}`. "
            "The bot will stop using the DB during restore. Continue?",
        )
        if not ok:
            return

        try:
            db = await self._db()
            await db.commit()
            await db.close()
            shutil.copyfile(path, DB_PATH)
            # Re-open the connection — adjust this to however your bot
            # originally establishes self.bot.db.
            import aiosqlite
            self.bot.db = await aiosqlite.connect(DB_PATH)
            await ctx.send(f"♻️ Database restored from `{backup}`.")
        except Exception as e:
            await ctx.send(f"❌ Restore failed: `{e}`")

    # ==================================================================
    # TESTING
    # ==================================================================
    @commands.command(name="dailyreset")
    @commands.is_owner()
    async def dailyreset(self, ctx: commands.Context):
        """Reset everyone's daily cooldown."""
        db = await self._db()
        await db.execute("UPDATE users SET daily_cd = 0")
        await db.commit()
        await ctx.send("🌅 Reset the daily cooldown for all users.")

    @commands.command(name="cooldowns")
    @commands.is_owner()
    async def cooldowns(self, ctx: commands.Context, user: discord.User = None):
        """View all cooldown values for a user."""
        target = self._resolve_target(ctx, user)
        row = await self._get_row(target.id)
        lines = []
        for c in COOLDOWN_COLUMNS:
            ts = row.get(c, 0)
            status = "Ready" if not ts or ts <= time.time() else f"<t:{int(ts)}:R>"
            lines.append(f"**{c}**: {status}")
        embed = discord.Embed(
            title=f"Cooldowns — {target}",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="forceinterest")
    @commands.is_owner()
    async def forceinterest(self, ctx: commands.Context, rate: float = 0.01):
        """Force bank interest for all users (default 1%)."""
        db = await self._db()
        cur = await db.execute("SELECT user_id, bank FROM users")
        rows = await cur.fetchall()
        await cur.close()
        for user_id, bank in rows:
            gain = int(bank * rate)
            if gain > 0:
                await db.execute(
                    "UPDATE users SET bank = bank + ? WHERE user_id = ?", (gain, user_id)
                )
        await db.commit()
        await ctx.send(f"🏦 Forced interest at {rate*100:.2f}% for {len(rows)} user(s).")

    @commands.command(name="forcesave")
    @commands.is_owner()
    async def forcesave(self, ctx: commands.Context):
        """Force a database commit/save."""
        db = await self._db()
        await db.commit()
        await ctx.send("💾 Database save forced (committed).")


async def setup(bot: commands.Bot):
    await bot.add_cog(Owner(bot))
