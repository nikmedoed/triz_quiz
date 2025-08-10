import random
from types import SimpleNamespace
from io import BytesIO

import pytest
from PIL import Image

from app.bot import _emoji_avatar, AVATAR_SIZE, cairosvg
from app.settings import settings


class DummyResponse:
    def __init__(self, content: bytes, url_store):
        self.content = content
        self._url_store = url_store

    def raise_for_status(self):
        pass


@pytest.mark.skipif(cairosvg is None, reason="cairosvg not installed")
def test_emoji_avatar_uses_svg(tmp_path, monkeypatch):
    random.seed(0)
    monkeypatch.setattr(settings, "AVATAR_DIR", str(tmp_path))

    url_holder = {}

    def fake_get(url, timeout=10):
        url_holder["url"] = url
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 36 36'>"
            "<circle cx='18' cy='18' r='18' fill='#FF0000'/></svg>"
        )
        return DummyResponse(svg.encode(), url_holder)

    monkeypatch.setattr("app.bot.requests.get", fake_get)

    user = SimpleNamespace(id=1)
    _emoji_avatar(tmp_path, user, "🔥")

    assert "/svg/" in url_holder["url"]
    file = tmp_path / "1.png"
    assert file.exists()
    img = Image.open(file)
    assert img.mode == "RGBA"
    assert img.size == (AVATAR_SIZE, AVATAR_SIZE)
    assert img.getpixel((AVATAR_SIZE // 2, AVATAR_SIZE // 2))[:3] == (255, 0, 0)


def test_emoji_avatar_font_fallback(tmp_path, monkeypatch):
    random.seed(0)
    monkeypatch.setattr(settings, "AVATAR_DIR", str(tmp_path))

    def fake_get(url, timeout=10):  # should not be called
        raise AssertionError("network not expected")

    monkeypatch.setattr("app.bot.requests.get", fake_get)
    monkeypatch.setattr("app.bot.cairosvg", None)

    user = SimpleNamespace(id=1)
    _emoji_avatar(tmp_path, user, "🔥")

    file = tmp_path / "1.png"
    assert file.exists()
    img = Image.open(file)
    assert img.mode == "RGBA"
    assert img.size == (AVATAR_SIZE, AVATAR_SIZE)
    # center pixel should be opaque even if the glyph is missing
    assert img.getpixel((AVATAR_SIZE // 2, AVATAR_SIZE // 2))[3] == 255
