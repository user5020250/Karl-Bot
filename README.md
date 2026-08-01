# Moderation Bot

A Discord moderation bot built with discord.py 2.x and slash (application) commands. Ready to push to GitHub and deploy on Railway.

## Project layout

```
discord-bot/
├── main.py            entry point, loads all cogs and syncs slash commands
├── helpers.py          shared embed/logging helpers (all embeds are black)
├── storage.py           JSON file-backed storage for settings and history
├── requirements.txt
├── Procfile              tells Railway how to start the bot
├── railway.toml           Railway build/deploy config
├── .env.example
├── .gitignore
└── cogs/
    ├── moderation.py     ban, tempban, softban, unban, kick, timeout, untimeout, history
    ├── messages.py        clear, purge (user/bots/links/invites/images/embeds/files/mentions/contains)
    ├── channels.py         lock, unlock, slowmode, clone, nuke, archive, renamechannel
    ├── voice.py             voicekick, move, moveall, mutevoice, unmutevoice, deafen, undeafen
    ├── roles.py              addrole, removerole, nickname
    ├── automod.py             automod, antispam, antilink, antiinvite, antimention, antiraid,
    │                           antibot, antiemoji, antigif, duplicatefilter, capsfilter,
    │                           profanity, whitelist, blacklist, ignore (+ enforcement listeners)
    ├── server.py              lockdown, unlockdown, maintenance, verify, unverify, setverifyrole,
    │                           autorole, welcome, goodbye, logs
    ├── modlogs.py              modlogs, exportlogs
    ├── utility.py               say, embed, announce, poll, reactionrole, sticky, pin, unpin
    ├── info.py                   userinfo, avatar, banner, roles, permissions, joined, created,
    │                              serverinfo, channelinfo, roleinfo
    ├── afk.py                     afk
    └── jail.py                     setjail, jail, unjail
```

All embeds use a black color and every response is in English, with no emojis anywhere in command output.

## 1. Create the bot application

1. Go to https://discord.com/developers/applications and create a New Application.
2. Under **Bot**, click **Add Bot**, then copy the **Token** — you'll need it as `DISCORD_TOKEN`.
3. Under **Bot**, enable these **Privileged Gateway Intents**:
   - Server Members Intent
   - Message Content Intent
4. Under **OAuth2 → URL Generator**, select the `bot` and `applications.commands` scopes, then pick these bot permissions (or just Administrator for simplicity):
   - Ban Members, Kick Members, Moderate Members, Manage Messages, Manage Channels,
     Move Members, Mute Members, Deafen Members, Manage Roles, Manage Nicknames,
     Manage Guild, View Audit Log, Mention Everyone, Read Message History, Send Messages,
     Embed Links, Attach Files, Add Reactions
5. Open the generated URL and invite the bot to your server.

## 2. Run locally

```bash
git clone <your-repo-url>
cd discord-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and paste your bot token
python main.py
```

Slash commands are synced automatically on startup (`bot.tree.sync()` in `main.py`). It can take up to an hour for global commands to fully propagate the first time; if you want instant updates while developing, sync to a single guild instead (see the comment in `main.py`'s `setup_hook`).

## 3. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

`.env` and `data.json` are already excluded via `.gitignore` so your token and local data never get committed.

## 4. Deploy on Railway

1. Go to https://railway.app, create a New Project, and choose **Deploy from GitHub repo**.
2. Select the repository you just pushed.
3. Railway will detect `railway.toml` and `Procfile` and use `python main.py` as the start command automatically (Nixpacks builder).
4. Open the service's **Variables** tab and add:
   - `DISCORD_TOKEN` — your bot token
   - `BOT_PREFIX` — optional, defaults to `!` (slash commands don't need this, it's only for any future prefix commands)
5. Deploy. Check the **Deploy Logs** tab for `Logged in as ...` to confirm it connected.

### Persisting data across deploys

This bot stores settings and moderation history in a local `data.json` file (see `storage.py`). Railway's default filesystem is ephemeral and resets on every redeploy. To keep data:
- Attach a **Railway Volume** to the service and mount it at the project's working directory, or
- Swap `storage.py` for a real database (Postgres/Redis) — Railway can provision either with one click.

## Notes and limitations

- `/tempban` schedules the unban with an in-memory timer; if the bot restarts before the timer fires, the member will stay banned until manually unbanned with `/unban`. For guaranteed persistence across restarts, back this with a database and a startup reconciliation job.
- `/antiraid` currently posts an alert to the configured log channel rather than automatically locking the server; pair it with `/lockdown` if you want to act on the alert.
- Anti-spam, anti-emoji, and duplicate-message tracking are kept in memory per running process, so they reset on restart/redeploy.
- Set your log channel with `/logs` so moderation actions and AutoMod deletions are recorded somewhere.
- Configure `/setjail` and `/setverifyrole` before using `/jail`, `/unjail`, `/verify`, and `/unverify`.

## Original command reference

| Command          | Description                                                      | Required Permission |
| ---------------- | ------------------------------------------------------------------ | ------------------- |
| `/ban`           | Permanently bans a member.                                       | Ban Members         |
| `/tempban`       | Bans a member for a specified duration.                          | Ban Members         |
| `/softban`       | Bans then immediately unbans a member to delete recent messages. | Ban Members         |
| `/unban`         | Unbans a member.                                                 | Ban Members         |
| `/kick`          | Kicks a member from the server.                                  | Kick Members        |
| `/timeout`       | Times out a member.                                              | Moderate Members    |
| `/untimeout`     | Removes a timeout.                                               | Moderate Members    |
| `/history`       | Displays a member's moderation history.                          | Moderate Members    |
| `/clear`          | Deletes recent messages.               | Manage Messages     |
| `/purge user`     | Deletes messages from a specific user. | Manage Messages     |
| `/purge bots`     | Deletes bot messages.                  | Manage Messages     |
| `/purge links`    | Deletes messages containing links.     | Manage Messages     |
| `/purge invites`  | Deletes Discord invite links.          | Manage Messages     |
| `/purge images`   | Deletes image messages.                | Manage Messages     |
| `/purge embeds`   | Deletes embedded messages.             | Manage Messages     |
| `/purge files`    | Deletes messages with attachments.     | Manage Messages     |
| `/purge mentions` | Deletes messages containing mentions.  | Manage Messages     |
| `/purge contains` | Deletes messages containing text.      | Manage Messages     |
| `/lock`          | Locks a channel.                                | Manage Channels     |
| `/unlock`        | Unlocks a channel.                              | Manage Channels     |
| `/slowmode`      | Sets channel slowmode.                          | Manage Channels     |
| `/clone`         | Clones a channel.                               | Manage Channels     |
| `/nuke`          | Deletes all messages by recreating the channel. | Manage Channels     |
| `/archive`       | Archives a channel.                             | Manage Channels     |
| `/renamechannel` | Renames a channel.                              | Manage Channels     |
| `/voicekick`   | Disconnects a user from voice.     | Move Members        |
| `/move`        | Moves a member.                    | Move Members        |
| `/moveall`     | Moves everyone in a voice channel. | Move Members        |
| `/mutevoice`   | Server mutes a member.             | Mute Members        |
| `/unmutevoice` | Removes server mute.               | Mute Members        |
| `/deafen`      | Server deafens a member.           | Deafen Members      |
| `/undeafen`    | Removes server deafening.          | Deafen Members      |
| `/addrole`    | Gives a role.           | Manage Roles        |
| `/removerole` | Removes a role.         | Manage Roles        |
| `/nickname`   | Changes nickname.       | Manage Nicknames    |
| `/automod`         | Configure AutoMod.               | Administrator       |
| `/antispam`        | Anti-spam settings.              | Administrator       |
| `/antilink`        | Anti-link settings.              | Administrator       |
| `/antiinvite`      | Block Discord invites.           | Administrator       |
| `/antimention`     | Limit mass mentions.             | Administrator       |
| `/antiraid`        | Raid protection.                 | Administrator       |
| `/antibot`         | Prevent unauthorized bot joins.  | Administrator       |
| `/antiemoji`       | Limit emoji spam.                | Administrator       |
| `/antigif`         | Block GIF spam.                  | Administrator       |
| `/duplicatefilter` | Remove duplicate messages.       | Administrator       |
| `/capsfilter`      | Limit excessive capital letters. | Administrator       |
| `/profanity`       | Manage blocked words.            | Administrator       |
| `/whitelist`       | Whitelist users or roles.        | Administrator       |
| `/blacklist`       | Blacklist users or roles.        | Administrator       |
| `/ignore`          | Ignore channels or roles.        | Administrator       |
| `/lockdown`    | Lock every channel.         | Administrator       |
| `/unlockdown`  | End lockdown.               | Administrator       |
| `/maintenance` | Toggle maintenance mode.    | Administrator       |
| `/verify`      | Verify a member.            | Manage Roles        |
| `/unverify`    | Remove verification.        | Manage Roles        |
| `/autorole`    | Configure automatic roles.  | Manage Roles        |
| `/welcome`     | Configure welcome messages. | Manage Server       |
| `/goodbye`     | Configure leave messages.   | Manage Server       |
| `/logs`        | Configure log channels.     | Manage Server       |
| `/modlogs`    | View moderation logs.        | View Audit Log      |
| `/exportlogs` | Export moderation logs.      | Administrator       |
| `/say`          | Sends a message as the bot.                   | Manage Messages     |
| `/embed`        | Sends a custom embed.                         | Manage Messages     |
| `/announce`     | Posts an announcement.                        | Manage Messages     |
| `/poll`         | Creates a poll.                               | Manage Messages     |
| `/reactionrole` | Creates a reaction role message.              | Manage Roles        |
| `/sticky`       | Pins a message to the bottom by reposting it. | Manage Messages     |
| `/pin`          | Pins a message.                               | Manage Messages     |
| `/unpin`        | Unpins a message.                             | Manage Messages     |
| `/userinfo`    | View member information.                | None                |
| `/avatar`      | Display a user's avatar.                | None                |
| `/banner`      | Display a user's banner.                | None                |
| `/roles`       | View a member's roles.                  | None                |
| `/permissions` | View a member's permissions.            | None                |
| `/joined`      | See when a member joined.               | None                |
| `/created`     | See when a Discord account was created. | None                |
| `/serverinfo`  | View server information.                | None                |
| `/channelinfo` | View channel information.               | None                |
| `/roleinfo`    | View role information.                  | None                |
| `/afk`  | Sets your AFK status with an optional reason. Automatically cleared when you next send a message. | None |
| `/jail` / `/unjail` | Move users into a restricted "jail" role and channel. | Moderate Members |
