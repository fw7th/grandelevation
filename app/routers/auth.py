import asyncio
import traceback
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import BASE_DIR, templates

from ..database import get_session
from ..models import PasswordResetToken, Session, Users
from ..security import (
    create_session_token,
    is_locked_out,
    password_hash,
    record_attempt,
)
from ..utils import authenticate, sync_gmail_dispatch

router = APIRouter(tags=["auth"])


@router.get("/signup", response_class=HTMLResponse)
async def signup(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)
    if user:
        return RedirectResponse("/catalog")

    return templates.TemplateResponse(
        request=request,
        name="signup.html",
        context={
            "errors": {},
            "username": "",
            "email": "",
        },
    )


@router.post("/signup", response_class=HTMLResponse)
async def signup_post(
    request: Request,
    session: AsyncSession = Depends(get_session),
    username: str | None = Form(default=None),
    email: str | None = Form(default=None),
    password: str | None = Form(default=None),
):
    errors = {}

    username = (username or "").strip()
    email = (email or "").strip()
    password = password or ""

    # ---------- Validation ----------
    if not username:
        errors["username"] = "Username is required."

    if not email:
        errors["email"] = "Email is required."
    elif "@" not in email or "." not in email.rsplit("@", 1)[1]:
        errors["email"] = "Enter a valid email address."

    if len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."

    # ---------- Username uniqueness ----------
    if username:
        statement = select(Users).where(Users.username == username)
        result = await session.exec(statement)
        if result.first():
            errors["username"] = "This username is already taken."

    # ---------- Email uniqueness ----------
    if email:
        statement = select(Users).where(Users.email == email)
        result = await session.exec(statement)
        if result.first():
            errors["email"] = "An account with this email already exists."

    # ---------- Validation failed ----------
    if errors:
        return templates.TemplateResponse(
            request=request,
            name="signup.html",
            context={
                "errors": errors,
                "username": username,
                "email": email,
            },
        )

    # ---------- Create user and session ----------
    user = Users(
        username=username,
        email=email,
        password_hash=password_hash.hash(password),
    )

    token = create_session_token()

    try:
        session.add(user)
        await session.flush()

        session.add(
            Session(
                token=token,
                user_id=user.id,
                expires_at=datetime.utcnow() + timedelta(days=30),
            )
        )

        await session.commit()

    except IntegrityError:
        await session.rollback()

        return templates.TemplateResponse(
            request=request,
            name="signup.html",
            context={
                "errors": {
                    "username": "Username or email has just been taken. Please try again."
                },
                "username": username,
                "email": email,
            },
        )

    response = RedirectResponse(
        url="/catalog",
        status_code=303,
    )

    response.set_cookie(
        key="session_token",
        value=token,
        max_age=60 * 60 * 24 * 30,  # 30 days
        httponly=True,
        secure=False,  # True in production
        samesite="lax",
    )

    return response


@router.get("/signin")
async def signin(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)
    if user:
        return RedirectResponse("/catalog")

    return templates.TemplateResponse(
        request=request,
        name="signin.html",
        context={"errors": {}, "email": ""},
    )


@router.post("/signin", response_class=HTMLResponse)
async def signin_post(
    request: Request,
    session: AsyncSession = Depends(get_session),
    email: str | None = Form(default=None),
    password: str | None = Form(default=None),
    remember_me: bool = Form(False),
):
    errors = {}
    email = (email or "").strip()
    password = password or ""
    ip_address = request.client.host if request.client else "unknown"

    # ---------- Lockout check (before touching the password at all) ----------
    if email and await is_locked_out(email, session):
        errors["email"] = "Too many failed attempts. Please try again in 15 minutes."
        return templates.TemplateResponse(
            request=request,
            name="signin.html",
            context={"errors": errors, "email": email},
        )

    # ---------- Validation ----------
    if not email:
        errors["email"] = "Email is required."
    elif "@" not in email or "." not in email.rsplit("@", 1)[1]:
        errors["email"] = "Enter a valid email address."

    if not password:
        errors["password"] = "Password is required."

    statement = select(Users).where(Users.email == email)
    result = await session.exec(statement)
    user = result.first()

    login_ok = user is not None and password_hash.verify(password, user.password_hash)

    if user is None or not login_ok:
        errors["email"] = "Invalid email or password."

    # ---------- Record this attempt regardless of outcome ----------
    if email:
        await record_attempt(
            email,
            ip_address,
            succeeded=bool(login_ok),
            session=session,
        )

    # ---------- Validation failed ----------
    if errors:
        return templates.TemplateResponse(
            request=request,
            name="signin.html",
            context={
                "errors": errors,
                "email": email,
            },
        )

    # ---------- Create session ----------
    token = create_session_token()

    try:
        ttl = timedelta(days=30) if remember_me else timedelta(hours=3)
        session.add(
            Session(
                token=token,
                user_id=user.id,
                expires_at=datetime.utcnow() + ttl,
            )
        )

        await session.commit()

    except IntegrityError:
        await session.rollback()

        return templates.TemplateResponse(
            request=request,
            name="signin.html",
            context={
                "errors": {
                    "email": "There was an issue while logging in. Please contact us."
                },
                "email": email,
            },
        )

    response = RedirectResponse(
        url="/catalog",
        status_code=303,
    )

    if remember_me:
        response.set_cookie(
            key="session_token",
            value=token,
            max_age=60 * 60 * 24 * 30,  # 30 days
            httponly=True,
            secure=False,  # True in production
            samesite="lax",
        )
    else:
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            secure=False,
            samesite="lax",
        )

    return response


@router.get("/forgot-password")
async def forgot_password(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="forgot-password.html",
        context={
            "errors": {},
            "email": "",
        },
    )


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_post(
    request: Request,
    session: AsyncSession = Depends(get_session),
    email: str | None = Form(default=None),
):
    # ---------- Validation ----------
    errors = {}
    email = (email or "").strip()

    if not email:
        errors["email"] = "Email is required."
    elif "@" not in email or "." not in email.rsplit("@", 1)[1]:
        errors["email"] = "Enter a valid email address."

    # ---------- Validation failed ----------
    if errors:
        return templates.TemplateResponse(
            request=request,
            name="forgot-password.html",
            context={
                "errors": errors,
                "email": email,
            },
        )

    try:
        # ---------- Find user ----------
        statement = select(Users.id).where(
            Users.email == email,
        )

        result = await session.exec(statement)
        user_id = result.one_or_none()

        # ---------- Check existing token ----------
        necessary_checks = select(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.utcnow(),
        )

        result_checks = await session.exec(necessary_checks)
        existing_token = result_checks.first()

        has_available_token = existing_token is not None

        if user_id and has_available_token:
            return FileResponse(
                BASE_DIR / "static" / "rate-limited.html",
                status_code=429,
            )

        # ---------- Create token ----------
        if user_id and not has_available_token:
            token = create_session_token()

            reset_token = PasswordResetToken(
                user_id=user_id,
                token_hash=token,
            )

            session.add(reset_token)
            await session.commit()

            reset_link = f"https://grandelevationsolar.com/reset-password?token={token}"

            print("Reset Link: ", reset_link)

            await asyncio.to_thread(
                sync_gmail_dispatch,
                email,
                reset_link,
            )

        return templates.TemplateResponse(
            request=request,
            name="forgot-password.html",
            context={
                "errors": {},
                "email": email,
                "show_success": True,
            },
        )

    except ValueError:
        await session.rollback()
        return FileResponse(
            BASE_DIR / "static" / "500.html",
            status_code=500,
        )

    except SQLAlchemyError:
        await session.rollback()
        return FileResponse(
            BASE_DIR / "static" / "500.html",
            status_code=500,
        )

    except Exception:
        await session.rollback()
        return FileResponse(
            BASE_DIR / "static" / "500.html",
            status_code=500,
        )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    token = request.query_params.get("token")
    print("Token: ", token)
    statement = select(PasswordResetToken).where(
        PasswordResetToken.token_hash == token,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > datetime.utcnow(),
    )
    result = await session.exec(statement)
    existing_token = result.first()

    if existing_token is None:
        return FileResponse(
            BASE_DIR / "static" / "expired-link.html",
            status_code=400,
        )

    return templates.TemplateResponse(
        request,
        name="reset-password.html",
        context={
            "token": token,
        },
    )


@router.post("/reset-password")
async def reset_password_post(
    request: Request,
    token: str | None = Form(default=None),
    password: str | None = Form(default=None),
    confirm: str | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
):
    print("Token: ", token)
    errors = {}
    password = password or ""
    confirm = confirm or ""

    if not password:
        errors["password"] = "Password is required."

    elif len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."

    if password != confirm:
        errors["password"] = "Passwords must match."

    # ---------- Validation failed ----------
    if errors:
        return templates.TemplateResponse(
            request=request,
            name="reset-password.html",
            context={
                "request": request,
                "errors": errors,
                "token": token,
            },
        )

    try:
        # --------------- Get user id -----------
        statement = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.utcnow(),
        )
        reset_token = (await session.exec(statement)).first()
        print("Reset Token:", reset_token)

        if reset_token is None:
            return FileResponse(
                BASE_DIR / "static" / "expired-link.html",
                status_code=400,
            )

        user = await session.get(Users, reset_token.user_id)

        print("mipa")
        if user is None:
            return FileResponse(
                BASE_DIR / "static" / "404.html",
                status_code=400,
            )

        user.password_hash = password_hash.hash(password)
        print("Iska")
        # ------------- Update token state -----------

        reset_token.used_at = datetime.utcnow()
        print("Muska")

        #  Delete User Open Sessions
        await session.exec(delete(Session).where(Session.user_id == user.id))
        print("micky mouse")
        session.add(user)
        session.add(reset_token)
        await session.commit()

        return RedirectResponse(
            url="/signin",
            status_code=303,
        )

    except HTTPException:
        await session.rollback()
        traceback.print_exc()
        raise

    except SQLAlchemyError:
        await session.rollback()
        return FileResponse(
            BASE_DIR / "static" / "500.html",
            status_code=500,
        )

    except Exception as e:
        await session.rollback()
        print(e)
        return FileResponse(
            BASE_DIR / "static" / "500.html",
            status_code=500,
        )


@router.post("/logout")
async def logout(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    token = request.cookies.get("session_token")

    if token:
        statement = select(Session).where(Session.token == token)
        result = await session.exec(statement)

        db_session = result.first()

        if db_session:
            await session.delete(db_session)
            await session.commit()

    response = RedirectResponse(
        url="/",
        status_code=303,
    )

    response.delete_cookie("session_token")

    return response
