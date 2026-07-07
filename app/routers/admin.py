from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..auth import authenticate
from ..database import get_session
from ..models import Product, Users
from ..specs import validate_specs

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


async def require_admin(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Users:
    user = await authenticate(request, session)
    if user is None or user.role != "admin":
        raise HTTPException(status_code=404)
    return user


@router.get("/products")
async def admin_products_list(
    request: Request,
    admin: Users = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    statement = select(Product)
    result = await session.exec(statement)
    products = result.all()
    return templates.TemplateResponse(
        request=request,
        name="admin/products.html",
        context={"products": products},
    )


@router.get("/products/new")
async def admin_product_new(request: Request, admin: Users = Depends(require_admin)):
    return templates.TemplateResponse(
        request=request,
        name="admin/product_form.html",
        context={"errors": {}, "product": None},
    )


@router.post("/products/new")
async def admin_product_create(
    request: Request,
    admin: Users = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    category: str = Form(...),
    name: str = Form(...),
    price: float = Form(...),
    description: str = Form(...),
    image_url: str = Form(""),
):
    form = await request.form()
    known = {"category", "name", "price", "description", "image_url"}
    raw_specs = {k: v for k, v in form.items() if k not in known}

    try:
        specs = validate_specs(category, raw_specs)
    except ValueError as e:
        return templates.TemplateResponse(
            request=request,
            name="admin/product_form.html",
            context={"errors": {"specs": str(e)}, "product": None},
        )

    product = Product(
        category=category,
        name=name,
        price=price,
        description=description,
        image_url=image_url or None,
        specs=specs,
    )
    session.add(product)
    await session.commit()

    return RedirectResponse(url="/admin/products", status_code=303)
