import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models import Base, Step, MultiAnswer, User
from app.scoring import add_multi_points


def test_multi_scoring():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with AsyncSessionLocal() as session:
            step = Step(order_index=1, type="multi", title="Q", correct_multi="0,2", points_correct=6)
            session.add(step)
            user1 = User(id="u1", name="A")
            user2 = User(id="u2", name="B")
            user3 = User(id="u3", name="C")
            session.add_all([user1, user2, user3])
            await session.flush()
            session.add(MultiAnswer(step_id=step.id, user_id="u1", choice_idxs="0,2"))
            session.add(MultiAnswer(step_id=step.id, user_id="u2", choice_idxs="0"))
            session.add(MultiAnswer(step_id=step.id, user_id="u3", choice_idxs="0,1"))
            await session.commit()
            await add_multi_points(session, step)
            u1 = await session.get(User, "u1")
            u2 = await session.get(User, "u2")
            u3 = await session.get(User, "u3")
            assert u1.total_score == 6
            assert u2.total_score == 3
            assert u3.total_score == 0
    asyncio.run(run())
