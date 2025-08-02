"""Quiz state and helper routines."""

import asyncio, aiohttp, json, html, time
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import settings
from db import Database
from resources import load_scenario

PROJECTOR_URL = settings.projector_url

db = Database(settings.db_file)
SCENARIO = load_scenario()

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
    global step_idx, participants, answers_current, votes_current, ideas
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
    answers_current.update(
        {
            uid: json.loads(val) if val.startswith('{') else {'text': val, 'time': 0}
            for uid, val in quiz_raw.items()
        }
    )
    votes_raw = db.get_responses(step_idx, "vote")
    votes_current = {
        uid: set(json.loads(v)) if v.startswith('[') else set()
        for uid, v in votes_raw.items()
    }
    if current_step() and current_step().get('type') == 'vote':
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
            "Ответы более не принимаются.\n\n"
            "<b>Начато голосование за идеи.</b>\n\n"
            "Выберите номера, которые считаете достойным и методологически "
            "обоснованным решением описанной проблемы."
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


async def watch_steps(bot):
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
                    # подсчитать результаты и сообщить участникам
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
                            msg = f'Верно! Вы получили {pts} балл(ов).'
                        elif ans:
                            msg = 'Вы ответили неверно.'
                        else:
                            msg = 'Вы не ответили.'
                        msg += '\n\nОтветы более не принимаются, вернитесь в общий зал.'
                        await bot.send_message(uid, msg)
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
                if db.get_stage() == 3:
                    board = db.get_leaderboard()
                    await push(
                        'rating',
                        [
                            {
                                'id': r['id'],
                                'name': r['name'],
                                'score': r['score'],
                                'place': r['place'],
                            }
                            for r in board
                        ],
                    )
                    stats = db.get_times_by_user()
                    for row in board:
                        uid = row['id']
                        o = stats.get(uid, {}).get('open', [])
                        q = stats.get(uid, {}).get('quiz', [])
                        avg_open = sum(o) / len(o) if o else 0
                        avg_quiz = sum(q) / len(q) if q else 0
                        text = (
                            "Викторина завершена.\n\n"
                            f"Вам набрано баллов: {row['score']}.\n"
                            f"Ваше место: {row['place']}.\n\n"
                            "Среднее время ответа:\n"
                            f"{avg_open:.1f} c - открытый вопрос\n"
                            f"{avg_quiz:.1f} c - выбор варианта"
                        )
                        await bot.send_message(uid, text)
                    return
                else:
                    pass
