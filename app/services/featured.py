# app/services/featured.py
"""
Daily featured product selection for the catalog homepage.

Goal: show a capped, randomized set of products (default 15) that is:
  - the SAME for every visitor on a given day (no per-request reshuffle)
  - automatically different the next day (no cron job needed)
  - balanced across categories, so a shopper doesn't load the page and
    see 15 panels with zero inverters

How the "stable for the day" part works:
  Instead of seeding Postgres' random() per-connection (fragile — depends
  on connection reuse and re-seeding correctly every time), we sort by
  md5(product_id || today's_date). This is a pure function of the row and
  the date: every connection, every worker process, every request
  computes the exact same ordering for today, and a different one
  tomorrow. No session state, no cron job, no table.
"""

import hashlib
import os
from datetime import date

from sqlalchemy import String, cast, func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..database import engine
from ..models import Product
from ..specs import SPEC_MODELS

CATEGORIES = list(SPEC_MODELS.keys())
PAGE_SIZE = 24


def _day_key() -> str:
    """Today's date as a stable string. Changes at midnight (server tz)."""
    return date.today().isoformat()  # e.g. "2026-09-17"


def _stable_digest(s: str) -> str:
    """Process-independent hash, unlike builtin hash() which varies by
    PYTHONHASHSEED across worker processes."""
    return hashlib.md5(s.encode()).hexdigest()


async def get_catalog_page(
    session: AsyncSession, offset: int, limit: int, category: str | None = None
) -> tuple[list[Product], bool]:
    """One page of products in today's stable shuffled order.
    Fetches limit+1 rows to learn whether another page exists."""
    day_key = _day_key()
    stmt = select(Product)
    if category:
        stmt = stmt.where(Product.category == category)

    if session.bind.dialect.name == "postgresql":
        stmt = (
            stmt.order_by(func.md5(cast(Product.id, String) + day_key), Product.id)
            .offset(offset)
            .limit(limit + 1)
        )
        rows = (await session.exec(stmt)).all()
    else:  # SQLite (tests)
        all_rows = sorted(
            (await session.exec(stmt)).all(),
            key=lambda p: (_stable_digest(f"{p.id}:{day_key}"), p.id),
        )
        rows = all_rows[offset : offset + limit + 1]
    return rows[:limit], len(rows) > limit
