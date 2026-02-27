from __future__ import annotations

import asyncio
from dataclasses import dataclass

from deep_translator import GoogleTranslator


@dataclass(slots=True)
class TranslationResult:
    original: str
    translated: str
    source: str
    target: str
    changed: bool


class TranslatorService:
    def __init__(self, source: str = "en", target: str = "ru"):
        self.source = source
        self.target = target

    async def translate(self, text: str) -> TranslationResult:
        cleaned = (text or "").strip()
        if not cleaned:
            return TranslationResult(text, text, self.source, self.target, False)

        def _translate() -> str:
            return GoogleTranslator(source=self.source, target=self.target).translate(cleaned)

        try:
            translated = await asyncio.to_thread(_translate)
        except Exception:
            translated = cleaned

        return TranslationResult(
            original=cleaned,
            translated=translated,
            source=self.source,
            target=self.target,
            changed=(translated or "").strip() != cleaned,
        )
