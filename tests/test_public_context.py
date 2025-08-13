import asyncio
import pathlib
import sys
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from app.models import (
    Base,
    Step,
    GlobalState,
    User,
    Idea,
    IdeaVote,
    StepOption,
    MultiAnswer,
)
from app import texts
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
            gs = GlobalState(id=1, current_step_id=step.id, step_started_at=start, phase_started_at=start, phase=0)
            session.add(gs)

            u1 = User(id="1", name="A")
            u2 = User(id="2", name="B")
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


def test_multi_results_instruction_and_percent():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with AsyncSessionLocal() as session:
            step = Step(order_index=1, type="multi", title="Q", correct_multi="0,2")
            session.add(step)
            await session.flush()
            options = [
                StepOption(step_id=step.id, idx=0, text="A"),
                StepOption(step_id=step.id, idx=1, text="B"),
                StepOption(step_id=step.id, idx=2, text="C"),
            ]
            session.add_all(options)
            u1 = User(id="u1", name="U1")
            u2 = User(id="u2", name="U2")
            session.add_all([u1, u2])
            await session.flush()
            session.add(MultiAnswer(step_id=step.id, user_id="u1", choice_idxs="0,2"))
            session.add(MultiAnswer(step_id=step.id, user_id="u2", choice_idxs="0"))
            await session.flush()
            gs = GlobalState(
                id=1,
                current_step_id=step.id,
                step_started_at=datetime.utcnow(),
                phase_started_at=datetime.utcnow(),
                phase=1,
            )
            session.add(gs)
            await session.commit()
            ctx = await build_public_context(session, step, gs)
            assert ctx["percents"] == [100, 0, 50]
            assert ctx["instruction"] == texts.MULTI_RESULTS_INSTRUCTION.format(
                partial=1, full=1, total=2
            )

    asyncio.run(run())


def test_idea_delay_after_phase_change():
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
            gs = GlobalState(
                id=1,
                current_step_id=step.id,
                step_started_at=start,
                phase_started_at=start + timedelta(seconds=20),
                phase=1,
            )
            session.add(gs)

            u1 = User(id="1", name="A")
            session.add(u1)
            await session.flush()

            idea1 = Idea(
                step_id=step.id,
                user_id=u1.id,
                text="a",
                submitted_at=start + timedelta(seconds=5),
            )
            session.add(idea1)
            await session.commit()

            ctx = await build_public_context(session, step, gs)
            assert ctx["ideas"][0].delay_text == "5 с"

    asyncio.run(run())


def test_votes_sort_but_keep_original_numbers():
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
            gs = GlobalState(
                id=1,
                current_step_id=step.id,
                step_started_at=start,
                phase_started_at=start,
                phase=2,
            )
            session.add(gs)

            users = [User(id=str(i), name=f"U{i}") for i in range(1, 5)]
            session.add_all(users)
            await session.flush()

            ideas = []
            for idx, u in enumerate(users[:3], start=1):
                idea = Idea(
                    step_id=step.id,
                    user_id=u.id,
                    text=f"idea{idx}",
                    submitted_at=start + timedelta(seconds=idx),
                )
                ideas.append(idea)
            session.add_all(ideas)
            await session.flush()

            votes = [
                IdeaVote(step_id=step.id, idea_id=ideas[1].id, voter_id=users[3].id),
                IdeaVote(step_id=step.id, idea_id=ideas[1].id, voter_id=users[0].id),
                IdeaVote(step_id=step.id, idea_id=ideas[2].id, voter_id=users[0].id),
                IdeaVote(step_id=step.id, idea_id=ideas[2].id, voter_id=users[3].id),
                IdeaVote(step_id=step.id, idea_id=ideas[0].id, voter_id=users[0].id),
            ]
            session.add_all(votes)
            await session.commit()

            ctx = await build_public_context(session, step, gs)
            ids = [idea.id for idea in ctx["ideas"]]
            assert ids == [ideas[1].id, ideas[2].id, ideas[0].id]
            idxs = [idea.idx for idea in ctx["ideas"]]
            assert idxs == [2, 3, 1]

    asyncio.run(run())
