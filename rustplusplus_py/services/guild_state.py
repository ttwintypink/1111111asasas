from __future__ import annotations

from pathlib import Path
from typing import Any

from rustplusplus_py.config import GUILD_CONFIG_DIR
from rustplusplus_py.utils.storage import load_json, save_json


DEFAULT_STATE: dict[str, Any] = {
    "translate_enabled": True,
    "channels": {},
    "server_config": {},
    "snapshot": {
        "server": {},
        "time": {},
        "team": {"players": []},
        "events": [],
        "entities": {},
        "map_markers": [],
        "connection": {"status": "disconnected"},
    },
    "queue": [],
}


class GuildStateService:
    def path_for(self, guild_id: int) -> Path:
        return GUILD_CONFIG_DIR / f"{guild_id}.json"

    def load(self, guild_id: int) -> dict[str, Any]:
        state = load_json(self.path_for(guild_id), DEFAULT_STATE.copy())
        merged = DEFAULT_STATE.copy()
        merged.update(state)
        for key in ("snapshot", "channels", "server_config"):
            if key not in merged or not isinstance(merged[key], dict):
                merged[key] = DEFAULT_STATE[key].copy()
        if "queue" not in merged or not isinstance(merged["queue"], list):
            merged["queue"] = []
        return merged

    def save(self, guild_id: int, state: dict[str, Any]) -> None:
        save_json(self.path_for(guild_id), state)

    def enqueue_action(self, guild_id: int, action: dict[str, Any]) -> None:
        state = self.load(guild_id)
        state.setdefault("queue", []).append(action)
        self.save(guild_id, state)

    def pop_actions(self, guild_id: int, limit: int = 20) -> list[dict[str, Any]]:
        state = self.load(guild_id)
        queue = state.setdefault("queue", [])
        actions = queue[:limit]
        state["queue"] = queue[limit:]
        self.save(guild_id, state)
        return actions
