"""Avatar generation utilities package."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image
from aiogram import Bot

from app.models import User
from app.settings import settings

try:  # optional dependency for .tgs rendering
    from rlottie_python import LottieAnimation  # type: ignore
except Exception:  # pragma: no cover
    LottieAnimation = None  # type: ignore

AVATAR_SIZE = 640

from .utils import _resize_fit_rgba  # noqa: E402
from .emoji import _emoji_avatar, _render_emoji_from_font  # noqa: E402
from .sticker import _sticker_avatar, _render_tgs_high_quality  # noqa: E402


async def save_avatar(bot: Bot, user: User) -> bool:
    path = Path(settings.AVATAR_DIR)
    path.mkdir(exist_ok=True)
    chat = await bot.get_chat(user.id)
    if chat.photo:
        buf = BytesIO()
        await bot.download(chat.photo.big_file_id, destination=buf)
        buf.seek(0)
        img = Image.open(buf)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        img.thumbnail((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
        background = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (0, 0, 0, 0))
        x = (AVATAR_SIZE - img.width) // 2
        y = (AVATAR_SIZE - img.height) // 2
        background.alpha_composite(img, dest=(x, y))
        background.save(path / f"{user.id}.png")
        return True
    return False
