# EconoBot

A Discord economy bot built with `discord.py` (slash commands only), SQLite, and designed to run on Railway.

All responses are black embeds with bold titles, no emojis, and numeric values in backticks, per spec.

## Commands

**Social** — `/help` `/profile` `/leaderboard` `/achievements` `/balance` `/give` `/rob`
**Rewards** — `/daily` `/weekly` `/monthly` `/yearly`
**Work & Side Hustles** — `/jobs` `/job apply` `/job resign` `/work` `/overtime` `/beg` `/cook` `/fish` `/farm` `/harvest`
**Bank** — `/deposit` `/withdraw` `/interest` `/bank upg`
**Gambling** — `/scatter` `/colorgame` `/tongits` `/sabong`
**Pets** — `/petshop` `/adopt` `/pet rename` `/pet disowned` `/feed` `/play`
**Prestige** — `/prestige`
**Events** — `/event setchannel` `/claim`

> `/cooldown` was removed as a standalone command — all active/available
> cooldowns are now shown in `/profile`'s **Cooldowns** dropdown, alongside
> **Pets**, **Achievements**, and **Gambling** breakdowns.
>
> `/pet name` was removed since `/adopt <species> <name>` already names a pet
> at adoption time; `/pet rename` remains for renaming later.
>
> `/work` now requires an active job (`/job apply`) before it can be used.

> Note: Discord does not allow a command to be both standalone (`/work`) and a
> parent of subcommands at the same time. Job applications were therefore
> implemented as `/job apply` / `/job resign` rather than `/work apply` /
> `/work resign`, so `/work` can remain the plain income command.

## Project structure

```
econobot/
├── main.py              # entry point, loads cogs, syncs slash commands
├── config.py             # env vars + all tunable economy numbers
├── database.py            # aiosqlite schema + query helpers
├── cogs/                   # one file per category
├── utils/                   # embeds, cooldowns, achievements, economy math
├── data/                     # jobs.json, pets.json, achievements.json
├── requirements.txt
├── Procfile
├── railway.json
└── .env.example
```

## 1. Local setup

```bash
git clone <your-repo-url>
cd econobot
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `DISCORD_TOKEN` to your bot's token from the
[Discord Developer Portal](https://discord.com/developers/applications).

When creating the bot in the Developer Portal:
- Under **Bot**, no privileged intents are required (the bot only uses slash commands).
- Under **OAuth2 → URL Generator**, select the `bot` and `applications.commands`
  scopes, and at minimum the `Send Messages` and `Embed Links` permissions, then
  use the generated URL to invite the bot to your server.

Run it:

```bash
python main.py
```

Slash commands sync globally on startup, which can take up to an hour to
propagate the first time. For instant testing, temporarily sync to a single
guild instead (see the `discord.py` docs on `CommandTree.copy_global_to`).

## 2. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

`.env` and the local `data/database.db` file are already git-ignored, so your
token and local save data won't be committed.

## 3. Deploy on Railway

1. Go to [railway.app](https://railway.app) and create a **New Project → Deploy from GitHub repo**, selecting the repo you just pushed.
2. Railway will detect `requirements.txt` and `railway.json` and build automatically (Nixpacks).
3. Open the service's **Variables** tab and add:
   - `DISCORD_TOKEN` = your bot token
   - `DB_PATH` = `/data/database.db`
4. **Attach a Volume** (Service → Settings → Volumes → New Volume), mount it at
   `/data`. This is required — without it, SQLite's file is wiped every time
   Railway redeploys or restarts the container, and all balances/pets/progress
   would be lost.
5. Deploy. Check the **Deploy Logs** for `Synced N application commands` and
   `Logged in as ...` to confirm the bot is online.

## Notes on game design choices

- **Bank capacity** is no longer tied to player level. Every user starts at
  `config.BANK_STARTING_CAPACITY` (₱500,000). Capacity only grows through
  `/bank upg` (+`BANK_UPG_CAPACITY_INCREASE` per purchase) and automatically
  on every prestige (+`BANK_CAPACITY_PRESTIGE_INCREASE`). It never resets.
  `/deposit` and `/withdraw` accept any amount you actually have — the only
  cap is how much room is left in your bank.
- **Prestige & bank upgrades share one price ladder** (`tier_cost` in
  `utils/economy.py`): tier 0→1 costs ₱1,000,000, then ₱5,000,000 × tier
  for every tier after (₱1m, ₱5m, ₱10m, ₱15m, ...). Prestiging only ever
  requires money (net worth = cash + bank).
- **Prestige** resets `balance` to `0` (any cash not spent on the prestige
  cost is lost) but never touches `bank` (beyond what's needed to cover the
  cost) or `level`/`exp`.
- **Leveling/EXP**: every command grants exp (`config.EXP_PER_COMMAND`),
  boosted by `config.EXP_PET_BONUS_PER_PET` for each pet you own. Leveling
  has no cap — `/profile`'s **Main** section shows a progress bar toward the
  next level.
- **Amounts as text**: any command that takes a money amount (`/deposit`,
  `/withdraw`, `/give`, gambling bets, etc.) accepts plain numbers, `k`/`m`/
  `b`/`t` suffixes (`1k`, `2.5m`, `1b`, `1t`), or `all` (see
  `utils/parsing.py`).
- **Pets**: hunger decays over time based on `last_fed`; a pet not fed for
  `DEATH_DAYS` (7, in `cogs/pets.py`) dies. Feeding fully restores hunger.
- **Jobs**: stock (open positions) resets to max every 30 minutes via a
  background task; applying consumes a slot, resigning frees one. `/work`
  now requires an active job.
- **Gambling stats** are tracked per game (`gambling_stats` table) in
  addition to the lifetime totals on the user row, so `/profile`'s
  **Gambling** section can break down earned/lost/used per command.
- **Achievements**: "Reach" achievements check net worth (cash + bank);
  "Earn" achievements check lifetime earnings so they can't be re-triggered
  by giving money back and forth.
- **Events**: spawn on a randomized interval/chance in the configured channel
  with weighted rarity (Jackpot Event is rarest). `/claim` is a race —
  whoever runs it first while the event is active wins.

All numeric tuning (reward ranges, cooldown lengths, rob odds, tier prices,
exp rates, etc.) lives in `config.py` so you can rebalance the economy
without touching command logic.
