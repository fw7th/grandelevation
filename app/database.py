# database.py
import os
from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

load_dotenv()

raw_url = os.getenv(
    "NEON_POSTGRES_DATABASE_URL",
    "postgresql+asyncpg://fw7th:135917@localhost:5432/ges",
)

raw_url = os.getenv(
    "NEON_POSTGRES_DATABASE_URL",
    "postgresql+asyncpg://fw7th:135917@localhost:5432/ges",
)

if raw_url.startswith("postgresql://"):
    raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql+asyncpg://", 1)


def _strip_libpq_only_params(url: str) -> str:
    """Remove query params asyncpg doesn't understand (sslmode, channel_binding),
    which SQLAlchemy would otherwise pass through as invalid connect() kwargs."""
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    query.pop("sslmode", None)
    query.pop("channel_binding", None)
    new_query = urlencode(query, doseq=True)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
    )


DATABASE_URL = _strip_libpq_only_params(raw_url)
is_local = "localhost" in DATABASE_URL or "127.0.0.1" in DATABASE_URL

connect_args = {"statement_cache_size": 0}
if not is_local:
    connect_args["ssl"] = "require"

engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args=connect_args,
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
