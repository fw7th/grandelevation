import asyncio
import sys
from datetime import datetime

from fastapi import Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .database import engine
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


async def make_admin_async(identifier: str):
    # Use AsyncSession instead of Session for async engines
    async with AsyncSession(engine) as session:
        statement = select(Users).where(
            (Users.username == identifier) | (Users.email == identifier)
        )
        result = await session.exec(statement)
        user = result.first()

        if not user:
            print(f"Error: User '{identifier}' not found.")
            return

        # Update the role
        user.role = "admin"
        session.add(user)

        # Await the commit to avoid the MissingGreenlet exception
        await session.commit()
        print(f"Success: User '{user.username}' is now an admin!")

    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python -m app.security <username_or_email>")
    else:
        # Run the async loop
        asyncio.run(make_admin_async(sys.argv[1]))
