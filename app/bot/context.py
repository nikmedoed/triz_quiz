from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models import User, GlobalState, Step


async def get_ctx(tg_id: str):
    session = AsyncSessionLocal()
    try:
        user = (
            await session.execute(select(User).where(User.id == tg_id))
        ).scalar_one_or_none()
        if not user:
            user = User(id=tg_id, name="")
            session.add(user)
            await session.commit()
            await session.refresh(user)
        state = await session.get(GlobalState, 1)
        step = await session.get(Step, state.current_step_id)
        return session, user, state, step
    except Exception:
        await session.close()
        raise
