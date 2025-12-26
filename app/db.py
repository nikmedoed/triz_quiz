# Async SQLAlchemy engine/session setup
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.settings import settings


async def apply_migrations(conn) -> None:
    """Lightweight schema tweaks for existing SQLite DB."""
    result = await conn.exec_driver_sql("PRAGMA table_info(users)")
    cols = [row[1] for row in result.fetchall()]
    if "waiting_for_name" not in cols:
        await conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN waiting_for_name BOOLEAN NOT NULL DEFAULT 0"
        )
    if "avatar_emoji" not in cols:
        await conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN avatar_emoji VARCHAR(16)"
        )
    if "is_blocked" not in cols:
        await conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN is_blocked BOOLEAN NOT NULL DEFAULT 0"
        )

    result = await conn.exec_driver_sql("PRAGMA table_info(steps)")
    cols = [row[1] for row in result.fetchall()]
    if "timer_ms" not in cols:
        await conn.exec_driver_sql(
            "ALTER TABLE steps ADD COLUMN timer_ms INTEGER"
        )
    if "correct_multi" not in cols:
        await conn.exec_driver_sql(
            "ALTER TABLE steps ADD COLUMN correct_multi VARCHAR"
        )


engine = create_async_engine(settings.DATABASE_URL, future=True, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
