from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = BASE_DIR / "runtime"
CONFIG_DIR = BASE_DIR / "config"
CHANNEL_NAMES_FILE = CONFIG_DIR / "channel_names.json"
GUILD_CONFIG_DIR = RUNTIME_DIR / "guilds"


@dataclass(slots=True)
class Settings:
    discord_token: str
    discord_guild_id: int | None
    bot_prefix: str
    bot_language: str
    translate_enabled: bool
    translate_source: str
    translate_target: str
    category_name: str
    translation_mode: str
    http_enabled: bool
    http_host: str
    http_port: int
    http_shared_secret: str
    poll_interval_seconds: int


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_settings() -> Settings:
    load_dotenv(BASE_DIR / ".env")
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    GUILD_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    token = os.getenv("DISCORD_TOKEN", "").strip()
    guild_raw = os.getenv("DISCORD_GUILD_ID", "").strip()

    return Settings(
        discord_token=token,
        discord_guild_id=int(guild_raw) if guild_raw.isdigit() else None,
        bot_prefix=os.getenv("BOT_PREFIX", "!").strip() or "!",
        bot_language=os.getenv("BOT_LANGUAGE", "ru").strip() or "ru",
        translate_enabled=_to_bool(os.getenv("TRANSLATE_ENABLED"), True),
        translate_source=os.getenv("TRANSLATE_SOURCE", "en").strip() or "en",
        translate_target=os.getenv("TRANSLATE_TARGET", "ru").strip() or "ru",
        category_name=os.getenv("CATEGORY_NAME", "rust-плюс").strip() or "rust-плюс",
        translation_mode=os.getenv("TRANSLATION_MODE", "append").strip() or "append",
        http_enabled=_to_bool(os.getenv("HTTP_ENABLED"), True),
        http_host=os.getenv("HTTP_HOST", "0.0.0.0").strip() or "0.0.0.0",
        http_port=int(os.getenv("HTTP_PORT", "8080")),
        http_shared_secret=os.getenv("HTTP_SHARED_SECRET", "change_me").strip() or "change_me",
        poll_interval_seconds=max(10, int(os.getenv("POLL_INTERVAL_SECONDS", "30"))),
    )
