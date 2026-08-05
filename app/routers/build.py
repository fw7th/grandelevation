from fastapi import APIRouter, Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session

from ..utils import authenticate

router = APIRouter(tags=["build"])


@router.get("/build")
async def build_page(request: Request, session: AsyncSession = Depends(get_session)):
    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory="app/templates")

    # Public page — no auth required
    # If logged in, we can load their saved favorites as starting products
    user = await authenticate(request, session)
    products = []

    if user:
        from sqlmodel import select

        from app.models import Favorite, Product

        result = await session.exec(
            select(Product)
            .join(Favorite, Favorite.product_id == Product.id)
            .where(Favorite.user_id == user.id)
            .order_by(Favorite.created_at.desc())
        )
        products = result.all()

    return templates.TemplateResponse(
        request=request,
        name="build.html",
        context={
            "products": products,
            "username": user.username if user else None,
            "favorite_ids": {p.id for p in products} if user else set(),
        },
    )
