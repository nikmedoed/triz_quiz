import sys
import pathlib
from PIL import Image

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from app.avatars import _resize_fit_rgba


def test_premultiplied_resize_preserves_color():
    img = Image.new("RGBA", (1, 2))
    img.putpixel((0, 0), (0, 0, 0, 0))
    img.putpixel((0, 1), (255, 0, 0, 255))

    out = _resize_fit_rgba(img, 1, allow_upscale=False)
    assert out.size == (1, 1)
    r, g, b, a = out.getpixel((0, 0))
    assert a == 128
    assert r >= 250 and g == 0 and b == 0

