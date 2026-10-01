"""Minimal async Telegram Bot API client (one instance per client bot)."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class TelegramError(Exception):
    def __init__(self, method: str, description: str, retry_after: int | None = None):
        super().__init__(f"{method}: {description}")
        self.retry_after = retry_after


class TelegramBot:
    def __init__(self, token: str, http: httpx.AsyncClient | None = None):
        self._base = f"https://api.telegram.org/bot{token}"
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(60, read=300, write=300))
        self.username: str | None = None

    async def close(self) -> None:
        await self._http.aclose()

    async def call(self, method: str, data: dict | None = None, files: dict | None = None,
                   timeout: float | None = None, attempts: int = 4):
        data = {k: v for k, v in (data or {}).items() if v is not None}
        for attempt in range(attempts):
            try:
                if files:
                    # Multipart fields must be strings; rewind files on retry.
                    for f in files.values():
                        f[1].seek(0)
                    form = {k: v if isinstance(v, str) else json.dumps(v) for k, v in data.items()}
                    r = await self._http.post(f"{self._base}/{method}", data=form, files=files, timeout=timeout)
                else:
                    r = await self._http.post(f"{self._base}/{method}", json=data, timeout=timeout)
                body = r.json()
            except (httpx.TransportError, ValueError) as e:
                if attempt == attempts - 1:
                    raise TelegramError(method, f"network error: {e}") from e
                await asyncio.sleep(2 ** attempt)
                continue
            if body.get("ok"):
                return body["result"]
            retry_after = (body.get("parameters") or {}).get("retry_after")
            if retry_after is not None and attempt < attempts - 1:
                log.warning("Telegram rate limit on %s, waiting %ss", method, retry_after)
                await asyncio.sleep(retry_after + 1)
                continue
            raise TelegramError(method, body.get("description", "unknown error"), retry_after)

    async def get_me(self) -> dict:
        me = await self.call("getMe")
        self.username = me.get("username")
        return me

    async def send_message(self, chat_id, text: str, reply_to: int | None = None):
        return await self.call("sendMessage", {
            "chat_id": chat_id, "text": text[:4096], "disable_web_page_preview": True,
            "reply_parameters": {"message_id": reply_to, "allow_sending_without_reply": True} if reply_to else None,
        })

    async def send_video(self, chat_id, path: Path, caption: str, duration: float | None = None):
        with open(path, "rb") as f:
            return await self.call(
                "sendVideo",
                {"chat_id": str(chat_id), "caption": caption, "supports_streaming": "true",
                 "duration": str(int(duration)) if duration else None},
                files={"video": (path.name, f, "video/mp4")},
            )

    async def get_updates(self, offset: int | None, timeout: int = 50) -> list[dict]:
        return await self.call(
            "getUpdates",
            {"offset": offset, "timeout": timeout,
             "allowed_updates": ["message", "channel_post", "my_chat_member"]},
            timeout=timeout + 15,
            attempts=1,
        )
