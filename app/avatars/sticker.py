from __future__ import annotations

import gzip
import subprocess
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from aiogram import Bot
from aiogram.types import Sticker

from app.models import User
from app.settings import settings
from . import AVATAR_SIZE
from .utils import _gradient, _resize_fit_rgba, _auto_crop, _post_sharpen

if TYPE_CHECKING:  # pragma: no cover
    from rlottie_python import LottieAnimation


def _pick_nice_frame_index(total_frames: int) -> int:
    """Heuristic: take ~30% into the animation."""
    if total_frames <= 1:
        return 0
    idx = int(total_frames * 0.3)
    return max(0, min(total_frames - 1, idx))


def _render_pillow_frame_scaled(anim: "LottieAnimation", frame_idx: int, w: int, h: int) -> Image.Image:
    """Render a frame at given size using available rlottie-python APIs."""
    try:
        im = anim.render_pillow_frame(frame_num=frame_idx, width=w, height=h)
        return im.convert("RGBA")
    except TypeError:
        pass
    try:
        buf = anim.lottie_animation_render(frame_num=frame_idx, width=w, height=h)
        im = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA")
        return im.convert("RGBA")
    except TypeError:
        pass
    buf = anim.lottie_animation_render(frame_num=frame_idx)
    w0, h0 = anim.lottie_animation_get_size()
    im0 = Image.frombuffer("RGBA", (w0, h0), buf, "raw", "BGRA").convert("RGBA")
    if (w0, h0) != (w, h):
        im0 = im0.resize((w, h), Image.LANCZOS)
    return im0


def _render_tgs_high_quality(tgs_bytes: bytes, target_max: int, oversample: int = 4) -> Image.Image | None:
    """Render a crisp RGBA frame from .tgs using rlottie if available."""
    try:
        import rlottie
        anim = rlottie.Animation.from_tgs(tgs_bytes)
        w, h = anim.width(), anim.height()
        total_frames = anim.totalFrame() or 1
        f = _pick_nice_frame_index(total_frames)
        scale = (target_max * oversample) / max(w, h)
        W, H = max(1, int(w * scale)), max(1, int(h * scale))
        bgra = anim.render(f, W, H)
        img = Image.frombytes("RGBA", (W, H), bgra, "raw", "BGRA")
        return _resize_fit_rgba(img, target_max, allow_upscale=False)
    except Exception:
        pass
    from . import LottieAnimation
    data = tgs_bytes.decode("utf-8")
    with LottieAnimation.from_data(data) as anim:
        w, h = anim.lottie_animation_get_size()
        total_frames = getattr(anim, "lottie_animation_get_totalframe", lambda: 1)() or 1
        f = _pick_nice_frame_index(total_frames)
        scale = (target_max * oversample) / max(w, h)
        W, H = max(1, int(w * scale)), max(1, int(h * scale))
        img = _render_pillow_frame_scaled(anim, f, W, H)
        return _resize_fit_rgba(img, target_max, allow_upscale=False)


def _extract_webm_frame_rgba(webm_bytes: bytes, sec: float = 0.5) -> Image.Image | None:
    """Use ffmpeg to grab a single RGBA PNG frame with alpha preserved."""
    cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-ss",
        f"{sec}",
        "-i",
        "pipe:0",
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


async def _sticker_avatar(bot: Bot, user: User, sticker: Sticker, target_size: int = AVATAR_SIZE) -> None:
    """Extract a crisp frame from a Telegram sticker and save an avatar."""
    path = Path(settings.AVATAR_DIR)
    path.mkdir(exist_ok=True)

    buf = BytesIO()
    await bot.download(sticker.file_id, destination=buf)
    data_bytes = buf.getvalue()

    size = target_size
    max_size = int(size * 0.8)
    img = None

    try:
        img = Image.open(BytesIO(data_bytes)).convert("RGBA")
    except Exception:
        img = None

    if img is None and sticker.is_animated and not sticker.is_video:
        try:
            tgs = gzip.decompress(data_bytes)
            img = _render_tgs_high_quality(tgs_bytes=tgs, target_max=max_size, oversample=4)
        except Exception:
            img = None

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
