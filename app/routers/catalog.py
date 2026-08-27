from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import templates

from ..database import get_session
from ..models import Favorite, Product
from ..services.featured import get_daily_featured
from ..specs import (
    SPEC_MODELS,
)
from ..utils import authenticate, get_active_categories

router = APIRouter(tags=["catalog"])


@router.get("/catalog")
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


@router.get("/catalog/category/{category}")
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
