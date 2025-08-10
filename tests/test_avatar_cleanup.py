import asyncio
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
import app.bot as bot
from app.models import Base, Step, GlobalState
from app.settings import settings


def test_old_avatar_removed_for_new_user(tmp_path, monkeypatch):
    async def run():
        monkeypatch.setattr(settings, "AVATAR_DIR", str(tmp_path))
        old_file = Path(tmp_path) / "42.png"
        old_file.write_bytes(b"old")

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        TestSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with TestSessionLocal() as session:
            step = Step(order_index=1, type="open", title="Q1")
            session.add(step)
            await session.flush()
            now = datetime.utcnow()
            gs = GlobalState(
                id=1,
                current_step_id=step.id,
                step_started_at=now,
                phase_started_at=now,
                phase=0,
            )
            session.add(gs)
            await session.commit()

        monkeypatch.setattr(bot, "AsyncSessionLocal", TestSessionLocal)
        session, user, state, step_obj = await bot.get_ctx("42")
        try:
            assert not old_file.exists()
        finally:
            await session.close()

    asyncio.run(run())
