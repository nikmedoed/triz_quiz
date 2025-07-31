"""
Telegram-bot for TRIZ-quiz.
Run:  python bot.py
Env:  BOT_TOKEN, PROJECTOR_URL (e.g. http://localhost:5000/update)
"""
import os, asyncio, aiohttp, json, logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage

load_dotenv()

BOT_TOKEN      = os.getenv('BOT_TOKEN')
PROJECTOR_URL  = os.getenv('PROJECTOR_URL', 'http://localhost:5000/update')

bot  = Bot(BOT_TOKEN, parse_mode='HTML')
dp   = Dispatcher(bot, storage=MemoryStorage())          # in-memory FSM

# ---------- простой статичный сценарий -------------
with open('scenario.json', encoding='utf-8') as f:
    SCENARIO = json.load(f)

step_idx          = 0               # глобальный «шаг»
participants      = {}              # telegram_id -> {'name', 'score'}
answers_current   = {}              # telegram_id -> answer text / quiz option
votes_current     = {}              # telegram_id -> voted_for(telegram_id)
ADMIN_ID          = int(os.getenv('ADMIN_ID', 0))   # ведущий

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
    await msg.answer("Вы зарегистрированы! Ожидайте вопросов.")
    await push('participants', {'who': list(p['name'] for p in participants.values())})

# ---------- ответы открытого вопроса ---------------
@dp.message_handler(lambda m: current_step() and current_step()['type']=='open')
async def open_answer(msg: types.Message):
    answers_current[msg.from_user.id] = msg.text.strip()[:200]
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
        await msg.answer("Голос учтён.")
        await push('vote_in', {'voter': msg.from_user.full_name})

# ---------- вариант-квиз ---------------------------
@dp.message_handler(lambda m: current_step() and current_step()['type']=='quiz')
async def quiz_answer(msg: types.Message):
    answers_current[msg.from_user.id] = msg.text.strip().upper()
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
    await push('quiz_result', {'correct': correct})
    await msg.answer("Итоги квиза выведены.")

@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID, commands=['rating'])
async def cmd_rating(msg: types.Message):
    """Показать общий рейтинг."""
    rating = sorted(participants.values(), key=lambda p: p['score'], reverse=True)
    txt = "\n".join(f"{p['name']}: {p['score']}" for p in rating)
    await msg.answer(txt)
    await push('rating', rating)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    executor.start_polling(dp)
