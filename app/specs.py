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


class SolarGeneratorSpecs(BaseModel):
    capacity_wh: float  # total energy storage, Wh
    rated_output_power: float  # continuous output, W
    peak_output_power: float  # surge rating, W -- compat only
    max_input_charging_watts: float  # solar input limit, W
    output_voltage: float  # V, e.g. 220
    battery_chemistry: str  # "lithium" | "lead_acid"


class SolarStreetLightSpecs(BaseModel):
    panel_wattage: float  # attached panel rating, W
    lumen_output: float
    battery_capacity_ah: float
    battery_voltage: float  # V -- compat only
    lighting_mode: str  # "dusk_to_dawn" | "motion_sensor" | "timer"
    pole_height_m: float | None = None


class FanSpecs(BaseModel):
    wattage: float
    voltage: float  # V -- compat only, must match battery/inverter output
    airflow_cfm: float | None = None
    noise_level_db: float | None = None
    blade_span_cm: float | None = None


SPEC_MODELS = {
    "panel": PanelSpecs,
    "inverter": InverterSpecs,
    "battery": BatterySpecs,
    "accessory": AccessorySpecs,
    "solar_generator": SolarGeneratorSpecs,
    "solar_street_light": SolarStreetLightSpecs,
    "fan": FanSpecs,
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
    "solar_generator": [
        "capacity_wh",
        "rated_output_power",
        "output_voltage",
        "battery_chemistry",
    ],
    "solar_street_light": [
        "panel_wattage",
        "lumen_output",
        "lighting_mode",
        "pole_height_m",
    ],
    "fan": ["wattage", "airflow_cfm", "noise_level_db", "blade_span_cm"],
}


# Field metadata for the ADMIN form. Unlike DISPLAY_FIELDS (customer-facing
# subset), this lists EVERY field per category -- including compat-only
# ones like voc, max_input_voltage -- since the admin is the one entering
# raw spec-sheet numbers.
#
# Each entry: (field_name, label, input_type, required)
# input_type is a plain HTML input type ("number", "text") or "select"
# for fields with a fixed set of choices.
ADMIN_FORM_FIELDS = {
    "panel": [
        ("wattage", "Wattage (W)", "number", True),
        ("voc", "Open-circuit voltage — Voc (V)", "number", True),
        ("vmp", "Voltage at max power — Vmp (V)", "number", True),
        ("imp", "Current at max power — Imp (A)", "number", True),
        ("panel_type", "Panel type", "select", True),
        ("dimensions", "Dimensions", "text", False),
    ],
    "inverter": [
        ("max_input_voltage", "Max input voltage (V)", "number", True),
        ("mppt_range_min", "MPPT range — min (V)", "number", True),
        ("mppt_range_max", "MPPT range — max (V)", "number", True),
        ("max_input_current", "Max input current (A)", "number", True),
        ("rated_output_power", "Rated output power (W)", "number", True),
        ("output_voltage", "Output voltage (V)", "number", True),
    ],
    "battery": [
        ("nominal_voltage", "Nominal voltage (V)", "number", True),
        ("capacity_ah", "Capacity (Ah)", "number", True),
        ("max_charge_current", "Max charge current (A)", "number", True),
        ("chemistry", "Chemistry", "select", True),
    ],
    "accessory": [],
    "solar_generator": [
        ("capacity_wh", "Capacity (Wh)", "number", True),
        ("rated_output_power", "Rated output power (W)", "number", True),
        ("peak_output_power", "Peak/surge output power (W)", "number", True),
        ("max_input_charging_watts", "Max solar input charging (W)", "number", True),
        ("output_voltage", "Output voltage (V)", "number", True),
        ("battery_chemistry", "Battery chemistry", "select", True),
    ],
    "solar_street_light": [
        ("panel_wattage", "Panel wattage (W)", "number", True),
        ("lumen_output", "Lumen output (lm)", "number", True),
        ("battery_capacity_ah", "Battery capacity (Ah)", "number", True),
        ("battery_voltage", "Battery voltage (V)", "number", True),
        ("lighting_mode", "Lighting mode", "select", True),
        ("pole_height_m", "Pole height (m)", "number", False),
    ],
    "fan": [
        ("wattage", "Wattage (W)", "number", True),
        ("voltage", "Voltage (V)", "number", True),
        ("airflow_cfm", "Airflow (CFM)", "number", False),
        ("noise_level_db", "Noise level (dB)", "number", False),
        ("blade_span_cm", "Blade span (cm)", "number", False),
    ],
}


# Choices for "select" type fields above.
FIELD_CHOICES = {
    "panel_type": ["monocrystalline", "polycrystalline"],
    "chemistry": ["lithium", "lead_acid"],
    "battery_chemistry": ["lithium", "lead_acid"],
    "lighting_mode": ["dusk_to_dawn", "motion_sensor", "timer"],
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
