from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from rustplusplus_py.protocol.models import ConnectionState


class RustPlusProtocolClient:
    '''
    This class is the Python-side protocol facade.

    It intentionally mirrors the high-level operations that rustplusplus uses:
    - getInfo
    - getTime
    - getTeamInfo
    - getMapMarkers
    - getEntityInfo
    - setEntityValue
    - sendTeamMessage

    In this project, the live transport is an HTTP bridge because the raw Rust+
    websocket/protobuf transport is not bundled in the original archive. The bot
    still exposes the same logical operations and queue semantics so a direct
    transport can be plugged in later without changing the Discord layer.
    '''

    TRANSPORT_NAME = "bridge"

    async def get_info(self, guild_id: int, state: dict[str, Any]) -> dict[str, Any]:
        return state.get("snapshot", {}).get("server", {})

    async def get_time(self, guild_id: int, state: dict[str, Any]) -> dict[str, Any]:
        return state.get("snapshot", {}).get("time", {})

    async def get_team_info(self, guild_id: int, state: dict[str, Any]) -> dict[str, Any]:
        return state.get("snapshot", {}).get("team", {"players": []})

    async def get_map_markers(self, guild_id: int, state: dict[str, Any]) -> list[dict[str, Any]]:
        return state.get("snapshot", {}).get("map_markers", [])

    async def get_entity_info(self, guild_id: int, state: dict[str, Any], entity_id: str) -> dict[str, Any]:
        return state.get("snapshot", {}).get("entities", {}).get(str(entity_id), {})

    async def set_entity_value(self, guild_state_service, guild_id: int, entity_id: str, value: bool) -> dict[str, Any]:
        action = {"type": "set_entity_value", "entity_id": str(entity_id), "value": bool(value), "created_at": _now_iso()}
        guild_state_service.enqueue_action(guild_id, action)
        return {"queued": True, **action}

    async def send_team_message(self, guild_state_service, guild_id: int, message: str) -> dict[str, Any]:
        action = {"type": "send_team_message", "message": message, "created_at": _now_iso()}
        guild_state_service.enqueue_action(guild_id, action)
        return {"queued": True, **action}

    def build_connection_state(self, status: str = "connected", last_error: str = "", last_seen: str = "") -> dict[str, Any]:
        if not last_seen:
            last_seen = _now_iso()
        return asdict(ConnectionState(status=status, transport=self.TRANSPORT_NAME, last_error=last_error, last_seen=last_seen))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
