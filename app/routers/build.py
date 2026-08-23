import math
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.build_model import (
    SavedProductItem,
    SavedSystemPayload,
    SystemBundle,
    SystemConfiguration,
    SystemProductSelection,
)
from app.database import get_session
from app.models import Product, SavedSystem
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
COMPONENT_PENALTY = 25000  # ₦25k per extra unit beyond the first


def _dod(chemistry: str) -> float:
    return 0.85 if chemistry == "lithium" else 0.50


def _product_to_dict(product: Product, quantity: int = 1) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "price": product.price,
        "image_url": product.image_url[0] if product.image_url else "",
        "specs": {**product.specs, "quantity": quantity},
    }


@router.get("/build")
async def build_page(request: Request, session: AsyncSession = Depends(get_session)):
    from app.utils import authenticate

    user = await authenticate(request, session)

    latest_draft_id = None
    latest_draft_date = None
    if user:
        statement = (
            select(SavedSystem)
            .where(SavedSystem.user_id == user.id)
            .order_by(SavedSystem.created_at.desc())
            .limit(1)
        )
        result = await session.exec(statement)
        draft = result.first()
        if draft:
            latest_draft_id = draft.id
            latest_draft_date = (
                draft.created_at.isoformat() if draft.created_at else None
            )

    return templates.TemplateResponse(
        request=request,
        name="build.html",
        context={
            "username": user.username if user else None,
            "latest_draft_id": latest_draft_id,
            "latest_draft_date": latest_draft_date,
        },
    )


@router.post("/build/save")
async def save_system(
    bundle: SystemBundle,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    from app.utils import authenticate

    user = await authenticate(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Resolve product details from DB so the snapshot is authoritative
    products: list[SavedProductItem] = []
    selections = bundle.selections

    id_to_meta = {}
    if selections.panel_id:
        id_to_meta[selections.panel_id] = ("panel", selections.panel_quantity)
    if selections.inverter_id:
        id_to_meta[selections.inverter_id] = ("inverter", selections.inverter_quantity)
    if selections.battery_id:
        id_to_meta[selections.battery_id] = ("battery", selections.battery_quantity)
    if selections.generator_id:
        id_to_meta[selections.generator_id] = (
            "generator",
            selections.generator_quantity,
        )
    if selections.accessory_bundle_id:
        id_to_meta[selections.accessory_bundle_id] = (
            "accessory",
            selections.accessory_bundle_quantity,
        )

    for pid, (cat, qty) in id_to_meta.items():
        p = await session.get(Product, pid)
        if not p:
            continue
        specs = {k: v for k, v in p.specs.items()}
        products.append(
            SavedProductItem(
                id=p.id,
                name=p.name,
                category=cat,
                price=p.price,
                quantity=qty,
                image_url=p.image_url[0] if p.image_url else None,
                specs=specs,
            )
        )

    payload = SavedSystemPayload(
        build_mode=bundle.configuration.build_mode,
        use_default_household=bundle.configuration.use_default_household,
        autonomy_hours=bundle.configuration.autonomy_hours,
        preferred_chemistry=bundle.configuration.preferred_chemistry,
        appliances=bundle.configuration.appliances,
        products=products,
        budget_min=bundle.configuration.budget_min,
        budget_max=bundle.configuration.budget_max,
        total_price=bundle.total_price,
        estimated_daily_wh=bundle.estimated_daily_wh,
        estimated_peak_w=bundle.estimated_peak_w,
        created_at=datetime.utcnow().isoformat(),
    )

    saved = SavedSystem(
        user_id=user.id,
        configuration=payload.model_dump(),
        total_price=bundle.total_price,
        estimated_daily_wh=bundle.estimated_daily_wh,
        estimated_peak_w=bundle.estimated_peak_w,
    )
    session.add(saved)
    await session.commit()
    await session.refresh(saved)

    return {"id": saved.id, "message": "System saved successfully"}


@router.get("/build/load/{saved_system_id}")
async def load_system(
    saved_system_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    from app.utils import authenticate

    user = await authenticate(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    statement = select(SavedSystem).where(
        SavedSystem.id == saved_system_id,
        SavedSystem.user_id == user.id,
    )
    result = await session.exec(statement)
    saved = result.first()

    if not saved:
        raise HTTPException(status_code=404, detail="Saved system not found")

    return saved.configuration


@router.delete("/build/system/{saved_system_id}")
async def delete_saved_system(
    saved_system_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    from app.utils import authenticate

    user = await authenticate(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    statement = select(SavedSystem).where(
        SavedSystem.id == saved_system_id,
        SavedSystem.user_id == user.id,
    )
    result = await session.exec(statement)
    saved = result.first()

    if not saved:
        raise HTTPException(status_code=404, detail="Saved system not found")

    await session.delete(saved)
    await session.commit()

    return {"message": "Deleted successfully"}


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

    if config.build_mode == "generator":
        best = _search_generator_mode(
            config,
            daily_wh,
            peak_w,
            autonomy_days,
            generators,
            panels,
            accessories,
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


def _search_custom_mode(
    config: SystemConfiguration,
    daily_wh: float,
    peak_w: float,
    autonomy_days: float,
    panels: list[Product],
    inverters: list[Product],
    batteries: list[Product],
    accessories: list[Product],
) -> SystemBundle | None:
    required_array_w = daily_wh / PEAK_SUN_HOURS / SYSTEM_EFFICIENCY
    min_inverter_w = peak_w * 1.2
    best_bundle: SystemBundle | None = None
    best_effective: float | None = None

    for panel in panels:
        try:
            ps = PanelSpecs(**panel.specs)
        except Exception:
            continue

        panel_count = max(1, math.ceil(required_array_w / ps.wattage))
        total_panel_w = ps.wattage * panel_count
        panel_cost = panel.price * panel_count
        panel_penalty = max(0, panel_count - 1) * COMPONENT_PENALTY

        for inv in inverters:
            try:
                iv = InverterSpecs(**inv.specs)
            except Exception:
                continue

            voc_max = ps.voc * VOC_TEMP_MARGIN
            if voc_max > iv.max_input_voltage:
                continue
            if not (iv.mppt_range_min <= ps.vmp <= iv.mppt_range_max):
                continue
            if ps.imp > iv.max_input_current:
                continue
            if iv.rated_output_power < min_inverter_w:
                continue

            for batt in batteries:
                try:
                    bs = BatterySpecs(**batt.specs)
                except Exception:
                    continue

                if bs.nominal_voltage != iv.output_voltage:
                    continue

                usable_wh_needed = daily_wh * autonomy_days
                total_batt_wh = usable_wh_needed / _dod(bs.chemistry)
                unit_wh = bs.nominal_voltage * bs.capacity_ah
                batt_count = max(1, math.ceil(total_batt_wh / unit_wh))
                batt_cost = batt.price * batt_count
                batt_penalty = max(0, batt_count - 1) * COMPONENT_PENALTY

                for acc in accessories:
                    try:
                        ac = AccessoryBundleSpecs(**acc.specs)
                    except Exception:
                        continue

                    if ac.max_system_watts < total_panel_w:
                        continue
                    if ac.max_panel_count < panel_count:
                        continue

                    real_total = panel_cost + inv.price + batt_cost + acc.price
                    if config.budget_max is not None and real_total > config.budget_max:
                        continue

                    effective_total = real_total + panel_penalty + batt_penalty

                    warnings = []
                    if not iv.has_charge_controller:
                        warnings.append(
                            "Inverter has no built-in charge controller — "
                            "ensure a separate charge controller is installed."
                        )

                    bundle = SystemBundle(
                        configuration=config,
                        selections=SystemProductSelection(
                            panel_id=panel.id,
                            panel_quantity=panel_count,
                            inverter_id=inv.id,
                            inverter_quantity=1,
                            battery_id=batt.id,
                            battery_quantity=batt_count,
                            accessory_bundle_id=acc.id,
                            accessory_bundle_quantity=1,
                        ),
                        products={
                            "panel": _product_to_dict(panel, panel_count),
                            "inverter": _product_to_dict(inv),
                            "battery": _product_to_dict(batt, batt_count),
                            "accessory": _product_to_dict(acc),
                        },
                        total_price=real_total,
                        compatibility_warnings=warnings,
                        estimated_daily_wh=daily_wh,
                        estimated_peak_w=peak_w,
                    )

                    if best_bundle is None or effective_total < best_effective:
                        best_bundle = bundle
                        best_effective = effective_total

    return best_bundle


def _search_generator_mode(
    config: SystemConfiguration,
    daily_wh: float,
    peak_w: float,
    autonomy_days: float,
    generators: list[Product],
    panels: list[Product],
    accessories: list[Product],
) -> SystemBundle | None:
    min_gen_w = peak_w * 1.2
    required_panel_w = daily_wh / PEAK_SUN_HOURS / SYSTEM_EFFICIENCY
    best_bundle: SystemBundle | None = None
    best_effective: float | None = None

    for gen in generators:
        try:
            gs = SolarGeneratorSpecs(**gen.specs)
        except Exception:
            continue

        usable_wh_needed = daily_wh * autonomy_days
        total_wh = usable_wh_needed / _dod(gs.battery_chemistry)

        gen_count_for_capacity = max(1, math.ceil(total_wh / gs.capacity_wh))
        gen_count_for_power = max(1, math.ceil(min_gen_w / gs.rated_output_power))
        gen_count = max(gen_count_for_capacity, gen_count_for_power)
        gen_penalty = max(0, gen_count - 1) * COMPONENT_PENALTY

        for panel in panels:
            try:
                ps = PanelSpecs(**panel.specs)
            except Exception:
                continue

            panel_count = max(1, math.ceil(required_panel_w / ps.wattage))
            total_panel_w = ps.wattage * panel_count
            panel_penalty = max(0, panel_count - 1) * COMPONENT_PENALTY

            for acc in accessories:
                try:
                    ac = AccessoryBundleSpecs(**acc.specs)
                except Exception:
                    continue

                if ac.max_system_watts < total_panel_w:
                    continue
                if ac.max_panel_count < panel_count:
                    continue

                real_total = (
                    (gen.price * gen_count) + (panel.price * panel_count) + acc.price
                )
                if config.budget_max is not None and real_total > config.budget_max:
                    continue

                effective_total = real_total + gen_penalty + panel_penalty

                fleet_max_input = gen_count * gs.max_input_charging_watts
                warnings = []
                if total_panel_w > fleet_max_input:
                    warnings.append(
                        f"Panel array ({total_panel_w:.0f}W) exceeds total generator "
                        f"solar input ({fleet_max_input:.0f}W). Some panel output will be "
                        f"wasted during peak sun."
                    )

                bundle = SystemBundle(
                    configuration=config,
                    selections=SystemProductSelection(
                        generator_id=gen.id,
                        generator_quantity=gen_count,
                        panel_id=panel.id,
                        panel_quantity=panel_count,
                        accessory_bundle_id=acc.id,
                        accessory_bundle_quantity=1,
                    ),
                    products={
                        "generator": _product_to_dict(gen, gen_count),
                        "panel": _product_to_dict(panel, panel_count),
                        "accessory": _product_to_dict(acc),
                    },
                    total_price=real_total,
                    compatibility_warnings=warnings,
                    estimated_daily_wh=daily_wh,
                    estimated_peak_w=peak_w,
                )

                if best_bundle is None or effective_total < best_effective:
                    best_bundle = bundle
                    best_effective = effective_total

    return best_bundle


@router.post("/build/validate")
async def validate_selections(
    selections: SystemProductSelection,
    config: SystemConfiguration,
    session: AsyncSession = Depends(get_session),
):
    warnings: list[str] = []
    ids = [
        selections.panel_id,
        selections.inverter_id,
        selections.battery_id,
        selections.generator_id,
    ]
    ids = [i for i in ids if i is not None]

    if not ids:
        return {"warnings": ["No components selected."], "is_compatible": False}

    products = {}
    for pid in ids:
        p = await session.get(Product, pid)
        if p:
            products[p.category] = p

    if "panel" in products and "inverter" in products:
        ps = PanelSpecs(**products["panel"].specs)
        iv = InverterSpecs(**products["inverter"].specs)
        if ps.voc * VOC_TEMP_MARGIN > iv.max_input_voltage:
            warnings.append("Panel voltage exceeds inverter limit at low temperatures.")
        if not (iv.mppt_range_min <= ps.vmp <= iv.mppt_range_max):
            warnings.append("Panel voltage is outside inverter MPPT range.")
        if ps.imp > iv.max_input_current:
            warnings.append("Panel current exceeds inverter input limit.")

    if "battery" in products and "inverter" in products:
        bs = BatterySpecs(**products["battery"].specs)
        iv = InverterSpecs(**products["inverter"].specs)
        if bs.nominal_voltage != iv.output_voltage:
            warnings.append("Battery voltage does not match inverter output voltage.")
        if not iv.has_charge_controller:
            warnings.append("Inverter lacks built-in charge controller.")

    if "panel" in products and "generator" in products:
        ps = PanelSpecs(**products["panel"].specs)
        gs = SolarGeneratorSpecs(**products["generator"].specs)
        if ps.wattage > gs.max_input_charging_watts:
            warnings.append("Panel wattage exceeds generator solar input limit.")

    return {
        "warnings": warnings,
        "is_compatible": len(warnings) == 0,
    }
