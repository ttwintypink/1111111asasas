from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ServerConfig:
    server_ip: str = ""
    app_port: int = 0
    steam_id: str = ""
    player_token: str = ""
    title: str = ""


@dataclass(slots=True)
class ConnectionState:
    status: str = "disconnected"
    transport: str = "bridge"
    last_error: str = ""
    last_seen: str = ""


@dataclass(slots=True)
class Snapshot:
    server: dict[str, Any] = field(default_factory=dict)
    time: dict[str, Any] = field(default_factory=dict)
    team: dict[str, Any] = field(default_factory=lambda: {"players": []})
    events: list[dict[str, Any]] = field(default_factory=list)
    entities: dict[str, Any] = field(default_factory=dict)
    map_markers: list[dict[str, Any]] = field(default_factory=list)
    connection: dict[str, Any] = field(default_factory=lambda: ConnectionState().__dict__)
