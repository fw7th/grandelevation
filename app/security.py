import secrets
from datetime import datetime, timedelta

from pwdlib import PasswordHash
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import LoginAttempt

password_hash = PasswordHash.recommended()


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


class PageException(Exception):
    def __init__(self, message: str | None, status_code: int = 400):
        self.message = message
        self.status_code = status_code


MAX_ATTEMPTS = 5
LOCKOUT_WINDOW = timedelta(minutes=15)


async def is_locked_out(email: str, session: AsyncSession) -> bool:
    cutoff = datetime.utcnow() - LOCKOUT_WINDOW
    statement = (
        select(func.count())
        .select_from(LoginAttempt)
        .where(
            LoginAttempt.email == email,
            LoginAttempt.succeeded == False,
            LoginAttempt.attempted_at >= cutoff,
        )
    )
    result = await session.exec(statement)
    failed_count = result.one()
    return failed_count >= MAX_ATTEMPTS


async def record_attempt(
    email: str, ip_address: str, succeeded: bool, session: AsyncSession
):
    session.add(LoginAttempt(email=email, ip_address=ip_address, succeeded=succeeded))
    await session.commit()
