#!/usr/bin/env python
"""Start both the Telegram bot and the web app simultaneously."""

import asyncio

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from app.bot import router as bot_router
from app.db import Base, engine, AsyncSessionLocal
from app.scenario_loader import load_if_empty
from app.settings import settings
from app.web import router as web_router


async def init_db_and_scenario() -> None:
    """Create tables and load scenario if database is empty."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        try:
            await load_if_empty(session, path="scenario.yaml")
        except FileNotFoundError:
            await load_if_empty(session, path="scenario.json")


async def run_web() -> None:
    """Run FastAPI web server."""
    app = FastAPI()
    app.include_router(web_router)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()


async def run_bot() -> None:
    """Run Telegram bot polling."""
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(bot_router)
    await dp.start_polling(bot)


async def main() -> None:
    await init_db_and_scenario()
    await asyncio.gather(run_web(), run_bot())


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
