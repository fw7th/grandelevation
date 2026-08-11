from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..database import get_session
from ..models import Product, Users
from ..specs import ADMIN_FORM_FIELDS, FIELD_CHOICES, validate_specs
from ..utils import authenticate

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


async def require_admin(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Users:
    user = await authenticate(request, session)
    if user is None or user.role != "admin":
        # raise PageException(message=None, status_code=404)
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
        context={
            "errors": {},
            "product": None,
            "form_values": {},
            "values": {},
            "choices": FIELD_CHOICES,
            "fields": [],
        },
    )


@router.get("/products/specs-fields")
async def admin_specs_fields(
    request: Request,
    category: str = "",
    admin: Users = Depends(require_admin),
):
    fields = ADMIN_FORM_FIELDS.get(category, [])
    return templates.TemplateResponse(
        request=request,
        name="admin/_specs_fields.html",
        context={"fields": fields, "choices": FIELD_CHOICES, "values": {}},
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
        # Re-render with everything they typed intact -- category, the
        # top-level fields, AND the spec values -- so nothing is lost.
        return templates.TemplateResponse(
            request=request,
            name="admin/product_form.html",
            context={
                "errors": {"specs": str(e)},
                "product": None,
                "form_values": {
                    "category": category,
                    "name": name,
                    "price": price,
                    "description": description,
                    "image_url": image_url,
                },
                "values": raw_specs,
                "choices": FIELD_CHOICES,
                "fields": ADMIN_FORM_FIELDS.get(category, []),
            },
        )

    product = Product(
        category=category,
        name=name,
        price=price,
        description=description,
        image_url=[u.strip() for u in image_url.split(",") if u.strip()]
        if image_url
        else [],
        specs=specs,
    )
    session.add(product)
    await session.commit()

    return RedirectResponse(url="/admin/products", status_code=303)
