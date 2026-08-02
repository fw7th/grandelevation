from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..database import get_session
from ..models import Product
from ..utils import authenticate, get_active_categories

router = APIRouter(prefix="/products", tags=["products"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/{slug}")
async def product_page(
    slug: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)
    statement = select(Product).where(Product.id == slug)
    result = await session.exec(statement)
    product = result.one()

    print("Product Specs: ", product.specs)

    return templates.TemplateResponse(
        request=request,
        name="/products.html",
        context={
            "username": user.username if user else None,
            "product": product,
            "categories": await get_active_categories(session),
        },
    )
