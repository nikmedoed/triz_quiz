from __future__ import annotations

from html import escape

from aiogram import Bot
from sqlalchemy import func, select

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


async def build_prompt_messages(user: User, step: Step, phase: int):
    msgs = []
    if step.type == "registration":
        msgs.append((texts.REGISTRATION_WAIT, {}))
    elif step.type == "open":
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
    elif step.type == "quiz":
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
            instr = texts.QUIZ_INSTR
            text = f"<b>{header}</b>\n\n{title}\n\n<i>{instr}</i>"
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
    elif step.type == "leaderboard":
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
        msgs.append((text, {}))
    return msgs


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
