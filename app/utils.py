import secrets

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import Product


async def get_active_categories(session: AsyncSession) -> list[str]:
    """
    Categories that actually have products right now, pulled live from
    the DB -- not the static SPEC_MODELS list. This is what the admin
    panel can create products in, and it grows/shrinks automatically as
    products are added/removed, with no code change needed.
    """
    statement = select(Product.category).distinct()
    result = await session.exec(statement)
    return sorted(result.all())
