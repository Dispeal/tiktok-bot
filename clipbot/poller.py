"""Checks every TikTok account and delivers new videos to the channels that follow it."""
from __future__ import annotations

import asyncio
import logging
import random
import tempfile
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings
from .db import Database
from .telegram import MAX_UPLOAD_BYTES
from .tiktok import Video

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class Route:
    client: str
    channel: str
    chat_id: int | str


@dataclass
class CycleStats:
    started_at: float = 0
    finished_at: float = 0
    accounts_checked: int = 0
    accounts_failed: int = 0
    new_videos: int = 0
    posted: int = 0


@dataclass
class PollerStatus:
    last_cycle: CycleStats | None = None
    running: bool = False
    errors: deque = field(default_factory=lambda: deque(maxlen=20))


def build_routes(settings: Settings, db: Database) -> dict[str, list[Route]]:
    """username -> every (client, channel) that should receive its videos."""
    routes: dict[str, set[Route]] = defaultdict(set)
    for client in settings.clients.values():
        accounts = {key: set(ch.accounts) for key, ch in client.channels.items()}
        for channel_key, username, removed in db.account_overrides(client.name):
            if channel_key not in accounts:
                continue
            (accounts[channel_key].discard if removed else accounts[channel_key].add)(username)
        for key, users in accounts.items():
            ch = client.channels[key]
            for username in users:
                routes[username].add(Route(client.name, key, ch.chat_id))
    return {u: sorted(r, key=lambda x: (x.client, x.channel)) for u, r in routes.items()}


class Poller:
    def __init__(self, settings: Settings, db: Database, source, captioner, bots: dict):
        self.settings = settings
        self.db = db
        self.source = source
        self.captioner = captioner
        self.bots = bots
        self.status = PollerStatus()
        self._wake = asyncio.Event()
        self._failures: dict[str, int] = defaultdict(int)

    def trigger(self) -> None:
        self._wake.set()

    def _error(self, msg: str) -> None:
        log.warning(msg)
        self.status.errors.append((time.time(), msg))

    async def run_forever(self) -> None:
        while True:
            try:
                await self.run_cycle()
            except Exception:
                log.exception("poll cycle crashed")
            delay = self.settings.poll_interval_minutes * 60 * random.uniform(0.85, 1.15)
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

    async def run_cycle(self) -> CycleStats:
        stats = CycleStats(started_at=time.time())
        self.status.running = True
        routes = build_routes(self.settings, self.db)
        usernames = list(routes)
        random.shuffle(usernames)
        log.info("checking %d accounts", len(usernames))
        sem = asyncio.Semaphore(max(1, self.settings.max_concurrent_checks))

        async def check(username: str) -> None:
            async with sem:
                await asyncio.sleep(random.uniform(0.5, 3))
                await self._check_account(username, routes[username], stats)

        try:
            await asyncio.gather(*(check(u) for u in usernames))
        finally:
            stats.finished_at = time.time()
            self.status.last_cycle = stats
            self.status.running = False
        log.info("cycle done in %.0fs: %d checked, %d failed, %d new, %d posted",
                 stats.finished_at - stats.started_at, stats.accounts_checked,
                 stats.accounts_failed, stats.new_videos, stats.posted)
        return stats

    async def _check_account(self, username: str, routes: list[Route], stats: CycleStats) -> None:
        try:
            videos = await self.source.list_recent(username, self.settings.videos_per_check)
        except Exception as e:
            stats.accounts_failed += 1
            self._error(f"@{username}: could not list videos ({str(e)[:200]})")
            return
        stats.accounts_checked += 1

        first_time = not self.db.has_polled(username)
        self.db.mark_polled(username)
        if first_time and not self.settings.post_existing_on_first_run:
            # Don't flood channels with an account's back catalogue the first time we see it.
            self.db.mark_seen(username, [v.id for v in videos])
            log.info("@%s: first check, recorded %d existing videos", username, len(videos))
            return

        new = [v for v in videos if not self.db.is_seen(username, v.id)]
        new.sort(key=lambda v: (v.timestamp or 0, v.id))  # oldest first
        for video in new:
            stats.new_videos += 1
            await self._process(video, routes, stats)

    async def _process(self, video: Video, routes: list[Route], stats: CycleStats) -> None:
        pending = [r for r in routes if not self.db.was_delivered(r.client, r.channel, video.id)]
        if not pending:
            self.db.mark_seen(video.username, [video.id])
            return

        with tempfile.TemporaryDirectory(prefix="clipbot-") as tmp:
            try:
                video = await self.source.download(video, Path(tmp))
            except Exception as e:
                self._give_up_maybe(video, f"download failed ({str(e)[:200]})")
                return

            captions: dict[str, str] = {}
            all_ok = True
            for route in pending:
                client = self.settings.clients[route.client]
                if route.client not in captions:
                    captions[route.client] = await self.captioner.caption(video, client)
                try:
                    await self._send(route, video, captions[route.client])
                except Exception as e:
                    all_ok = False
                    self._error(f"{route.client}/{route.channel}: send failed for {video.url} ({str(e)[:200]})")
                    continue
                self.db.mark_delivered(route.client, route.channel, video.id, video.username)
                stats.posted += 1
                log.info("posted %s to %s/%s", video.url, route.client, route.channel)

        if all_ok:
            self.db.mark_seen(video.username, [video.id])
            self._failures.pop(video.id, None)
        else:
            self._give_up_maybe(video, "some channels failed, will retry")

    def _give_up_maybe(self, video: Video, reason: str) -> None:
        self._failures[video.id] += 1
        attempts = self._failures[video.id]
        if attempts >= MAX_ATTEMPTS:
            self._error(f"@{video.username} {video.url}: {reason}; giving up after {attempts} attempts")
            self.db.mark_seen(video.username, [video.id])
            self._failures.pop(video.id, None)
        else:
            self._error(f"@{video.username} {video.url}: {reason} (attempt {attempts}/{MAX_ATTEMPTS})")

    async def _send(self, route: Route, video: Video, caption: str) -> None:
        bot = self.bots[route.client]
        path = video.file_path
        if path and path.exists() and path.stat().st_size <= MAX_UPLOAD_BYTES:
            await bot.send_video(route.chat_id, path, caption, video.duration)
        else:
            # Too big for a bot upload: post the caption with the link instead.
            await bot.send_message(route.chat_id, f"{caption}\n\n{video.url}")
