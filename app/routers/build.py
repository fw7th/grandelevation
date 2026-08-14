from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.build_model import (
    SystemBundle,
    SystemConfiguration,
    SystemProductSelection,
)
from app.database import get_session
from app.models import Product
from app.specs import (
    AccessoryBundleSpecs,
    BatterySpecs,
    InverterSpecs,
    PanelSpecs,
    SolarGeneratorSpecs,
)

router = APIRouter(tags=["build"])
templates = Jinja2Templates(directory="app/templates")

PEAK_SUN_HOURS = 4.5
SYSTEM_EFFICIENCY = 0.80
VOC_TEMP_MARGIN = 1.15


def _dod(chemistry: str) -> float:
    return 0.85 if chemistry == "lithium" else 0.50


def _product_to_dict(product: Product, quantity: int = 1) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "price": product.price * quantity,
        "image_url": product.image_url[0] if product.image_url else "",
        "specs": {**product.specs, "quantity": quantity},
    }


@router.get("/build")
async def build_page(request: Request, session: AsyncSession = Depends(get_session)):
    from app.utils import authenticate

    user = await authenticate(request, session)
    return templates.TemplateResponse(
        request=request,
        name="build.html",
        context={"username": user.username if user else None},
    )


@router.post("/build/recommend")
async def recommend_system(
    config: SystemConfiguration,
    session: AsyncSession = Depends(get_session),
) -> SystemBundle:
    daily_wh = sum(a.qty * a.watts * a.hours_per_day for a in config.appliances)
    peak_w = sum(a.qty * a.watts for a in config.appliances)
    autonomy_days = config.autonomy_hours / 24

    result = await session.exec(select(Product))
    all_products = result.all()

    panels = [p for p in all_products if p.category == "panel"]
    inverters = [p for p in all_products if p.category == "inverter"]
    batteries = [p for p in all_products if p.category == "battery"]
    generators = [p for p in all_products if p.category == "solar_generator"]
    accessories = [p for p in all_products if p.category == "accessory"]

    if config.preferred_chemistry != "any":
        batteries = [
            b
            for b in batteries
            if b.specs.get("chemistry") == config.preferred_chemistry
        ]

    inverters = [
        inv for inv in inverters if inv.specs.get("type") in ("hybrid", "off_grid")
    ]

    best: SystemBundle | None = None

    if config.build_mode == "generator":
        best = _search_generator_mode(
            config, daily_wh, peak_w, autonomy_days, generators, accessories
        )
    else:
        best = _search_custom_mode(
            config,
            daily_wh,
            peak_w,
            autonomy_days,
            panels,
            inverters,
            batteries,
            accessories,
        )

    if best is None:
        raise HTTPException(
            status_code=404,
            detail="No valid system found for your requirements and budget.",
        )

    return best
