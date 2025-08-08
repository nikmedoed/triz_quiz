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


settings = Settings()
