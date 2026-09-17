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


def _day_key() -> str:
    """Today's date as a stable string. Changes at midnight (server tz)."""
    return date.today().isoformat()  # e.g. "2026-09-17"


def _stable_digest(s: str) -> str:
    """Process-independent hash, unlike builtin hash() which varies by
    PYTHONHASHSEED across worker processes."""
    return hashlib.md5(s.encode()).hexdigest()


async def get_daily_featured(session: AsyncSession, count: int = 15) -> list[Product]:
    day_key = _day_key()
    per_category = count // len(CATEGORIES)
    remainder = count % len(CATEGORIES)

    bonus_categories = set(
        sorted(CATEGORIES, key=lambda c: _stable_digest(f"{c}:{day_key}"))[:remainder]
    )

    is_postgres = session.bind.dialect.name == "postgresql"

    selected: list[Product] = []
    for category in CATEGORIES:
        take = per_category + (1 if category in bonus_categories else 0)
        if take <= 0:
            continue

        if is_postgres:
            statement = (
                select(Product)
                .where(Product.category == category)
                .order_by(func.md5(cast(Product.id, String) + day_key))
                .limit(take)
            )
            result = await session.exec(statement)
            selected.extend(result.all())
        else:
            # SQLite (tests) has no md5() — sort in Python instead
            result = await session.exec(
                select(Product).where(Product.category == category)
            )
            rows = sorted(
                result.all(), key=lambda p: _stable_digest(f"{p.id}:{day_key}")
            )
            selected.extend(rows[:take])

    return selected
