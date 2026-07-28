import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .auth import authenticate
from .database import get_session, init_db
from .models import Favorite, PasswordResetToken, Product, Session, Users
from .routers import admin as admin_router
from .routers import products as product_router
from .security import (
    PageException,
    create_session_token,
    is_locked_out,
    password_hash,
    record_attempt,
)
from .services.featured import get_daily_featured
from .specs import (
    SPEC_MODELS,
)  # still needed for /catalog/category/{category} validation
from .utils import (
    get_active_categories,
    sync_gmail_dispatch,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    yield


app = FastAPI(lifespan=lifespan)
app.include_router(admin_router.router)
app.include_router(product_router.router)


# Static files (CSS, htmx.js) served from app/static at /static/*
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Jinja2 looks for .html files in app/templates
templates = Jinja2Templates(directory="app/templates")


@app.get("/")
async def home():
    return FileResponse("app/static/index.html")


@app.get("/signup", response_class=HTMLResponse)
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
    response: Response,
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
    elif "@" not in email:
        errors["email"] = "Enter a valid email address."
    elif "." not in email.rsplit("@", 1)[1]:
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


@app.get("/catalog")
async def catalog(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)

    products = await get_daily_featured(session, count=15)

    favorite_ids: set[int] = set()
    if user:
        fav_statement = select(Favorite.product_id).where(Favorite.user_id == user.id)
        fav_result = await session.exec(fav_statement)
        favorite_ids = set(fav_result.all())

    return templates.TemplateResponse(
        request=request,
        name="catalog.html",
        context={
            "products": products,
            "username": user.username if user else None,
            "favorite_ids": favorite_ids,
            "categories": await get_active_categories(session),
        },
    )


@app.get("/catalog/category/{category}")
async def catalog_by_category(
    request: Request,
    category: str,
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)

    if category not in SPEC_MODELS:
        raise HTTPException(status_code=404, detail="Unknown category")

    statement = select(Product).where(Product.category == category)
    result = await session.exec(statement)
    products = result.all()

    favorite_ids: set[int] = set()
    if user:
        fav_statement = select(Favorite.product_id).where(Favorite.user_id == user.id)
        fav_result = await session.exec(fav_statement)
        favorite_ids = set(fav_result.all())

    return templates.TemplateResponse(
        request=request,
        name="catalog.html",
        context={
            "products": products,
            "username": user.username if user else None,
            "favorite_ids": favorite_ids,
            "categories": await get_active_categories(session),
            "active_category": category,
        },
    )


@app.get("/forgot-password")
async def forgot_password(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="forgot-password.html",
        context={
            "errors": {},
            "email": "",
        },
    )


@app.post("/forgot-password", response_class=HTMLResponse)
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
    elif "@" not in email:
        errors["email"] = "Enter a valid email address."
    elif "." not in email.rsplit("@", 1)[1]:
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

    statement = select(Users.id).where(
        Users.email == email,
    )
    result = await session.exec(statement)
    user_id = result.one_or_none()

    necessary_checks = select(PasswordResetToken).where(
        PasswordResetToken.user_id == user_id,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > datetime.utcnow(),
    )
    result_checks = await session.exec(necessary_checks)
    existing_token = result_checks.first()
    # has available token
    has_available_token = existing_token is not None

    # ---------- Create token ----------
    token = create_session_token()

    if user_id and not has_available_token:
        try:
            reset_token = PasswordResetToken(
                user_id=user_id,
                token_hash=password_hash.hash(token),
            )

            session.add(reset_token)
            await session.commit()

            reset_link = (
                f"https://grandelevationsolar.com/reset-password?token={reset_token}"
            )

            result = await asyncio.to_thread(
                sync_gmail_dispatch,
                email,
                reset_link,
            )

        except ValueError as val_err:
            raise HTTPException(status_code=500, detail=str(val_err))
        except Exception as err:
            raise HTTPException(
                status_code=500, detail=f"Google API routing failure: {str(err)}"
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

    # login_ok = user is not None and password_hash.verify(password, user.password_hash)


@app.post("/favorites/{product_id}")
async def toggle_favorite(
    request: Request,
    product_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)

    if not user:
        # Plain RedirectResponse won't navigate the browser on an htmx
        # request (htmx follows redirects via XHR). HX-Redirect is the
        # header htmx checks for "navigate the whole page here instead".
        response = Response(status_code=200)
        response.headers["HX-Redirect"] = "/signup"
        return response

    statement = select(Favorite).where(
        Favorite.user_id == user.id, Favorite.product_id == product_id
    )
    result = await session.exec(statement)
    existing = result.first()

    if existing:
        await session.delete(existing)
        is_favorited = False
    else:
        session.add(Favorite(user_id=user.id, product_id=product_id))
        is_favorited = True

    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="_favorite_button.html",
        context={
            "product_id": product_id,
            "is_favorited": is_favorited,
        },
    )


@app.get("/favorites")
async def favorites_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)

    if not user:
        return RedirectResponse(url="/signup", status_code=303)

    statement = (
        select(Product)
        .join(Favorite, Favorite.product_id == Product.id)
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc())
    )
    result = await session.exec(statement)
    products = result.all()

    return templates.TemplateResponse(
        request=request,
        name="favorites.html",
        context={
            "products": products,
            "username": user.username,
            "favorite_ids": {p.id for p in products},
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
