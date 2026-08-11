from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..database import get_session
from ..models import Favorite, Product
from ..specs import DISPLAY_FIELDS
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

    similar_products = await get_similar_products(product, session)

    print("Product Images: ", product.image_url)

    await session.commit()
    return templates.TemplateResponse(
        request=request,
        name="/products.html",
        context={
            "username": user.username if user else None,
            "product": product,
            "images": product.image_url or [],
            "is_favorited": is_favorited,
            "categories": await get_active_categories(session),
            "similar_products": similar_products,
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
    candidate_pool: int = 80,
) -> list[Product]:
    """
    Return similar products with two performance guards:
      1. Only pull a small candidate pool from the DB (not the whole table).
      2. Pre-filter by name similarity in SQL so Python only scores relevant rows.
    """
    current_name = product.name.lower()
    name_words = [
        w.strip("()-,:;")
        for w in current_name.split()
        if len(w.strip("()-,:;")) > 2 and w.strip("()-,:;") not in COMMON_NAME_WORDS
    ][:6]  # cap at 6 words to avoid exploding the WHERE clause

    # Build name-matching filters (case-insensitive substring match)
    name_filters = []
    for word in name_words:
        pattern = f"%{word}%"
        name_filters.append(func.lower(Product.name).like(pattern))

    # Fetch a limited pool of same-category candidates.
    # We OR the name filters so we get products that share *any* significant word.
    # If no name words were extracted, we just grab the newest N items in the category.
    stmt = (
        select(Product)
        .where(
            Product.category == product.category,
            Product.id != product.id,
        )
        .where(or_(*name_filters) if name_filters else True)
        .order_by(Product.id.desc())  # newest first as a sensible default
        .limit(candidate_pool)
    )

    result = await session.exec(stmt)
    candidates = result.all()

    if not candidates:
        return []

    current_specs = product.specs or {}
    display_fields = DISPLAY_FIELDS.get(product.category, [])
    current_words = set(name_words)

    scored: list[tuple[int, Product]] = []

    for candidate in candidates:
        cand_name = candidate.name.lower()
        cand_specs = candidate.specs or {}

        # ---- Name score ----
        name_score = 0
        if current_name in cand_name or cand_name in current_name:
            name_score = 5
        else:
            cand_words = {
                w.strip("()-,:;")
                for w in cand_name.split()
                if len(w.strip("()-,:;")) > 2
            }
            shared = current_words & cand_words
            if shared:
                name_score = len(shared) * 2

        # ---- Spec matches (customer-facing only) ----
        spec_matches = 0
        for key in display_fields:
            if key not in current_specs or key not in cand_specs:
                continue
            a = str(current_specs[key]).lower().strip()
            b = str(cand_specs[key]).lower().strip()
            if a and a != "none" and a == b:
                spec_matches += 1

        if name_score > 0 or spec_matches >= 2:
            scored.append((name_score + spec_matches, candidate))

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:limit]]
