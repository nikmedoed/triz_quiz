from __future__ import annotations

from html import escape

from aiogram import Bot
from sqlalchemy import func, select
from typing import Awaitable, Callable, Dict, List, Tuple

import app.texts as texts
from app.db import AsyncSessionLocal
from app.models import (
    Idea,
    IdeaVote,
    McqAnswer,
    Step,
    StepOption,
    User,
)
from app.scoring import get_leaderboard_users
from .keyboards import idea_vote_kb, mcq_kb

Prompt = Tuple[str, Dict[str, object]]
PromptBuilder = Callable[[User, Step, int], Awaitable[List[Prompt]]]


async def _registration_prompt(user: User, step: Step, phase: int) -> List[Prompt]:
    return [(texts.REGISTRATION_WAIT, {})]


async def _open_prompt(user: User, step: Step, phase: int) -> List[Prompt]:
    msgs: List[Prompt] = []
    if phase == 0:
        header = texts.OPEN_HEADER
        title = escape(step.title)
        body = escape(step.text or "")
        instr = texts.OPEN_INSTR
        text = (
            f"<b>{header}</b>\n\n"
            f"{title}\n\n"
            f"{body}\n\n\n"
            f"<i>{instr}</i>"
        ).strip()
        msgs.append((text, {"parse_mode": "HTML"}))
    elif phase == 1:
        async with AsyncSessionLocal() as s:
            kb = await idea_vote_kb(s, step, user)
            if kb:
                msgs.append((texts.VOTE_START, {"parse_mode": "HTML", "reply_markup": kb}))
            else:
                msgs.append((texts.VOTE_NO_OPTIONS, {}))
    elif phase == 2:
        async with AsyncSessionLocal() as s:
            points = await s.scalar(
                select(func.count(IdeaVote.id))
                .join(Idea, Idea.id == IdeaVote.idea_id)
                .where(Idea.step_id == step.id, Idea.user_id == user.id)
            )
        msgs.append((texts.VOTE_FINISHED.format(points=int(points or 0)), {}))
    return msgs


async def _quiz_prompt(user: User, step: Step, phase: int) -> List[Prompt]:
    msgs: List[Prompt] = []
    if phase == 0:
        async with AsyncSessionLocal() as s:
            options = [
                o.text
                for o in (
                    await s.execute(
                        select(StepOption)
                        .where(StepOption.step_id == step.id)
                        .order_by(StepOption.idx)
                    )
                ).scalars().all()
            ]
        header = texts.QUIZ_HEADER
        title = escape(step.title)
        body = escape(step.text or "")
        instr = texts.QUIZ_INSTR
        parts = [f"<b>{header}</b>", title]
        if body:
            parts.append(body)
        parts.append(f"<i>{instr}</i>")
        text = "\n\n".join(parts)
        msgs.append((text, {"parse_mode": "HTML", "reply_markup": mcq_kb(options, selected=None)}))
    else:
        async with AsyncSessionLocal() as s:
            ans = (
                await s.execute(
                    select(McqAnswer).where(
                        McqAnswer.step_id == step.id, McqAnswer.user_id == user.id
                    )
                )
            ).scalar_one_or_none()
        if not ans:
            text = texts.NO_ANSWER + texts.RESPONSES_CLOSED
        elif step.correct_index is not None and ans.choice_idx == step.correct_index:
            points = step.points_correct or 0
            text = texts.CORRECT_PREFIX.format(points=points) + texts.RESPONSES_CLOSED
        else:
            text = texts.WRONG_ANSWER + texts.RESPONSES_CLOSED
        msgs.append((text, {}))
    return msgs


async def _leaderboard_prompt(user: User, step: Step, phase: int) -> List[Prompt]:
    async with AsyncSessionLocal() as s:
        users = await get_leaderboard_users(s)
    place = next(i for i, u in enumerate(users, start=1) if u.id == user.id)
    open_avg = (
        user.open_answer_ms / user.open_answer_count / 1000
        if user.open_answer_count
        else 0
    )
    quiz_avg = (
        user.quiz_answer_ms / user.quiz_answer_count / 1000
        if user.quiz_answer_count
        else 0
    )
    text = texts.LEADERBOARD.format(
        score=user.total_score, place=place, open_avg=open_avg, quiz_avg=quiz_avg
    )
    return [(text, {})]


PROMPT_BUILDERS: Dict[str, PromptBuilder] = {
    "registration": _registration_prompt,
    "open": _open_prompt,
    "quiz": _quiz_prompt,
    "leaderboard": _leaderboard_prompt,
}


async def build_prompt_messages(user: User, step: Step, phase: int) -> List[Prompt]:
    builder = PROMPT_BUILDERS.get(step.type)
    if not builder:
        return []
    return await builder(user, step, phase)


async def send_prompt(
    bot: Bot, user: User, step: Step, phase: int, prefix: str | None = None
):
    if step.type == "open" and phase == 2 and user.last_vote_msg_id:
        try:
            await bot.edit_message_reply_markup(
                user.id, user.last_vote_msg_id, reply_markup=None
            )
        except Exception:
            pass
        async with AsyncSessionLocal() as s:
            u = await s.get(User, user.id)
            if u:
                u.last_vote_msg_id = None
                await s.commit()
    msgs = await build_prompt_messages(user, step, phase)
    if prefix:
        if msgs:
            text, kwargs = msgs[0]
            sep = "\n\n" if text else ""
            msgs[0] = (f"{prefix}{sep}{text}", kwargs)
        else:
            msgs.insert(0, (prefix, {}))
    for text, kwargs in msgs:
        msg = await bot.send_message(user.id, text, **kwargs)
        if step.type == "open" and phase == 1 and kwargs.get("reply_markup"):
            async with AsyncSessionLocal() as s:
                u = await s.get(User, user.id)
                if u:
                    u.last_vote_msg_id = msg.message_id
                    await s.commit()
