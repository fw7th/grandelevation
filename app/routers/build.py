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
