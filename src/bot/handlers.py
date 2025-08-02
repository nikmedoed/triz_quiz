"""Telegram bot handlers for TRIZ quiz."""

import json
import time

import aiohttp
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from . import core

router = Router()


def step_filter(step_type: str):
    def check(_):
        step = core.current_step()
        return core.db.get_stage() == 2 and step and step.get('type') == step_type

    return check


@router.message(Command("start"))
async def start(msg: Message):
    core.pending_names.add(msg.from_user.id)
    await msg.answer("Введите ваше имя:")


@router.message(lambda m: m.from_user.id in core.pending_names)
async def name_received(msg: Message):
    user = msg.from_user
    name = msg.text.strip()
    avatar = None
    photos = await msg.bot.get_user_profile_photos(user.id, limit=1)
    if photos.total_count:
        file = await msg.bot.get_file(photos.photos[0][-1].file_id)
        avatar = (await msg.bot.download_file(file.file_path)).getvalue()
    score = core.participants.get(user.id, {}).get("score", 0)
    core.participants[user.id] = {"name": name, "score": score}
    core.db.add_participant(user.id, name, avatar)
    core.pending_names.remove(user.id)
    stage = core.db.get_stage()
    if stage == 1:
        await core.push(
            "participants",
            {
                "who": [
                    {"id": uid, "name": p["name"]} for uid, p in core.participants.items()
                ]
            },
        )
        await msg.answer("Вы зарегистрированы! Ожидайте начала.")
    elif stage == 2:
        step = core.current_step()
        if step:
            await msg.answer(core.format_step(step))
        else:
            await msg.answer("Викторина уже началась, ожидайте вопросов.")
        await core.send_progress()
    else:
        rows = core.db.get_leaderboard()
        await msg.answer("Викторина завершена.\n" + core.format_leaderboard(rows))


@router.message(step_filter('open'))
async def open_answer(msg: Message):
    text = msg.text.strip()[:200]
    core.record_answer(msg.from_user.id, 'open', text)
    await msg.answer(
        "Идея принята!\n\n<i>Вы можете изменить ответ, отправив новое сообщение. "
        "Редактирование сообщений не поддерживается, скопируйте, измените и пришлите новое</i>"
    )
    await core.send_progress()
    await core.push('answer_in', {'name': msg.from_user.full_name})


@router.callback_query(step_filter('vote'), lambda c: c.data.startswith('vote:'))
async def vote(cb: CallbackQuery):
    idea_id = int(cb.data.split(':')[1])
    idea = next((i for i in core.ideas if i['id'] == idea_id), None)
    if not idea or idea['user_id'] == cb.from_user.id:
        await cb.answer("За себя голосовать нельзя!", show_alert=True)
        return
    votes = core.votes_current.setdefault(cb.from_user.id, set())
    if idea_id in votes:
        votes.remove(idea_id)
    else:
        votes.add(idea_id)
    core.db.record_response(cb.from_user.id, core.step_idx, 'vote', json.dumps(list(votes)))
    core.last_answer_ts = time.time()
    kb = core.vote_keyboard_for(cb.from_user.id)
    await cb.message.edit_reply_markup(reply_markup=kb)
    await cb.answer("Голос учтён.")
    await core.send_progress()
    await core.push('vote_in', {'voter': cb.from_user.full_name})


@router.callback_query(step_filter('quiz'), lambda c: c.data.startswith('quiz:'))
async def quiz_answer(cb: CallbackQuery):
    ans = cb.data.split(':')[1]
    prev = core.answers_current.get(cb.from_user.id, {}).get('text')
    if prev == ans:
        await cb.answer("Этот вариант уже выбран.")
        return
    core.record_answer(cb.from_user.id, 'quiz', ans)
    step = core.current_step()
    kb = core.quiz_keyboard_for(step, cb.from_user.id)
    await cb.message.edit_reply_markup(reply_markup=kb)
    await cb.answer("Ответ записан.")
    await core.send_progress()
    await core.push('answer_in', {'name': cb.from_user.full_name})


@router.message(Command('next'), lambda m: m.from_user.id == core.ADMIN_ID)
async def cmd_next(msg: Message):
    base = core.PROJECTOR_URL.rsplit('/', 1)[0]
    async with aiohttp.ClientSession() as session:
        await session.post(f"{base}/next")
    await msg.answer("Переключение шага.")


@router.message(Command('rating'), lambda m: m.from_user.id == core.ADMIN_ID)
async def cmd_rating(msg: Message):
    rows = core.db.get_leaderboard()
    await msg.answer("Текущий рейтинг:\n" + core.format_leaderboard(rows))
    await core.broadcast_rating(rows)


@router.message(Command('reset'), lambda m: m.from_user.id == core.ADMIN_ID)
async def cmd_reset(msg: Message):
    core.step_idx = -1
    core.participants.clear()
    core.answers_current.clear()
    core.votes_current.clear()
    core.ideas = []
    core.vote_gains = {}
    core.db.reset()
    await msg.answer("Состояние сброшено.")
    await core.push('participants', {'who': []})
    await core.push('reset', {})
