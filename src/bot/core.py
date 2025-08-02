"""Quiz runtime routines."""

import asyncio
import time
from typing import Any

import aiohttp

from . import formatting, state

Payload = dict[str, Any] | list[dict[str, Any]]


async def push(event: str, payload: Payload):
    """Отправка данных на проектор."""
    async with aiohttp.ClientSession() as session:
        await session.post(state.PROJECTOR_URL, json={'event': event, 'payload': payload})


async def send_progress():
    step = state.current_step()
    if not step or step.get("type") not in ("open", "quiz", "vote"):
        await push('progress', {'inactive': True})
        return
    if step['type'] == 'vote':
        answered = sum(1 for v in state.votes_current.values() if v)
    else:
        answered = len(state.answers_current)
    ts = state.last_answer_ts if answered else None
    await push('progress', {'answered': answered, 'total': len(state.participants), 'ts': ts})


async def finalize_vote() -> None:
    """Process vote results and update scores."""
    state.vote_gains = {uid: 0 for uid in state.participants}
    results = []
    for idea in state.ideas:
        voters = [uid for uid, vs in state.votes_current.items() if idea['id'] in vs]
        results.append(
            {
                'id': idea['id'],
                'text': idea['text'],
                'author': {
                    'id': idea['user_id'],
                    'name': state.participants[idea['user_id']]['name'],
                },
                'votes': voters,
                'time': idea['time'],
            }
        )
        pts = len(voters)
        state.vote_gains[idea['user_id']] = pts
        if pts:
            state.participants[idea['user_id']]['score'] += pts
            state.db.update_score(idea['user_id'], pts)
    await push('vote_result', {'ideas': results})


async def finalize_quiz(bot, stepq: dict) -> None:
    """Process quiz answers, push results and notify users."""
    correct = str(stepq.get('correct'))
    pts = stepq.get('points', 1)
    options = stepq.get('options', [])
    summary = []
    for i, opt in enumerate(options, start=1):
        voters = [uid for uid, ans in state.answers_current.items() if ans.get('text') == str(i)]
        summary.append({'id': i, 'text': opt, 'voters': voters})
        if str(i) == correct:
            for uid in voters:
                state.participants[uid]['score'] += pts
                state.db.update_score(uid, pts)
    await push('quiz_result', {'options': summary, 'correct': correct})
    for uid in state.participants:
        ans = state.answers_current.get(uid, {}).get('text')
        if ans == correct:
            msg = f'Верно! Вы получили {pts} балл(ов).'
        elif ans:
            msg = 'Вы ответили неверно.'
        else:
            msg = 'Вы не ответили.'
        msg += '\n\nОтветы более не принимаются, вернитесь в общий зал.'
        await bot.send_message(uid, msg)


async def announce_step(bot, step: dict) -> None:
    """Send step description to all participants with optional keyboard."""
    text = formatting.format_step(step)
    for uid in state.participants:
        if step['type'] == 'quiz':
            kb = formatting.quiz_keyboard_for(step, uid)
        elif step['type'] == 'vote':
            kb = formatting.vote_keyboard_for(uid)
        else:
            kb = None
        await bot.send_message(uid, text, reply_markup=kb)


async def notify_vote_results(bot) -> None:
    """Notify participants about vote results."""
    for uid in state.participants:
        pts = state.vote_gains.get(uid, 0)
        await bot.send_message(
            uid,
            f"Голосование завершено.\nРезультаты на экране.\nВы набрали {pts} балл(ов).",
        )


async def broadcast_rating(rows: list[dict]) -> None:
    """Push rating update to projector."""
    await push('rating', formatting.build_rating(rows))


async def finish_quiz(bot) -> None:
    """Send final rating and statistics to participants."""
    board = state.db.get_leaderboard()
    await broadcast_rating(board)
    stats = state.db.get_times_by_user()
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


async def watch_steps(bot):
    last = state.step_idx
    finished = False
    while True:
        await asyncio.sleep(1)
        cur = state.db.get_step()
        if cur == last:
            if state.db.get_stage() != 3:
                finished = False
            continue
        old_step = state.current_step()
        last = cur
        state.step_idx = cur
        if old_step:
            if old_step.get('type') == 'vote':
                await finalize_vote()
            elif old_step.get('type') == 'quiz':
                await finalize_quiz(bot, old_step)
        state.answers_current.clear()
        state.votes_current.clear()
        state.ideas = []
        step = state.current_step()
        if step and step.get('type') in ('open', 'quiz', 'vote'):
            state.step_start_ts = state.last_answer_ts = time.time()
            await send_progress()
        else:
            await push('progress', {'inactive': True})
        if step:
            if step['type'] == 'vote_results':
                await notify_vote_results(bot)
            else:
                if step['type'] == 'vote':
                    state.ideas = state.db.get_ideas(state.step_idx - 1)
                await announce_step(bot, step)
        else:
            if state.db.get_stage() == 3:
                if not finished:
                    await finish_quiz(bot)
                    finished = True
            else:
                finished = False
