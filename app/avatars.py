"""Avatar generation utilities."""

from __future__ import annotations

import random
import gzip
import json
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

import requests
from cairosvg import svg2png
from PIL import (
    Image,
    ImageChops,
    ImageDraw,
    ImageFont,
    ImageFilter,
    ImageMath,
    ImageStat,
)

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
    # Heuristic: tiny glyph means missing character (e.g., placeholder cross)
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

    emoji_img = _render_emoji_from_font(emoji, emoji_size)
    if emoji_img is None:
        try:
            codepoints = "-".join(f"{ord(c):x}" for c in emoji)
            url = f"https://emojiapi.dev/api/v1/{codepoints}/512.png"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            emoji_img = Image.open(BytesIO(resp.content)).convert("RGBA")
            emoji_img = emoji_img.resize((emoji_size, emoji_size), Image.LANCZOS)
        except Exception:
            # Last resort: placeholder transparent square
            emoji_img = Image.new("RGBA", (emoji_size, emoji_size), (0, 0, 0, 0))
    shadow = Image.new("RGBA", emoji_img.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 80), mask=emoji_img.split()[3])
    shadow = shadow.filter(ImageFilter.GaussianBlur(4))
    x = (size - emoji_img.width) // 2
    y = (size - emoji_img.height) // 2
    img.paste(shadow, (x + 4, y + 4), shadow)
    img.paste(emoji_img, (x, y), emoji_img)
    img.save(path / f"{user.id}.png")


def _resize_fit_rgba(img: Image.Image, target_max: int, allow_upscale: bool) -> Image.Image:
    """Resize to target_max using premultiplied alpha; optionally upscale."""
    w, h = img.size
    if w == 0 or h == 0:
        return img

    scale = target_max / max(w, h)
    if scale >= 1.0 and not allow_upscale:
        return img

    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    r, g, b, a = img.split()
    r = ImageChops.multiply(r, a)
    g = ImageChops.multiply(g, a)
    b = ImageChops.multiply(b, a)

    r = r.resize(new_size, Image.LANCZOS)
    g = g.resize(new_size, Image.LANCZOS)
    b = b.resize(new_size, Image.LANCZOS)
    a = a.resize(new_size, Image.LANCZOS)

    r = ImageMath.eval("convert(r*255/(a+(a==0)), 'L')", r=r, a=a)
    g = ImageMath.eval("convert(g*255/(a+(a==0)), 'L')", g=g, a=a)
    b = ImageMath.eval("convert(b*255/(a+(a==0)), 'L')", b=b, a=a)

    return Image.merge("RGBA", (r, g, b, a))


def _pick_nice_frame_index(total_frames: int) -> int:
    """Heuristic: take ~30% into the animation."""
    if total_frames <= 1:
        return 0
    idx = int(total_frames * 0.3)
    return max(0, min(total_frames - 1, idx))


def _render_tgs_with_python_lottie_cli(
    tgs_gz_bytes: bytes, target_max: int, oversample: int = 4
) -> Image.Image | None:
    """Render one crisp frame from a .tgs using python-lottie's CLI."""
    frame_index = 0
    try:
        data = gzip.decompress(tgs_gz_bytes).decode("utf-8")
        j = json.loads(data)
        ip = int(j.get("ip", 0))
        op = int(j.get("op", ip + 1))
        total_frames = max(1, op - ip)
        frame_index = _pick_nice_frame_index(total_frames)
    except Exception:
        frame_index = 0

    with tempfile.TemporaryDirectory() as td:
        in_path = Path(td) / "input.tgs"
        out_svg = Path(td) / "frame.svg"
        in_path.write_bytes(tgs_gz_bytes)
        cmd = [
            "lottie_convert.py",
            str(in_path),
            str(out_svg),
            "--frame",
            str(frame_index),
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            svg_bytes = out_svg.read_bytes()
        except Exception:
            return None

    big = target_max * oversample
    try:
        png_bytes = svg2png(bytestring=svg_bytes, output_width=big, output_height=big)
        img = Image.open(BytesIO(png_bytes)).convert("RGBA")
    except Exception:
        return None
    return _resize_fit_rgba(img, target_max, allow_upscale=False)


def _extract_webm_frame_rgba(webm_bytes: bytes, sec: float = 0.5) -> Image.Image | None:
    """Use ffmpeg to grab a single RGBA PNG frame with alpha preserved."""
    cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-ss",
        f"{sec}",
        "-frames:v",
        "1",
        "-pix_fmt",
        "rgba",
        "-f",
        "image2",
        "-vcodec",
        "png",
        "pipe:1",
    ]
    try:
        proc = subprocess.run(
            cmd, input=webm_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
        )
        return Image.open(BytesIO(proc.stdout)).convert("RGBA")
    except Exception:
        return None


def _auto_crop(img: Image.Image) -> Image.Image:
    """Crop by alpha channel with small padding."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    a = img.split()[3]
    bbox = a.getbbox()
    if not bbox:
        return img
    left, top, right, bottom = bbox
    pad = max(2, int(0.01 * max(img.width, img.height)))
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(img.width, right + pad)
    bottom = min(img.height, bottom + pad)
    return img.crop((left, top, right, bottom))


def _post_sharpen(img: Image.Image) -> Image.Image:
    """Very mild sharpening after downscale."""
    edge_var = ImageStat.Stat(img.filter(ImageFilter.FIND_EDGES).convert("L")).var[0]
    if edge_var < 8:
        return img
    return img.filter(ImageFilter.UnsharpMask(radius=0.8, percent=40, threshold=4))


async def _sticker_avatar(bot: Bot, user: User, sticker: Sticker, target_size: int = AVATAR_SIZE) -> None:
    """Extract a crisp frame from a Telegram sticker and save an avatar."""
    path = Path(settings.AVATAR_DIR)
    path.mkdir(exist_ok=True)

    buf = BytesIO()
    await bot.download(sticker.file_id, destination=buf)
    data_bytes = buf.getvalue()

    size = target_size
    max_size = int(size * 0.9)
    img = None

    try:
        img = Image.open(BytesIO(data_bytes)).convert("RGBA")
    except Exception:
        img = None

    if img is None and sticker.is_animated and not sticker.is_video:
        img = _render_tgs_with_python_lottie_cli(
            data_bytes, target_max=max_size, oversample=4
        )

    if img is None and sticker.is_video:
        img = _extract_webm_frame_rgba(data_bytes, sec=0.5)

    if img is None and getattr(sticker, "thumbnail", None):
        th_buf = BytesIO()
        await bot.download(sticker.thumbnail.file_id, destination=th_buf)
        th_buf.seek(0)
        img = Image.open(th_buf).convert("RGBA")

    if img is None:
        raise RuntimeError("Failed to decode sticker to an image")

    img = _auto_crop(img)
    if sticker.is_animated or sticker.is_video:
        img = _resize_fit_rgba(img, max_size, allow_upscale=True)
    else:
        img = _resize_fit_rgba(img, max_size, allow_upscale=False)
    if not (sticker.is_animated or sticker.is_video):
        img = _post_sharpen(img)

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
