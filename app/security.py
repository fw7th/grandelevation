import asyncio
import secrets
import sys

from pwdlib import PasswordHash
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .database import engine
from .models import Users

password_hash = PasswordHash.recommended()


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


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
