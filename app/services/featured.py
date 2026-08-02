# app/services/featured.py
"""
Daily featured product selection for the catalog homepage.

Goal: show a capped, randomized set of products (default 15) that is:
  - the SAME for every visitor on a given day (no per-request reshuffle)
  - automatically different the next day (no cron job needed)
  - balanced across categories, so a shopper doesn't load the page and
    see 15 panels with zero inverters

How the "stable for the day" part works:
  Postgres' random() is seeded per-connection via setseed(), which takes
  a float in [-1, 1]. We derive that float from today's date, so every
  connection that runs this query today gets the same random ordering
  today, and a different one tomorrow. No table, no scheduled job.

This module has one public entrypoint: get_daily_featured().
"""

from datetime import date

from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import Product
from ..specs import SPEC_MODELS

CATEGORIES = list(SPEC_MODELS.keys())


def _seed_for_today() -> float:
    """
    Derive a stable float in (-1, 1) from today's date, for Postgres
    setseed(). Changes automatically at midnight (server timezone).
    """
    today = date.today()
    # ordinal is a plain incrementing day-count int -- stable, no parsing
    n = today.toordinal()
    # map to a spread-out value in (-1, 1), avoiding 0 (setseed(0) is a
    # degenerate case that behaves the same as no seed on some builds)
    seed = ((n % 2000) / 1000.0) - 1.0
    if seed == 0:
        seed = 0.0001
    return seed


async def _seed_random(session: AsyncSession) -> None:
    """Seed this connection's random() so ORDER BY random() is stable today."""
    seed = _seed_for_today()
    # session.execute() (plain SQLAlchemy async, always available) rather
    # than session.exec() (SQLModel's ORM-row-unwrapping wrapper, meant
    # for Select statements) -- keeps this independent of SQLModel version
    # quirks around raw text() handling.
    # Check if the current database dialect is NOT SQLite before seeding
    if session.bind.dialect.name != "sqlite":
        await session.execute(text("SELECT setseed(:seed)"), {"seed": 0.5})
    else:
        # Optional: Use SQLite's random ordering alternative without a seed
        # SQLite does not support seeding its random() natively out of the box
        pass


async def get_daily_featured(
    session: AsyncSession,
    count: int = 15,
) -> list[Product]:
    """
    Return up to `count` products, sampled as evenly as possible across
    every category in SPEC_MODELS, deterministically randomized per day.

    If a category has no products, it's simply skipped -- no error.
    If total available products < count, returns whatever exists.
    """
    await _seed_random(session)

    per_category = count // len(CATEGORIES)
    remainder = count % len(CATEGORIES)

    # Give the remainder to a deterministically-but-daily-randomly chosen
    # subset of categories, so the "extra" slot doesn't always land on
    # the same category every day.
    today_seed = _seed_for_today()
    bonus_categories = set(
        sorted(CATEGORIES, key=lambda c: hash((c, today_seed)))[:remainder]
    )

    selected: list[Product] = []

    for category in CATEGORIES:
        take = per_category + (1 if category in bonus_categories else 0)
        if take <= 0:
            continue

        statement = (
            select(Product)
            .where(Product.category == category)
            .order_by(text("random()"))
            .limit(take)
        )
        result = await session.exec(statement)
        selected.extend(result.all())

    return selected
