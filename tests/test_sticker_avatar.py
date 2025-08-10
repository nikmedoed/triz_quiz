import asyncio
from types import SimpleNamespace
from io import BytesIO

from PIL import Image

from app.bot import _sticker_avatar
from app.settings import settings


class DummyBot:
    def __init__(self):
        self.downloaded = []

    async def download(self, file_id: str, destination: BytesIO):
        self.downloaded.append(file_id)
        img = Image.new("RGB", (10, 10), (123, 222, 111))
        img.save(destination, format="PNG")


def test_static_sticker(tmp_path, monkeypatch):
    async def run():
        monkeypatch.setattr(settings, "AVATAR_DIR", str(tmp_path))
        bot = DummyBot()
        sticker = SimpleNamespace(file_id="orig", is_animated=False, is_video=False, thumbnail=None)
        user = SimpleNamespace(id=1)
        await _sticker_avatar(bot, user, sticker)
        assert bot.downloaded == ["orig"]
        assert (tmp_path / "1.jpg").exists()

    asyncio.run(run())


def test_animated_sticker_uses_thumbnail(tmp_path, monkeypatch):
    async def run():
        monkeypatch.setattr(settings, "AVATAR_DIR", str(tmp_path))
        bot = DummyBot()
        thumb = SimpleNamespace(file_id="thumb")
        sticker = SimpleNamespace(file_id="orig", is_animated=True, is_video=False, thumbnail=thumb)
        user = SimpleNamespace(id=2)
        await _sticker_avatar(bot, user, sticker)
        assert bot.downloaded == ["thumb"]
        assert (tmp_path / "2.jpg").exists()

    asyncio.run(run())
