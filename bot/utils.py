from __future__ import annotations
from datetime import datetime, timezone


def ts_to_iso(ts: int | float | None) -> str:
    if not ts:
        return '—'
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(ts)


def clamp_text(text: str, limit: int = 1800) -> str:
    return text if len(text) <= limit else text[:limit - 3] + '...'
