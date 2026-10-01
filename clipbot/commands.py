"""Telegram commands for each client bot (admins only, except the setup helpers)."""
from __future__ import annotations

import asyncio
import logging
import time

from .config import Client, normalize_username
from .db import Database
from .poller import Poller, build_routes
from .telegram import TelegramBot, TelegramError

log = logging.getLogger(__name__)

HELP = """Commands:
/status - last check, posts today, recent errors
/accounts - accounts each channel follows
/add <channel> @user - follow an account in a channel
/remove <channel> @user - stop following it
/checknow - check all accounts right now
/myid - your Telegram user id
/chatid - this chat's id (also works when posted in a channel)"""


class CommandHandler:
    def __init__(self, bot: TelegramBot, client: Client, db: Database, poller: Poller):
        self.bot = bot
        self.client = client
        self.db = db
        self.poller = poller

    async def run_forever(self) -> None:
        offset = None
        while True:
            try:
                updates = await self.bot.get_updates(offset)
            except TelegramError as e:
                log.warning("[%s] getUpdates failed: %s", self.client.name, e)
                await asyncio.sleep(5)
                continue
            for u in updates:
                offset = u["update_id"] + 1
                try:
                    await self.handle(u)
                except Exception:
                    log.exception("[%s] error handling update", self.client.name)

    async def handle(self, update: dict) -> None:
        if "my_chat_member" in update:
            m = update["my_chat_member"]
            chat = m["chat"]
            log.info("[%s] bot is now '%s' in %s %r (chat_id=%s)", self.client.name,
                     m["new_chat_member"]["status"], chat.get("type"), chat.get("title"), chat["id"])
            return

        msg = update.get("message") or update.get("channel_post")
        if not msg or not msg.get("text", "").startswith("/"):
            return
        chat_id = msg["chat"]["id"]
        parts = msg["text"].split()
        command = parts[0][1:].split("@")[0].lower()
        if "@" in parts[0] and self.bot.username and parts[0].split("@", 1)[1].lower() != self.bot.username.lower():
            return  # addressed to a different bot in a group
        args = parts[1:]
        user_id = (msg.get("from") or {}).get("id")

        async def reply(text: str) -> None:
            await self.bot.send_message(chat_id, text, reply_to=msg["message_id"])

        if command == "chatid":
            return await reply(f"chat_id: {chat_id}")
        if command == "myid":
            return await reply(f"your user id: {user_id}" if user_id else "Send this in a private chat with me.")
        if user_id is None or user_id not in self.client.admins:
            if update.get("message") and msg["chat"].get("type") == "private":
                await reply(f"You're not an admin of this bot. Your user id is {user_id}; "
                            "add it under 'admins' in config.yaml.")
            return

        handler = getattr(self, f"cmd_{command}", None)
        if handler is None:
            return await reply(HELP)
        await reply(await handler(args))

    async def cmd_start(self, args) -> str:
        return HELP

    async def cmd_help(self, args) -> str:
        return HELP

    async def cmd_status(self, args) -> str:
        routes = build_routes(self.poller.settings, self.db)
        mine = sum(1 for rs in routes.values() if any(r.client == self.client.name for r in rs))
        since = int(time.time()) - 86400
        lines = [f"Client: {self.client.name}", f"Accounts followed: {mine}",
                 f"Posts in last 24h: {self.db.delivery_count(self.client.name, since)}",
                 f"AI captions: {'on' if self.poller.captioner.ai_enabled else 'off'}"]
        st = self.poller.status
        if st.running:
            lines.append("Check in progress…")
        if st.last_cycle:
            c = st.last_cycle
            ago = int((time.time() - c.finished_at) / 60)
            lines.append(f"Last check: {ago} min ago, {c.accounts_checked} ok / {c.accounts_failed} failed, "
                         f"{c.new_videos} new, {c.posted} posted")
        if st.errors:
            lines.append("\nRecent errors:")
            lines += [f"- {time.strftime('%H:%M', time.gmtime(t))} UTC {m}" for t, m in list(st.errors)[-5:]]
        return "\n".join(lines)

    async def cmd_accounts(self, args) -> str:
        routes = build_routes(self.poller.settings, self.db)
        by_channel: dict[str, list[str]] = {k: [] for k in self.client.channels}
        for username, rs in routes.items():
            for r in rs:
                if r.client == self.client.name:
                    by_channel[r.channel].append(username)
        out = []
        for key, users in by_channel.items():
            out.append(f"{key} ({len(users)}):")
            out.append(", ".join(f"@{u}" for u in sorted(users)) or "(none)")
        return "\n".join(out)

    def _parse_channel_user(self, args) -> tuple[str, str] | str:
        if len(args) == 1 and len(self.client.channels) == 1:
            args = [next(iter(self.client.channels)), args[0]]
        if len(args) != 2:
            return f"Usage: <channel> @user. Channels: {', '.join(self.client.channels)}"
        channel, user = args[0], normalize_username(args[1])
        if channel not in self.client.channels:
            return f"Unknown channel '{channel}'. Channels: {', '.join(self.client.channels)}"
        if not user:
            return "Give a TikTok username."
        return channel, user

    async def cmd_add(self, args) -> str:
        parsed = self._parse_channel_user(args)
        if isinstance(parsed, str):
            return parsed
        channel, user = parsed
        self.db.set_account_override(self.client.name, channel, user, removed=False)
        return f"Following @{user} in {channel}. New posts start from the next check (existing videos are skipped)."

    async def cmd_remove(self, args) -> str:
        parsed = self._parse_channel_user(args)
        if isinstance(parsed, str):
            return parsed
        channel, user = parsed
        self.db.set_account_override(self.client.name, channel, user, removed=True)
        return f"Stopped following @{user} in {channel}."

    async def cmd_checknow(self, args) -> str:
        if self.poller.status.running:
            return "A check is already running."
        self.poller.trigger()
        return "Checking all accounts now. Use /status in a few minutes."
