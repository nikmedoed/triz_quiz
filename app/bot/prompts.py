from __future__ import annotations

from aiogram import Bot

from app.bot.media_cache import send_photo_album_cached, send_photo_cached
from app.models import Step, User
from app.step_types import STEP_TYPES


async def build_prompt_messages(user: User, step: Step, phase: int):
    handler = STEP_TYPES.get(step.type)
    if handler and handler.build_bot_prompts:
        return await handler.build_bot_prompts(user, step, phase)
    return []


async def send_prompt(
        bot: Bot, user: User, step: Step, phase: int, prefix: str | None = None
):
    handler = STEP_TYPES.get(step.type)
    if handler and handler.on_prompt_pre:
        await handler.on_prompt_pre(bot, user, step, phase)
    raw_msgs = await build_prompt_messages(user, step, phase)

    msgs = []
    for item in raw_msgs:
        if isinstance(item, dict):
            msgs.append(item)
        else:
            text, kwargs = item
            msgs.append({"type": "text", "text": text, "kwargs": kwargs})

    if prefix:
        for msg in msgs:
            if msg.get("type") == "text":
                text = msg.get("text", "")
                sep = "\n\n" if text else ""
                msg["text"] = f"{prefix}{sep}{text}"
                break
        else:
            msgs.insert(0, {"type": "text", "text": prefix, "kwargs": {}})

    photo_buffer: list[dict] = []

    async def flush_photos() -> None:
        nonlocal photo_buffer
        if not photo_buffer:
            return
        if len(photo_buffer) == 1:
            msg = photo_buffer[0]
            sent_items = [
                await send_photo_cached(
                    bot,
                    user.id,
                    msg.get("path", ""),
                    caption=msg.get("caption"),
                    **(msg.get("kwargs") or {}),
                )
            ]
        else:
            sent_items = await send_photo_album_cached(bot, user.id, photo_buffer)
        if handler and handler.on_prompt_post:
            for sent in sent_items:
                if sent:
                    await handler.on_prompt_post(bot, user, step, phase, sent)
        photo_buffer = []

    for msg in msgs:
        msg_type = msg.get("type", "text")
        if msg_type == "photo":
            photo_buffer.append(msg)
            continue

        await flush_photos()
        sent = await bot.send_message(user.id, msg.get("text", ""), **(msg.get("kwargs") or {}))
        if sent and handler and handler.on_prompt_post:
            await handler.on_prompt_post(bot, user, step, phase, sent)

    await flush_photos()
