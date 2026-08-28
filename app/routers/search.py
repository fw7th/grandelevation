from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import BASE_DIR, templates
from app.database import get_session
from app.models import Favorite, Product

from ..utils import authenticate

router = APIRouter(tags=["search"])


@router.get("/search")
async def search_page(
    request: Request,
    q: str = Query(default=""),
    session: AsyncSession = Depends(get_session),
):
    try:
        user = await authenticate(request, session)
        products = []
        query = q.strip()

        if query:
            terms = query.split()
            conditions = []
            for term in terms:
                pattern = f"%{term}%"
                conditions.append(Product.name.ilike(pattern))
                conditions.append(Product.description.ilike(pattern))
                conditions.append(Product.category.ilike(pattern))

            statement = select(Product).where(or_(*conditions)).order_by(Product.name)
            result = await session.exec(statement)
            products = result.all()

        favorite_ids = set()
        if user:
            fav_result = await session.exec(
                select(Favorite.product_id).where(Favorite.user_id == user.id)
            )
            favorite_ids = set(fav_result.all())

        return templates.TemplateResponse(
            request=request,
            name="search.html",
            context={
                "query": query,
                "products": products,
                "username": user.username if user else None,
                "favorite_ids": favorite_ids,
            },
        )

    except Exception:
        await session.rollback()
        return FileResponse(
            BASE_DIR / "static" / "500.html",
            status_code=500,
        )
