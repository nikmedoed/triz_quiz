from datetime import datetime, timedelta

import asyncio
import pathlib
import sys

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from app.models import Base, Step, GlobalState, User, Idea
from app.web import build_public_context


def test_idea_delay_uses_step_start():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with AsyncSessionLocal() as session:
            step = Step(order_index=1, type="open", title="Q1")
            session.add(step)
            await session.flush()

            start = datetime(2025, 1, 1, 0, 0, 0)
            gs = GlobalState(id=1, current_step_id=step.id, step_started_at=start, phase=0)
            session.add(gs)

            u1 = User(telegram_id="1", name="A")
            u2 = User(telegram_id="2", name="B")
            session.add_all([u1, u2])
            await session.flush()

            idea1 = Idea(
                step_id=step.id,
                user_id=u1.id,
                text="a",
                submitted_at=start + timedelta(seconds=5),
            )
            idea2 = Idea(
                step_id=step.id,
                user_id=u2.id,
                text="b",
                submitted_at=start + timedelta(seconds=12),
            )
            session.add_all([idea1, idea2])
            await session.commit()

            ctx = await build_public_context(session, step, gs)
            delays = [idea.delay_text for idea in ctx["ideas"]]
            assert delays == ["5 с", "12 с"]

    asyncio.run(run())

