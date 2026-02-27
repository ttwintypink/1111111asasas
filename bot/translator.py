from __future__ import annotations
import asyncio
from functools import lru_cache

class Translator:
    def __init__(self):
        self._enabled = True

    @staticmethod
    @lru_cache(maxsize=4)
    def _build(source: str, target: str):
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source=source, target=target)

    async def translate(self, text: str, source: str, target: str) -> str:
        if not text.strip() or source == target:
            return text
        try:
            return await asyncio.to_thread(self._build(source, target).translate, text)
        except Exception:
            return text

translator = Translator()
