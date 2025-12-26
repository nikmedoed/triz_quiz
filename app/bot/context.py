from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.hub import hub
from app.models import User, GlobalState, Step


async def get_ctx(tg_id: str) -> tuple[AsyncSession, User, GlobalState, Step]:
    """Return session, user, global state, and current step."""
    session = AsyncSessionLocal()
    try:
        changed = False
        user = (
            await session.execute(select(User).where(User.id == tg_id))
        ).scalar_one_or_none()
        if not user:
            user = User(id=tg_id, name="")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            changed = True
        elif user.is_blocked:
            user.is_blocked = False
            await session.commit()
            await session.refresh(user)
            changed = True
        state = await session.get(GlobalState, 1)
        step = await session.get(Step, state.current_step_id)
        if changed:
            await hub.broadcast({"type": "reload"})
        return session, user, state, step
    except Exception:
        await session.close()
        raise
