from pydantic import BaseModel, ValidationError


class PanelSpecs(BaseModel):
    wattage: float  # rated power, W
    voc: float  # open-circuit voltage, V -- compat only, not shown
    vmp: float  # voltage at max power, V
    imp: float  # current at max power, A
    panel_type: str  # "monocrystalline" | "polycrystalline"
    dimensions: str | None = None


class InverterSpecs(BaseModel):
    max_input_voltage: float  # V -- compat only, not shown
    mppt_range_min: float  # V
    mppt_range_max: float  # V
    max_input_current: float  # A
    rated_output_power: float  # W
    output_voltage: float  # V, e.g. 220


class BatterySpecs(BaseModel):
    nominal_voltage: float
    capacity_ah: float
    max_charge_current: float  # A -- compat only, not shown
    chemistry: str  # "lithium" | "lead_acid"


class AccessorySpecs(BaseModel):
    pass  # no compat-relevant fields


SPEC_MODELS = {
    "panel": PanelSpecs,
    "inverter": InverterSpecs,
    "battery": BatterySpecs,
    "accessory": AccessorySpecs,
}

# Fields shown on the customer-facing product page, per category.
# Anything compat-relevant but not listed here (e.g. voc, max_input_voltage,
# max_charge_current) is used by the compatibility engine only.
DISPLAY_FIELDS = {
    "panel": ["wattage", "vmp", "imp", "panel_type", "dimensions"],
    "inverter": [
        "mppt_range_min",
        "mppt_range_max",
        "max_input_current",
        "rated_output_power",
        "output_voltage",
    ],
    "battery": ["nominal_voltage", "capacity_ah", "chemistry"],
    "accessory": [],
}


def validate_specs(category: str, raw_specs: dict) -> dict:
    """
    Validate raw specs data against the Pydantic model for the given
    category. Returns a clean dict ready to store in Product.specs.
    Raises ValueError (with a readable message) if category is unknown
    or specs data doesn't match the required shape.

    This is the single choke point both the admin create/edit routes
    and any future bulk-import path should call before writing to the
    DB -- specs should never reach Product.specs unvalidated.
    """
    model = SPEC_MODELS.get(category)

    if model is None:
        raise ValueError(f"Unknown product category: {category!r}")

    try:
        validated = model(**raw_specs)
    except ValidationError as e:
        raise ValueError(f"Invalid specs for category {category!r}: {e}")

    return validated.model_dump()
