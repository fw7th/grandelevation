from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .database import get_session, init_db
from .models import User
from .security import password_hash


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

    if not username:
        errors["username"] = "Username is required."

    if not email:
        errors["email"] = "Email is required."
    elif "@" not in email or "." not in email.split("@")[-1]:
        errors["email"] = "Enter a valid email address."

    if len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."

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

    statement = select(User).where(User.email == email)
    result = await session.exec(statement)
    existing_user = result.first()

    if existing_user:
        errors["email"] = "An account with this email already exists."

    user = User(
        username=username,
        email=email,
        password_hash=password_hash.hash(password),
    )

    session.add(user)
    await session.commit()
    await session.refresh(user)

    return RedirectResponse(
        url="/catalog",
        status_code=303,
    )


@app.get("/signin", response_class=HTMLResponse)
async def signin(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="signin.html",
        context={},
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
