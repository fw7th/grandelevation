import traceback

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import BASE_DIR, templates

from ..database import get_session
from ..models import Favorite
from ..services.featured import PAGE_SIZE, get_catalog_page
from ..specs import SPEC_MODELS
from ..utils import authenticate, get_active_categories

router = APIRouter(tags=["catalog"])


async def _favorite_ids(session: AsyncSession, user) -> set[int]:
    if not user:
        return set()
    result = await session.exec(
        select(Favorite.product_id).where(Favorite.user_id == user.id)
    )
    return set(result.all())


async def _render_catalog(request, session, category: str | None = None):
    user = await authenticate(request, session)
    products, has_more = await get_catalog_page(session, 0, PAGE_SIZE, category)
    return templates.TemplateResponse(
        request=request,
        name="catalog.html",
        context={
            "products": products,
            "has_more": has_more,
            "next_offset": PAGE_SIZE,
            "active_category": category,
            "username": user.username if user else None,
            "favorite_ids": await _favorite_ids(session, user),
            "categories": await get_active_categories(session),
        },
    )


@router.get("/catalog")
async def catalog(request: Request, session: AsyncSession = Depends(get_session)):
    try:
        return await _render_catalog(request, session)
    except Exception:
        traceback.print_exc()
        await session.rollback()
        return FileResponse(BASE_DIR / "static" / "500.html", status_code=500)


@router.get("/catalog/category/{category}")
async def catalog_by_category(
    request: Request, category: str, session: AsyncSession = Depends(get_session)
):
    if category not in SPEC_MODELS:
        raise HTTPException(status_code=404, detail="Unknown category")
    try:
        return await _render_catalog(request, session, category)
    except Exception:
        traceback.print_exc()
        await session.rollback()
        return FileResponse(BASE_DIR / "static" / "500.html", status_code=500)


@router.get("/catalog/more")
async def catalog_more(
    request: Request,
    offset: int = 0,
    category: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    if category is not None and category not in SPEC_MODELS:
        raise HTTPException(status_code=404, detail="Unknown category")
    try:
        user = await authenticate(request, session)
        offset = max(offset, 0)
        products, has_more = await get_catalog_page(
            session, offset, PAGE_SIZE, category
        )
        return templates.TemplateResponse(
            request=request,
            name="_catalog_more.html",
            context={
                "products": products,
                "has_more": has_more,
                "next_offset": offset + PAGE_SIZE,
                "active_category": category,
                "username": user.username if user else None,
                "favorite_ids": await _favorite_ids(session, user),
                "oob": True,
            },
        )
    except Exception:
        traceback.print_exc()
        await session.rollback()
        return Response(status_code=500)
