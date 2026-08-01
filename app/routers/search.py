from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

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
    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory="app/templates")

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
