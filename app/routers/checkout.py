import random
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session

from ..models import CartItem, Invoice, Product
from ..utils import authenticate

router = APIRouter(tags=["checkout"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/checkout")
async def checkout(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
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

    return templates.TemplateResponse(
        request=request,
        name="checkout.html",
        context={
            "username": user.username if user else None,
            "cart_items": cart_items,
            "system_bundles": [],
            "total": subtotal,
            "subtotal": subtotal,
        },
    )


@router.post("/checkout/complete")
async def complete_checkout(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in first")

    data = await request.json()
    delivery_method = data.get("delivery_method", "delivery")
    payment_method = data.get("payment_method", "transfer")
    delivery_location = data.get("location", "")
    delivery_note = data.get("delivery_note", "")

    # Fetch current cart items
    statement = (
        select(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(CartItem.user_id == user.id)
        .order_by(CartItem.updated_at.desc())
    )
    results = await session.exec(statement)
    cart_items = results.all()

    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    subtotal = 0.0
    items_list = []
    for cart_item, product in cart_items:
        item_total = cart_item.quantity * product.price
        subtotal += item_total
        items_list.append(
            {
                "product_id": product.id,
                "name": product.name,
                "price": product.price,
                "quantity": cart_item.quantity,
                "subtotal": item_total,
            }
        )

    # Delivery fee – match client calculation (₦4000 per item)
    delivery_fee = 0.0
    if delivery_method == "delivery":
        total_qty = sum(item["quantity"] for item in items_list)
        delivery_fee = total_qty * 4000

    total = subtotal + delivery_fee

    # Generate unique invoice number
    invoice_number = f"INV-{int(time.time())}-{random.randint(1000, 9999)}"

    invoice = Invoice(
        user_id=user.id,
        invoice_number=invoice_number,
        items=items_list,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        total=total,
        payment_method=payment_method,
        delivery_method=delivery_method,
        delivery_location=delivery_location,
        delivery_note=delivery_note,
        status="pending",
    )
    session.add(invoice)
    await session.commit()
    await session.refresh(invoice)

    # (Optional: clear the cart? Leave it; user can re-order)
    # We'll return the invoice ID so the frontend can redirect
    return {"invoice_id": invoice.id, "invoice_number": invoice_number}
