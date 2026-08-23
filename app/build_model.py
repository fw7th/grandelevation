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
    panel_quantity: int = Field(default=1, ge=1)
    inverter_id: int | None = None
    inverter_quantity: int = Field(default=1, ge=1)
    battery_id: int | None = None
    battery_quantity: int = Field(default=1, ge=1)
    generator_id: int | None = None
    generator_quantity: int = Field(default=1, ge=1)
    accessory_bundle_id: int | None = None
    accessory_bundle_quantity: int = Field(default=1, ge=1)


class SystemBundle(BaseModel):
    configuration: SystemConfiguration
    selections: SystemProductSelection
    products: dict[str, dict | None] = {}
    total_price: float
    compatibility_warnings: list[str] = []
    estimated_daily_wh: float
    estimated_peak_w: float


class SavedProductItem(BaseModel):
    """A product snapshot inside a saved system."""

    id: int
    name: str
    category: str
    price: float
    quantity: int
    image_url: str | None = None
    specs: dict = {}


class SavedSystemPayload(BaseModel):
    """What gets stored in SavedSystem.configuration and returned to frontend."""

    build_mode: str
    autonomy_hours: float
    preferred_chemistry: str
    appliances: list[ApplianceItem]
    products: list[SavedProductItem]
    total_price: float
    estimated_daily_wh: float
    estimated_peak_w: float
    created_at: str | None = None  # ISO format
