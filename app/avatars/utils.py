from __future__ import annotations

import random
from typing import TYPE_CHECKING

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageMath, ImageStat

if TYPE_CHECKING:  # pragma: no cover
    pass


def _gradient(size: int) -> Image.Image:
    """Create a colorful four-corner gradient image."""
    corners = [tuple(random.randint(0, 255) for _ in range(3)) for _ in range(4)]
    img = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(img)
    for x in range(size):
        rx = x / (size - 1)
        for y in range(size):
            ry = y / (size - 1)
            top = [int(corners[0][i] * (1 - rx) + corners[1][i] * rx) for i in range(3)]
            bottom = [int(corners[2][i] * (1 - rx) + corners[3][i] * rx) for i in range(3)]
            r = int(top[0] * (1 - ry) + bottom[0] * ry)
            g = int(top[1] * (1 - ry) + bottom[1] * ry)
            b = int(top[2] * (1 - ry) + bottom[2] * ry)
            draw.point((x, y), fill=(r, g, b, 255))
    return img


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
