from typing import Iterable

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from specs import DISPLAY_FIELDS
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

    is_favorited = None
    if user:
        fav_statement = select(Favorite.product_id).where(
            Favorite.user_id == user.id,
        )
        fav_result = await session.exec(fav_statement)
        fav_ = fav_result.one_or_none()
        is_favorited = fav_ if fav_ else None

    statement = select(Product).where(Product.id == slug)
    result = await session.exec(statement)
    product = result.one()

    print("Product Specs: ", product.specs)

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


COMMON_NAME_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "with",
    "for",
    "of",
    "in",
    "to",
    "on",
    "at",
    "by",
    "from",
    "as",
    "is",
    "it",
    "this",
    "that",
    "are",
    "was",
    "solar",
    "panel",
    "panels",
    "inverter",
    "inverters",
    "battery",
    "batteries",
    "generator",
    "generators",
    "light",
    "lights",
    "fan",
    "fans",
    "accessory",
    "accessories",
    "street",
    "system",
    "systems",
    "w",
    "watt",
    "watts",
    "v",
    "volt",
    "volts",
    "a",
    "ah",
    "wh",
    "kw",
    "kwh",
    "kva",
    "mono",
    "poly",
    "monocrystalline",
    "polycrystalline",
    "lithium",
    "lead",
    "acid",
    "lifepo4",
    "gel",
}


async def get_similar_products(
    product: Product,
    session: AsyncSession,
    limit: int = 10,
) -> list[Product]:
    """
    Return products similar to `product`:
      - Same category
      - AND (similar name  OR  >=2 matching customer-facing specs)
    """
    stmt = select(Product).where(
        Product.category == product.category,
        Product.id != product.id,
    )
    result = await session.exec(stmt)
    candidates: Iterable[Product] = result.all()

    if not candidates:
        return []

    current_specs = product.specs or {}
    current_name = product.name.lower()

    # Significant words in the current product name
    current_words = {
        w.strip("()-,:;")
        for w in current_name.split()
        if len(w.strip("()-,:;")) > 2 and w.strip("()-,:;") not in COMMON_NAME_WORDS
    }

    display_fields = DISPLAY_FIELDS.get(product.category, [])
    scored: list[tuple[int, Product]] = []

    for candidate in candidates:
        cand_name = candidate.name.lower()
        cand_specs = candidate.specs or {}

        # ---- Name similarity ----
        name_match = False
        name_score = 0

        # Strong signal: one name contains the other
        if current_name in cand_name or cand_name in current_name:
            name_match = True
            name_score = 5
        else:
            cand_words = {
                w.strip("()-,:;")
                for w in cand_name.split()
                if len(w.strip("()-,:;")) > 2
            }
            shared = current_words & cand_words
            if shared:
                name_match = True
                name_score = len(shared) * 2

        # ---- Spec similarity (customer-facing fields only) ----
        spec_matches = 0
        for key in display_fields:
            if key not in current_specs or key not in cand_specs:
                continue
            a = str(current_specs[key]).lower().strip()
            b = str(cand_specs[key]).lower().strip()
            if a and a != "none" and a == b:
                spec_matches += 1

        # ---- Keep if name matches OR >=2 spec matches ----
        if name_match or spec_matches >= 2:
            total_score = name_score + spec_matches
            scored.append((total_score, candidate))

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:limit]]
