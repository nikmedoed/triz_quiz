import random
from types import SimpleNamespace

import pathlib
import sys

from PIL import Image, ImageFont, ImageDraw

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from app.avatars import _emoji_avatar, AVATAR_SIZE
from app.settings import settings


def test_emoji_avatar_draws_text(tmp_path, monkeypatch):
    random.seed(0)
    monkeypatch.setattr(settings, "AVATAR_DIR", str(tmp_path))

    calls = {}

    default_font = ImageFont.load_default()

    def fake_truetype(font, size, *_, **__):
        calls["size"] = size
        return default_font

    monkeypatch.setattr(ImageFont, "truetype", fake_truetype)

    original_text = ImageDraw.ImageDraw.text

    def fake_text(self, xy, text, font=None, anchor=None, embedded_color=False):
        calls["text"] = text
        return original_text(self, xy, text, font=font, anchor=anchor, embedded_color=embedded_color)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", fake_text)

    user = SimpleNamespace(id=1)
    _emoji_avatar(tmp_path, user, "🔥")

    file = tmp_path / "1.png"
    assert file.exists()
    img = Image.open(file)
    assert img.size == (AVATAR_SIZE, AVATAR_SIZE)
    assert calls["size"] == int(AVATAR_SIZE * 0.7)
    assert calls["text"] == "🔥"
