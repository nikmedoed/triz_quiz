from __future__ import annotations

from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from app.models import User
from . import AVATAR_SIZE
from .utils import _gradient


def _possible_emoji_fonts() -> list[Path]:
    paths = [
        Path("/System/Library/Fonts/Apple Color Emoji.ttc"),
        Path("/System/Library/Fonts/Apple Color Emoji.ttf"),
        Path("C:/Windows/Fonts/seguiemj.ttf"),
        Path("C:/Windows/Fonts/SegoeUIEmoji.ttf"),
        Path("C:/Windows/Fonts/Segoe UI Emoji.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
        Path("/usr/share/fonts/truetype/joypixels/JoyPixels.ttf"),
        Path("/usr/share/fonts/truetype/twemoji/TwitterColorEmoji-SVGinOT.ttf"),
    ]
    return [p for p in paths if p.exists()]


def _load_emoji_font(size: int) -> ImageFont.ImageFont:
    for p in _possible_emoji_fonts():
        try:
            return ImageFont.truetype(str(p), size)
        except Exception:
            try:
                return ImageFont.truetype(str(p), size, index=0)
            except Exception:
                continue
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _render_emoji_from_font(emoji: str, target_size: int) -> Image.Image | None:
    """Render emoji via system fonts; return None if rendering failed."""
    render_scale = 4
    font_size = max(64, render_scale * target_size)
    font = _load_emoji_font(font_size)
    box = max(2 * font_size, render_scale * target_size * 2)
    img = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        draw.text((box // 2, box // 2), emoji, font=font, anchor="mm", embedded_color=True)
    except TypeError:
        draw.text((box // 2, box // 2), emoji, font=font, anchor="mm")
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    if not bbox:
        return None
    glyph = img.crop(bbox)
    if max(glyph.width, glyph.height) < box * 0.3:
        return None
    scale = target_size / max(glyph.width, glyph.height)
    new_size = (max(1, int(glyph.width * scale)), max(1, int(glyph.height * scale)))
    return glyph.resize(new_size, Image.LANCZOS)


def _emoji_avatar(path: Path, user: User, emoji: str) -> None:
    """Generate avatar from emoji image with a colorful gradient background."""
    size = AVATAR_SIZE
    img = _gradient(size)
    emoji_size = int(size * 0.8)

    from . import _render_emoji_from_font as _ref
    emoji_img = _ref(emoji, emoji_size)
    if emoji_img is None:
        try:
            codepoints = "-".join(f"{ord(c):x}" for c in emoji)
            url = f"https://emojiapi.dev/api/v1/{codepoints}/512.png"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            emoji_img = Image.open(BytesIO(resp.content)).convert("RGBA")
            emoji_img = emoji_img.resize((emoji_size, emoji_size), Image.LANCZOS)
        except Exception:
            emoji_img = Image.new("RGBA", (emoji_size, emoji_size), (0, 0, 0, 0))
    shadow = Image.new("RGBA", emoji_img.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 80), mask=emoji_img.split()[3])
    shadow = shadow.filter(ImageFilter.GaussianBlur(4))
    x = (size - emoji_img.width) // 2
    y = (size - emoji_img.height) // 2
    img.paste(shadow, (x + 4, y + 4), shadow)
    img.paste(emoji_img, (x, y), emoji_img)
    img.save(path / f"{user.id}.png")
