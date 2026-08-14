from pydantic import BaseModel, ValidationError


class PanelSpecs(BaseModel):
    wattage: float
    voc: float
    vmp: float
    imp: float
    panel_type: str
    temp_coefficient_voc: float | None = None  # %/°C, e.g. -0.30
    dimensions: str | None = None


class InverterSpecs(BaseModel):
    max_input_voltage: float
    mppt_range_min: float
    mppt_range_max: float
    max_input_current: float
    rated_output_power: float
    output_voltage: float
    has_charge_controller: bool = True
    type: str  # "hybrid" | "off_grid" | "grid_tie"


class BatterySpecs(BaseModel):
    nominal_voltage: float
    capacity_ah: float
    max_charge_current: float
    chemistry: str  # "lithium" | "lead_acid"


class AccessoryBundleSpecs(BaseModel):
    max_system_watts: float
    max_panel_count: int
    dc_wire_gauge_mm2: float
    ac_wire_gauge_mm2: float
    includes_disconnect: bool = False
    includes_mounting: bool = False


class SolarGeneratorSpecs(BaseModel):
    capacity_wh: float
    rated_output_power: float
    peak_output_power: float
    max_input_charging_watts: float
    output_voltage: float
    battery_chemistry: str


class SolarStreetLightSpecs(BaseModel):
    panel_wattage: float
    lumen_output: float
    battery_capacity_ah: float
    battery_voltage: float
    lighting_mode: str
    pole_height_m: float | None = None


class FanSpecs(BaseModel):
    wattage: float
    voltage: float
    airflow_cfm: float | None = None
    noise_level_db: float | None = None
    blade_span_cm: float | None = None


SPEC_MODELS = {
    "panel": PanelSpecs,
    "inverter": InverterSpecs,
    "battery": BatterySpecs,
    "accessory": AccessoryBundleSpecs,
    "solar_generator": SolarGeneratorSpecs,
    "solar_street_light": SolarStreetLightSpecs,
    "fan": FanSpecs,
}

DISPLAY_FIELDS = {
    "panel": ["wattage", "vmp", "imp", "panel_type", "dimensions"],
    "inverter": [
        "mppt_range_min",
        "mppt_range_max",
        "max_input_current",
        "rated_output_power",
        "output_voltage",
        "has_charge_controller",
        "type",
    ],
    "battery": ["nominal_voltage", "capacity_ah", "chemistry"],
    "accessory": [
        "max_system_watts",
        "max_panel_count",
        "dc_wire_gauge_mm2",
        "ac_wire_gauge_mm2",
        "includes_disconnect",
        "includes_mounting",
    ],
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

ADMIN_FORM_FIELDS = {
    "panel": [
        ("wattage", "Wattage (W)", "number", True),
        ("voc", "Open-circuit voltage — Voc (V)", "number", True),
        ("vmp", "Voltage at max power — Vmp (V)", "number", True),
        ("imp", "Current at max power — Imp (A)", "number", True),
        ("panel_type", "Panel type", "select", True),
        ("temp_coefficient_voc", "Temp coefficient Voc (%/°C)", "number", False),
        ("dimensions", "Dimensions", "text", False),
    ],
    "inverter": [
        ("max_input_voltage", "Max input voltage (V)", "number", True),
        ("mppt_range_min", "MPPT range — min (V)", "number", True),
        ("mppt_range_max", "MPPT range — max (V)", "number", True),
        ("max_input_current", "Max input current (A)", "number", True),
        ("rated_output_power", "Rated output power (W)", "number", True),
        ("output_voltage", "Output voltage (V)", "number", True),
        ("has_charge_controller", "Built-in charge controller", "select", True),
        ("type", "Inverter type", "select", True),
    ],
    "battery": [
        ("nominal_voltage", "Nominal voltage (V)", "number", True),
        ("capacity_ah", "Capacity (Ah)", "number", True),
        ("max_charge_current", "Max charge current (A)", "number", True),
        ("chemistry", "Chemistry", "select", True),
    ],
    "accessory": [
        ("max_system_watts", "Max system watts (W)", "number", True),
        ("max_panel_count", "Max panel count", "number", True),
        ("dc_wire_gauge_mm2", "DC wire gauge (mm²)", "number", True),
        ("ac_wire_gauge_mm2", "AC wire gauge (mm²)", "number", True),
        ("includes_disconnect", "Includes disconnect", "select", True),
        ("includes_mounting", "Includes mounting", "select", True),
    ],
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

FIELD_CHOICES = {
    "panel_type": ["monocrystalline", "polycrystalline"],
    "chemistry": ["lithium", "lead_acid"],
    "battery_chemistry": ["lithium", "lead_acid"],
    "lighting_mode": ["dusk_to_dawn", "motion_sensor", "timer"],
    "has_charge_controller": ["true", "false"],
    "type": ["hybrid", "off_grid", "grid_tie"],
    "includes_disconnect": ["true", "false"],
    "includes_mounting": ["true", "false"],
}


def validate_specs(category: str, raw_specs: dict) -> dict:
    model = SPEC_MODELS.get(category)
    if model is None:
        raise ValueError(f"Unknown product category: {category!r}")
    try:
        validated = model(**raw_specs)
    except ValidationError as e:
        raise ValueError(f"Invalid specs for category {category!r}: {e}")
    return validated.model_dump()
