from datetime import datetime

from fastapi import Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import Session, Users


async def authenticate(
    request: Request,
    session: AsyncSession,
) -> Users | None:
    token = request.cookies.get("session_token")

    if token is None:
        return None

    statement = select(Session).where(Session.token == token)
    result = await session.exec(statement)
    db_session = result.first()

    if db_session is None:
        return None

    if db_session.expires_at < datetime.utcnow():
        await session.delete(db_session)
        await session.commit()
        return None

    statement = select(Users).where(Users.id == db_session.user_id)
    result = await session.exec(statement)
    user = result.first()

    if user is None:
        await session.delete(db_session)
        await session.commit()
        return None

    return user
