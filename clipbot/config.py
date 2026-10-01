"""Loads config.yaml plus secrets from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import yaml

DEFAULT_STYLE = """\
Third-person entertainment-news tone, like a celebrity/fashion news account.
Open with a short scene-setter ("Tonight,", "Earlier today,", "Live on stream,").
Tag people with their @handles when the material tells you who they are.
Work one or two relevant hashtags into the sentence itself instead of piling them at the end.
Two sentences, roughly 40-70 words. No emojis."""

DEFAULT_EXAMPLES = [
    "Tonight, @thv took a turn in the audience as he watched @gracieabrams and @dojacat "
    "perform at #VogueWorld: Hollywood. No stranger to a fashion show either, the "
    "@bts.bighitofficial star dressed in a look that could have easily appeared on the runway.",
]


class ConfigError(Exception):
    pass


def normalize_username(name: str) -> str:
    return str(name).strip().lstrip("@").lower()


@dataclass
class Channel:
    key: str
    chat_id: int | str
    accounts: list[str]


@dataclass
class Client:
    name: str
    bot_token: str
    admins: set[int]
    style: str
    examples: list[str]
    credit_clipper: bool
    footer: str
    channels: dict[str, Channel]


@dataclass
class CaptionSettings:
    enabled: bool = True
    model: str = "claude-opus-5-5"
    effort: str = "low"


@dataclass
class Settings:
    clients: dict[str, Client]
    poll_interval_minutes: float = 15
    videos_per_check: int = 5
    max_concurrent_checks: int = 3
    post_existing_on_first_run: bool = False
    database_path: str = "data/clipbot.db"
    proxy_url: str | None = None
    caption: CaptionSettings = field(default_factory=CaptionSettings)


def _chat_id(value) -> int | str:
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.lstrip("-").isdigit():
        return int(text)
    if text.startswith("@"):
        return text
    raise ConfigError(f"chat_id must be a number like -1001234567890 or @channelname, got {value!r}")


def parse_settings(raw: Mapping, env: Mapping[str, str]) -> Settings:
    if not isinstance(raw, Mapping):
        raise ConfigError("config file is empty or not a mapping")
    raw_clients = raw.get("clients") or {}
    if not raw_clients:
        raise ConfigError("config needs at least one entry under 'clients'")

    clients: dict[str, Client] = {}
    seen_tokens: set[str] = set()
    for name, c in raw_clients.items():
        c = c or {}
        token_env = c.get("bot_token_env")
        if not token_env:
            raise ConfigError(f"client '{name}' is missing bot_token_env")
        token = env.get(token_env, "").strip()
        if not token:
            raise ConfigError(f"environment variable {token_env} (bot token for client '{name}') is not set")
        if token in seen_tokens:
            raise ConfigError(f"client '{name}' uses the same bot token as another client; each client needs its own bot")
        seen_tokens.add(token)

        channels: dict[str, Channel] = {}
        for key, ch in (c.get("channels") or {}).items():
            ch = ch or {}
            if "chat_id" not in ch:
                raise ConfigError(f"channel '{name}.{key}' is missing chat_id")
            accounts = [normalize_username(a) for a in (ch.get("accounts") or []) if str(a).strip()]
            channels[str(key)] = Channel(key=str(key), chat_id=_chat_id(ch["chat_id"]), accounts=sorted(set(accounts)))
        if not channels:
            raise ConfigError(f"client '{name}' has no channels")

        clients[str(name)] = Client(
            name=str(name),
            bot_token=token,
            admins={int(a) for a in (c.get("admins") or [])},
            style=(c.get("style") or DEFAULT_STYLE).strip(),
            examples=[str(e).strip() for e in (c.get("examples") or DEFAULT_EXAMPLES)],
            credit_clipper=bool(c.get("credit_clipper", True)),
            footer=str(c.get("footer") or "").strip(),
            channels=channels,
        )

    cap = raw.get("caption") or {}
    proxy = env.get("PROXY_URL", "").strip() or None
    return Settings(
        clients=clients,
        poll_interval_minutes=float(raw.get("poll_interval_minutes", 15)),
        videos_per_check=int(raw.get("videos_per_check", 5)),
        max_concurrent_checks=int(raw.get("max_concurrent_checks", 3)),
        post_existing_on_first_run=bool(raw.get("post_existing_on_first_run", False)),
        database_path=env.get("DATABASE_PATH") or raw.get("database_path", "data/clipbot.db"),
        proxy_url=proxy,
        caption=CaptionSettings(
            enabled=bool(cap.get("enabled", True)),
            model=str(cap.get("model", "claude-opus-5-5")),
            effort=str(cap.get("effort", "low")),
        ),
    )


def load_settings(path: str | Path | None = None, env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    path = Path(path or env.get("CONFIG_PATH") or "config.yaml")
    if not path.exists():
        raise ConfigError(f"config file not found: {path} (copy config.example.yaml to config.yaml)")
    with path.open(encoding="utf-8") as f:
        return parse_settings(yaml.safe_load(f), env)
