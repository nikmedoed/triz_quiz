"""Telegram-bot for TRIZ-quiz."""

import asyncio, aiohttp, json, logging, html, time
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
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

step_idx = -1  # текущий шаг сценария
participants: dict[int, dict] = {}
answers_current: dict[int, dict] = {}
votes_current: dict[int, set[int]] = {}
ideas: list[dict] = []  # текущие идеи для голосования
vote_gains: dict[int, int] = {}  # очки, полученные на последнем голосовании
ADMIN_ID = settings.admin_id  # ведущий
pending_names: set[int] = set()
last_answer_ts = time.time()
step_start_ts = time.time()

def current_step():
    return SCENARIO[step_idx] if 0 <= step_idx < len(SCENARIO) else None


def load_state() -> None:
    """Load quiz state from the database."""
    global step_idx, participants, answers_current, votes_current
    step_idx = db.get_step()
    participants = {
        row["id"]: {"name": row["name"], "score": row["score"]}
        for row in db.get_participants()
    }
    answers_raw = db.get_responses(step_idx, "open")
    answers_current = {
        uid: json.loads(val) if val.startswith('{') else {'text': val, 'time': 0}
        for uid, val in answers_raw.items()
    }
    quiz_raw = db.get_responses(step_idx, "quiz")
    answers_current.update({uid: {'text': val} for uid, val in quiz_raw.items()})
    votes_raw = db.get_responses(step_idx, "vote")
    votes_current = {
        uid: set(json.loads(v)) if v.startswith('[') else set()
        for uid, v in votes_raw.items()
    }
    if current_step() and current_step().get('type') == 'vote':
        prev = db.get_open_answers(step_idx - 1)
        prev.sort(key=lambda a: a['time'])
        global ideas
        ideas = [
            {
                'id': i + 1,
                'user_id': a['user_id'],
                'text': a['text'],
                'time': a['time'],
            }
            for i, a in enumerate(prev)
        ]


load_state()


def vote_keyboard_for(uid: int) -> InlineKeyboardMarkup:
    """Build inline keyboard with checkmarks for selected ideas."""
    selected = votes_current.get(uid, set())
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'✅ ' if idea['id'] in selected else ''}{idea['id']}. {idea['text'][:30]}",
                    callback_data=f"vote:{idea['id']}",
                )
            ]
            for idea in ideas
            if idea['user_id'] != uid
        ]
    )


def quiz_keyboard_for(step: dict, uid: int) -> InlineKeyboardMarkup:
    """Build quiz keyboard with a checkmark on the selected option."""
    chosen = answers_current.get(uid, {}).get('text')
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'✅ ' if str(i+1) == str(chosen) else ''}{i+1}. {opt[:30]}",
                    callback_data=f"quiz:{i+1}",
                )
            ]
            for i, opt in enumerate(step.get('options', []))
        ]
    )


def format_step(step: dict) -> str:
    """Render message for current step according to its type."""
    t = step.get("type")
    if t == "open":
        header = (
            "<b>Предложите идею решения проблемной ситуации (открытый ответ)</b>\n\n\n"
        )
        body = html.escape(step.get("title", ""))
        if step.get("description"):
            body += f"\n\n{html.escape(step['description'])}"
        tail = (
            "\n\n\n<i>Пришлите ваш ответ в этот чат.\n"
            "- Учитывается один последний ответ\n"
            "- В свободной форме\n"
            "- Лаконично, важна скорость\n"
            "- Укажите логику решения, использованные приёмы, методы, обоснуйте</i>"
        )
        return header + body + tail
    if t == "quiz":
        header = "<b>Выберите один вариант ответа</b>\n\n\n"
        body = html.escape(step.get("title", ""))
        if step.get("description"):
            body += f"\n{html.escape(step['description'])}"
        tail = (
            "\n\n\n<i>Выберите\n"
            "- Наиболее подходящий вариант\n"
            "- Быстро, пока есть время\n"
            "- Можно изменить выбор</i>"
        )
        return header + body + tail
    if t == "vote":
        return (
            "Ответы более не принимаются.\n"  # newline for readability
            "Начато голосование за идеи, выберите номера, которые считаете "
            "достойным и методологически обоснованным решением описанной проблемы."
        )
    if t == "vote_results":
        return "Голосование завершено. Результаты на экране."
    text = f"Сейчас идёт шаг: {step['title']}"
    if step.get('description'):
        text += f"\n{step['description']}"
    return text

async def push(event: str, payload: dict):
    """Отправка данных на проектор."""
    async with aiohttp.ClientSession() as session:
        await session.post(PROJECTOR_URL, json={'event': event, 'payload': payload})


async def send_progress():
    step = current_step()
    if not step or step.get("type") not in ("open", "quiz", "vote"):
        await push('progress', {'inactive': True})
        return
    if step['type'] == 'vote':
        answered = sum(1 for v in votes_current.values() if v)
    else:
        answered = len(answers_current)
    ts = last_answer_ts if answered else None
    await push('progress', {'answered': answered, 'total': len(participants), 'ts': ts})


async def watch_steps():
    global step_idx, answers_current, votes_current, last_answer_ts, step_start_ts, ideas, vote_gains
    last = step_idx
    while True:
        await asyncio.sleep(1)
        cur = db.get_step()
        if cur != last:
            old_step = current_step()
            last = cur
            step_idx = cur
            # обработать завершение предыдущего шага
            if old_step:
                if old_step.get('type') == 'vote':
                    vote_gains = {uid: 0 for uid in participants}
                    results = []
                    for idea in ideas:
                        voters = [uid for uid, vs in votes_current.items() if idea['id'] in vs]
                        results.append(
                            {
                                'id': idea['id'],
                                'text': idea['text'],
                                'author': {'id': idea['user_id'], 'name': participants[idea['user_id']]['name']},
                                'votes': voters,
                                'time': idea['time'],
                            }
                        )
                        pts = len(voters)
                        vote_gains[idea['user_id']] = pts
                        if pts:
                            participants[idea['user_id']]['score'] += pts
                            db.update_score(idea['user_id'], pts)
                    await push('vote_result', {'ideas': results})
                elif old_step.get('type') == 'quiz':
                    # сообщить об окончании и подсчитать результаты
                    for uid in participants:
                        await bot.send_message(uid, 'Ответы более не принимаются, вернитесь в общий зал.')
                    stepq = old_step
                    correct = str(stepq.get('correct'))
                    pts = stepq.get('points', 1)
                    options = stepq.get('options', [])
                    summary = []
                    for i, opt in enumerate(options, start=1):
                        voters = [uid for uid, ans in answers_current.items() if ans.get('text') == str(i)]
                        summary.append({'id': i, 'text': opt, 'voters': voters})
                        if str(i) == correct:
                            for uid in voters:
                                participants[uid]['score'] += pts
                                db.update_score(uid, pts)
                    await push('quiz_result', {'options': summary, 'correct': correct})
                    for uid in participants:
                        ans = answers_current.get(uid, {}).get('text')
                        if ans == correct:
                            await bot.send_message(uid, f'Верно! Вы получили {pts} балл(ов).')
                        elif ans:
                            await bot.send_message(uid, 'Неверно.')
                        else:
                            await bot.send_message(uid, 'Вы не ответили.')
            answers_current.clear(); votes_current.clear(); ideas = []
            step = current_step()
            if step and step.get("type") in ("open", "quiz", "vote"):
                step_start_ts = last_answer_ts = time.time()
                await send_progress()
            else:
                await push('progress', {'inactive': True})
            if step:
                if step['type'] == 'vote_results':
                    for uid in participants:
                        pts = vote_gains.get(uid, 0)
                        await bot.send_message(
                            uid,
                            f"Голосование завершено.\nРезультаты на экране.\nВы набрали {pts} балл(ов).",
                        )
                else:
                    text = format_step(step)
                    if step['type'] == 'vote':
                        prev = db.get_open_answers(step_idx - 1)
                        prev.sort(key=lambda a: a['time'])
                        ideas = [
                            {
                                'id': i + 1,
                                'user_id': a['user_id'],
                                'text': a['text'],
                                'time': a['time'],
                            }
                            for i, a in enumerate(prev)
                        ]
                    for uid in participants:
                        if step['type'] == 'quiz':
                            kb = quiz_keyboard_for(step, uid)
                            await bot.send_message(uid, text, reply_markup=kb)
                        elif step['type'] == 'vote':
                            kb = vote_keyboard_for(uid)
                            await bot.send_message(uid, text, reply_markup=kb)
                        else:
                            await bot.send_message(uid, text)
            else:
                pass

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
        avatar = (await bot.download_file(file.file_path)).getvalue()
    score = participants.get(user.id, {}).get("score", 0)
    participants[user.id] = {"name": name, "score": score}
    db.add_participant(user.id, name, avatar)
    pending_names.remove(user.id)
    stage = db.get_stage()
    if stage == 1:
        await push(
            "participants",
            {
                "who": [
                    {"id": uid, "name": p["name"]} for uid, p in participants.items()
                ]
            },
        )
        await msg.answer("Вы зарегистрированы! Ожидайте начала.")
    elif stage == 2:
        step = current_step()
        if step:
            await msg.answer(format_step(step))
        else:
            await msg.answer("Викторина уже началась, ожидайте вопросов.")
        await send_progress()
    else:
        rating = db.get_rating()
        table = "\n".join(f"{n}: {s}" for n, s in rating)
        await msg.answer("Викторина завершена.\n" + table)

# ---------- ответы открытого вопроса ---------------
@dp.message(lambda m: db.get_stage() == 2 and current_step() and current_step()['type']=='open')
async def open_answer(msg: Message):
    global last_answer_ts
    text = msg.text.strip()[:200]
    delta = time.time() - step_start_ts
    answers_current[msg.from_user.id] = {'text': text, 'time': delta}
    db.record_response(msg.from_user.id, step_idx, 'open', json.dumps({'text': text, 'time': delta}))
    last_answer_ts = time.time()
    await msg.answer(
        "Идея принята!\n\n<i>Вы можете изменить ответ, отправив новое сообщение. "
        "Редактирование сообщений не поддерживается, скопируйте, измените и пришлите новое</i>"
    )
    await send_progress()
    await push('answer_in', {'name': msg.from_user.full_name})

# ---------- голосование ----------------------------
@dp.callback_query(
    lambda c: db.get_stage() == 2
    and current_step()
    and current_step()['type'] == 'vote'
    and c.data.startswith('vote:')
)
async def vote(cb: CallbackQuery):
    idea_id = int(cb.data.split(':')[1])
    idea = next((i for i in ideas if i['id'] == idea_id), None)
    if not idea or idea['user_id'] == cb.from_user.id:
        await cb.answer("За себя голосовать нельзя!", show_alert=True)
        return
    global last_answer_ts
    votes = votes_current.setdefault(cb.from_user.id, set())
    if idea_id in votes:
        votes.remove(idea_id)
    else:
        votes.add(idea_id)
    db.record_response(cb.from_user.id, step_idx, 'vote', json.dumps(list(votes)))
    last_answer_ts = time.time()
    kb = vote_keyboard_for(cb.from_user.id)
    await cb.message.edit_reply_markup(reply_markup=kb)
    await cb.answer("Голос учтён.")
    await send_progress()
    await push('vote_in', {'voter': cb.from_user.full_name})

# ---------- вариант-квиз ---------------------------
@dp.callback_query(
    lambda c: db.get_stage() == 2
    and current_step()
    and current_step()['type'] == 'quiz'
    and c.data.startswith('quiz:')
)
async def quiz_answer(cb: CallbackQuery):
    global last_answer_ts
    ans = cb.data.split(':')[1]
    prev = answers_current.get(cb.from_user.id, {}).get('text')
    if prev == ans:
        await cb.answer("Этот вариант уже выбран.")
        return
    answers_current[cb.from_user.id] = {'text': ans}
    db.record_response(cb.from_user.id, step_idx, 'quiz', ans)
    last_answer_ts = time.time()
    step = current_step()
    kb = quiz_keyboard_for(step, cb.from_user.id)
    await cb.message.edit_reply_markup(reply_markup=kb)
    await cb.answer("Ответ записан.")
    await send_progress()
    await push('answer_in', {'name': cb.from_user.full_name})

# ---------- команды ведущего -----------------------
@dp.message(Command('next'), lambda m: m.from_user.id == ADMIN_ID)
async def cmd_next(msg: Message):
    """Перейти к следующему шагу сценария."""
    base = PROJECTOR_URL.rsplit('/', 1)[0]
    async with aiohttp.ClientSession() as session:
        await session.post(f"{base}/next")
    await msg.answer("Переключение шага.")


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
    global step_idx, participants, answers_current, votes_current, ideas, vote_gains
    step_idx = -1
    participants.clear()
    answers_current.clear()
    votes_current.clear()
    ideas = []
    vote_gains = {}
    db.reset()
    await msg.answer("Состояние сброшено.")
    await push('participants', {'who': []})
    await push('reset', {})

def run_bot():
    """Запуск Telegram-бота."""
    logging.basicConfig(level=logging.INFO)
    async def main_loop():
        asyncio.create_task(watch_steps())
        await dp.start_polling(bot)

    asyncio.run(main_loop())


if __name__ == '__main__':
    run_bot()
