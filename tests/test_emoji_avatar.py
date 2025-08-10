import random
from types import SimpleNamespace
from io import BytesIO

import pathlib
import sys

import requests
from PIL import Image

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from app.avatars import _emoji_avatar, AVATAR_SIZE
from app.settings import settings


def test_emoji_avatar_downloads_image(tmp_path, monkeypatch):
    random.seed(0)
    monkeypatch.setattr(settings, "AVATAR_DIR", str(tmp_path))

    calls = {}

    def fake_get(url, timeout):
        calls["url"] = url
        img = Image.new("RGBA", (512, 512), (255, 0, 0, 255))
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        class Resp:
            content = buf.getvalue()
            def raise_for_status(self):
                return None
        return Resp()

    monkeypatch.setattr(requests, "get", fake_get)

    user = SimpleNamespace(id=1)
    _emoji_avatar(tmp_path, user, "🔥")

    assert calls["url"].endswith("1f525/512.png")
    file = tmp_path / "1.png"
    assert file.exists()
    img = Image.open(file)
    assert img.size == (AVATAR_SIZE, AVATAR_SIZE)
    center = img.getpixel((AVATAR_SIZE // 2, AVATAR_SIZE // 2))
    assert center[:3] == (255, 0, 0)
    left = (AVATAR_SIZE - int(AVATAR_SIZE * 0.8)) // 2
    right = left + int(AVATAR_SIZE * 0.8) - 1
    assert img.getpixel((left - 1, AVATAR_SIZE // 2))[:3] != (255, 0, 0)
    assert img.getpixel((left, AVATAR_SIZE // 2))[:3] == (255, 0, 0)
    assert img.getpixel((right, AVATAR_SIZE // 2))[:3] == (255, 0, 0)
    assert img.getpixel((right + 1, AVATAR_SIZE // 2))[:3] != (255, 0, 0)


def test_emoji_avatar_font_fallback(tmp_path, monkeypatch):
    random.seed(0)
    monkeypatch.setattr(settings, "AVATAR_DIR", str(tmp_path))

    def fake_get(url, timeout):
        raise requests.RequestException("fail")

    monkeypatch.setattr(requests, "get", fake_get)

    import app.avatars as avatars

    called = {}

    def fake_render(emoji, target):
        called["emoji"] = emoji
        called["target"] = target
        return Image.new("RGBA", (target, target), (0, 255, 0, 255))

    monkeypatch.setattr(avatars, "_render_emoji_from_font", fake_render)

    user = SimpleNamespace(id=2)
    avatars._emoji_avatar(tmp_path, user, "🔥")

    assert called["emoji"] == "🔥"
    assert called["target"] == int(AVATAR_SIZE * 0.8)
    file = tmp_path / "2.png"
    assert file.exists()
    img = Image.open(file)
    assert img.size == (AVATAR_SIZE, AVATAR_SIZE)
    center = img.getpixel((AVATAR_SIZE // 2, AVATAR_SIZE // 2))
    assert center[:3] == (0, 255, 0)
    left = (AVATAR_SIZE - int(AVATAR_SIZE * 0.8)) // 2
    right = left + int(AVATAR_SIZE * 0.8) - 1
    assert img.getpixel((left - 1, AVATAR_SIZE // 2))[:3] != (0, 255, 0)
    assert img.getpixel((left, AVATAR_SIZE // 2))[:3] == (0, 255, 0)
    assert img.getpixel((right, AVATAR_SIZE // 2))[:3] == (0, 255, 0)
    assert img.getpixel((right + 1, AVATAR_SIZE // 2))[:3] != (0, 255, 0)
