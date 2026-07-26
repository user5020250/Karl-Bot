"""
cogs/owner.py
-------------
Owner-only administration cog.

This version is written against your actual `Database` class in
database.py (not raw SQL against assumed columns), so it uses:

- self.bot.db                -> the Database instance (has .conn, .path)
- db.get_user(user_id)       -> aiosqlite.Row from `users`
- db.add_balance / add_bank / add_bank_capacity(user_id, amount)
- db.set_field(user_id, field, value)
- db.increment_field(user_id, field, amount)
- db.get_all_cooldowns(user_id) -> rows of (command, expires_at)
- db.unlock_title / get_titles(user_id)
- db.get_unlocked_achievements(user_id)
- db.get_pets(user_id)
- db.fetchall / fetchone / execute  (generic, still available for raw SQL)

Real schema notes (from your database.py):
- XP is stored as `exp`, not `xp`.
- Command usage is `total_commands`, not `commands_used`.
- There is NO single `stats` JSON blob — "stats" are spread across
  lifetime_earned, total_commands, work_count, gambling_won/lost/count,
  has_gone_bankrupt, plus the separate `gambling_stats` table.
- There is NO cooldown column on `users` — cooldowns live in their own
  `cooldowns` table, keyed by (user_id, command), storing an absolute
  `expires_at` unix timestamp.
- Achievements live in `achievements_unlocked`, titles in
  `titles_unlocked` — not JSON blobs on `users`.
- `job` on `users` is just a text label; actual job *slots* live in the
  per-guild `jobs` table. Resetting a user's job here does not release
  a slot back to a specific guild's job pool (there's no guild context
  on the user row) — flagged below where relevant.

If checks.py has its own owner-check decorator you use elsewhere, swap
it in for @commands.is_owner() for consistency — behavior is the same
either way here.
"""

import os
import shutil
import time
from datetime import datetime

import discord
from discord.ext import commands

import config


def fmt_money(n: int) -> str:
    return f"₱{n:,}"


def fmt_ts(expires_at: float) -> str:
    remaining = expires_at - time.time()
    if remaining <= 0:
        return "Ready"
    return f"<t:{int(expires_at)}:R>"


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

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    @property
    def db(self):
        return self.bot.db  # Database instance

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
        """Give cash to yourself or another user. Does not count toward
        lifetime_earned (that's reserved for actual income sources)."""
        target = self._resolve_target(ctx, user)
        if amount <= 0:
            return await ctx.send("Amount must be positive.")
        await self.db.add_balance(target.id, amount)
        await ctx.send(f"💸 Gave {fmt_money(amount)} to **{target}**.")

    @commands.command(name="take")
    @commands.is_owner()
    async def take(self, ctx: commands.Context, amount: int, user: discord.User):
        """Remove cash from a user (floors at 0)."""
        if amount <= 0:
            return await ctx.send("Amount must be positive.")
        row = await self.db.get_user(user.id)
        new_bal = max(0, row["balance"] - amount)
        await self.db.set_field(user.id, "balance", new_bal)
        await ctx.send(f"🧹 Took {fmt_money(amount)} from **{user}**. New balance: {fmt_money(new_bal)}")

    @commands.command(name="setbal")
    @commands.is_owner()
    async def setbal(self, ctx: commands.Context, amount: int, user: discord.User = None):
        """Set a user's cash balance."""
        target = self._resolve_target(ctx, user)
        if amount < 0:
            return await ctx.send("Amount cannot be negative.")
        await self.db.set_field(target.id, "balance", amount)
        await ctx.send(f"⚙️ Set **{target}**'s balance to {fmt_money(amount)}.")

    @commands.command(name="addbal")
    @commands.is_owner()
    async def addbal(self, ctx: commands.Context, amount: int, user: discord.User = None):
        """Add cash without replacing the balance."""
        target = self._resolve_target(ctx, user)
        await self.db.add_balance(target.id, amount)
        await ctx.send(f"➕ Added {fmt_money(amount)} to **{target}**'s balance.")

    @commands.command(name="setbank")
    @commands.is_owner()
    async def setbank(self, ctx: commands.Context, amount: int, user: discord.User = None):
        """Set a user's bank balance."""
        target = self._resolve_target(ctx, user)
        if amount < 0:
            return await ctx.send("Amount cannot be negative.")
        await self.db.set_field(target.id, "bank", amount)
        await ctx.send(f"⚙️ Set **{target}**'s bank balance to {fmt_money(amount)}.")

    @commands.command(name="addbank")
    @commands.is_owner()
    async def addbank(self, ctx: commands.Context, amount: int, user: discord.User = None):
        """Add money directly to the bank."""
        target = self._resolve_target(ctx, user)
        await self.db.add_bank(target.id, amount)
        await ctx.send(f"🏦 Added {fmt_money(amount)} to **{target}**'s bank.")

    @commands.command(name="setbankcap")
    @commands.is_owner()
    async def setbankcap(self, ctx: commands.Context, amount: int, user: discord.User = None):
        """Set a user's bank capacity."""
        target = self._resolve_target(ctx, user)
        if amount < 0:
            return await ctx.send("Amount cannot be negative.")
        await self.db.set_field(target.id, "bank_capacity", amount)
        await ctx.send(f"⚙️ Set **{target}**'s bank capacity to {fmt_money(amount)}.")

    @commands.command(name="addbankcap")
    @commands.is_owner()
    async def addbankcap(self, ctx: commands.Context, amount: int, user: discord.User = None):
        """Increase bank capacity."""
        target = self._resolve_target(ctx, user)
        await self.db.add_bank_capacity(target.id, amount)
        await ctx.send(f"📈 Increased **{target}**'s bank capacity by {fmt_money(amount)}.")

    # ==================================================================
    # PROGRESSION
    # ==================================================================
    @commands.command(name="setlevel")
    @commands.is_owner()
    async def setlevel(self, ctx: commands.Context, level: int, user: discord.User = None):
        target = self._resolve_target(ctx, user)
        if level < 1:
            return await ctx.send("Level must be at least 1.")
        await self.db.set_field(target.id, "level", level)
        await ctx.send(f"⚙️ Set **{target}**'s level to {level}.")

    @commands.command(name="setxp")
    @commands.is_owner()
    async def setxp(self, ctx: commands.Context, xp: int, user: discord.User = None):
        target = self._resolve_target(ctx, user)
        if xp < 0:
            return await ctx.send("XP cannot be negative.")
        await self.db.set_field(target.id, "exp", xp)
        await ctx.send(f"⚙️ Set **{target}**'s XP to {xp:,}.")

    @commands.command(name="addxp")
    @commands.is_owner()
    async def addxp(self, ctx: commands.Context, xp: int, user: discord.User = None):
        target = self._resolve_target(ctx, user)
        await self.db.increment_field(target.id, "exp", xp)
        await ctx.send(f"➕ Added {xp:,} XP to **{target}**.")

    @commands.command(name="setprestige")
    @commands.is_owner()
    async def setprestige(self, ctx: commands.Context, level: int, user: discord.User = None):
        target = self._resolve_target(ctx, user)
        if level < 0:
            return await ctx.send("Prestige cannot be negative.")
        await self.db.set_field(target.id, "prestige", level)
        await ctx.send(f"⚙️ Set **{target}**'s prestige to {level}.")

    @commands.command(name="settitle")
    @commands.is_owner()
    async def settitle(self, ctx: commands.Context, title: str, user: discord.User = None):
        """Sets the user's active title, and also registers it as unlocked."""
        target = self._resolve_target(ctx, user)
        await self.db.set_field(target.id, "title", title)
        await self.db.unlock_title(target.id, title)
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
        """Clears every row in the `cooldowns` table for this user."""
        target = self._resolve_target(ctx, user)
        await self.db.execute("DELETE FROM cooldowns WHERE user_id = ?", (target.id,))
        await ctx.send(f"⏱️ Reset all cooldowns for **{target}**.")

    @reset.command(name="economy")
    @commands.is_owner()
    async def reset_economy(self, ctx: commands.Context, user: discord.User = None):
        """Resets cash, bank, capacity, prestige, level, XP, title, job,
        lifetime stats, and cooldowns. Achievement/title unlock history and
        pets are left alone (use the other reset subcommands / bank on
        !reset all for those)."""
        target = self._resolve_target(ctx, user)
        ok = await self._confirm(
            ctx, f"⚠️ This will reset **all economy data** for {target}. Continue?"
        )
        if not ok:
            return

        await self.db.execute(
            "UPDATE users SET balance = 0, bank = 0, bank_capacity = ?, "
            "lifetime_earned = 0, exp = 0, level = 1, prestige = 0, title = NULL, "
            "job = NULL, total_commands = 0, work_count = 0, gambling_won = 0, "
            "gambling_lost = 0, gambling_count = 0, has_gone_bankrupt = 0 "
            "WHERE user_id = ?",
            (config.BANK_STARTING_CAPACITY, target.id),
        )
        await self.db.execute("DELETE FROM cooldowns WHERE user_id = ?", (target.id,))
        await self.db.execute("DELETE FROM gambling_stats WHERE user_id = ?", (target.id,))
        await ctx.send(f"♻️ Economy data reset for **{target}**.")

    @reset.command(name="achievements")
    @commands.is_owner()
    async def reset_achievements(self, ctx: commands.Context, user: discord.User = None):
        target = self._resolve_target(ctx, user)
        await self.db.execute(
            "DELETE FROM achievements_unlocked WHERE user_id = ?", (target.id,)
        )
        await ctx.send(f"🏆 Cleared achievements for **{target}**.")

    @reset.command(name="stats")
    @commands.is_owner()
    async def reset_stats(self, ctx: commands.Context, user: discord.User = None):
        """Zeroes lifetime_earned, total_commands, work_count, and gambling
        counters, and clears per-game gambling_stats rows."""
        target = self._resolve_target(ctx, user)
        await self.db.execute(
            "UPDATE users SET lifetime_earned = 0, total_commands = 0, work_count = 0, "
            "gambling_won = 0, gambling_lost = 0, gambling_count = 0, has_gone_bankrupt = 0 "
            "WHERE user_id = ?",
            (target.id,),
        )
        await self.db.execute("DELETE FROM gambling_stats WHERE user_id = ?", (target.id,))
        await ctx.send(f"📊 Cleared stats for **{target}**.")

    @reset.command(name="all")
    @commands.is_owner()
    async def reset_all(self, ctx: commands.Context, user: discord.User = None):
        """Completely wipes a player's data across every table: users row,
        cooldowns, gambling_stats, achievements_unlocked, titles_unlocked,
        and pets. Recreates a fresh default row afterward.

        Note: this does not release job slots in the per-guild `jobs`
        table, since the user row doesn't track which guild's job they
        held — the slot will simply free up next scheduled refresh."""
        target = self._resolve_target(ctx, user)
        ok = await self._confirm(
            ctx, f"🚨 This will **completely wipe** all data for {target}. This cannot be undone. Continue?"
        )
        if not ok:
            return

        for table in (
            "cooldowns", "gambling_stats", "achievements_unlocked",
            "titles_unlocked", "pets",
        ):
            id_col = "owner_id" if table == "pets" else "user_id"
            await self.db.execute(f"DELETE FROM {table} WHERE {id_col} = ?", (target.id,))

        await self.db.execute("DELETE FROM users WHERE user_id = ?", (target.id,))
        await self.db.ensure_user(target.id)
        await ctx.send(f"🗑️ **{target}**'s data has been completely wiped and reset to defaults.")

    # ==================================================================
    # INFORMATION
    # ==================================================================
    @commands.command(name="userinfo")
    @commands.is_owner()
    async def userinfo(self, ctx: commands.Context, user: discord.User = None):
        """Shows every database field for a user."""
        target = self._resolve_target(ctx, user)
        row = await self.db.get_user(target.id)
        titles = await self.db.get_titles(target.id)
        achievements = await self.db.get_unlocked_achievements(target.id)
        cooldowns = await self.db.get_all_cooldowns(target.id)
        pets = await self.db.get_pets(target.id)

        lines = [
            f"ID: {row['user_id']}",
            f"Balance: {fmt_money(row['balance'])}",
            f"Bank: {fmt_money(row['bank'])}",
            f"Capacity: {fmt_money(row['bank_capacity'])}",
            f"Lifetime Earned: {fmt_money(row['lifetime_earned'])}",
            f"Prestige: {row['prestige']}",
            f"Level: {row['level']}",
            f"XP: {row['exp']:,}",
            f"Job: {row['job'] or 'Unemployed'}",
            f"Title: {row['title'] or 'None'}",
            f"Titles Unlocked: {len(titles)}",
            f"Commands Used: {row['total_commands']:,}",
            f"Work Count: {row['work_count']:,}",
            f"Gambling: {row['gambling_won']:,} won / {row['gambling_lost']:,} lost "
            f"across {row['gambling_count']:,} plays",
            f"Has Gone Bankrupt: {'Yes' if row['has_gone_bankrupt'] else 'No'}",
            f"Achievements Unlocked: {len(achievements)}",
            f"Active Pets: {len(pets)}",
            f"Active Cooldowns: {len(cooldowns)}",
        ]

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
            await self.bot.reload_extension(f"cogs.{cog}" if "." not in cog else cog)
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
            await self.bot.load_extension(f"cogs.{cog}" if "." not in cog else cog)
            await ctx.send(f"📦 Loaded `{cog}`.")
        except Exception as e:
            await ctx.send(f"❌ Failed to load `{cog}`: `{e}`")

    @commands.command(name="unload")
    @commands.is_owner()
    async def unload(self, ctx: commands.Context, cog: str):
        try:
            await self.bot.unload_extension(f"cogs.{cog}" if "." not in cog else cog)
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
        """Execute raw SQL directly against self.bot.db.conn.
        Auto-backs up before any non-SELECT statement."""
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
            cur = await self.db.conn.execute(query)
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
                await self.db.conn.commit()
                await ctx.send(f"✅ Query executed. Rows affected: {cur.rowcount}")
        except Exception as e:
            await ctx.send(f"❌ SQL error: `{e}`")

    async def _backup(self) -> str:
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(backup_dir, f"economy_{timestamp}.db")
        await self.db.conn.commit()  # flush pending writes first
        shutil.copyfile(self.db.path, dest)
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
        path = os.path.join("backups", backup)
        if not os.path.isfile(path):
            return await ctx.send(f"❌ Backup file not found: `{path}`")

        ok = await self._confirm(
            ctx,
            f"🚨 This will **overwrite the live database** with `{backup}`. "
            "Continue?",
        )
        if not ok:
            return

        try:
            await self.db.close()
            shutil.copyfile(path, self.db.path)
            await self.db.connect()  # reopens self.bot.db.conn, reruns schema/migrations
            await ctx.send(f"♻️ Database restored from `{backup}`.")
        except Exception as e:
            await ctx.send(f"❌ Restore failed: `{e}`")

    # ==================================================================
    # TESTING
    # ==================================================================
    @commands.command(name="dailyreset")
    @commands.is_owner()
    async def dailyreset(self, ctx: commands.Context):
        """Reset everyone's `daily` cooldown (cooldowns table, command='daily').
        Adjust the command name below if your daily command is registered
        under a different `command` string when calling db.set_cooldown()."""
        await self.db.execute("DELETE FROM cooldowns WHERE command = ?", ("daily",))
        await ctx.send("🌅 Reset the daily cooldown for all users.")

    @commands.command(name="cooldowns")
    @commands.is_owner()
    async def cooldowns(self, ctx: commands.Context, user: discord.User = None):
        """View all active cooldowns for a user."""
        target = self._resolve_target(ctx, user)
        rows = await self.db.get_all_cooldowns(target.id)
        if not rows:
            return await ctx.send(f"**{target}** has no active cooldowns.")
        lines = [f"**{r['command']}**: {fmt_ts(r['expires_at'])}" for r in rows]
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
        rows = await self.db.fetchall("SELECT user_id, bank FROM users")
        count = 0
        for row in rows:
            gain = int(row["bank"] * rate)
            if gain > 0:
                await self.db.add_bank(row["user_id"], gain)
                count += 1
        await ctx.send(f"🏦 Forced interest at {rate*100:.2f}% for {count} user(s) with a positive bank balance.")

    @commands.command(name="forcesave")
    @commands.is_owner()
    async def forcesave(self, ctx: commands.Context):
        """Force a database commit. Note: db.execute() already commits
        after every call, so this is mainly useful if you've made changes
        directly via self.bot.db.conn without going through the wrapper."""
        await self.db.conn.commit()
        await ctx.send("💾 Database save forced (committed).")


async def setup(bot: commands.Bot):
    await bot.add_cog(Owner(bot))
