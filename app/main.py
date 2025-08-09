# App wiring & bot startup
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher

from app.db import Base, engine, AsyncSessionLocal, apply_migrations
from app.web import router
from app.scenario_loader import load_if_empty
from app.settings import settings
from app.bot import router as bot_router

app = FastAPI()
app.include_router(router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/avatars", StaticFiles(directory=settings.AVATAR_DIR, check_dir=False), name="avatars")

@app.on_event("startup")
async def on_startup():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_migrations(conn)
    # Load scenario once
    async with AsyncSessionLocal() as s:
        try:
            await load_if_empty(s, path="scenario.yaml")
        except FileNotFoundError:
            await load_if_empty(s, path="scenario.json")

@app.on_event("startup")
async def start_bot():
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(bot_router)
    asyncio.create_task(dp.start_polling(bot))
