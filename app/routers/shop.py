from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session

from ..models import CartItem
from ..utils import authenticate

router = APIRouter(tags=["shop"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/cart")
async def cart(request: Request, session: AsyncSession = Depends(get_session)):
    user = await authenticate(request, session)
    if not user:
        return RedirectResponse("/catalog")

    statement = select(CartItem).where(CartItem.user_id == user.id)
    cartitems = await session.exec(statement)

    # TODO: query CartItem + Product, compute totals
    return templates.TemplateResponse(
        request=request,
        name="cart.html",
        context={
            "user": user,
            "cart_items": cartitems.all(),
            "system_bundles": [],
            "subtotal": 0.0,
            "vat": 0.0,
            "total": 0.0,
        },
    )


@router.post("/cart/add")
async def cart_add(
    request: Request,
    product_id: int = Form(...),
    quantity: int = Form(...),
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)
    if not user:
        return RedirectResponse("/catalog")

    cartitem = CartItem(
        user_id=user.id,
        product_id=product_id,
        quantity=quantity,
    )

    try:
        session.add(cartitem)
        await session.commit()

    except SQLAlchemyError:
        await session.rollback()


@router.get("/account")
async def account(request: Request, session: AsyncSession = Depends(get_session)):
    user = await authenticate(request, session)
    if not user:
        return RedirectResponse("/catalog")

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
