from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import BASE_DIR, templates

from ..database import get_session
from ..models import Favorite, Product
from ..utils import authenticate

router = APIRouter(tags=["favorites"])


@router.post("/favorites/{product_id}")
async def toggle_favorite(
    request: Request,
    product_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(request, session)

    if not user:
        # Plain RedirectResponse won't navigate the browser on an htmx
        # request (htmx follows redirects via XHR). HX-Redirect is the
        # header htmx checks for "navigate the whole page here instead".
        response = Response(status_code=200)
        response.headers["HX-Redirect"] = "/signup"
        return response

    statement = select(Favorite).where(
        Favorite.user_id == user.id, Favorite.product_id == product_id
    )
    result = await session.exec(statement)
    existing = result.first()

    if existing:
        await session.delete(existing)
        is_favorited = False
    else:
        session.add(Favorite(user_id=user.id, product_id=product_id))
        is_favorited = True

    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="_favorite_button.html",
        context={
            "product_id": product_id,
            "is_favorited": is_favorited,
        },
    )


@router.get("/favorites")
async def favorites_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    try:
        user = await authenticate(request, session)

        if not user:
            return RedirectResponse(url="/signup", status_code=303)

        statement = (
            select(Product)
            .join(Favorite, Favorite.product_id == Product.id)
            .where(Favorite.user_id == user.id)
            .order_by(Favorite.created_at.desc())
        )
        result = await session.exec(statement)
        products = result.all()

        return templates.TemplateResponse(
            request=request,
            name="favorites.html",
            context={
                "products": products,
                "username": user.username,
                "favorite_ids": {p.id for p in products},
            },
        )

    except Exception:
        await session.rollback()
        return FileResponse(
            BASE_DIR / "static" / "500.html",
            status_code=500,
        )
