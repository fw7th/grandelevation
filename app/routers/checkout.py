from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.security import password_hash

from ..models import CartItem, Product, Users
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

    return templates.TemplateResponse(
        request=request,
        name="checkout.html",
        context={
            "username": user.username if user else None,
            #        "cart_items": cart_items,
            "system_bundles": [],
            #        "total": subtotal,
            #        "subtotal": subtotal,
            #        "added_product": added_product,
        },
    )
