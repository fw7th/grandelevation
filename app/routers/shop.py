from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.security import password_hash

from ..models import CartItem, Invoice, Product, SavedSystem, Users
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


@router.post("/cart/remove")
async def cart_remove(
    request: Request,
    cart_item_id: int = Form(...),
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)
    if not user:
        return RedirectResponse("/catalog")

    cart_item = await session.get(CartItem, cart_item_id)

    # Safety check: only delete if it exists and belongs to this user
    if cart_item and cart_item.user_id == user.id:
        try:
            await session.delete(cart_item)
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()

    return RedirectResponse("/cart", status_code=status.HTTP_302_FOUND)


@router.post("/cart/update")
async def cart_update(
    request: Request,
    cart_item_id: int = Form(...),
    delta: int = Form(...),
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)
    if not user:
        return RedirectResponse("/catalog")

    cart_item = await session.get(CartItem, cart_item_id)
    if not cart_item or cart_item.user_id != user.id:
        return RedirectResponse("/cart", status_code=status.HTTP_302_FOUND)

    new_qty = cart_item.quantity + delta

    if new_qty <= 0:
        await session.delete(cart_item)
    else:
        cart_item.quantity = new_qty

    try:
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()

    return RedirectResponse("/cart", status_code=status.HTTP_302_FOUND)


@router.get("/account")
async def account(request: Request, session: AsyncSession = Depends(get_session)):
    user = await authenticate(request, session)
    if not user:
        return RedirectResponse("/catalog")

    success = request.query_params.get("updated") == "1"

    # ─── FETCH INVOICES ───
    stmt = (
        select(Invoice)
        .where(Invoice.user_id == user.id)
        .order_by(Invoice.created_at.desc())
    )
    result = await session.exec(stmt)
    invoices = result.all()

    return templates.TemplateResponse(
        request=request,
        name="account.html",
        context={
            "username": user.username,
            "email": user.email,
            "phone": getattr(user, "phone", "") or "",
            "success": success,
            "rate_limited": False,
            "errors": {},
            "orders": invoices,
        },
    )


@router.post("/account/profile")
async def update_profile(
    request: Request,
    session: AsyncSession = Depends(get_session),
    username: str = Form(default=""),
    email: str = Form(default=""),
    phone: str = Form(default=""),
    password: str = Form(default=""),
):
    user = await authenticate(request, session)
    if not user:
        return RedirectResponse("/signin", status_code=303)

    username = username.strip()
    email = email.strip()
    phone = phone.strip()
    password = password or ""

    current_phone = getattr(user, "phone", "") or ""

    # No changes
    if (
        user.username == username
        and user.email == email
        and current_phone == phone
        and not password
    ):
        return templates.TemplateResponse(
            request=request,
            name="account.html",
            context={
                "username": user.username,
                "email": user.email,
                "phone": current_phone,
                "success": False,
                "rate_limited": False,
                "errors": {},
                "orders": [],
                "saved_systems": [],
            },
        )

    # Rate limit
    if user.updated_at and (user.updated_at + timedelta(hours=3)) >= datetime.utcnow():
        return templates.TemplateResponse(
            request=request,
            name="account.html",
            context={
                "username": user.username,
                "email": user.email,
                "phone": current_phone,
                "success": False,
                "rate_limited": True,
                "errors": {},
                "orders": [],
                "saved_systems": [],
            },
        )

    errors = {}

    if not username:
        errors["username"] = "Username is required."
    elif username != user.username:
        stmt = select(Users).where(Users.username == username)
        result = await session.exec(stmt)
        if result.first():
            errors["username"] = "This username is already taken."

    if not email:
        errors["email"] = "Email is required."
    elif "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        errors["email"] = "Enter a valid email address."
    elif email != user.email:
        stmt = select(Users).where(Users.email == email)
        result = await session.exec(stmt)
        if result.first():
            errors["email"] = "An account with this email already exists."

    if password and len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."

    if errors:
        return templates.TemplateResponse(
            request=request,
            name="account.html",
            context={
                "username": username,
                "email": email,
                "phone": phone,
                "success": False,
                "rate_limited": False,
                "errors": errors,
                "orders": [],
                "saved_systems": [],
            },
        )

    # Apply
    user.username = username
    user.email = email
    if hasattr(user, "phone"):
        user.phone = phone

    if password:
        user.password_hash = password_hash.hash(password)

    session.add(user)
    await session.commit()

    return RedirectResponse("/account?updated=1", status_code=303)
