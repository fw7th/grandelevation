# database.py
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app import models

DATABASE_URL = "postgresql+asyncpg://fw7th:135917@localhost:5432/ges"

engine = create_async_engine(
    DATABASE_URL,
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


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
