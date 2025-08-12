# Scoring helpers
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Step, Idea, IdeaVote, McqAnswer


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


async def get_leaderboard_users(session: AsyncSession) -> list[User]:
    """Return users sorted for leaderboard display."""
    users = (await session.execute(select(User))).scalars().all()
    users.sort(key=lambda u: (-u.total_score, u.total_answer_ms, u.joined_at))
    return users
