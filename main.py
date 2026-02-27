from __future__ import annotations
import logging
import sys

from bot.config import settings
from bot.discord_bot import bot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    stream=sys.stdout,
)

if not settings.discord_token:
    raise SystemExit('DISCORD_TOKEN не задан. Заполни .env файл.')

bot.run(settings.discord_token)
