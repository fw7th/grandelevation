# app/routers/seo.py
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..database import get_session
from ..models import Product

router = APIRouter()

BASE_URL = "https://grandelevationsolar.com"


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return (
        "User-agent: *\n"
        "Allow: /\n\n"
        "Disallow: /admin/\n"
        "Disallow: /internal/\n"
        "Disallow: /checkout\n"
        "Disallow: /account\n\n"
        f"Sitemap: {BASE_URL}/sitemap.xml\n"
    )


@router.get("/sitemap.xml")
async def sitemap(session: AsyncSession = Depends(get_session)):
    result = await session.exec(
        select(Product.id, Product.category, Product.updated_at)
    )
    rows = result.all()

    categories = {category for _, category, _ in rows if category}

    urls = [
        f"<url><loc>{BASE_URL}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>",
        f"<url><loc>{BASE_URL}/catalog</loc><changefreq>daily</changefreq><priority>0.9</priority></url>",
    ]

    for category in sorted(categories):
        urls.append(
            f"<url><loc>{BASE_URL}/catalog/category/{category}</loc>"
            f"<changefreq>daily</changefreq><priority>0.8</priority></url>"
        )

    for product_id, _, updated_at in rows:
        lastmod = (
            updated_at.date().isoformat() if updated_at else date.today().isoformat()
        )
        urls.append(
            f"<url><loc>{BASE_URL}/products/{product_id}</loc>"
            f"<lastmod>{lastmod}</lastmod><changefreq>weekly</changefreq></url>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(urls)
        + "</urlset>"
    )

    return Response(content=xml, media_type="application/xml")
