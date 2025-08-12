from __future__ import annotations

from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

import app.texts as texts
from app.avatars import _emoji_avatar, _sticker_avatar, save_avatar
from app.hub import hub
from app.settings import settings
from app.step_types import STEP_TYPES

from .context import get_ctx
from .prompts import send_prompt


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        await save_avatar(bot, user)
        user.waiting_for_name = True
        await session.commit()
        if user.name:
            await message.answer(texts.CURRENT_NAME.format(name=user.name))
        else:
            await message.answer(texts.ENTER_NAME)
    finally:
        await session.close()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        user.waiting_for_name = False
        await session.commit()
        await send_prompt(bot, user, step, state.phase, prefix=texts.NAME_UNCHANGED)
    finally:
        await session.close()


@router.message(F.text & ~F.via_bot)
async def on_text(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        if user.waiting_for_avatar:
            emoji = message.text.strip()
            if not emoji:
                await message.answer(texts.ASK_AVATAR)
                return
            path = Path(settings.AVATAR_DIR)
            path.mkdir(exist_ok=True)
            _emoji_avatar(path, user, emoji[0])
            user.waiting_for_avatar = False
            await session.commit()
            await hub.broadcast({"type": "reload"})
            await send_prompt(bot, user, step, state.phase, prefix=texts.NAME_SAVED)
            return

        if user.waiting_for_name:
            new_name = message.text.strip()[:120]
            if not new_name:
                await message.answer(texts.NAME_EMPTY)
                return
            was_new = user.name == ""
            user.name = new_name
            user.waiting_for_name = False
            await session.commit()
            saved = await save_avatar(bot, user)
            if was_new and not saved:
                user.waiting_for_avatar = True
                await session.commit()
                await message.answer(texts.ASK_AVATAR)
            else:
                await hub.broadcast({"type": "reload"})
                await send_prompt(bot, user, step, state.phase, prefix=texts.NAME_SAVED)
            return

        handler = STEP_TYPES.get(step.type)
        if handler and handler.on_text:
            handled = await handler.on_text(message, bot, session, user, state, step)
            if handled:
                return
        await message.answer(texts.TEXT_NOT_ACCEPTED)
    finally:
        await session.close()


@router.message(F.sticker)
async def on_sticker(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        if user.waiting_for_avatar:
            await _sticker_avatar(bot, user, message.sticker)
            user.waiting_for_avatar = False
            await session.commit()
            await hub.broadcast({"type": "reload"})
            await send_prompt(bot, user, step, state.phase, prefix=texts.NAME_SAVED)
    finally:
        await session.close()


@router.callback_query(F.data.contains(":"))
async def on_callback(cb: CallbackQuery, bot: Bot):
    prefix, payload = cb.data.split(":", 1)
    session, user, state, step = await get_ctx(str(cb.from_user.id))
    try:
        handler = STEP_TYPES.get(step.type)
        if handler and handler.callback_prefix == prefix and handler.on_callback:
            await handler.on_callback(cb, bot, session, user, state, step, payload)
        else:
            fallback = next(
                (h for h in STEP_TYPES.values() if h.callback_prefix == prefix),
                None,
            )
            msg = fallback.callback_error if fallback else texts.NOT_VOTE_PHASE
            await cb.answer(msg, show_alert=True)
    finally:
        await session.close()
