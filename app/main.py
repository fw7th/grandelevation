from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .auth import authenticate
from .database import get_session, init_db
from .models import Session, Users
from .routers import admin as admin_router
from .security import PageException, create_session_token, password_hash


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    yield


app = FastAPI(lifespan=lifespan)
app.include_router(admin_router.router)


# Static files (CSS, htmx.js) served from app/static at /static/*
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Jinja2 looks for .html files in app/templates
templates = Jinja2Templates(directory="app/templates")


@app.get("/")
async def home():
    return FileResponse("app/static/index.html")


@app.get("/signup", response_class=HTMLResponse)
async def signup(request: Request, session: AsyncSession = Depends(get_session)):
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


@app.post("/signup", response_class=HTMLResponse)
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
    elif "@" not in email:
        errors["email"] = "Enter a valid email address."
    elif "." not in email.rsplit("@", 1)[1]:
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
        await session.refresh(user)

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


@app.get("/signin")
async def signin(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)

    if user:
        return RedirectResponse("/catalog")

    return templates.TemplateResponse(
        request=request,
        name="signin.html",
        context={
            "errors": {},
            "email": "",
        },
    )


@app.post("/signin", response_class=HTMLResponse)
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

    # ---------- Validation ----------
    if not email:
        errors["email"] = "Email is required."
    elif "@" not in email:
        errors["email"] = "Enter a valid email address."
    elif "." not in email.rsplit("@", 1)[1]:
        errors["email"] = "Enter a valid email address."

    if not password:
        errors["password"] = "Password is required."

    statement = select(Users).where(Users.email == email)
    result = await session.exec(statement)
    user = result.first()

    if user is None:
        errors["email"] = "Invalid email or password."

    elif not password_hash.verify(password, user.password_hash):
        errors["email"] = "Invalid email or password."

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


@app.get("/catalog")
async def catalog(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)

    if user is None:
        return RedirectResponse("/signin")

    return templates.TemplateResponse(
        request=request,
        name="catalog.html",
        context={
            "username": user.username,
        },
    )


@app.post("/logout")
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


@app.exception_handler(PageException)
async def page_exception_handler(request: Request, exc: PageException):
    # Craft your custom HTML error layout
    if exc.message is not None:
        html_content = f"""
        <html>
            <head><title>Error Occurred</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: #ff4d4d;">Oops! Something went wrong</h1>
                <p style="font-size: 18px;">{exc.message}</p>
                <a href="/" style="color: #0066cc; text-decoration: none;">Return Home</a>
            </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=exc.status_code)
    else:
        return FileResponse("app/static/404.html")
