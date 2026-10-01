"""Entry point: python -m clipbot"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from .captions import Captioner
from .commands import CommandHandler
from .config import ConfigError, load_settings
from .db import Database
from .poller import Poller
from .telegram import TelegramBot
from .tiktok import TikTokSource

log = logging.getLogger("clipbot")


async def main() -> None:
    settings = load_settings()
    db = Database(settings.database_path)
    source = TikTokSource(
        proxy_url=settings.proxy_url,
        cookies_file=os.environ.get("TIKTOK_COOKIES_FILE") or None,
        proxy_downloads=os.environ.get("PROXY_DOWNLOADS", "true").lower() not in ("0", "false", "no"),
    )
    captioner = Captioner(settings.caption)

    bots = {name: TelegramBot(c.bot_token) for name, c in settings.clients.items()}
    for name, bot in bots.items():
        me = await bot.get_me()
        log.info("client %s -> bot @%s", name, me.get("username"))
    log.info("proxy: %s", ("on" + ("" if source.proxy_downloads else " (listings only)")) if settings.proxy_url else "off")

    poller = Poller(settings, db, source, captioner, bots)
    tasks = [asyncio.create_task(poller.run_forever(), name="poller")]
    for name, client in settings.clients.items():
        handler = CommandHandler(bots[name], client, db, poller)
        tasks.append(asyncio.create_task(handler.run_forever(), name=f"commands-{name}"))
    try:
        await asyncio.gather(*tasks)
    finally:
        for bot in bots.values():
            await bot.close()
        db.close()


def run() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(main())
    except ConfigError as e:
        log.error("config error: %s", e)
        sys.exit(2)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
