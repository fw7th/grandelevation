from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Path, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..auth import authenticate
from ..database import get_session
from ..models import Product

router = APIRouter(prefix="/products", tags=["products"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/{slug}")
async def product_page(
    slug: Annotated[
        str,
        Path(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    ],
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    try:
        statement = select(Product).where(Product.id == slug)
        result = session.exec(statement).all()

    except Exception as e:
        pass

    return templates.TemplateResponse(
        request=request,
        name="/products.html",
        context={
            "product": slug,
        },
    )
