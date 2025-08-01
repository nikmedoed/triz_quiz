"""Telegram-bot for TRIZ-quiz."""

import asyncio, aiohttp, json, logging, os
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from config import settings
from db import Database

bot = Bot(settings.bot_token, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())  # in-memory FSM
PROJECTOR_URL = settings.projector_url
STATE_FILE = settings.state_file
db = Database(settings.db_file)

# ---------- простой статичный сценарий -------------
with open('scenario.json', encoding='utf-8') as f:
    SCENARIO = json.load(f)

step_idx        = 0               # глобальный «шаг»
participants    = {}              # telegram_id -> {'name', 'score'}
answers_current = {}              # telegram_id -> answer text / quiz option
votes_current   = {}              # telegram_id -> voted_for(telegram_id)
ADMIN_ID        = settings.admin_id  # ведущий


def load_state():
    """Загрузить состояние викторины из файла."""
    global step_idx, participants, answers_current, votes_current
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding='utf-8') as f:
            data = json.load(f)
        step_idx = data.get('step_idx', 0)
        participants = {int(k): v for k, v in data.get('participants', {}).items()}
        answers_current = {int(k): v for k, v in data.get('answers_current', {}).items()}
        votes_current = {int(k): v for k, v in data.get('votes_current', {}).items()}


def save_state():
    """Сохранить текущее состояние викторины в файл."""
    data = {
        'step_idx': step_idx,
        'participants': {str(k): v for k, v in participants.items()},
        'answers_current': {str(k): v for k, v in answers_current.items()},
        'votes_current': {str(k): v for k, v in votes_current.items()},
    }
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def reset_state():
    """Очистить состояние и удалить файл хранения."""
    global step_idx, participants, answers_current, votes_current
    step_idx = 0
    participants.clear()
    answers_current.clear()
    votes_current.clear()
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)


load_state()
for pid, p in participants.items():
    db.add_participant(pid, p['name'], p['score'])

def current_step():
    return SCENARIO[step_idx] if step_idx < len(SCENARIO) else None

async def push(event: str, payload: dict):
    """Отправка данных на проектор."""
    async with aiohttp.ClientSession() as session:
        await session.post(PROJECTOR_URL, json={'event': event, 'payload': payload})

# ---------- регистрация ----------------------------
@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    user = msg.from_user
    participants[user.id] = {'name': user.full_name, 'score': 0}
    save_state()
    db.add_participant(user.id, user.full_name)
    await msg.answer("Вы зарегистрированы! Ожидайте вопросов.")
    await push('participants', {'who': list(p['name'] for p in participants.values())})

# ---------- ответы открытого вопроса ---------------
@dp.message_handler(lambda m: current_step() and current_step()['type']=='open')
async def open_answer(msg: types.Message):
    answers_current[msg.from_user.id] = msg.text.strip()[:200]
    save_state()
    db.record_response(msg.from_user.id, step_idx, 'open', answers_current[msg.from_user.id])
    await msg.answer("Ответ принят!")
    await push('answer_in', {'name': msg.from_user.full_name})

# ---------- голосование ----------------------------
@dp.message_handler(lambda m: current_step() and current_step()['type']=='vote')
async def vote(msg: types.Message):
    target = msg.text.strip()
    if target == msg.from_user.full_name:
        await msg.answer("За себя голосовать нельзя!")
    else:
        votes_current[msg.from_user.id] = target
        save_state()
        db.record_response(msg.from_user.id, step_idx, 'vote', target)
        await msg.answer("Голос учтён.")
        await push('vote_in', {'voter': msg.from_user.full_name})

# ---------- вариант-квиз ---------------------------
@dp.message_handler(lambda m: current_step() and current_step()['type']=='quiz')
async def quiz_answer(msg: types.Message):
    answers_current[msg.from_user.id] = msg.text.strip().upper()
    save_state()
    db.record_response(msg.from_user.id, step_idx, 'quiz', answers_current[msg.from_user.id])
    await msg.answer("Ответ записан.")
    await push('answer_in', {'name': msg.from_user.full_name})

# ---------- команды ведущего -----------------------
@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID, commands=['next'])
async def cmd_next(msg: types.Message):
    """Перейти к следующему шагу сценария."""
    global step_idx, answers_current, votes_current
    answers_current.clear(); votes_current.clear()
    step_idx += 1
    step = current_step()
    save_state()
    if not step:
        await push('end', {})
        await msg.answer("Конец сценария.")
        return
    await push('step', step)
    await msg.answer(f"Шаг {step_idx+1}: {step['title']} отправлен на экран.")

@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID, commands=['show_votes'])
async def cmd_show_votes(msg: types.Message):
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
    save_state()
    await push('votes_result', tally)
    await msg.answer("Результаты голосования выведены.")

@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID, commands=['show_quiz'])
async def cmd_show_quiz(msg: types.Message):
    """Проверить правильные ответы, начислить баллы."""
    step = current_step()
    correct = step['correct']
    for uid, ans in answers_current.items():
        if ans.upper() == correct.upper():
            participants[uid]['score'] += step.get('points', 1)
            db.update_score(uid, step.get('points', 1))
    save_state()
    await push('quiz_result', {'correct': correct})
    await msg.answer("Итоги квиза выведены.")

@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID, commands=['rating'])
async def cmd_rating(msg: types.Message):
    """Показать общий рейтинг."""
    rows = db.get_rating()
    txt = "\n".join(f"{name}: {score}" for name, score in rows)
    await msg.answer(txt)
    await push('rating', [{'name': name, 'score': score} for name, score in rows])


@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID, commands=['reset'])
async def cmd_reset(msg: types.Message):
    """Сбросить состояние викторины."""
    reset_state()
    db.reset()
    await msg.answer("Состояние сброшено.")
    await push('participants', {'who': []})
    await push('reset', {})

def run_bot():
    """Запуск Telegram-бота."""
    logging.basicConfig(level=logging.INFO)
    executor.start_polling(dp)


if __name__ == '__main__':
    run_bot()
