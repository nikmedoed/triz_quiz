from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    """Application configuration loaded from environment variables."""
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_id: int = int(os.getenv("ADMIN_ID", 0))
    projector_url: str = os.getenv("PROJECTOR_URL", "http://localhost:5000/update")
    server_host: str = os.getenv("SERVER_HOST", "0.0.0.0")
    server_port: int = int(os.getenv("SERVER_PORT", 5000))
    db_file: str = os.getenv("DB_FILE", "quiz.db")

settings = Settings()

if not settings.bot_token:
    raise RuntimeError("BOT_TOKEN is required. Set it in the environment or .env file.")
