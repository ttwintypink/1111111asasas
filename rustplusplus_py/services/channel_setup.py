from __future__ import annotations

import json
from pathlib import Path

import discord

from rustplusplus_py.config import CHANNEL_NAMES_FILE
from rustplusplus_py.services.guild_state import GuildStateService


class ChannelSetupService:
    def __init__(self, guild_state_service: GuildStateService, fallback_category_name: str):
        self.guild_state_service = guild_state_service
        self.fallback_category_name = fallback_category_name

    def _read_channel_names(self) -> dict[str, str]:
        path = Path(CHANNEL_NAMES_FILE)
        if not path.exists():
            return {"category": self.fallback_category_name, "teamchat": "тимчат", "information": "информация"}
        return json.loads(path.read_text(encoding="utf-8"))

    async def ensure(self, guild: discord.Guild) -> dict[str, int]:
        if guild is None:
            raise ValueError("Guild is required")

        names = self._read_channel_names()
        category_name = names.get("category") or self.fallback_category_name

        category = discord.utils.get(guild.categories, name=category_name)
        if category is None:
            category = await guild.create_category(category_name)

        state = self.guild_state_service.load(guild.id)
        channels = state.get("channels", {})
        updated: dict[str, int] = {}

        for key, wanted_name in names.items():
            if key == "category":
                continue

            existing = None
            channel_id = channels.get(key)
            if channel_id:
                candidate = guild.get_channel(channel_id)
                if isinstance(candidate, discord.TextChannel):
                    existing = candidate

            if existing is None:
                existing = discord.utils.get(guild.text_channels, name=wanted_name)

            if existing is None:
                existing = await guild.create_text_channel(wanted_name, category=category)
            else:
                edits = {}
                if existing.name != wanted_name:
                    edits["name"] = wanted_name
                if existing.category_id != category.id:
                    edits["category"] = category
                if edits:
                    await existing.edit(**edits)

            updated[key] = existing.id

        state["channels"] = updated
        self.guild_state_service.save(guild.id, state)
        return updated
