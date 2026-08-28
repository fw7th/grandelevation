import random
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import BASE_DIR, templates
from app.database import get_session

from ..models import CartItem, Invoice, Product, Users
from ..utils import authenticate

router = APIRouter(tags=["checkout"])


@router.get("/checkout")
async def checkout(
    request: Request,
    session: AsyncSession = Depends(get_session),
    product_id: int | None = None,
    quantity: int = 1,
):
    user = await authenticate(request, session)
    if not user:
        return RedirectResponse("/catalog")

    checkout_items = []
    subtotal = 0.0
    buy_now_mode = product_id is not None
    build_mode = False

    if buy_now_mode:
        # ... your existing buy_now code ...
        product = await session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        item = {
            "product": product,
            "quantity": quantity,
            "subtotal": product.price * quantity,
        }
        checkout_items.append(item)
        subtotal = item["subtotal"]

    elif request.query_params.get("build") and request.session.get(
        "checkout_build_items"
    ):
        # ===== NEW: Build mode from session =====
        build_mode = True
        items = request.session.get("checkout_build_items")  # consume once
        for entry in items:
            product = await session.get(Product, entry["product_id"])
            if not product:
                continue
            item = {
                "product": product,
                "quantity": entry.get("quantity", 1),
                "subtotal": product.price * entry.get("quantity", 1),
            }
            checkout_items.append(item)
            subtotal += item["subtotal"]

    else:
        # ... your existing cart mode code ...
        statement = (
            select(CartItem, Product)
            .join(Product, CartItem.product_id == Product.id)
            .where(CartItem.user_id == user.id)
            .order_by(CartItem.updated_at.desc())
        )
        results = await session.exec(statement)
        for cart_item, product in results.all():
            item = {
                "product": product,
                "quantity": cart_item.quantity,
                "subtotal": cart_item.quantity * product.price,
            }
            checkout_items.append(item)
            subtotal += item["subtotal"]

    return templates.TemplateResponse(
        request=request,
        name="checkout.html",
        context={
            "username": user.username,
            "checkout_items": checkout_items,
            "buy_now_mode": buy_now_mode,
            "buy_now_product_id": product_id if buy_now_mode else None,
            "buy_now_quantity": quantity if buy_now_mode else None,
            "total": subtotal,
            "subtotal": subtotal,
            "build_mode": build_mode,
            "build_items": [],
        },
    )


@router.post("/checkout/build")
async def checkout_build(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    data = await request.json()
    items = data.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="No items provided")

    request.session["checkout_build_items"] = items
    return {"redirect_url": "/checkout?build=1"}  # <-- JSON, not RedirectResponse


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
    items_payload = data.get("items")  # buy-now only
    client_delivery_fee = data.get("delivery_fee", 0.0)

    items_list = []
    subtotal = 0.0
    source = None  # 'buy_now' | 'build' | 'cart'

    # ─── 1. Buy-now mode ───
    if items_payload:
        source = "buy_now"
        for item in items_payload:
            product_id = item.get("product_id")
            qty = item.get("quantity", 1)
            product = await session.get(Product, product_id)
            if not product:
                raise HTTPException(
                    status_code=400, detail=f"Product {product_id} not found"
                )
            item_subtotal = product.price * qty
            subtotal += item_subtotal
            items_list.append(
                {
                    "product_id": product.id,
                    "name": product.name,
                    "price": product.price,
                    "quantity": qty,
                    "subtotal": item_subtotal,
                }
            )

    # ─── 2. Build mode (from session) ───
    elif request.session.get("checkout_build_items"):
        source = "build"
        build_items = request.session.get("checkout_build_items")
        for entry in build_items:
            product_id = entry.get("product_id")
            qty = entry.get("quantity", 1)
            product = await session.get(Product, product_id)
            if not product:
                continue
            item_subtotal = product.price * qty
            subtotal += item_subtotal
            items_list.append(
                {
                    "product_id": product.id,
                    "name": product.name,
                    "price": product.price,
                    "quantity": qty,
                    "subtotal": item_subtotal,
                }
            )

    # ─── 3. Cart mode ───
    else:
        source = "cart"
        statement = (
            select(CartItem, Product)
            .join(Product, CartItem.product_id == Product.id)
            .where(CartItem.user_id == user.id)
        )
        results = await session.exec(statement)
        cart_items = results.all()

        if not cart_items:
            raise HTTPException(status_code=400, detail="Cart is empty")

        for cart_item, product in cart_items:
            item_subtotal = cart_item.quantity * product.price
            subtotal += item_subtotal
            items_list.append(
                {
                    "product_id": product.id,
                    "name": product.name,
                    "price": product.price,
                    "quantity": cart_item.quantity,
                    "subtotal": item_subtotal,
                }
            )

    if not items_list:
        raise HTTPException(status_code=400, detail="No items to checkout")

    # ─── Delivery fee (trust client; fix the overwrite bug) ───
    delivery_fee = client_delivery_fee if delivery_method == "delivery" else 0.0
    total = subtotal + delivery_fee

    # ─── Create invoice ───
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

    # ─── Cleanup ───
    if source == "cart":
        stmt = delete(CartItem).where(CartItem.user_id == user.id)
        await session.exec(stmt)
        await session.commit()

    if source == "build":
        request.session.pop("checkout_build_items", None)

    return {"invoice_id": invoice.id, "invoice_number": invoice_number}


@router.get("/invoice/{invoice_id}")
async def view_invoice(
    invoice_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user_page = await authenticate(request, session)

    invoice = await session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Load user details (for display name/email)
    user = await session.get(Users, invoice.user_id)

    # Generate the full URL for this invoice (to include in WhatsApp message)
    invoice_url = str(request.url_for("view_invoice", invoice_id=invoice.id))
    # But request.url_for may not work if we don't name the route; we'll construct manually
    # Actually, we can use request.url.path and replace, but easier:
    base_url = str(request.base_url).rstrip("/")
    invoice_url = f"{base_url}/invoice/{invoice.id}"

    return templates.TemplateResponse(
        request=request,
        name="invoice.html",
        context={
            "username": user_page.username if user_page else None,
            "invoice": invoice,
            "user": user,
            "invoice_url": invoice_url,
            "whatsapp_number": "2348107730018",  # from checkout.html
        },
    )
