
from pydantic import BaseModel


class ApplianceItem(BaseModel):
    name: str
    qty: int
    watts: float
    hours_per_day: float


class SystemConfiguration(BaseModel):
    appliances: list[ApplianceItem]
    use_default_household: bool = False
    budget_min: float | None = None
    budget_max: float | None = None


class SystemProductSelection(BaseModel):
    panel_id: int | None = None
    inverter_id: int | None = None
    battery_id: int | None = None
    accessory_id: int | None = None  # or list[int] if multiple


class SystemBundle(BaseModel):
    """What gets stored in cart / checkout."""

    configuration: SystemConfiguration
    selections: SystemProductSelection
    total_price: float
    compatibility_warnings: list[str] = []
    estimated_daily_wh: float
    estimated_peak_w: float


# Example endpoint signatures you'll wire up later:
# @app.post("/build/recommend") -> SystemProductSelection
# @app.post("/build/validate") -> { "warnings": [...], "is_compatible": bool }
# @app.post("/cart/system") -> adds a SystemBundle to cart
