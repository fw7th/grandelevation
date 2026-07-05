from datetime import datetime

from fastapi import Depends, HTTPException, Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .database import get_session
from .models import Session, Users


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Users:
    token = request.cookies.get("session_token")

    if token is None:
        raise HTTPException(status_code=401)

    statement = select(Session).where(Session.token == token)
    result = await session.exec(statement)
    db_session = result.first()

    if db_session is None:
        raise HTTPException(status_code=401)

    if db_session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401)

    statement = select(Users).where(Users.id == db_session.user_id)
    result = await session.exec(statement)

    user = result.first()

    if user is None:
        raise HTTPException(status_code=401)

    return user
