import sys
import pathlib
from PIL import Image

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from app.avatars import _downscale_high_quality


def test_premultiplied_resize_preserves_color():
    img = Image.new("RGBA", (1, 2))
    img.putpixel((0, 0), (0, 0, 0, 0))
    img.putpixel((0, 1), (255, 0, 0, 255))

    out = _downscale_high_quality(img, 1)
    assert out.size == (1, 1)
    r, g, b, a = out.getpixel((0, 0))
    assert a == 128
    assert r >= 250 and g == 0 and b == 0

