from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .config import settings

class Storage:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or settings.data_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'guilds').mkdir(exist_ok=True)
        (self.root / 'maps').mkdir(exist_ok=True)

    def guild_path(self, guild_id: int) -> Path:
        return self.root / 'guilds' / f'{guild_id}.json'

    def load_guild(self, guild_id: int) -> dict[str, Any]:
        path = self.guild_path(guild_id)
        if not path.exists():
            return {
                'guild_id': guild_id,
                'language': 'ru',
                'channels': {
                    'category': None,
                    'teamchat': None,
                    'events': None,
                    'commands': None,
                    'logs': None,
                },
                'rust': {
                    'server_ip': '',
                    'app_port': 0,
                    'player_id': '',
                    'player_token': 0,
                    'use_proxy': False,
                    'connected': False,
                },
                'relay': {
                    'discord_to_rust': True,
                    'rust_to_discord': True,
                    'translate_incoming': True,
                    'translate_outgoing': True,
                },
                'watch_entities': {},
                'last_messages': [],
            }
        return json.loads(path.read_text('utf-8'))

    def save_guild(self, guild_id: int, data: dict[str, Any]) -> None:
        self.guild_path(guild_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')

    def save_map(self, guild_id: int, jpg_bytes: bytes) -> Path:
        path = self.root / 'maps' / f'{guild_id}.jpg'
        path.write_bytes(jpg_bytes)
        return path
