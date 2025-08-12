# Scoring helpers
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import json

from app.models import User, Step, Idea, IdeaVote, McqAnswer, SequenceAnswer, StepOption
from app.models import User, Step, Idea, IdeaVote, McqAnswer, MultiAnswer


async def add_vote_points(session: AsyncSession, open_step_id: int) -> None:
    # +1 per vote to the author of each idea in this open block
    res = await session.execute(
        select(Idea.user_id, func.count(IdeaVote.id))
        .join(IdeaVote, IdeaVote.idea_id == Idea.id)
        .where(Idea.step_id == open_step_id, IdeaVote.step_id == open_step_id)
        .group_by(Idea.user_id)
    )
    for user_id, votes in res.all():
        user = await session.get(User, user_id)
        if user:
            user.total_score += int(votes)
    await session.commit()


async def add_mcq_points(session: AsyncSession, mcq_step: Step) -> None:
    if mcq_step.points_correct is None or mcq_step.correct_index is None:
        return
    res = await session.execute(
        select(User)
        .join(McqAnswer, McqAnswer.user_id == User.id)
        .where(McqAnswer.step_id == mcq_step.id, McqAnswer.choice_idx == mcq_step.correct_index)
    )
    for (user,) in res.all():
        user.total_score += mcq_step.points_correct
    await session.commit()


async def add_multi_points(session: AsyncSession, step: Step) -> None:
    if not step.correct_multi or step.points_correct is None:
        return
    correct_set = {
        int(x)
        for x in step.correct_multi.split(",")
        if x.strip().isdigit()
    }
    if not correct_set:
        return
    share = step.points_correct / len(correct_set)
    answers = (
        await session.execute(
            select(MultiAnswer).where(MultiAnswer.step_id == step.id)
        )
    ).scalars().all()
    for ans in answers:
        user = await session.get(User, ans.user_id)
        if not user:
            continue
        chosen = {
            int(x)
            for x in ans.choice_idxs.split(",")
            if x.strip().isdigit()
        }
        if not chosen or not chosen.issubset(correct_set):
            continue
        points = int(share * len(chosen))
        if points:
            user.total_score += points
    await session.commit()


async def add_sequence_points(session: AsyncSession, seq_step: Step) -> None:
    if seq_step.points_correct is None:
        return
    options = (
        await session.execute(
            select(StepOption.idx)
            .where(StepOption.step_id == seq_step.id)
            .order_by(StepOption.idx)
        )
    ).scalars().all()
    correct_order = list(options)
    rows = (
        await session.execute(
            select(User, SequenceAnswer).join(
                SequenceAnswer, SequenceAnswer.user_id == User.id
            ).where(SequenceAnswer.step_id == seq_step.id)
        )
    ).all()
    for user, ans in rows:
        order = json.loads(ans.order_json or "[]")
        if len(order) == len(correct_order) and order == correct_order:
            user.total_score += seq_step.points_correct
    await session.commit()


async def get_leaderboard_users(session: AsyncSession) -> list[User]:
    """Return users sorted for leaderboard display."""
    users = (await session.execute(select(User))).scalars().all()
    users.sort(key=lambda u: (-u.total_score, u.total_answer_ms, u.joined_at))
    return users
