from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..database import get_session
from ..models import Favorite, Product
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
    if not user:
        # Plain RedirectResponse won't navigate the browser on an htmx
        # request (htmx follows redirects via XHR). HX-Redirect is the
        # header htmx checks for "navigate the whole page here instead".
        response = Response(status_code=200)
        response.headers["HX-Redirect"] = "/signup"
        return response

    statement = select(Product).where(Product.id == slug)
    result = await session.exec(statement)
    product = result.one()

    print("Product Specs: ", product.specs)

    fav_statement = select(Favorite.product_id).where(Favorite.user_id == user.id)
    fav_result = await session.exec(fav_statement)
    fav_ = fav_result.one_or_none()
    is_favorited = fav_ if fav_ else None

    await session.commit()
    return templates.TemplateResponse(
        request=request,
        name="/products.html",
        context={
            "username": user.username if user else None,
            "product": product,
            "is_favorited": is_favorited,
            "categories": await get_active_categories(session),
        },
    )
