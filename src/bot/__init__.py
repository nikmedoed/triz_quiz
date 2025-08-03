"""Telegram bot launcher."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from . import core, state
from .handlers import router
from ..config import settings

bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)


def run_bot() -> None:
    """Запуск Telegram-бота."""
    logging.basicConfig(level=logging.INFO)
    state.load_state()

    async def main_loop():
        base = settings.projector_url.rsplit('/', 1)[0]
        logging.info("Reset link: %s/reset", base)
        asyncio.create_task(core.watch_steps(bot))
        await dp.start_polling(bot)

    asyncio.run(main_loop())
