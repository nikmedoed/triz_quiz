"""Application configuration settings."""

import os

from dotenv import load_dotenv
from pydantic import BaseModel


# Ensure environment variables from a .env file are loaded before accessing them.
load_dotenv()


class Settings(BaseModel):
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./quiz.db")
    AVATAR_DIR: str = os.getenv("AVATAR_DIR", "avatars")
    TELEGRAM_SEND_DELAY: float = float(os.getenv("TELEGRAM_SEND_DELAY", "0.05"))
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))


settings = Settings()
