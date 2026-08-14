from pydantic import BaseModel, Field


class ApplianceItem(BaseModel):
    name: str
    qty: int = Field(..., ge=1)
    watts: float = Field(..., gt=0)
    hours_per_day: float = Field(..., gt=0, le=24)


class SystemConfiguration(BaseModel):
    appliances: list[ApplianceItem]
    use_default_household: bool = False
    autonomy_hours: float = Field(default=24.0, ge=0, le=72)
    preferred_chemistry: str = Field(default="any", pattern="^(any|lithium|lead_acid)$")
    budget_min: float | None = Field(default=None, ge=0)
    budget_max: float | None = Field(default=None, ge=0)
    build_mode: str = Field(default="custom", pattern="^(custom|generator)$")


class SystemProductSelection(BaseModel):
    panel_id: int | None = None
    inverter_id: int | None = None
    battery_id: int | None = None
    generator_id: int | None = None
    accessory_bundle_id: int | None = None


class SystemBundle(BaseModel):
    configuration: SystemConfiguration
    selections: SystemProductSelection
    products: dict[str, dict | None] = {}
    total_price: float
    compatibility_warnings: list[str] = []
    estimated_daily_wh: float
    estimated_peak_w: float
