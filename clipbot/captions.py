"""Writes captions in each client's house style with Claude, falling back to the clipper's own caption."""
from __future__ import annotations

import base64
import logging
import os
import re

import httpx

from .config import CaptionSettings, Client
from .tiktok import Video

log = logging.getLogger(__name__)

TELEGRAM_CAPTION_LIMIT = 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}

SYSTEM_TEMPLATE = """\
You write captions for short video clips (mostly clips of Kick/Twitch streamers) that get reposted to a Telegram channel.

House style:
{style}

Example captions in this style:
{examples}

Rules:
- Use only facts that are in the material you are given: the clipper's original caption, hashtags, the account name, and the thumbnail image. Never invent names, events, places, quotes or numbers. If you can't tell who is in the clip, write around it instead of guessing.
- Keep @handles and #hashtags exactly as they appear in the material; do not make up new handles.
- Output only the caption text: no preamble, no quotation marks, no markdown.
- Stay under 800 characters."""


def build_system_prompt(client: Client) -> str:
    examples = "\n".join(f"- {e}" for e in client.examples) or "- (none)"
    return SYSTEM_TEMPLATE.format(style=client.style, examples=examples)


def build_user_text(video: Video) -> str:
    lines = [f"Clipper account: @{video.username}"]
    if video.uploader and video.uploader.lower() != video.username:
        lines.append(f"Display name: {video.uploader}")
    lines.append(f"Original caption: {video.description.strip() or '(empty)'}")
    lines.append("\nWrite the caption for this clip.")
    return "\n".join(lines)


def clean_caption(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'“”":
        text = text[1:-1].strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def finalize_caption(body: str, video: Video, client: Client) -> str:
    """Adds credit/footer and trims to Telegram's caption limit."""
    tail_parts = []
    if client.credit_clipper:
        tail_parts.append(f"🎥 @{video.username}")
    if client.footer:
        tail_parts.append(client.footer)
    tail = "\n\n".join(tail_parts)
    room = TELEGRAM_CAPTION_LIMIT - (len(tail) + 2 if tail else 0)
    body = body.strip()
    if len(body) > room:
        body = body[: max(room - 1, 0)].rstrip() + "…"
    return f"{body}\n\n{tail}".strip() if tail else body


class Captioner:
    def __init__(self, settings: CaptionSettings, api_key: str | None = None):
        self.settings = settings
        api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        self._client = None
        if settings.enabled and api_key:
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        elif settings.enabled:
            log.warning("ANTHROPIC_API_KEY not set: posting clipper captions as-is")

    @property
    def ai_enabled(self) -> bool:
        return self._client is not None

    async def caption(self, video: Video, client: Client) -> str:
        body = video.description
        if self._client is not None:
            try:
                body = await self._generate(video, client) or body
            except Exception:
                log.exception("caption generation failed for %s; using original caption", video.id)
        return finalize_caption(clean_caption(body), video, client)

    async def _thumbnail_block(self, url: str | None) -> dict | None:
        if not url:
            return None
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as http:
                r = await http.get(url)
            media_type = r.headers.get("content-type", "").split(";")[0].strip()
            if r.status_code != 200 or media_type not in IMAGE_TYPES or len(r.content) > 4_000_000:
                return None
            data = base64.standard_b64encode(r.content).decode()
            return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}
        except Exception:
            log.debug("could not fetch thumbnail %s", url, exc_info=True)
            return None

    async def _generate(self, video: Video, client: Client) -> str | None:
        content = []
        image = await self._thumbnail_block(video.thumbnail)
        if image:
            content.append(image)
        content.append({"type": "text", "text": build_user_text(video)})

        model = self.settings.model
        kwargs = dict(
            model=model,
            max_tokens=4000,
            system=build_system_prompt(client),
            messages=[{"role": "user", "content": content}],
        )
        if not model.startswith("claude-haiku"):
            kwargs["output_config"] = {"effort": self.settings.effort}
        if model in FALLBACK_MODELS:
            # If the model declines, the API retries on a fallback model in the same call.
            resp = await self._client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            )
        else:
            resp = await self._client.messages.create(**kwargs)

        if resp.stop_reason == "refusal":
            log.warning("caption request for %s was declined; using original caption", video.id)
            return None
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return text or None
