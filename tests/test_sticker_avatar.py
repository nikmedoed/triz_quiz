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
        img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        img.save(destination, format="PNG")


def test_static_sticker(tmp_path, monkeypatch):
    async def run():
        monkeypatch.setattr(settings, "AVATAR_DIR", str(tmp_path))
        bot = DummyBot()
        sticker = SimpleNamespace(file_id="orig", is_animated=False, is_video=False, thumbnail=None)
        user = SimpleNamespace(id=1)
        await _sticker_avatar(bot, user, sticker)
        assert bot.downloaded == ["orig"]
        file = tmp_path / "1.png"
        assert file.exists()
        img = Image.open(file)
        assert img.mode == "RGBA"
        assert img.getpixel((0, 0))[3] == 0

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
        file = tmp_path / "2.png"
        assert file.exists()
        img = Image.open(file)
        assert img.mode == "RGBA"
        assert img.getpixel((0, 0))[3] == 0

    asyncio.run(run())
