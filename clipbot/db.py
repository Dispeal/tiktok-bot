"""SQLite state: which videos were seen, what was delivered where, and accounts added from Telegram."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    username TEXT NOT NULL,
    video_id TEXT NOT NULL,
    seen_at INTEGER NOT NULL,
    PRIMARY KEY (username, video_id)
);
CREATE TABLE IF NOT EXISTS polled (
    username TEXT PRIMARY KEY,
    first_polled_at INTEGER NOT NULL,
    last_polled_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS deliveries (
    client TEXT NOT NULL,
    channel TEXT NOT NULL,
    video_id TEXT NOT NULL,
    username TEXT NOT NULL,
    delivered_at INTEGER NOT NULL,
    PRIMARY KEY (client, channel, video_id)
);
CREATE TABLE IF NOT EXISTS account_overrides (
    client TEXT NOT NULL,
    channel TEXT NOT NULL,
    username TEXT NOT NULL,
    removed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (client, channel, username)
);
"""


class Database:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- polling state -------------------------------------------------
    def has_polled(self, username: str) -> bool:
        return self.conn.execute("SELECT 1 FROM polled WHERE username=?", (username,)).fetchone() is not None

    def mark_polled(self, username: str) -> None:
        now = int(time.time())
        self.conn.execute(
            "INSERT INTO polled (username, first_polled_at, last_polled_at) VALUES (?, ?, ?) "
            "ON CONFLICT(username) DO UPDATE SET last_polled_at=excluded.last_polled_at",
            (username, now, now),
        )
        self.conn.commit()

    def is_seen(self, username: str, video_id: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM seen WHERE username=? AND video_id=?", (username, video_id)
        ).fetchone() is not None

    def mark_seen(self, username: str, video_ids) -> None:
        now = int(time.time())
        self.conn.executemany(
            "INSERT OR IGNORE INTO seen (username, video_id, seen_at) VALUES (?, ?, ?)",
            [(username, vid, now) for vid in video_ids],
        )
        self.conn.commit()

    # --- deliveries ----------------------------------------------------
    def was_delivered(self, client: str, channel: str, video_id: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM deliveries WHERE client=? AND channel=? AND video_id=?", (client, channel, video_id)
        ).fetchone() is not None

    def mark_delivered(self, client: str, channel: str, video_id: str, username: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO deliveries (client, channel, video_id, username, delivered_at) VALUES (?, ?, ?, ?, ?)",
            (client, channel, video_id, username, int(time.time())),
        )
        self.conn.commit()

    def delivery_count(self, client: str, since: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM deliveries WHERE client=? AND delivered_at>=?", (client, since)
        ).fetchone()
        return row[0]

    # --- accounts added/removed from Telegram --------------------------
    def set_account_override(self, client: str, channel: str, username: str, removed: bool) -> None:
        self.conn.execute(
            "INSERT INTO account_overrides (client, channel, username, removed) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(client, channel, username) DO UPDATE SET removed=excluded.removed",
            (client, channel, username, int(removed)),
        )
        self.conn.commit()

    def account_overrides(self, client: str) -> list[tuple[str, str, bool]]:
        rows = self.conn.execute(
            "SELECT channel, username, removed FROM account_overrides WHERE client=?", (client,)
        ).fetchall()
        return [(ch, user, bool(removed)) for ch, user, removed in rows]
