# Clip Bot

Telegram bots that watch TikTok clipper accounts and repost every new clip to Telegram channels, with a caption rewritten in your house style.

- **Several clients, one process.** Each client gets its own Telegram bot, channels, caption style and admins.
- **Any number of accounts per channel.** The same TikTok account can feed several channels or clients, and each video is downloaded only once.
- **No flooding.** When an account is added, its existing videos are skipped. Only uploads made after that point are posted.
- **AI captions.** Claude rewrites the clipper's caption in your style, using the caption text and the video thumbnail. If no API key is set, the clipper's original caption is posted instead.
- **Reliable delivery.** Each failed download or post is retried up to 3 times, and a video is never posted twice to the same channel.
- **Managed from Telegram.** Commands: `/status`, `/accounts`, `/add`, `/remove`, `/checknow`.

## How it works

```
every ~15 min ─► for each TikTok account (3 at a time, random order)
                   list latest 5 videos (yt-dlp, through your proxy)
                   new ones ─► download once ─► caption per client (Claude)
                                              ─► sendVideo to every channel following that account
```

State (seen videos, deliveries, accounts added from Telegram) lives in SQLite at `DATABASE_PATH`.

## Setup

### 1. Create the bots (one per client)
1. In Telegram, message **@BotFather** and send `/newbot`. Do this twice, once per client.
2. Keep each token. They go in `CLIENT_A_BOT_TOKEN` and `CLIENT_B_BOT_TOKEN`.

### 2. Connect each bot to its channel(s)
1. Add the client's bot to the channel as an **admin** with permission to post messages.
2. Post `/chatid` in the channel. The bot replies with an id like `-1001234567890`. Put it in `config.yaml`.
3. DM the bot `/myid` and put your user id under `admins`.

### 3. Fill in `config.yaml`
```bash
cp config.example.yaml config.yaml
```
List each channel's TikTok usernames under `accounts:`, with or without the `@`. Each client's caption style and example captions are set in its `style:` and `examples:` fields.

### 4. Environment variables
Copy `.env.example` and fill it in:

| Variable | What |
|---|---|
| `CLIENT_A_BOT_TOKEN`, `CLIENT_B_BOT_TOKEN` | Bot tokens from BotFather. The variable names must match `bot_token_env` in the config. |
| `ANTHROPIC_API_KEY` | Key for AI captions, from console.anthropic.com. |
| `PROXY_URL` | Rotating residential proxy for TikTok, e.g. `http://user:pass@host:port`. |
| `PROXY_DOWNLOADS` | `false` sends only account checks through the proxy. Videos download directly. |
| `DATABASE_PATH` | Location of the SQLite file. Defaults to `/data/clipbot.db` in Docker. |
| `TIKTOK_COOKIES_FILE` | Optional `cookies.txt` (Netscape format) from a logged-in browser. Use it if TikTok still blocks listings with a proxy. |

### 5. Run it

**Railway (recommended)**
1. Create a new project from this GitHub repo. Railway builds it from the `Dockerfile`.
2. Under **Variables**, add the variables from step 4.
3. Add a **Volume** mounted at `/data`. Without it, the bot forgets what it already posted on every redeploy.
4. Deploy. Messages like `client client_a -> bot @yourbot` in the logs mean it started.

**Locally**
```bash
pip install -r requirements.txt   # also needs ffmpeg installed
export $(cat .env | xargs)
python -m clipbot
```

## Telegram commands (DM the bot)

| Command | |
|---|---|
| `/status` | Last check result, posts in the last 24h, recent errors |
| `/accounts` | Accounts each channel follows |
| `/add main @someclipper` | Start following an account. The channel name can be left out if there is only one channel. |
| `/remove main @someclipper` | Stop following it |
| `/checknow` | Check every account immediately |
| `/myid`, `/chatid` | Setup helpers (available to anyone) |

Accounts added with `/add` are saved in the database. The ones in `config.yaml` always load at startup.

## Proxies

TikTok often blocks or rate-limits requests from cloud servers such as Railway. With 50 accounts checked every 15 minutes (about 200 profile checks an hour), you will very likely need a proxy.

**Recommended path**
1. Start with no proxy. If `/status` shows many `could not list videos` errors, you need one.
2. Get a **rotating residential proxy**. These are usually billed per GB at around $3–8/GB. Set `PROXY_URL` and redeploy.
3. Watch the GB usage in your proxy dashboard for a day. Bandwidth has two sources:
   - **Video downloads**, at roughly 2–10 MB per clip. 100 clips a day at 5 MB each is about 15 GB a month.
   - **Account checks**. These are small, but there are about 4,800 a day.
4. If downloads are too costly, set `PROXY_DOWNLOADS=false`. Account checks will still use the proxy but videos will download directly, which usually works. If downloads then start failing, turn it back on.
5. If listings still fail behind a proxy, export your browser cookies to `cookies.txt` and set `TIKTOK_COOKIES_FILE`. Also redeploy to pick up the newest yt-dlp, since TikTok changes often.

To reduce traffic in general, raise `poll_interval_minutes` (20–30 minutes is fine for clips) or lower `videos_per_check`.

## Costs at a glance
- Hosting: Railway hobby plan, about $5/month.
- Proxy: depends on volume. Expect roughly $10–50/month at 50 accounts, and less with `PROXY_DOWNLOADS=false`.
- AI captions: each caption is one short Claude call. To cut cost, set `caption.model: claude-haiku-4-5`. Captions run through Claude's built-in fallback, so if one model declines a caption another writes it, and if all decline the original caption is used.

## Tests
```bash
python -m unittest -v
```

## A note on content
Reposting other people's clips can raise copyright and platform-rule issues. `credit_clipper: true` tags the original clipper on every post. Make sure you have permission from the clippers or creators whose content you redistribute.
