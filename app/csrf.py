import secrets

from fastapi import Depends, Form, HTTPException, Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .database import get_session
from .models import Session


async def get_csrf_token(
    request: Request, session: AsyncSession = Depends(get_session)
) -> str:
    """
    Fetches (or lazily creates) a CSRF token tied to the current session
    cookie, for embedding in a form as a hidden input. Safe to call on
    GET routes that render a form -- doesn't require the user to be
    authenticated as admin, since signup/signin forms are pre-auth.
    """

    from .models import Session

    token_cookie = request.cookies.get("session_token")
    if not token_cookie:
        # No session yet (e.g. first visit to /signup) -- CSRF isn't
        # meaningful without a session to tie it to, so nothing to check
        # on submit either in that case. Return an unused placeholder.
        return ""

    statement = select(Session).where(Session.token == token_cookie)
    result = await session.exec(statement)
    db_session = result.first()
    return db_session.csrf_token if db_session else ""


async def verify_csrf(
    request: Request,
    csrf_token: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Dependency for POST routes. Raises 403 if the submitted csrf_token
    doesn't match the one tied to the session cookie.
    """
    token_cookie = request.cookies.get("session_token")
    if not token_cookie:
        raise HTTPException(status_code=403, detail="Missing session")

    statement = select(Session).where(Session.token == token_cookie)
    result = await session.exec(statement)
    db_session = result.first()

    if not db_session or not secrets.compare_digest(db_session.csrf_token, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
