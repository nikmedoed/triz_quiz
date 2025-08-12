import asyncio
from datetime import datetime
import pathlib

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.models import Base, Step, GlobalState
from app.web import build_public_context
from app.scenario_loader import load_if_empty


def test_quiz_default_timer():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with AsyncSessionLocal() as session:
            step = Step(order_index=1, type="quiz", title="Q1")
            session.add(step)
            await session.flush()
            now = datetime.utcnow()
            gs = GlobalState(id=1, current_step_id=step.id, step_started_at=now, phase_started_at=now, phase=0)
            session.add(gs)
            await session.commit()
            ctx = await build_public_context(session, step, gs)
            assert ctx["timer_ms"] == 60 * 1000
            assert ctx["timer_text"] == "01:00"
    asyncio.run(run())


def test_quiz_custom_timer():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with AsyncSessionLocal() as session:
            step = Step(order_index=1, type="quiz", title="Q1", timer_ms=30 * 1000)
            session.add(step)
            await session.flush()
            now = datetime.utcnow()
            gs = GlobalState(id=1, current_step_id=step.id, step_started_at=now, phase_started_at=now, phase=0)
            session.add(gs)
            await session.commit()
            ctx = await build_public_context(session, step, gs)
            assert ctx["timer_ms"] == 30 * 1000
            assert ctx["timer_text"] == "00:30"
    asyncio.run(run())


def test_scenario_loader_time_param(tmp_path):
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        scenario_path = tmp_path / "scenario.json"
        scenario_path.write_text('[{"type": "quiz", "title": "Q", "options": ["a"], "correct": "1", "time": 45}]')
        async with AsyncSessionLocal() as session:
            await load_if_empty(session, str(scenario_path))
            quiz_step = await session.scalar(select(Step).where(Step.type == "quiz"))
            assert quiz_step.timer_ms == 45 * 1000
    asyncio.run(run())
