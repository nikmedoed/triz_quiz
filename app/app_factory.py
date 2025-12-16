import asyncio
import os
from contextlib import asynccontextmanager, suppress

from aiogram import Bot, Dispatcher
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.bot import router as bot_router
from app.db import Base, engine, AsyncSessionLocal, apply_migrations
from app.scenario_loader import load_if_empty
from app.settings import settings
from app.web import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database and load scenario
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_migrations(conn)
    async with AsyncSessionLocal() as session:
        if os.path.exists("scenario.yaml"):
            await load_if_empty(session, path="scenario.yaml")
        elif os.path.exists("scenario.json"):
            await load_if_empty(session, path="scenario.json")

    # Start Telegram bot
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(bot_router)
    bot_task = asyncio.create_task(dp.start_polling(bot))

    try:
        yield
    finally:
        bot_task.cancel()
        with suppress(asyncio.CancelledError):
            await bot_task
        await bot.session.close()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(web_router)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.mount("/avatars", StaticFiles(directory=settings.AVATAR_DIR, check_dir=False), name="avatars")
    app.mount("/media", StaticFiles(directory="media", check_dir=False), name="media")
    return app
