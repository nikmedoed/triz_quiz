"""Telegram bot handlers for TRIZ quiz."""

import json
import time

import aiohttp
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from . import core, formatting, state

router = Router()


def step_filter(step_type: str):
    def check(_):
        step = state.current_step()
        return state.db.get_stage() == 2 and step and step.get('type') == step_type

    return check


async def send_current_step(uid: int, bot) -> None:
    stage = state.db.get_stage()
    if stage == 1:
        await bot.send_message(uid, "Вы зарегистрированы! Ожидайте начала.")
        return
    if stage == 2:
        step = state.current_step()
        if step:
            text = formatting.format_step(step)
            if step["type"] == "quiz":
                kb = formatting.quiz_keyboard_for(step, uid)
            elif step["type"] == "vote":
                kb = formatting.vote_keyboard_for(uid)
            else:
                kb = None
            await bot.send_message(uid, text, reply_markup=kb)
        else:
            await bot.send_message(uid, "Викторина уже началась, ожидайте вопросов.")
        await core.send_progress()
        return
    rows = state.db.get_leaderboard()
    await bot.send_message(
        uid, "Викторина завершена.\n" + formatting.format_leaderboard(rows)
    )


@router.message(Command("start"))
async def start(msg: Message):
    uid = msg.from_user.id
    state.pending_names.add(uid)
    kb = None
    if uid in state.participants:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Отменить", callback_data="cancel_name")]]
        )
    await msg.answer("Введите ваше имя:", reply_markup=kb)


@router.message(lambda m: m.from_user.id in state.pending_names)
async def name_received(msg: Message):
    user = msg.from_user
    name = msg.text.strip()
    avatar = None
    photos = await msg.bot.get_user_profile_photos(user.id, limit=1)
    if photos.total_count:
        file = await msg.bot.get_file(photos.photos[0][-1].file_id)
        avatar = (await msg.bot.download_file(file.file_path)).getvalue()
    score = state.participants.get(user.id, {}).get("score", 0)
    state.participants[user.id] = {"name": name, "score": score}
    state.db.add_participant(user.id, name, avatar)
    state.pending_names.remove(user.id)
    stage = state.db.get_stage()
    if stage == 1:
        await core.push(
            "participants",
            {
                "who": [
                    {"id": uid, "name": p["name"]} for uid, p in state.participants.items()
                ]
            },
        )
        await msg.answer("Вы зарегистрированы! Ожидайте начала.")
        return
    await send_current_step(user.id, msg.bot)


@router.callback_query(lambda c: c.data == "cancel_name")
async def cancel_name(cb: CallbackQuery):
    uid = cb.from_user.id
    if uid in state.pending_names:
        state.pending_names.remove(uid)
    await cb.message.edit_text("Отменено.")
    await send_current_step(uid, cb.bot)
    await cb.answer()


@router.message(step_filter('open'))
async def open_answer(msg: Message):
    text = msg.text.strip()[:200]
    state.record_answer(msg.from_user.id, 'open', text)
    await msg.answer(
        "Идея принята!\n\n<i>Вы можете изменить ответ, отправив новое сообщение. "
        "Редактирование сообщений не поддерживается, скопируйте, измените и пришлите новое</i>"
    )
    await core.send_progress()
    await core.push('answer_in', {'name': msg.from_user.full_name})


@router.callback_query(step_filter('vote'), lambda c: c.data.startswith('vote:'))
async def vote(cb: CallbackQuery):
    idea_id = int(cb.data.split(':')[1])
    idea = next((i for i in state.ideas if i['id'] == idea_id), None)
    if not idea or idea['user_id'] == cb.from_user.id:
        await cb.answer("За себя голосовать нельзя!", show_alert=True)
        return
    votes = state.votes_current.setdefault(cb.from_user.id, set())
    if idea_id in votes:
        votes.remove(idea_id)
    else:
        votes.add(idea_id)
    state.db.record_response(cb.from_user.id, state.step_idx, 'vote', json.dumps(list(votes)))
    state.last_answer_ts = time.time()
    kb = formatting.vote_keyboard_for(cb.from_user.id)
    await cb.message.edit_reply_markup(reply_markup=kb)
    await cb.answer("Голос учтён.")
    await core.send_progress()
    await core.push('vote_in', {'voter': cb.from_user.full_name})


@router.callback_query(step_filter('quiz'), lambda c: c.data.startswith('quiz:'))
async def quiz_answer(cb: CallbackQuery):
    ans = cb.data.split(':')[1]
    prev = state.answers_current.get(cb.from_user.id, {}).get('text')
    if prev == ans:
        await cb.answer("Этот вариант уже выбран.")
        return
    state.record_answer(cb.from_user.id, 'quiz', ans)
    step = state.current_step()
    kb = formatting.quiz_keyboard_for(step, cb.from_user.id)
    await cb.message.edit_reply_markup(reply_markup=kb)
    await cb.answer("Ответ записан.")
    await core.send_progress()
    await core.push('answer_in', {'name': cb.from_user.full_name})


@router.message(Command('next'), lambda m: m.from_user.id == state.ADMIN_ID)
async def cmd_next(msg: Message):
    base = state.PROJECTOR_URL.rsplit('/', 1)[0]
    async with aiohttp.ClientSession() as session:
        await session.post(f"{base}/next")
    await msg.answer("Переключение шага.")


@router.message(Command('rating'), lambda m: m.from_user.id == state.ADMIN_ID)
async def cmd_rating(msg: Message):
    rows = state.db.get_leaderboard()
    await msg.answer("Текущий рейтинг:\n" + formatting.format_leaderboard(rows))
    await core.broadcast_rating(rows)


@router.message(Command('reset'), lambda m: m.from_user.id == state.ADMIN_ID)
async def cmd_reset(msg: Message):
    state.step_idx = -1
    state.participants.clear()
    state.answers_current.clear()
    state.votes_current.clear()
    state.ideas = []
    state.vote_gains = {}
    state.db.reset()
    await msg.answer("Состояние сброшено.")
    await core.push('participants', {'who': []})
    await core.push('reset', {})
