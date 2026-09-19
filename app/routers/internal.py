# app/routers/internal.py
"""
Small cron job ping so database doesn't get paused.
"""

import os

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..database import get_session
from ..models import Product

router = APIRouter()

CRON_SECRET = os.getenv("CRON_SECRET")  # Vercel sets this automatically


@router.get("/internal/keep-alive")
async def keep_alive(
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
):
    if CRON_SECRET and authorization != f"Bearer {CRON_SECRET}":
        raise HTTPException(status_code=404)

    result = await session.exec(select(Product).limit(1))
    result.first()
    return {"status": "ok"}
