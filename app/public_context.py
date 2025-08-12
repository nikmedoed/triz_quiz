"""Build context for public screens depending on current step."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
import json
import random

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app import texts
from app.models import (
    GlobalState,
    Step,
    StepOption,
    Idea,
    IdeaVote,
    McqAnswer,
    SequenceAnswer,
    User,
)
from app.scoring import get_leaderboard_users


def humanize_seconds(sec: int) -> str:
    """Return human-friendly string for seconds."""
    m, s = divmod(sec, 60)
    return f"{m} мин {s} с" if m else f"{s} с"



def format_mmss(ms: int) -> str:
    """Format milliseconds as MM:SS string."""
    m, s = divmod(ms // 1000, 60)
    return f"{m:02d}:{s:02d}"


async def registration_context(
    session: AsyncSession, step: Step, gs: GlobalState, ctx: Dict[str, Any]
) -> None:
    users = (
        await session.execute(
            select(User).where(User.name != "").order_by(User.joined_at.asc())
        )
    ).scalars().all()
    ctx.update(users=users, stage_title="Регистрация", show_reset=True)


async def open_context(
    session: AsyncSession, step: Step, gs: GlobalState, ctx: Dict[str, Any]
) -> None:
    rows = (
        await session.execute(
            select(Idea, User)
            .join(User, User.id == Idea.user_id)
            .where(Idea.step_id == step.id)
            .order_by(Idea.submitted_at.asc())
        )
    ).all()
    ideas = []
    for idx, (idea, author) in enumerate(rows, start=1):
        idea.author = author
        idea.idx = idx
        ideas.append(idea)
    if ideas:
        for i in ideas:
            delta = int((i.submitted_at - gs.step_started_at).total_seconds())
            i.delay_text = humanize_seconds(max(0, delta))
    ctx.update(ideas=ideas)
    suffix = ""
    if gs.phase == 1:
        suffix = " — " + texts.STAGE_VOTING_SUFFIX
        if ideas:
            ctx.update(content_class="ideas-page")
    elif gs.phase == 2:
        suffix = " — " + texts.STAGE_RESULTS_SUFFIX
        if ideas:
            ctx.update(content_class="ideas-page")
    ctx.update(stage_title=texts.TITLE_OPEN + suffix)
    if gs.phase == 0:
        total_users = await session.scalar(select(func.count(User.id)).where(User.name != ""))
        last_at = await session.scalar(
            select(func.max(Idea.submitted_at)).where(Idea.step_id == step.id)
        )
        last_ago_s = None
        if last_at:
            last_ago_s = int((datetime.utcnow() - last_at).total_seconds())
        ctx.update(
            total_users=int(total_users or 0),
            last_answer_ago_s=last_ago_s,
            timer_id="ideaTimer",
            timer_text="05:00",
            timer_ms=5 * 60 * 1000,
            status_mode="answers",
            status_current=len(ideas),
            status_total=int(total_users or 0),
            status_last=last_ago_s if last_ago_s is not None else "-",
            instruction="Отправляйте идеи боту. Здесь они пока не видны.",
            content_class="description-page",
        )
    if gs.phase == 1 and ideas:
        voters = (
            await session.execute(
                select(IdeaVote.voter_id)
                .where(IdeaVote.step_id == step.id)
                .group_by(IdeaVote.voter_id)
            )
        ).all()
        last_vote_at = await session.scalar(
            select(func.max(IdeaVote.created_at)).where(IdeaVote.step_id == step.id)
        )
        total_users = await session.scalar(
            select(func.count(User.id)).where(User.name != "")
        )
        last_vote_ago_s = None
        if last_vote_at:
            last_vote_ago_s = int((datetime.utcnow() - last_vote_at).total_seconds())
        ctx.update(
            voters_count=len(voters),
            last_vote_ago_s=last_vote_ago_s,
            timer_id="voteTimer",
            timer_text="01:00",
            timer_ms=60 * 1000,
            status_mode="votes",
            status_current=len(voters),
            status_total=int(total_users or 0),
            status_last=last_vote_ago_s if last_vote_ago_s is not None else "-",
        )
    if gs.phase == 2:
        voters_map = {}
        for idea in ideas:
            rows = (
                await session.execute(
                    select(User)
                    .join(IdeaVote, IdeaVote.voter_id == User.id)
                    .where(IdeaVote.step_id == step.id, IdeaVote.idea_id == idea.id)
                )
            ).scalars().all()
            voters_map[idea.id] = rows
            idea.votes = len(rows)
        ideas.sort(key=lambda x: x.votes, reverse=True)
        ctx.update(voters_map=voters_map, ideas=ideas)


async def quiz_context(
    session: AsyncSession, step: Step, gs: GlobalState, ctx: Dict[str, Any]
) -> None:
    options = (
        await session.execute(
            select(StepOption).where(StepOption.step_id == step.id).order_by(StepOption.idx)
        )
    ).scalars().all()
    ctx.update(
        options=options,
        stage_title="Выбери верный" if gs.phase == 0 else "Выбери верный — результаты",
    )
    if gs.phase == 0:
        total_users = await session.scalar(select(func.count(User.id)).where(User.name != ""))
        answers_count = await session.scalar(
            select(func.count(McqAnswer.id)).where(McqAnswer.step_id == step.id)
        )
        last_at = await session.scalar(
            select(func.max(McqAnswer.answered_at)).where(McqAnswer.step_id == step.id)
        )
        last_answer_ago_s = None
        if last_at:
            last_answer_ago_s = int((datetime.utcnow() - last_at).total_seconds())
        duration_ms = step.timer_ms or 60 * 1000
        ctx.update(
            total_users=int(total_users or 0),
            answers_count=int(answers_count or 0),
            last_answer_ago_s=last_answer_ago_s,
            status_mode="answers",
            status_current=int(answers_count or 0),
            status_total=int(total_users or 0),
            status_last=last_answer_ago_s if last_answer_ago_s is not None else "-",
            instruction="Участники выбирают вариант в боте.",
            timer_id="quizTimer",
            timer_text=format_mmss(duration_ms),
            timer_ms=duration_ms,
        )
    if gs.phase == 1:
        counts = []
        avatars_map = []
        names_map = {}
        for opt in options:
            n = await session.scalar(
                select(func.count(McqAnswer.id)).where(
                    McqAnswer.step_id == step.id, McqAnswer.choice_idx == opt.idx
                )
            )
            counts.append(int(n or 0))
            users = (
                await session.execute(
                    select(User)
                    .join(McqAnswer, McqAnswer.user_id == User.id)
                    .where(McqAnswer.step_id == step.id, McqAnswer.choice_idx == opt.idx)
                )
            ).scalars().all()
            avatars_map.append([u.id for u in users])
            for u in users:
                names_map[str(u.id)] = u.name
        total = sum(counts)
        percents = [round((c / total) * 100) if total else 0 for c in counts]
        ctx.update(
            counts=counts,
            percents=percents,
            correct=step.correct_index,
            avatars_map=avatars_map,
            names_map=names_map,
            content_class="mcq-results",
        )


async def sequence_context(
    session: AsyncSession, step: Step, gs: GlobalState, ctx: Dict[str, Any]
) -> None:
    options = (
        await session.execute(
            select(StepOption).where(StepOption.step_id == step.id).order_by(StepOption.idx)
        )
    ).scalars().all()
    if gs.phase == 0:
        shuffled = list(options)
        rng = random.Random(step.id)
        rng.shuffle(shuffled)
        ctx.update(options=shuffled)
    else:
        ctx.update(options=options)
    ctx.update(
        stage_title=
            texts.TITLE_SEQUENCE
            if gs.phase == 0
            else f"{texts.TITLE_SEQUENCE} — результаты",
    )
    if gs.phase == 0:
        total_users = await session.scalar(
            select(func.count(User.id)).where(User.name != "")
        )
        answers_count = await session.scalar(
            select(func.count(SequenceAnswer.id)).where(
                SequenceAnswer.step_id == step.id,
                func.json_array_length(SequenceAnswer.order_json) == len(options),
            )
        )
        last_at = await session.scalar(
            select(func.max(SequenceAnswer.answered_at)).where(
                SequenceAnswer.step_id == step.id
            )
        )
        last_answer_ago_s = None
        if last_at:
            last_answer_ago_s = int((datetime.utcnow() - last_at).total_seconds())
        duration_ms = step.timer_ms or 2 * 60 * 1000
        ctx.update(
            total_users=int(total_users or 0),
            answers_count=int(answers_count or 0),
            last_answer_ago_s=last_answer_ago_s,
            status_mode="answers",
            status_current=int(answers_count or 0),
            status_total=int(total_users or 0),
            status_last=last_answer_ago_s if last_answer_ago_s is not None else "-",
            instruction=texts.SEQUENCE_PUBLIC_INSTR,
            timer_id="sequenceTimer",
            timer_text=format_mmss(duration_ms),
            timer_ms=duration_ms,
        )
    if gs.phase == 1:
        rows = (
            await session.execute(
                select(User, SequenceAnswer)
                .join(SequenceAnswer, SequenceAnswer.user_id == User.id)
                .where(SequenceAnswer.step_id == step.id)
            )
        ).all()
        correct_order = [o.idx for o in options]
        correct_users = []
        wrong = 0
        for user, ans in rows:
            order = json.loads(ans.order_json or "[]")
            if len(order) != len(correct_order):
                continue
            if order == correct_order:
                correct_users.append(user)
            else:
                wrong += 1
        ctx.update(
            correct_users=correct_users,
            correct_count=len(correct_users),
            wrong_count=wrong,
            content_class="sequence-results",
        )


async def leaderboard_context(
    session: AsyncSession, step: Step, gs: GlobalState, ctx: Dict[str, Any]
) -> None:
    users = await get_leaderboard_users(session)
    ctx.update(
        users=users,
        stage_title="Результаты",
        show_reset=True,
        show_next=False,
        content_class="leaderboard-page",
    )


async def build_public_context(
    session: AsyncSession, step: Step, gs: GlobalState
) -> Dict[str, Any]:
    """Build context for the public screen based on step type and phase."""
    ctx: Dict[str, Any] = {
        "step": step,
        "phase": gs.phase,
        "since": gs.phase_started_at,
        "stage_title": "",
        "instruction": "",
        "timer_id": None,
        "timer_text": "",
        "timer_ms": 0,
        "status_mode": "",
        "status_current": 0,
        "status_total": 0,
        "status_last": "-",
        "show_reset": False,
        "content_class": "",
    }
    from app.step_types import STEP_TYPES

    handler = STEP_TYPES.get(step.type)
    if handler:
        await handler.build_context(session, step, gs, ctx)
    return ctx
