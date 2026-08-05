from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session

from ..models import CartItem, Product
from ..utils import authenticate

router = APIRouter(tags=["shop"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/cart")
async def cart(request: Request, session: AsyncSession = Depends(get_session)):
    user = await authenticate(request, session)
    if not user:
        return RedirectResponse("/catalog")

    statement = (
        select(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(CartItem.user_id == user.id)
        .order_by(CartItem.updated_at.desc())  # LIFO: newest first
    )

    results = await session.exec(statement)
    cart_items = results.all()

    subtotal = 0.0
    # Each result is (CartItem, Product)
    for cart_item, product in cart_items:
        subtotal += cart_item.quantity * product.price

    # Dopamine hit: product just added?
    added_product = None
    added_param = request.query_params.get("added")
    if added_param:
        try:
            added_product = await session.get(Product, int(added_param))
        except (ValueError, TypeError):
            pass

    return templates.TemplateResponse(
        request=request,
        name="cart.html",
        context={
            "username": user.username if user else None,
            "cart_items": cart_items,
            "system_bundles": [],
            "total": subtotal,
            "subtotal": subtotal,
            "added_product": added_product,
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

    return RedirectResponse(
        f"/cart?added={product_id}", status_code=status.HTTP_302_FOUND
    )


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
