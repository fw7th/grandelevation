from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session

from ..utils import authenticate

router = APIRouter(tags=["shop"])


@router.get("/cart")
async def cart(request: Request, session: AsyncSession = Depends(get_session)):
    user = await authenticate(request, session)
    if not user:
        return RedirectResponse("/catalog")

    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory="app/templates")

    # TODO: query CartItem + Product, compute totals
    return templates.TemplateResponse(
        request=request,
        name="cart.html",
        context={
            "user": user,
            "cart_items": [],
            "system_bundles": [],
            "subtotal": 0.0,
            "vat": 0.0,
            "total": 0.0,
        },
    )


@router.get("/account")
async def account(request: Request, session: AsyncSession = Depends(get_session)):
    user = await authenticate(request, session)
    if not user:
        return RedirectResponse("/catalog")

    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory="app/templates")

    # TODO: query orders and saved_systems
    return templates.TemplateResponse(
        request=request,
        name="account.html",
        context={
            "user": user,
            "orders": [],
            "saved_systems": [],
        },
    )


@router.post("/cart/add")
async def cart_add(
    product_id: int = Form(...),
    quantity: int = Form(...),
    action: str = Form(...),  # "add" or "buy_now"
):
    pass


@router.post("/account/profile")
async def update_profile(
    request: Request,
    session: AsyncSession = Depends(get_session),
    username: str = Form(),
    email: str = Form(),
    phone: str = Form(default=""),
    password: str = Form(default=""),
):
    user = await authenticate(request, session)
    if not user:
        return RedirectResponse("/signin", status_code=303)

    from sqlmodel import select

    from app.models import Users

    user.username = username.strip()
    user.email = email.strip()

    if hasattr(user, "phone"):
        user.phone = phone.strip()

    if password and len(password) >= 8:
        from app.security import password_hash

        user.password_hash = password_hash.hash(password)

    session.add(user)
    await session.commit()

    return RedirectResponse("/account", status_code=303)
