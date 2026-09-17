# database.py
import os
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

load_dotenv()

DATABASE_URL = os.getenv(
    "NHOST_DATABASE_URL",
    "postgresql+asyncpg://fw7th:135917@localhost:5432/ges",
)

engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"statement_cache_size": 0},
    echo=True,  # Logs SQL statements
    future=True,
)


SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
