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
