from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import BASE_DIR, templates

from ..blob_storage import BlobStorageError, delete_images, upload_image
from ..database import get_session
from ..models import CartItem, Favorite, Product, Users
from ..specs import ADMIN_FORM_FIELDS, FIELD_CHOICES, validate_specs
from ..utils import authenticate

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_admin(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Users:
    user = await authenticate(request, session)
    if user is None or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
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
            "existing_images": [],
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


async def _upload_new_images(
    images: list[UploadFile], category: str
) -> tuple[list[str], str | None]:
    """
    Upload any non-empty files in `images` to Vercel Blob.

    Returns (urls, error). If error is set, urls may be partial — callers
    should treat a non-None error as "stop and re-render the form".
    """
    urls: list[str] = []
    for image in images:
        if not image or not image.filename:
            continue
        try:
            result = await upload_image(image, category)
        except BlobStorageError as e:
            return urls, str(e)
        urls.append(result["url"])
    return urls, None


@router.post("/products/new")
async def admin_product_create(
    request: Request,
    admin: Users = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    category: str = Form(...),
    name: str = Form(...),
    price: float = Form(...),
    description: str = Form(...),
    images: list[UploadFile] = File(default=[]),
):
    form = await request.form()
    known = {"category", "name", "price", "description", "images"}
    raw_specs = {k: v for k, v in form.items() if k not in known}

    def rerender(error: str):
        return templates.TemplateResponse(
            request=request,
            name="admin/product_form.html",
            context={
                "errors": {"specs": error},
                "product": None,
                "form_values": {
                    "category": category,
                    "name": name,
                    "price": price,
                    "description": description,
                },
                "values": raw_specs,
                "choices": FIELD_CHOICES,
                "fields": ADMIN_FORM_FIELDS.get(category, []),
                "existing_images": [],
            },
        )

    try:
        specs = validate_specs(category, raw_specs)
    except ValueError as e:
        return rerender(str(e))

    image_urls, upload_error = await _upload_new_images(images, category)
    if upload_error:
        if image_urls:
            await delete_images(image_urls)
        return rerender(upload_error)

    product = Product(
        category=category,
        name=name,
        price=price,
        description=description,
        image_url=image_urls,
        specs=specs,
    )
    session.add(product)
    await session.commit()

    return RedirectResponse(url="/admin/products", status_code=303)


@router.get("/products/{product_id}/edit")
async def admin_product_edit(
    request: Request,
    product_id: int,
    admin: Users = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="admin/product_form.html",
        context={
            "errors": {},
            "product": product,
            "form_values": {
                "category": product.category,
                "name": product.name,
                "price": product.price,
                "description": product.description,
            },
            "values": product.specs,
            "choices": FIELD_CHOICES,
            "fields": ADMIN_FORM_FIELDS.get(product.category, []),
            "existing_images": product.image_url or [],
        },
    )


@router.post("/products/{product_id}/edit")
async def admin_product_update(
    request: Request,
    product_id: int,
    admin: Users = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    category: str = Form(...),
    name: str = Form(...),
    price: float = Form(...),
    description: str = Form(...),
    images: list[UploadFile] = File(default=[]),
    keep_images: list[str] = Form(default=[]),
):
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404)

    form = await request.form()
    known = {"category", "name", "price", "description", "images", "keep_images"}
    raw_specs = {k: v for k, v in form.items() if k not in known}

    existing = product.image_url or []
    kept = [u for u in existing if u in set(keep_images)]
    removed = [u for u in existing if u not in set(keep_images)]

    def rerender(error: str):
        return templates.TemplateResponse(
            request=request,
            name="admin/product_form.html",
            context={
                "errors": {"specs": error},
                "product": product,
                "form_values": {
                    "category": category,
                    "name": name,
                    "price": price,
                    "description": description,
                },
                "values": raw_specs,
                "choices": FIELD_CHOICES,
                "fields": ADMIN_FORM_FIELDS.get(category, []),
                # Show what the admin still had checked, not the
                # original list, so a validation error doesn't
                # silently un-remove images they'd already unchecked.
                "existing_images": kept,
            },
        )

    try:
        specs = validate_specs(category, raw_specs)
    except ValueError as e:
        return rerender(str(e))

    new_urls, upload_error = await _upload_new_images(images, category)
    if upload_error:
        if new_urls:
            await delete_images(new_urls)
        return rerender(upload_error)

    product.category = category
    product.name = name
    product.price = price
    product.description = description
    product.image_url = kept + new_urls
    product.specs = specs
    session.add(product)
    await session.commit()

    # Only delete from the bucket after the DB write succeeds, so a
    # crash between the two never leaves a product pointing at a
    # blob we've already destroyed.
    if removed:
        try:
            await delete_images(removed)
        except BlobStorageError:
            # The product record is already correct; a lingering
            # orphaned blob is a cheap price for not losing data.
            pass

    return RedirectResponse(url="/admin/products", status_code=303)


@router.post("/products/{product_id}/delete")
async def admin_product_delete(
    product_id: int,
    admin: Users = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404)

    # Delete related favorites and cart items to avoid FK errors
    stmt_fav = delete(Favorite).where(Favorite.product_id == product_id)
    await session.exec(stmt_fav)

    stmt_cart = delete(CartItem).where(CartItem.product_id == product_id)
    await session.exec(stmt_cart)

    image_urls = product.image_url or []

    await session.delete(product)
    await session.commit()

    if image_urls:
        try:
            await delete_images(image_urls)
        except BlobStorageError:
            # Product is already gone from the DB; an orphaned blob
            # doesn't block the admin flow.
            pass

    return RedirectResponse(url="/admin/products", status_code=303)
