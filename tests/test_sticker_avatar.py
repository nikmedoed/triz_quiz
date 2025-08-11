import asyncio
import random
from types import SimpleNamespace
from io import BytesIO

from PIL import Image

from app.avatars import _sticker_avatar, AVATAR_SIZE, _render_tgs_high_quality
from app.settings import settings


class DummyBot:
    def __init__(self, orig_valid=True):
        self.downloaded = []
        self.orig_valid = orig_valid

    async def download(self, file_id: str, destination: BytesIO):
        self.downloaded.append(file_id)
        if file_id == "orig" and not self.orig_valid:
            destination.write(b"bad")
            return
        size = 300 if file_id == "orig" else 50
        img = Image.new("RGBA", (size, size), (255, 0, 0, 255))
        img.save(destination, format="PNG")


def test_static_sticker(tmp_path, monkeypatch):
    async def run():
        random.seed(0)
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
        assert img.size == (AVATAR_SIZE, AVATAR_SIZE)
        assert img.getpixel((0, 0))[3] == 255
        assert img.getpixel((0, 0)) != img.getpixel((AVATAR_SIZE - 1, AVATAR_SIZE - 1))

    asyncio.run(run())


def test_animated_sticker_uses_original(tmp_path, monkeypatch):
    async def run():
        random.seed(0)
        monkeypatch.setattr(settings, "AVATAR_DIR", str(tmp_path))
        bot = DummyBot()
        thumb = SimpleNamespace(file_id="thumb")
        sticker = SimpleNamespace(file_id="orig", is_animated=True, is_video=False, thumbnail=thumb)
        user = SimpleNamespace(id=2)
        await _sticker_avatar(bot, user, sticker)
        assert bot.downloaded == ["orig"]
        file = tmp_path / "2.png"
        assert file.exists()
        img = Image.open(file)
        assert img.mode == "RGBA"
        assert img.size == (AVATAR_SIZE, AVATAR_SIZE)
        assert img.getpixel((0, 0))[3] == 255
        assert img.getpixel((0, 0)) != img.getpixel((AVATAR_SIZE - 1, AVATAR_SIZE - 1))
        bbox = img.getbbox()
        assert bbox[2] - bbox[0] >= 200
        assert bbox[3] - bbox[1] >= 200

    asyncio.run(run())


def test_animated_sticker_fallback_to_thumbnail(tmp_path, monkeypatch):
    async def run():
        random.seed(0)
        monkeypatch.setattr(settings, "AVATAR_DIR", str(tmp_path))
        bot = DummyBot(orig_valid=False)
        thumb = SimpleNamespace(file_id="thumb")
        sticker = SimpleNamespace(file_id="orig", is_animated=True, is_video=False, thumbnail=thumb)
        user = SimpleNamespace(id=3)
        await _sticker_avatar(bot, user, sticker)
        assert bot.downloaded == ["orig", "thumb"]
        file = tmp_path / "3.png"
        assert file.exists()
        img = Image.open(file)
        assert img.mode == "RGBA"
        assert img.size == (AVATAR_SIZE, AVATAR_SIZE)
        assert img.getpixel((0, 0))[3] == 255
        assert img.getpixel((0, 0)) != img.getpixel((AVATAR_SIZE - 1, AVATAR_SIZE - 1))
        bbox = img.getbbox()
        assert bbox[2] - bbox[0] >= 200
        assert bbox[3] - bbox[1] >= 200

    asyncio.run(run())


def test_render_tgs_high_quality(monkeypatch):
    calls = {}

    class DummyAnim:
        def __init__(self, data: str):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def lottie_animation_get_size(self):
            return (100, 50)

        def lottie_animation_get_totalframe(self):
            return 10

        def render_pillow_frame(self, frame_num: int, width: int, height: int):
            self.calls.append((frame_num, width, height))
            return Image.new("RGBA", (width, height), (255, 0, 0, 255))

    class DummyLottie:
        @staticmethod
        def from_data(data: str):
            calls["anim"] = DummyAnim(data)
            return calls["anim"]

    monkeypatch.setattr("app.avatars.LottieAnimation", DummyLottie)

    img = _render_tgs_high_quality(b"{}", target_max=64, oversample=2)
    assert img is not None
    assert img.size == (64, 32)
    anim = calls["anim"]
    assert anim.calls[0][1:] == (128, 64)
