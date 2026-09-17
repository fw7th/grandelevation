# app/routers/internal.py
from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..database import get_session
from ..models import Product

router = APIRouter()


@router.get("/internal/keep-alive")
async def keep_alive(session: AsyncSession = Depends(get_session)):
    await session.exec(select(Product).limit(1))
    return {"status": "ok"}
