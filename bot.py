"""Telegram-bot for TRIZ-quiz."""

import asyncio, aiohttp, json, logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from db import Database

bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())  # in-memory FSM
PROJECTOR_URL = settings.projector_url
db = Database(settings.db_file)

# ---------- простой статичный сценарий -------------
with open('scenario.json', encoding='utf-8') as f:
    SCENARIO = json.load(f)

step_idx = 0  # глобальный «шаг»
participants: dict[int, dict] = {}
answers_current: dict[int, str] = {}
votes_current: dict[int, str] = {}
ADMIN_ID = settings.admin_id  # ведущий
pending_names: set[int] = set()


def load_state() -> None:
    """Load quiz state from the database."""
    global step_idx, participants, answers_current, votes_current
    step_idx = db.get_step()
    participants = {
        row["id"]: {"name": row["name"], "score": row["score"]}
        for row in db.get_participants()
    }
    answers_current = db.get_responses(step_idx, "open")
    answers_current.update(db.get_responses(step_idx, "quiz"))
    votes_current = db.get_responses(step_idx, "vote")


load_state()

def current_step():
    return SCENARIO[step_idx] if step_idx < len(SCENARIO) else None

async def push(event: str, payload: dict):
    """Отправка данных на проектор."""
    async with aiohttp.ClientSession() as session:
        await session.post(PROJECTOR_URL, json={'event': event, 'payload': payload})

# ---------- регистрация ----------------------------
@dp.message(Command('start'))
async def start(msg: Message):
    pending_names.add(msg.from_user.id)
    await msg.answer("Введите ваше имя:")

@dp.message(lambda m: m.from_user.id in pending_names)
async def name_received(msg: Message):
    user = msg.from_user
    name = msg.text.strip()
    avatar = None
    photos = await bot.get_user_profile_photos(user.id, limit=1)
    if photos.total_count:
        file = await bot.get_file(photos.photos[0][-1].file_id)
        avatar = await bot.download_file(file.file_path)
    score = participants.get(user.id, {}).get("score", 0)
    participants[user.id] = {"name": name, "score": score}
    db.add_participant(user.id, name, avatar)
    pending_names.remove(user.id)
    await push(
        "participants",
        {
            "who": [
                {"id": uid, "name": p["name"]} for uid, p in participants.items()
            ]
        },
    )
    stage = db.get_stage()
    if stage == 1:
        await msg.answer("Вы зарегистрированы! Ожидайте начала.")
    elif stage == 2:
        step = current_step()
        if step:
            text = f"Сейчас идёт шаг: {step['title']}"
            if step.get('description'):
                text += f"\n{step['description']}"
            if step.get('options'):
                text += "\n" + "\n".join(
                    f"{i+1}. {opt}" for i, opt in enumerate(step['options'])
                )
            await msg.answer(text)
        else:
            await msg.answer("Викторина уже началась, ожидайте вопросов.")
    else:
        rating = db.get_rating()
        table = "\n".join(f"{n}: {s}" for n, s in rating)
        await msg.answer("Викторина завершена.\n" + table)

# ---------- ответы открытого вопроса ---------------
@dp.message(lambda m: db.get_stage() == 2 and current_step() and current_step()['type']=='open')
async def open_answer(msg: Message):
    answers_current[msg.from_user.id] = msg.text.strip()[:200]
    db.record_response(msg.from_user.id, step_idx, 'open', answers_current[msg.from_user.id])
    await msg.answer("Ответ принят!")
    await push('answer_in', {'name': msg.from_user.full_name})

# ---------- голосование ----------------------------
@dp.message(lambda m: db.get_stage() == 2 and current_step() and current_step()['type']=='vote')
async def vote(msg: Message):
    target = msg.text.strip()
    if target == msg.from_user.full_name:
        await msg.answer("За себя голосовать нельзя!")
    else:
        votes_current[msg.from_user.id] = target
        db.record_response(msg.from_user.id, step_idx, 'vote', target)
        await msg.answer("Голос учтён.")
        await push('vote_in', {'voter': msg.from_user.full_name})

# ---------- вариант-квиз ---------------------------
@dp.message(lambda m: db.get_stage() == 2 and current_step() and current_step()['type']=='quiz')
async def quiz_answer(msg: Message):
    answers_current[msg.from_user.id] = msg.text.strip().upper()
    db.record_response(msg.from_user.id, step_idx, 'quiz', answers_current[msg.from_user.id])
    await msg.answer("Ответ записан.")
    await push('answer_in', {'name': msg.from_user.full_name})

# ---------- команды ведущего -----------------------
@dp.message(Command('next'), lambda m: m.from_user.id == ADMIN_ID)
async def cmd_next(msg: Message):
    """Перейти к следующему шагу сценария."""
    global step_idx, answers_current, votes_current
    answers_current.clear(); votes_current.clear()
    step_idx += 1
    db.set_step(step_idx)
    step = current_step()
    if not step:
        await push('end', {})
        await msg.answer("Конец сценария.")
        return
    await push('step', step)
    await msg.answer(f"Шаг {step_idx+1}: {step['title']} отправлен на экран.")

@dp.message(Command('show_votes'), lambda m: m.from_user.id == ADMIN_ID)
async def cmd_show_votes(msg: Message):
    """Подвести итог голосования и начислить баллы."""
    tally = {}
    for voter, target in votes_current.items():
        tally[target] = tally.get(target, 0)+1
    # начисление баллов
    for user_id, target_name in votes_current.items():
        if target_name in [p['name'] for p in participants.values()]:
            pid = next(k for k,v in participants.items() if v['name']==target_name)
            participants[pid]['score'] += 1
            db.update_score(pid, 1)
    await push('votes_result', tally)
    await msg.answer("Результаты голосования выведены.")

@dp.message(Command('show_quiz'), lambda m: m.from_user.id == ADMIN_ID)
async def cmd_show_quiz(msg: Message):
    """Проверить правильные ответы, начислить баллы."""
    step = current_step()
    correct = step['correct']
    for uid, ans in answers_current.items():
        if ans.upper() == correct.upper():
            participants[uid]['score'] += step.get('points', 1)
            db.update_score(uid, step.get('points', 1))
    await push('quiz_result', {'correct': correct})
    await msg.answer("Итоги квиза выведены.")

@dp.message(Command('rating'), lambda m: m.from_user.id == ADMIN_ID)
async def cmd_rating(msg: Message):
    """Показать общий рейтинг."""
    rows = db.get_rating()
    txt = "\n".join(f"{name}: {score}" for name, score in rows)
    await msg.answer(txt)
    await push('rating', [{'name': name, 'score': score} for name, score in rows])


@dp.message(Command('reset'), lambda m: m.from_user.id == ADMIN_ID)
async def cmd_reset(msg: Message):
    """Сбросить состояние викторины."""
    global step_idx, participants, answers_current, votes_current
    step_idx = 0
    participants.clear()
    answers_current.clear()
    votes_current.clear()
    db.reset()
    await msg.answer("Состояние сброшено.")
    await push('participants', {'who': []})
    await push('reset', {})

def run_bot():
    """Запуск Telegram-бота."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))


if __name__ == '__main__':
    run_bot()
