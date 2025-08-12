import pathlib
import random
import sys
from io import BytesIO
from types import SimpleNamespace

import requests
from PIL import Image

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from app.avatars import _emoji_avatar, AVATAR_SIZE
from app.settings import settings


def test_emoji_avatar_prefers_font(tmp_path, monkeypatch):
    random.seed(0)
    monkeypatch.setattr(settings, "AVATAR_DIR", str(tmp_path))

    def fake_get(url, timeout):
        raise AssertionError("web request should not be used")

    monkeypatch.setattr(requests, "get", fake_get)

    import app.avatars as avatars

    called = {}

    def fake_render(emoji, target):
        called["emoji"] = emoji
        return Image.new("RGBA", (target, target), (0, 255, 0, 255))

    monkeypatch.setattr(avatars, "_render_emoji_from_font", fake_render)

    user = SimpleNamespace(id=1)
    _emoji_avatar(tmp_path, user, "🔥")

    assert called["emoji"] == "🔥"
    file = tmp_path / "1.png"
    assert file.exists()
    img = Image.open(file)
    assert img.size == (AVATAR_SIZE, AVATAR_SIZE)
    center = img.getpixel((AVATAR_SIZE // 2, AVATAR_SIZE // 2))
    assert center[:3] == (0, 255, 0)


def test_emoji_avatar_web_fallback(tmp_path, monkeypatch):
    random.seed(0)
    monkeypatch.setattr(settings, "AVATAR_DIR", str(tmp_path))

    import app.avatars as avatars

    def fake_render(emoji, target):
        return None

    monkeypatch.setattr(avatars, "_render_emoji_from_font", fake_render)

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

    user = SimpleNamespace(id=2)
    _emoji_avatar(tmp_path, user, "🔥")

    assert calls["url"].endswith("1f525/512.png")
    file = tmp_path / "2.png"
    assert file.exists()
    img = Image.open(file)
    center = img.getpixel((AVATAR_SIZE // 2, AVATAR_SIZE // 2))
    assert center[:3] == (255, 0, 0)
