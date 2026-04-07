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
    "u/l": "U/L",
    "iu/l": "U/L",
    "[iu]/l": "U/L",
    "g/l": "g/L",
    "g/dl": "g/dL",
    "ng/ml": "ng/mL",
    "pg/ml": "pg/mL",
    "miu/l": "mIU/L",
    "uiu/ml": "mIU/L",
    "µiu/ml": "mIU/L",
    "ng/dl": "ng/dL",
    "ug/dl": "ug/dL",
    "mcg/dl": "ug/dL",
    "k/ul": "K/uL",
    "k/µl": "K/uL",
    "10^3/ul": "K/uL",
    "10*3/ul": "K/uL",
    "10^9/l": "10^9/L",
    "10*9/l": "10^9/L",
    "l/l": "L/L",
    "pmol/l": "pmol/L",
    "nmol/l": "nmol/L",
    "mg/l": "mg/L",
    "meq/l": "mEq/L",
    "meq l": "mEq/L",
    "m/ul": "M/uL",
    "10^12/l": "10^12/L",
    "10*12/l": "10^12/L",
    "fl": "fL",
    "pg": "pg",
    "sec": "sec",
    "s": "sec",
    "ratio": "ratio",
    "{inr}": "ratio",
    "10*6/ul": "M/uL",
    "thou/ul": "K/uL",
    "x10e3/ul": "K/uL",
    "mill/ul": "M/uL",
    "x10e6/ul": "M/uL",
    "g%": "g/dL",
    "vol%": "%",
    "mu/l": "mIU/L",
    "miu/ml": "mIU/L",
    "iu/ml": "IU/mL",
    "ug/ml": "ug/mL",
    "10*3/ul": "K/uL",
    "ml/min/1.73m2": "mL/min/1.73m2",
    "ml/min/{1.73_m2}": "mL/min/1.73m2",
    "ml/min": "mL/min",
    "ph": "pH",
    "units": "units",
    "mmhg": "mmHg",
    "mm hg": "mmHg",
    "mm[hg]": "mmHg",
    "#/ul": "#/uL",
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
    "creatinine_urine": {
        "mg/dL": Decimal("1"),
        "umol/L": Decimal("1") / Decimal("88.4"),
    },
    # --- Wave 2: Liver panel ---
    "alt": {"U/L": Decimal("1")},
    "ast": {"U/L": Decimal("1")},
    "alp": {"U/L": Decimal("1")},
    "total_bilirubin": {
        "mg/dL": Decimal("1"),
        "umol/L": Decimal("1") / Decimal("17.1"),
    },
    "albumin": {
        "g/dL": Decimal("1"),
        "g/L": Decimal("0.1"),
    },
    # --- Wave 2: Thyroid ---
    "tsh": {"mIU/L": Decimal("1")},
    "free_t4": {
        "ng/dL": Decimal("1"),
        "pmol/L": Decimal("1") / Decimal("12.87"),
    },
    # --- Wave 2: Renal expansion ---
    "bun": {
        "mg/dL": Decimal("1"),
        "mmol/L": Decimal("2.8"),
    },
    # --- Wave 2: Inflammation ---
    "hscrp": {
        "mg/L": Decimal("1"),
        "mg/dL": Decimal("10"),
    },
    # --- Wave 2: CBC ---
    "wbc": {"K/uL": Decimal("1"), "10^9/L": Decimal("1")},
    "hemoglobin": {
        "g/dL": Decimal("1"),
        "g/L": Decimal("0.1"),
    },
    "hematocrit": {
        "%": Decimal("1"),
        "L/L": Decimal("100"),
    },
    "platelets": {"K/uL": Decimal("1"), "10^9/L": Decimal("1")},
    # --- Wave 3: Vitamins ---
    "vitamin_d": {
        "ng/mL": Decimal("1"),
        "nmol/L": Decimal("0.4"),
    },
    "vitamin_b12": {
        "pg/mL": Decimal("1"),
        "pmol/L": Decimal("1.355"),
    },
    "folate": {
        "ng/mL": Decimal("1"),
        "nmol/L": Decimal("1") / Decimal("2.266"),
    },
    # --- Wave 3: Minerals ---
    "iron": {
        "ug/dL": Decimal("1"),
        "umol/L": Decimal("5.585"),
    },
    "ferritin": {"ng/mL": Decimal("1")},
    "magnesium": {
        "mg/dL": Decimal("1"),
        "mmol/L": Decimal("2.4"),
    },
    # --- Wave 4: CBC sub-components ---
    "rbc": {"M/uL": Decimal("1"), "10^12/L": Decimal("1")},
    "mcv": {"fL": Decimal("1")},
    "mch": {"pg": Decimal("1")},
    "mchc": {"g/dL": Decimal("1"), "g/L": Decimal("0.1")},
    "rdw": {"%": Decimal("1")},
    # --- Wave 4: Coagulation ---
    "pt": {"sec": Decimal("1")},
    "inr": {"ratio": Decimal("1"), "": Decimal("1")},
    "ptt": {"sec": Decimal("1")},
    # --- Wave 4: Other ---
    "anion_gap": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1")},
    "lactate": {"mmol/L": Decimal("1"), "mg/dL": Decimal("1") / Decimal("9.01")},
    # --- Wave 4: Electrolytes ---
    "sodium": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1")},
    "potassium": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1")},
    "chloride": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1")},
    "bicarbonate": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1")},
    "calcium": {
        "mg/dL": Decimal("1"),
        "mmol/L": Decimal("4.008"),
    },
    "phosphate": {
        "mg/dL": Decimal("1"),
        "mmol/L": Decimal("3.097"),
    },
    "uric_acid": {
        "mg/dL": Decimal("1"),
        "umol/L": Decimal("1") / Decimal("59.48"),
    },
    # --- Wave 5: WBC differentials ---
    "neutrophils": {"K/uL": Decimal("1"), "10^9/L": Decimal("1")},
    "lymphocytes": {"K/uL": Decimal("1"), "10^9/L": Decimal("1")},
    "monocytes": {"K/uL": Decimal("1"), "10^9/L": Decimal("1")},
    "eosinophils": {"K/uL": Decimal("1"), "10^9/L": Decimal("1")},
    "basophils": {"K/uL": Decimal("1"), "10^9/L": Decimal("1")},
    # --- Wave 5: Other ---
    "total_protein": {"g/dL": Decimal("1"), "g/L": Decimal("0.1")},
    "rdw_sd": {"fL": Decimal("1")},
    "mpv": {"fL": Decimal("1")},
    "pdw": {"fL": Decimal("1")},
    "egfr": {"mL/min/1.73m2": Decimal("1"), "mL/min": Decimal("1")},
    # --- Wave 6: Enzymes ---
    "ldh": {"U/L": Decimal("1")},
    "lipase": {"U/L": Decimal("1")},
    "ck": {"U/L": Decimal("1")},
    "ck_mb": {"ng/mL": Decimal("1")},
    # --- Wave 6: Cardiac ---
    "troponin_t": {"ng/mL": Decimal("1")},
    # --- Wave 6: Blood gases ---
    "pco2": {"mmHg": Decimal("1")},
    "po2": {"mmHg": Decimal("1")},
    "base_excess": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1")},
    # --- Wave 6: Other ---
    "globulin": {"g/dL": Decimal("1"), "g/L": Decimal("0.1")},
    "ionized_calcium": {"mmol/L": Decimal("1"), "mg/dL": Decimal("1") / Decimal("4.008")},
    "fibrinogen": {"mg/dL": Decimal("1"), "g/L": Decimal("100")},
    "eag": {"mg/dL": Decimal("1")},
    "blood_ph": {"pH": Decimal("1"), "units": Decimal("1"), "": Decimal("1")},
    "oxygen_saturation": {"%": Decimal("1")},
    # --- Urinalysis ---
    "urine_specific_gravity": {"": Decimal("1")},
    "urine_ph": {"pH": Decimal("1"), "": Decimal("1"), "units": Decimal("1")},
    "urine_protein": {"mg/dL": Decimal("1")},
    "urine_ketones": {"mg/dL": Decimal("1")},
    "urine_bilirubin": {"mg/dL": Decimal("1")},
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


def is_inequality_value(value: str | None) -> bool:
    if value is None:
        return False
    stripped = value.strip()
    return bool(re.match(r"^[<>]=?\s*-?\d+(\.\d+)?$", stripped))


def parse_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        result = Decimal(stripped)
        if not result.is_finite():
            return None
        return result
    except Exception:
        return None


def parse_reference_range(text: str, fallback_unit: str) -> RangeValue | None:
    stripped = text.strip()
    if not stripped:
        return None

    match = re.match(
        r"^\s*(?P<low>-?\d+(?:\.\d+)?)\s*(?:to|–|—|-)\s*(?P<high>-?\d+(?:\.\d+)?)(?:\s+(?P<unit>\S.*))?$",
        stripped,
    )
    if not match:
        return None

    low = Decimal(match.group("low"))
    high = Decimal(match.group("high"))
    raw_unit = (match.group("unit") or "").strip()
    unit = normalize_unit(raw_unit or fallback_unit)
    return RangeValue(low=low, high=high, unit=unit)


def format_range(range_value: RangeValue | None) -> str:
    if range_value is None:
        return ""
    text = f"{format_decimal(range_value.low)}-{format_decimal(range_value.high)}"
    if range_value.unit:
        return f"{text} {range_value.unit}"
    return text
