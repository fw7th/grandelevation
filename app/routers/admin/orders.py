from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import templates

from ...database import get_session
from ...models import Orders, Users
from .products import require_admin

router = APIRouter(prefix="/admin/orders", tags=["admin-orders"])

VALID_STATUSES = {"pending", "issue", "done"}


@router.get("")
async def admin_orders_list(
    request: Request,
    admin: Users = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    status: str = "",
):
    statement = select(Orders).order_by(Orders.created_at.desc())
    if status in VALID_STATUSES:
        statement = statement.where(Orders.status == status)

    result = await session.exec(statement)
    orders = result.all()

    return templates.TemplateResponse(
        request=request,
        name="admin/orders.html",
        context={
            "orders": orders,
            "active_status": status if status in VALID_STATUSES else "",
        },
    )


@router.post("/{order_id}/status")
async def admin_order_set_status(
    order_id: int,
    request: Request,
    admin: Users = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    form = await request.form()
    new_status = form.get("status", "")
    if new_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    order = await session.get(Orders, order_id)
    if not order:
        raise HTTPException(status_code=404)

    order.status = new_status
    session.add(order)
    await session.commit()

    return RedirectResponse(url="/admin/orders", status_code=303)


@router.post("/{order_id}/delete")
async def admin_order_delete(
    order_id: int,
    admin: Users = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    order = await session.get(Orders, order_id)
    if not order:
        raise HTTPException(status_code=404)

    # Only "done" orders can be deleted — pending/issue orders still
    # need attention and shouldn't disappear from the tracker.
    if order.status != "done":
        raise HTTPException(status_code=400, detail="Only done orders can be deleted")

    await session.delete(order)
    await session.commit()

    return RedirectResponse(url="/admin/orders", status_code=303)
