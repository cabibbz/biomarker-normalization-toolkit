from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import re

from biomarker_normalization_toolkit.models import RangeValue


UNIT_SYNONYMS = {
    "mg/dl": "mg/dL",
    "mg dl": "mg/dL",
    "mg per dl": "mg/dL",
    "mmol/l": "mmol/L",
    "mmol l": "mmol/L",
    "mmol per l": "mmol/L",
    "umol/l": "umol/L",
    "umol l": "umol/L",
    "μmol/l": "umol/L",
    "µmol/l": "umol/L",
    "%": "%",
}



CONVERSION_TO_NORMALIZED: dict[str, dict[str, Decimal]] = {
    "glucose_serum": {
        "mg/dL": Decimal("1"),
        "mmol/L": Decimal("18"),
    },
    "glucose_urine": {
        "mg/dL": Decimal("1"),
        "mmol/L": Decimal("18"),
    },
    "hba1c": {
        "%": Decimal("1"),
    },
    "total_cholesterol": {
        "mg/dL": Decimal("1"),
        "mmol/L": Decimal("38.67"),
    },
    "ldl_cholesterol": {
        "mg/dL": Decimal("1"),
        "mmol/L": Decimal("38.67"),
    },
    "hdl_cholesterol": {
        "mg/dL": Decimal("1"),
        "mmol/L": Decimal("38.67"),
    },
    "triglycerides": {
        "mg/dL": Decimal("1"),
        "mmol/L": Decimal("88.57"),
    },
    "creatinine": {
        "mg/dL": Decimal("1"),
        "umol/L": Decimal("1") / Decimal("88.4"),
    },
}


def normalize_unit(value: str | None) -> str:
    if value is None:
        return ""
    key = re.sub(r"\s+", " ", value.strip().lower())
    return UNIT_SYNONYMS.get(key, value.strip())


def format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""

    quantized = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    text = format(quantized, "f").rstrip("0").rstrip(".")
    return text or "0"


def convert_to_normalized(value: Decimal, biomarker_id: str, source_unit: str) -> Decimal | None:
    factor = CONVERSION_TO_NORMALIZED.get(biomarker_id, {}).get(normalize_unit(source_unit))
    if factor is None:
        return None
    return value * factor


def parse_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return Decimal(stripped)
    except Exception:
        return None


def parse_reference_range(text: str, fallback_unit: str) -> RangeValue | None:
    stripped = text.strip()
    if not stripped:
        return None

    match = re.match(
        r"^\s*(?P<low>-?\d+(?:\.\d+)?)\s*-\s*(?P<high>-?\d+(?:\.\d+)?)\s*(?P<unit>.*)\s*$",
        stripped,
    )
    if not match:
        return None

    low = Decimal(match.group("low"))
    high = Decimal(match.group("high"))
    unit = normalize_unit(match.group("unit").strip() or fallback_unit)
    if not unit:
        return None
    return RangeValue(low=low, high=high, unit=unit)


def format_range(range_value: RangeValue | None) -> str:
    if range_value is None:
        return ""
    return f"{format_decimal(range_value.low)}-{format_decimal(range_value.high)} {range_value.unit}"
