"""Lists and downloads TikTok videos with yt-dlp (runs in a worker thread)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class Video:
    id: str
    username: str
    url: str
    description: str = ""
    timestamp: int | None = None
    thumbnail: str | None = None
    uploader: str | None = None
    duration: float | None = None
    file_path: Path | None = None


class TikTokSource:
    def __init__(self, proxy_url: str | None = None, cookies_file: str | None = None,
                 proxy_downloads: bool = True):
        self.proxy_url = proxy_url
        self.cookies_file = cookies_file
        self.proxy_downloads = proxy_downloads

    def _base_opts(self, use_proxy: bool = True) -> dict:
        opts = {"quiet": True, "no_warnings": True, "noprogress": True, "socket_timeout": 30, "retries": 3}
        if self.proxy_url and use_proxy:
            opts["proxy"] = self.proxy_url
        if self.cookies_file:
            opts["cookiefile"] = self.cookies_file
        return opts

    async def list_recent(self, username: str, limit: int) -> list[Video]:
        return await asyncio.to_thread(self._list_recent, username, limit)

    def _list_recent(self, username: str, limit: int) -> list[Video]:
        import yt_dlp

        opts = self._base_opts() | {"extract_flat": "in_playlist", "playlistend": limit, "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.tiktok.com/@{username}", download=False)
        videos = []
        for e in (info or {}).get("entries") or []:
            if not e or not e.get("id"):
                continue
            vid = str(e["id"])
            videos.append(Video(
                id=vid,
                username=username,
                url=e.get("webpage_url") or e.get("url") or f"https://www.tiktok.com/@{username}/video/{vid}",
                description=e.get("description") or e.get("title") or "",
                timestamp=e.get("timestamp"),
                thumbnail=e.get("thumbnail"),
            ))
        return videos[:limit]

    async def download(self, video: Video, dest_dir: Path) -> Video:
        return await asyncio.to_thread(self._download, video, dest_dir)

    def _download(self, video: Video, dest_dir: Path) -> Video:
        import yt_dlp

        opts = self._base_opts(use_proxy=self.proxy_downloads) | {
            "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
            # Prefer a single mp4 file under Telegram's 50 MB bot upload limit.
            "format": "best[ext=mp4][filesize<50M]/best[ext=mp4]/best",
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video.url, download=True)
            downloads = info.get("requested_downloads") or []
            path = Path(downloads[0]["filepath"]) if downloads else Path(ydl.prepare_filename(info))
        video.file_path = path
        video.description = info.get("description") or info.get("title") or video.description
        video.timestamp = info.get("timestamp") or video.timestamp
        video.thumbnail = info.get("thumbnail") or video.thumbnail
        video.uploader = info.get("uploader") or info.get("creator")
        video.duration = info.get("duration")
        return video
