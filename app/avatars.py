"""Avatar generation utilities."""

from __future__ import annotations

import random
import gzip
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from rlottie_python import LottieAnimation

from aiogram import Bot
from aiogram.types import Sticker

from app.settings import settings
from app.models import User


AVATAR_SIZE = 640


def _gradient(size: int) -> Image.Image:
    """Create a colorful four-corner gradient image."""
    corners = [
        tuple(random.randint(0, 255) for _ in range(3)) for _ in range(4)
    ]  # tl, tr, bl, br
    img = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(img)
    for x in range(size):
        rx = x / (size - 1)
        for y in range(size):
            ry = y / (size - 1)
            top = [
                int(corners[0][i] * (1 - rx) + corners[1][i] * rx) for i in range(3)
            ]
            bottom = [
                int(corners[2][i] * (1 - rx) + corners[3][i] * rx) for i in range(3)
            ]
            r = int(top[0] * (1 - ry) + bottom[0] * ry)
            g = int(top[1] * (1 - ry) + bottom[1] * ry)
            b = int(top[2] * (1 - ry) + bottom[2] * ry)
            draw.point((x, y), fill=(r, g, b, 255))
    return img


def _emoji_avatar(path: Path, user: User, emoji: str) -> None:
    """Generate avatar from emoji image with a colorful gradient background."""
    size = AVATAR_SIZE
    img = _gradient(size)
    try:
        codepoints = "-".join(f"{ord(c):x}" for c in emoji)
        url = f"https://emojiapi.dev/api/v1/{codepoints}/512.png"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        emoji_img = Image.open(BytesIO(resp.content)).convert("RGBA")
        emoji_size = int(size * 0.7)
        emoji_img = emoji_img.resize((emoji_size, emoji_size), Image.LANCZOS)
        shadow = Image.new("RGBA", emoji_img.size, (0, 0, 0, 0))
        shadow.paste((0, 0, 0, 80), mask=emoji_img.split()[3])
        shadow = shadow.filter(ImageFilter.GaussianBlur(4))
        x = (size - emoji_size) // 2
        y = (size - emoji_size) // 2
        img.paste(shadow, (x + 4, y + 4), shadow)
        img.paste(emoji_img, (x, y), emoji_img)
    except Exception:
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", int(size * 0.7))
        except Exception:
            font = ImageFont.load_default()
        draw.text(
            (size / 2, size / 2),
            emoji,
            font=font,
            anchor="mm",
            embedded_color=True,
        )
    img.save(path / f"{user.id}.png")


async def _sticker_avatar(bot: Bot, user: User, sticker: Sticker) -> None:
    path = Path(settings.AVATAR_DIR)
    path.mkdir(exist_ok=True)
    buf = BytesIO()
    await bot.download(sticker.file_id, destination=buf)
    buf.seek(0)
    size = AVATAR_SIZE
    max_size = int(size * 0.8)
    try:
        img = Image.open(buf).convert("RGBA")
    except Exception:
        img = None
        if sticker.is_animated and not sticker.is_video:
            try:
                buf.seek(0)
                data = gzip.decompress(buf.read()).decode("utf-8")
                anim = LottieAnimation(data=data)
                width, height = anim.lottie_animation_get_size()
                scale = max_size / max(width, height)
                img = anim.render_pillow_frame(
                    width=int(width * scale), height=int(height * scale)
                ).convert("RGBA")
            except Exception:
                img = None
        if img is None:
            if sticker.thumbnail:
                buf = BytesIO()
                await bot.download(sticker.thumbnail.file_id, destination=buf)
                buf.seek(0)
                img = Image.open(buf).convert("RGBA")
            else:
                raise
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    if sticker.is_animated or sticker.is_video:
        scale = max_size / max(img.width, img.height)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    else:
        img.thumbnail((max_size, max_size), Image.LANCZOS)
    background = _gradient(size)
    x = (size - img.width) // 2
    y = (size - img.height) // 2
    background.alpha_composite(img, dest=(x, y))
    background.save(path / f"{user.id}.png")


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

