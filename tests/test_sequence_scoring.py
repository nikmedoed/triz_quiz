import asyncio
import json

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models import Base, Step, StepOption, SequenceAnswer, User
from app.scoring import add_sequence_points


def test_sequence_scoring_requires_full_order():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with AsyncSessionLocal() as session:
            step = Step(order_index=1, type="sequence", title="S", points_correct=5)
            session.add(step)
            await session.flush()
            session.add_all(
                [
                    StepOption(step_id=step.id, idx=0, text="A"),
                    StepOption(step_id=step.id, idx=1, text="B"),
                    StepOption(step_id=step.id, idx=2, text="C"),
                ]
            )
            u1 = User(id=1, name="U1")
            u2 = User(id=2, name="U2")
            session.add_all([u1, u2])
            session.add_all(
                [
                    SequenceAnswer(step_id=step.id, user_id=1, order_json=json.dumps([0, 1, 2])),
                    SequenceAnswer(step_id=step.id, user_id=2, order_json=json.dumps([0, 1])),
                ]
            )
            await session.commit()
            await add_sequence_points(session, step)
            await session.refresh(u1)
            await session.refresh(u2)
            assert u1.total_score == 5
            assert u2.total_score == 0
    asyncio.run(run())
