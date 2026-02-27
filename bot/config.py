from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(slots=True)
class Settings:
    discord_token: str = os.getenv('DISCORD_TOKEN', '')
    app_host: str = os.getenv('APP_HOST', '0.0.0.0')
    app_port: int = int(os.getenv('APP_PORT', '8080'))
    data_dir: str = os.getenv('DATA_DIR', './data')
    default_language: str = os.getenv('DEFAULT_LANGUAGE', 'ru')
    translate_incoming: bool = os.getenv('TRANSLATE_INCOMING', 'true').lower() == 'true'
    translate_outgoing: bool = os.getenv('TRANSLATE_OUTGOING', 'true').lower() == 'true'
    rust_proxy: bool = os.getenv('RUST_USE_FACEPUNCH_PROXY', 'false').lower() == 'true'
    command_prefix: str = os.getenv('COMMAND_PREFIX', '!')

settings = Settings()
