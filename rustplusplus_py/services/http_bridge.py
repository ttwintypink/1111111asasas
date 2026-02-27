from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from aiohttp import web

from rustplusplus_py.services.guild_state import GuildStateService


log = logging.getLogger("rustplusplus_py.http_bridge")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HttpBridge:
    '''
    HTTP bridge contract:

    POST /bridge/push/teamchat
    {
      "guild_id": 123,
      "author": "Player",
      "content": "hello",
      "secret": "..."
    }

    POST /bridge/push/snapshot
    {
      "guild_id": 123,
      "snapshot": {
        "server": {...},
        "time": {...},
        "team": {"players": [...]},
        "events": [...],
        "entities": {"123": {...}},
        "map_markers": [...]
      },
      "secret": "..."
    }

    GET /bridge/pull/actions?guild_id=123&secret=...

    This lets a separate Rust+ worker feed data into the Python bot and consume
    queued actions such as send_team_message and set_entity_value.
    '''

    def __init__(self, bot, host: str, port: int, shared_secret: str):
        self.bot = bot
        self.host = host
        self.port = port
        self.shared_secret = shared_secret
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None

    async def start(self) -> None:
        app = web.Application()
        app.add_routes(
            [
                web.get("/healthz", self.healthz),
                web.post("/bridge/push/teamchat", self.push_teamchat),
                web.post("/bridge/push/snapshot", self.push_snapshot),
                web.get("/bridge/pull/actions", self.pull_actions),
            ]
        )
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host=self.host, port=self.port)
        await self.site.start()

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()

    async def healthz(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    def _validate_secret(self, provided: str | None) -> None:
        if (provided or "") != self.shared_secret:
            raise web.HTTPForbidden(text="invalid secret")

    async def push_teamchat(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self._validate_secret(payload.get("secret"))
        guild_id = int(payload["guild_id"])
        await self.bot.post_external_teamchat(guild_id, payload.get("author", "Unknown"), payload.get("content", ""))
        return web.json_response({"ok": True})

    async def push_snapshot(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self._validate_secret(payload.get("secret"))
        guild_id = int(payload["guild_id"])
        snapshot = payload.get("snapshot", {})
        state = self.bot.guild_state_service.load(guild_id)
        state["snapshot"] = {
            "server": snapshot.get("server", {}),
            "time": snapshot.get("time", {}),
            "team": snapshot.get("team", {"players": []}),
            "events": snapshot.get("events", []),
            "entities": snapshot.get("entities", {}),
            "map_markers": snapshot.get("map_markers", []),
            "connection": {
                "status": "connected",
                "transport": "bridge",
                "last_error": "",
                "last_seen": _utc_now(),
            },
        }
        self.bot.guild_state_service.save(guild_id, state)
        await self.bot.maybe_publish_snapshot(guild_id)
        return web.json_response({"ok": True})

    async def pull_actions(self, request: web.Request) -> web.Response:
        self._validate_secret(request.query.get("secret"))
        guild_id = int(request.query["guild_id"])
        actions = self.bot.guild_state_service.pop_actions(guild_id)
        return web.json_response({"ok": True, "actions": actions})
