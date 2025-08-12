from typing import List, Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Idea, IdeaVote, Step, User


def mcq_kb(options: List[str], selected: Optional[int]) -> InlineKeyboardMarkup:
    """Inline keyboard with options as button labels."""
    kb = InlineKeyboardBuilder()
    for i, text in enumerate(options):
        label = f"{i + 1}. {text}"
        if selected == i:
            label = "✅ " + label
        kb.button(text=label, callback_data=f"mcq:{i}")
    kb.adjust(1)
    return kb.as_markup()


async def idea_vote_kb(session: AsyncSession, open_step: Step, voter: User):
    ideas = (
        await session.execute(
            select(Idea)
            .where(Idea.step_id == open_step.id)
            .order_by(Idea.submitted_at.asc())
        )
    ).scalars().all()
    voted_ids = set(
        x
        for (x,) in (
            await session.execute(
                select(IdeaVote.idea_id).where(
                    IdeaVote.step_id == open_step.id,
                    IdeaVote.voter_id == voter.id,
                )
            )
        ).all()
    )
    rows = []
    for idx, idea in enumerate(ideas, start=1):
        if idea.user_id == voter.id:
            continue
        text = idea.text[:40].replace("\n", " ")
        prefix = "✅ " if idea.id in voted_ids else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=prefix + f"{idx}. {text}", callback_data=f"vote:{idea.id}"
                )
            ]
        )
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)
