# CLAUDE.md — TikTok Discord Bot

## Project Overview

This is a Discord bot written in Python that monitors a TikTok user's account and provides Discord server members with status, monitoring, and download helper commands. It is designed to be deployed on [Railway](https://railway.app).

---

## Repository Structure

```
tiktok-bot/
├── bot.py            # Main bot entry point — all logic lives here
├── requirements.txt  # Python dependencies (discord.py, aiohttp)
├── Procfile          # Railway/Heroku process definition
└── README.md         # Minimal project readme
```

The project is intentionally small and single-file. All bot logic, commands, and the background polling task are in `bot.py`.

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3 |
| Discord library | discord.py 2.3.2 |
| HTTP client | aiohttp 3.9.1 |
| Deployment platform | Railway (via `Procfile`) |
| Process type | `web` (runs `python bot.py`) |

---

## Key Files

### `bot.py`
The sole source file. Contains:
- **Bot setup** (`discord.Intents`, `commands.Bot`) with prefix `!`
- **Environment variable loading** for `DISCORD_TOKEN`, `CHANNEL_ID`, `TIKTOK_USERNAME`
- **`on_ready` event** — prints startup info and starts the background task
- **`check_tiktok` task** — polls every 5 minutes (`@tasks.loop(minutes=5)`); currently logs a check but does not yet scrape TikTok
- **Commands**: `!status`, `!ping`, `!download <url>`, `!setuser <username>`

### `requirements.txt`
```
discord.py==2.3.2
aiohttp==3.9.1
```
Pin versions when adding new dependencies.

### `Procfile`
```
web: python bot.py
```
Railway reads this to start the process. The `web` dyno type is used; if Railway prompts for a worker type, consider using `worker` instead if the bot does not serve HTTP traffic.

---

## Environment Variables

These must be set in the Railway dashboard (or local `.env` for development):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_TOKEN` | **Yes** | — | Discord bot token from the Developer Portal |
| `CHANNEL_ID` | **Yes** | `0` | Discord channel ID where notifications are sent |
| `TIKTOK_USERNAME` | No | `charlidamelio` | TikTok username to monitor (without `@`) |

The bot will refuse to start (`if not TOKEN`) if `DISCORD_TOKEN` is missing.

---

## Bot Commands

All commands use the `!` prefix.

| Command | Arguments | Description |
|---------|-----------|-------------|
| `!status` | — | Reports bot status, watched TikTok user, and check interval |
| `!ping` | — | Liveness check; replies with "Pong!" |
| `!download <url>` | TikTok URL | Provides links to third-party download services |
| `!setuser <username>` | TikTok handle | Changes the monitored account at runtime (not persisted) |

---

## Architecture & Design Notes

- **Single-file design**: All logic is in `bot.py`. Keep it this way unless complexity demands splitting into cogs.
- **Global mutable state**: `TIKTOK_USER` is a global variable mutated by `!setuser`. `last_video` is declared but currently unused — it is reserved to track the most recently seen TikTok video ID to avoid duplicate notifications.
- **Background task**: `check_tiktok` uses `discord.ext.tasks`. It starts inside `on_ready` to ensure the bot is connected before polling begins.
- **TikTok scraping is a stub**: The `check_tiktok` function currently only logs; actual TikTok fetching is not implemented. When implementing, add the logic inside this function and use `last_video` to deduplicate.
- **No database**: State is in-memory only. Restarting the bot resets `TIKTOK_USER` and `last_video`.
- **No HTTP server**: Despite the `web` Procfile type, the bot does not serve HTTP. Railway may require a keep-alive mechanism or switching to `worker` type to avoid sleep.

---

## Development Workflow

### Local Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set environment variables:
   ```bash
   export DISCORD_TOKEN="your-token"
   export CHANNEL_ID="your-channel-id"
   export TIKTOK_USERNAME="target-username"
   ```
3. Run the bot:
   ```bash
   python bot.py
   ```

### Deployment (Railway)

1. Push code to the `master` branch.
2. Set environment variables in the Railway dashboard.
3. Railway will automatically detect the `Procfile` and start `python bot.py`.

---

## Conventions & Guidelines for AI Assistants

- **Do not add external dependencies** without updating `requirements.txt` with pinned versions.
- **Preserve the single-file structure** unless a refactor to Discord cogs is explicitly requested.
- **Environment variables** must never be hardcoded into source files.
- **`last_video`** is a reserved global for deduplication tracking; implement TikTok scraping around this variable.
- **Error handling**: The `check_tiktok` task already wraps its body in `try/except`. Maintain this pattern for any background task additions.
- **Command prefix** is `!` — do not change it without updating all documentation and user-facing strings.
- **`setuser` changes are runtime-only** — changes are lost on restart. If persistence is needed, use an environment variable update via the Railway API or add a config file.
- **No tests exist** in this repository. If adding tests, use `pytest` and add it to `requirements.txt`.
- **Python version**: The codebase assumes Python 3.8+ (required by discord.py 2.x).

---

## Known Limitations & TODOs

- `check_tiktok` does not actually fetch TikTok data — this is the primary feature stub to implement.
- `last_video` is unused; it should track the latest video ID and trigger Discord notifications on new posts.
- `!setuser` changes do not persist across restarts.
- No rate-limit handling for Discord API calls inside the background task.
- The `web` process type in Procfile may cause Railway to expect HTTP responses; switching to `worker` may be appropriate.
