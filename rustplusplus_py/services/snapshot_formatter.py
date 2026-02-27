from __future__ import annotations

from typing import Any


def format_server(snapshot: dict[str, Any]) -> str:
    server = snapshot.get("server", {})
    time = snapshot.get("time", {})
    connection = snapshot.get("connection", {})
    lines = [
        f"**Статус:** {connection.get('status', 'unknown')}",
        f"**Название:** {server.get('name', '-')}",
        f"**Игроки:** {server.get('players', '-')}/{server.get('max_players', '-')}",
        f"**Очередь:** {server.get('queue', '-')}",
        f"**Карта:** {server.get('map', '-')}",
        f"**Wipe:** {server.get('wipe', '-')}",
        f"**В игре:** {time.get('time', '-')}",
        f"**День:** {time.get('is_day', '-')}",
    ]
    return "\n".join(lines)


def format_team(snapshot: dict[str, Any]) -> str:
    players = snapshot.get("team", {}).get("players", [])
    if not players:
        return "Нет данных о команде."
    lines = []
    for player in players[:25]:
        status = "онлайн" if player.get("is_online") else "оффлайн"
        leader = " 👑" if player.get("is_leader") else ""
        paired = " 📱" if player.get("is_paired") else ""
        lines.append(f"- **{player.get('name', 'Unknown')}** — {status}{leader}{paired}")
    return "\n".join(lines)


def format_events(snapshot: dict[str, Any]) -> str:
    events = snapshot.get("events", [])
    if not events:
        return "Событий пока нет."
    lines = []
    for event in events[:10]:
        if isinstance(event, dict):
            lines.append(f"- {event.get('time', '-')} — {event.get('text', '-')}")
        else:
            lines.append(f"- {event}")
    return "\n".join(lines)


def format_entities(snapshot: dict[str, Any]) -> str:
    entities = snapshot.get("entities", {})
    if not entities:
        return "Устройств пока нет."
    lines = []
    for entity_id, entity in list(entities.items())[:20]:
        lines.append(
            f"- **{entity.get('name', 'Entity')}** (`{entity_id}`) — "
            f"тип: {entity.get('type', '-')}, значение: {entity.get('value', '-')}, "
            f"онлайн: {entity.get('reachable', '-')}"
        )
    return "\n".join(lines)
