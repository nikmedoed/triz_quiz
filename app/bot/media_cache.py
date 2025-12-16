from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto, Message

_CACHE: Dict[str, str] = {}
_ROOT = Path(__file__).resolve().parent.parent.parent
_MEDIA_DIR = _ROOT / "media"
_MEDIA_KWARGS = {"caption", "parse_mode", "caption_entities", "has_spoiler"}
_GROUP_KWARGS = {
    "message_thread_id",
    "disable_notification",
    "protect_content",
    "reply_parameters",
    "allow_sending_without_reply",
}


def _resolve_media_path(path: str) -> Optional[Path]:
    """Return absolute media path if safe and exists."""
    if not path:
        return None
    relative = path.lstrip("/").replace("\\", "/")
    if not relative.startswith("media/"):
        return None
    safe_parts = [p for p in relative.split("/") if p and p not in {".", ".."}]
    if not safe_parts or safe_parts[0] != "media":
        return None
    full = _ROOT / Path("/".join(safe_parts))
    if not full.is_file():
        return None
    try:
        full.relative_to(_MEDIA_DIR)
    except ValueError:
        return None
    return full


async def send_photo_cached(
    bot: Bot,
    chat_id: int,
    path: str,
    caption: str | None = None,
    **kwargs,
) -> Message | None:
    """Send photo using cached Telegram file_id when available."""
    full_path = _resolve_media_path(path)
    if not full_path:
        return None

    key = str(full_path)
    file_id = _CACHE.get(key)

    if file_id:
        return await bot.send_photo(chat_id, file_id, caption=caption, **kwargs)

    msg = await bot.send_photo(chat_id, FSInputFile(full_path), caption=caption, **kwargs)
    if msg.photo:
        _CACHE[key] = msg.photo[-1].file_id
    return msg


def _filter_kwargs(src: dict | None, allowed: set[str]) -> dict:
    if not src:
        return {}
    return {k: v for k, v in src.items() if k in allowed}


async def send_photo_album_cached(
    bot: Bot,
    chat_id: int,
    photos: list[dict],
) -> list[Message]:
    """Send a batch of photos as an album, reusing cached file IDs when possible."""
    prepared: list[InputMediaPhoto] = []
    meta: list[tuple[str, Path]] = []
    payload_items: list[dict] = []
    for item in photos:
        full_path = _resolve_media_path(item.get("path", ""))
        if not full_path:
            continue
        key = str(full_path)
        file_id = _CACHE.get(key)
        kwargs = _filter_kwargs(item.get("kwargs"), _MEDIA_KWARGS)
        caption = item.get("caption", kwargs.get("caption"))
        media = file_id or FSInputFile(full_path)
        prepared.append(
            InputMediaPhoto(
                media=media,
                caption=caption,
                parse_mode=kwargs.get("parse_mode"),
                caption_entities=kwargs.get("caption_entities"),
                has_spoiler=kwargs.get("has_spoiler"),
            )
        )
        meta.append((key, full_path))
        payload_items.append(item)

    if not prepared:
        return []

    # send_media_group requires at least 2 items; fall back to single-photo flow
    if len(prepared) == 1:
        item = payload_items[0]
        msg = await send_photo_cached(
            bot,
            chat_id,
            item.get("path", ""),
            caption=item.get("caption"),
            **(item.get("kwargs") or {}),
        )
        return [msg] if msg else []

    group_kwargs = _filter_kwargs(payload_items[0].get("kwargs"), _GROUP_KWARGS)
    messages = await bot.send_media_group(chat_id, prepared, **group_kwargs)
    for msg, (key, _) in zip(messages, meta):
        if msg and msg.photo:
            _CACHE[key] = msg.photo[-1].file_id
    return messages
