from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select

import app.texts as texts
from app.avatars import _emoji_avatar, _sticker_avatar, save_avatar
from app.hub import hub
from app.models import User
from app.settings import settings
from ..avatars.emoji import EMOJI_SUGGESTION_POOL
from app.step_types import STEP_TYPES
from .context import get_ctx
from .prompts import send_prompt

router = Router()
PROFILE_NAME_CALLBACK = "name:profile"
AVATAR_EMOJI_CALLBACK = "avatar-emoji"
EMOJI_SUGGESTION_COUNT = 8


def _dedup_pool(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for token in items:
        emoji = token.strip()
        if not emoji or emoji in seen:
            continue
        seen.add(emoji)
        result.append(emoji)
    return result


EMOJI_POOL = _dedup_pool(list(EMOJI_SUGGESTION_POOL))
if len(EMOJI_POOL) < EMOJI_SUGGESTION_COUNT:
    EMOJI_POOL.extend(["😀", "😃", "😄", "😁", "😆", "😅", "😂", "🤣", "😊", "😇"])


def _encode_emoji(value: str) -> str:
    return "-".join(f"{ord(ch):x}" for ch in value)


def _decode_emoji(payload: str) -> str:
    chars: list[str] = []
    for chunk in payload.split("-"):
        if not chunk:
            continue
        try:
            chars.append(chr(int(chunk, 16)))
        except ValueError:
            return ""
    return "".join(chars)


def _profile_name_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=texts.PROFILE_NAME_BUTTON, callback_data=PROFILE_NAME_CALLBACK)
    ]])


def _pick_unique_emojis(pool: list[str], limit: int) -> list[str]:
    if not pool:
        return []
    if len(pool) <= limit:
        shuffled = pool.copy()
        random.shuffle(shuffled)
        return shuffled
    return random.sample(pool, k=limit)


async def _emoji_suggestions(session) -> list[str]:
    result = await session.execute(
        select(User.avatar_emoji).where(User.avatar_emoji.is_not(None))
    )
    used = {value for value in result.scalars().all() if value}
    available = [emoji for emoji in EMOJI_POOL if emoji not in used]
    selected = _pick_unique_emojis(available, EMOJI_SUGGESTION_COUNT)
    if len(selected) < EMOJI_SUGGESTION_COUNT:
        fallback = [emoji for emoji in EMOJI_POOL if emoji not in selected]
        selected.extend(_pick_unique_emojis(fallback, EMOJI_SUGGESTION_COUNT - len(selected)))
    return selected[:EMOJI_SUGGESTION_COUNT]


async def _avatar_keyboard(session) -> InlineKeyboardMarkup:
    emojis = await _emoji_suggestions(session)
    builder = InlineKeyboardBuilder()
    for emoji in emojis:
        encoded = _encode_emoji(emoji)
        builder.button(text=emoji, callback_data=f"{AVATAR_EMOJI_CALLBACK}:{encoded}")
    builder.adjust(4, 4)
    return builder.as_markup()


async def _send_avatar_prompt(session, reply: Callable[..., Awaitable[object]]) -> None:
    keyboard = await _avatar_keyboard(session)
    await reply(texts.ASK_AVATAR, reply_markup=keyboard)


async def _complete_emoji_avatar(bot: Bot, session, user, state, step, emoji: str) -> None:
    path = Path(settings.AVATAR_DIR)
    path.mkdir(exist_ok=True)
    _emoji_avatar(path, user, emoji)
    user.waiting_for_avatar = False
    user.avatar_emoji = emoji
    await session.commit()
    await hub.broadcast({"type": "reload"})
    await send_prompt(bot, user, step, state.phase, prefix=texts.NAME_SAVED)


async def _finish_name_update(bot: Bot, session, user, state, step, new_name: str,
                              reply: Callable[..., Awaitable[object]]) -> None:
    was_new = user.name == ""
    user.name = new_name
    user.waiting_for_name = False
    await session.commit()
    saved = await save_avatar(bot, user)
    if saved:
        user.avatar_emoji = None
        await session.commit()
    if was_new and not saved:
        user.waiting_for_avatar = True
        await session.commit()
        await _send_avatar_prompt(session, reply)
        return
    await hub.broadcast({"type": "reload"})
    await send_prompt(bot, user, step, state.phase, prefix=texts.NAME_SAVED)


def _profile_name_from_telegram(source_user) -> str | None:
    parts = []
    if source_user.last_name:
        parts.append(source_user.last_name.strip())
    if source_user.first_name:
        parts.append(source_user.first_name.strip())
    middle = getattr(source_user, "middle_name", None)
    if middle:
        parts.append(middle.strip())
    name = " ".join(part for part in parts if part)
    if name:
        return name.strip()
    full_name = getattr(source_user, "full_name", None)
    if full_name:
        full_name = full_name.strip()
        if full_name:
            return full_name
    username = source_user.username
    if username:
        return f"@{username}"
    return None


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        has_profile_photo = await save_avatar(bot, user)
        if has_profile_photo:
            user.avatar_emoji = None
        user.waiting_for_name = True
        await session.commit()
        if user.name:
            await message.answer(texts.CURRENT_NAME.format(name=user.name))
        else:
            await message.answer(texts.ENTER_NAME, reply_markup=_profile_name_keyboard())
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
                await _send_avatar_prompt(session, message.answer)
                return
            choice = emoji.split()[0]
            await _complete_emoji_avatar(bot, session, user, state, step, choice)
            return

        if user.waiting_for_name:
            new_name = message.text.strip()[:120]
            if not new_name:
                await message.answer(texts.NAME_EMPTY)
                return
            await _finish_name_update(bot, session, user, state, step, new_name, message.answer)
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
            user.avatar_emoji = None
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
        if prefix == AVATAR_EMOJI_CALLBACK:
            if not user.waiting_for_avatar:
                await cb.answer(texts.AVATAR_NOT_WAITING, show_alert=True)
                return
            emoji_choice = _decode_emoji(payload.strip())
            if not emoji_choice:
                await cb.answer(texts.AVATAR_INVALID, show_alert=True)
                return
            if cb.message:
                base = cb.message.text or texts.ASK_AVATAR
                note = texts.AVATAR_SELECTED.format(emoji=emoji_choice)
                try:
                    await cb.message.edit_text(f"{base}\n\n{note}")
                except TelegramBadRequest:
                    await cb.message.edit_reply_markup(reply_markup=None)
                    await cb.message.answer(note)
            else:
                await bot.send_message(cb.from_user.id, texts.AVATAR_SELECTED.format(emoji=emoji_choice))
            await _complete_emoji_avatar(bot, session, user, state, step, emoji_choice)
            await cb.answer()
            return
        if cb.data == PROFILE_NAME_CALLBACK:
            if not user.waiting_for_name:
                await cb.answer(texts.PROFILE_NAME_NOT_WAITING, show_alert=True)
                return
            profile_name = _profile_name_from_telegram(cb.from_user)
            if not profile_name:
                await cb.answer(texts.PROFILE_NAME_NOT_AVAILABLE, show_alert=True)
                return
            if cb.message:
                reply = cb.message.answer
            else:
                async def reply(text: str) -> None:
                    await bot.send_message(cb.from_user.id, text)
            await _finish_name_update(bot, session, user, state, step, profile_name[:120], reply)
            await cb.answer()
            return
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
