from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .database import get_session, init_db
from .models import Session, Users
from .security import create_session_token, password_hash


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    yield


app = FastAPI(lifespan=lifespan)


# Static files (CSS, htmx.js) served from app/static at /static/*
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Jinja2 looks for .html files in app/templates
templates = Jinja2Templates(directory="app/templates")


@app.get("/")
async def home():
    return FileResponse("app/static/index.html")


@app.get("/signup", response_class=HTMLResponse)
async def signup(request: Request):
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

    # ---------- Create user ----------
    user = Users(
        username=username,
        email=email,
        password_hash=password_hash.hash(password),
    )

    session.add(user)

    try:
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

    token = create_session_token()

    session_obj = Session(
        token=token,
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=30),
    )

    session.add(session_obj)
    await session.commit()

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


@app.get("/signin", response_class=HTMLResponse)
async def signin(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="signin.html",
        context={},
    )


@app.get("/catalog/{username}", response_class=HTMLResponse)
async def catalog(request: Request, username: str):
    return templates.TemplateResponse(
        request=request,
        name="catalog.html",
        context={
            "username": username,
        },
    )


@app.post("/api/ping", response_class=HTMLResponse)
def ping(request: Request):
    """
    A tiny htmx demo endpoint: returns a fragment of HTML, not a full page.
    This is the core pattern we'll reuse for the real compatibility checker:
    htmx sends a request, FastAPI returns a small chunk of rendered HTML,
    htmx swaps it into the page. No JSON, no client-side JS framework.
    """
    return templates.TemplateResponse(
        request=request,
        name="_ping_result.html",
        context={},
    )
