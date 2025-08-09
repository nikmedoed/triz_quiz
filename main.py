# App wiring & bot startup
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher

from app.db import Base, engine, AsyncSessionLocal, apply_migrations
from app.web import router
from app.scenario_loader import load_if_empty
from app.settings import settings
from app.bot import router as bot_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables and apply migrations
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_migrations(conn)
    # Load scenario once
    async with AsyncSessionLocal() as s:
        try:
            await load_if_empty(s, path="scenario.yaml")
        except FileNotFoundError:
            await load_if_empty(s, path="scenario.json")

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(bot_router)
    bot_task = asyncio.create_task(dp.start_polling(bot))
    try:
        yield
    finally:
        bot_task.cancel()
        await bot.session.close()


app = FastAPI(lifespan=lifespan)
app.include_router(router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
