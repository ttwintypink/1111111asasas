from __future__ import annotations

import sys

from rustplusplus_py.bot import RustPlusPythonBot
from rustplusplus_py.config import load_settings


if __name__ == "__main__":
    settings = load_settings()
    if not settings.discord_token:
        print("DISCORD_TOKEN is required. Copy .env.example to .env and fill it.", file=sys.stderr)
        raise SystemExit(1)

    bot = RustPlusPythonBot(settings)
    bot.run(settings.discord_token)
