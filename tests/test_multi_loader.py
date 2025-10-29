import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Step, StepOption
from app.scenario_loader import load_if_empty


def test_multi_loader_with_explicit_correct_options(tmp_path):
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        AsyncSessionLocal = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        scenario_path = tmp_path / "scenario.json"
        scenario_path.write_text(
            '[{"type": "multi", "title": "M", "correct_options": ["A", "B"], "other_options": ["C", "D"]}]'
        )
        async with AsyncSessionLocal() as session:
            await load_if_empty(session, str(scenario_path))
            step = await session.scalar(select(Step).where(Step.type == "multi"))
            assert step is not None
            options = (
                await session.execute(
                    select(StepOption)
                    .where(StepOption.step_id == step.id)
                    .order_by(StepOption.idx)
                )
            ).scalars().all()
            texts = [opt.text for opt in options]
            assert set(texts) == {"A", "B", "C", "D"}
            correct_indexes = {
                int(x) for x in (step.correct_multi or "").split(",") if x.strip()
            }
            assert correct_indexes
            correct_texts = {texts[i] for i in correct_indexes}
            assert correct_texts == {"A", "B"}

    asyncio.run(run())
