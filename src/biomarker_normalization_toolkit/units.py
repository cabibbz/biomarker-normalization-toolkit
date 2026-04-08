from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, localcontext
from functools import lru_cache
import re

from biomarker_normalization_toolkit.models import RangeValue

# Pre-compiled regexes for hot-path functions (30% of CPU per profiling)
_RE_WHITESPACE = re.compile(r"\s+")
_RE_SLASH_SPACES = re.compile(r"\s*/\s*")
_RE_SUPERSCRIPT_POWER = re.compile(r"10([¹²³⁴⁵⁶⁷⁸⁹⁰]+)")

# is_inequality_value
_RE_INEQUALITY = re.compile(r"^[<>]=?\s*-?\d+(\.\d+)?$")

# parse_decimal: European comma-decimal, scientific notation,
# thousands-with-dot validation
_RE_EURO_COMMA = re.compile(r"^-?\d+,\d{1,2}$")
_RE_X10_NOTATION = re.compile(r"^(-?\d+(?:\.\d+)?)\s*[xX]\s*10[\^eE](\d+)$")
_RE_SCI_NOTATION = re.compile(r"^(?P<mantissa>[+-]?\d+(?:\.\d+)?)[eE](?P<exp>[+-]?\d+)$")
_RE_THOUSANDS_DOT = re.compile(r"^-?\d{1,3}(,\d{3})*\.\d+$")

# parse_reference_range: thousands-separator strip, range patterns
_RE_THOUSANDS_SEP = re.compile(r"(\d),(\d{3})")
_RE_RANGE = re.compile(
    r"^\s*(?P<low>[+-]?\d+(?:\.\d+)?)\s*(?:to|–|—|-)\s*(?P<high>[+-]?\d+(?:\.\d+)?)(?:\s+(?P<unit>.+?))?$"
)
_RE_ONE_SIDED = re.compile(
    r"^\s*(?P<op>[<>]=?)\s*(?P<val>[+-]?\d+(?:\.\d+)?)(?:\s+(?P<unit>.+?))?$"
)

_HBA1C_IFCC_TO_NGSP_SLOPE = Decimal("0.09148")
_HBA1C_IFCC_TO_NGSP_INTERCEPT = Decimal("2.152")
_SUPERSCRIPT_DIGITS = str.maketrans({
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
})

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
    "percent": "%",
    "pct": "%",
    "u/l": "U/L",
    "iu/l": "U/L",
    "[iu]/l": "U/L",
    "g/l": "g/L",
    "g/dl": "g/dL",
    "ng/ml": "ng/mL",
    "ng/l": "ng/L",
    "pg/ml": "pg/mL",
    "mcg/ml": "ug/mL",
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
    "10 billion/l": "10^9/L",
    "l/l": "L/L",
    "pmol/l": "pmol/L",
    "nmol/l": "nmol/L",
    "mg/l": "mg/L",
    "meq/l": "mEq/L",
    "meq l": "mEq/L",
    "m/ul": "M/uL",
    "m/mcl": "M/uL",
    "10^12/l": "10^12/L",
    "10*12/l": "10^12/L",
    "10^12l": "10^12/L",
    "10*12l": "10^12/L",
    "10 trillion/l": "10^12/L",
    "fl": "fL",
    "pg": "pg",
    "sec": "sec",
    "secs": "sec",
    "sec.": "sec",
    "s": "sec",
    "seconds": "sec",
    "ratio": "ratio",
    "{inr}": "ratio",
    "{ratio}": "ratio",
    "10*6/ul": "M/uL",
    "thou/ul": "K/uL",
    "x10e3/ul": "K/uL",
    "mill/ul": "M/uL",
    "x10e6/ul": "M/uL",
    "g%": "g/dL",
    "vol%": "%",
    "mu/l": "mIU/L",
    "miu/ml": "mIU/mL",
    "iu/ml": "IU/mL",
    "ug/ml": "ug/mL",
    "ml/min/1.73m2": "mL/min/1.73m2",
    "ml/min/{1.73_m2}": "mL/min/1.73m2",
    "ml/min": "mL/min",
    "ml/dl": "mL/dL",
    "mls/dl": "mL/dL",
    "ph": "pH",
    "units": "units",
    "{nominal}": "",
    "{sg}": "",
    "[ph]": "pH",
    "mmhg": "mmHg",
    "mm hg": "mmHg",
    "mm[hg]": "mmHg",
    "#/ul": "#/uL",
    "cells/ul": "#/uL",
    # UCUM bracket notations (for FHIR round-trip)
    "m[iu]/l": "mIU/L",
    "m[iu]/ml": "mIU/mL",
    "[iu]/ml": "IU/mL",
    # Legacy / alternate notations
    "gm/dl": "g/dL",
    "gm/l": "g/L",
    "gm%": "g/dL",
    "ug/l": "ug/L",
    "cells/cumm": "#/uL",
    "thou/cumm": "K/uL",
    "k/cumm": "K/uL",
    "mill/cumm": "M/uL",
    "million/mm3": "M/uL",
    "million/mm^3": "M/uL",
    "/ul": "#/uL",
    "x10e9/l": "10^9/L",
    "x10e12/l": "10^12/L",
    "x10e12l": "10^12/L",
    "thous/mcl": "K/uL",
    "thous/ul": "K/uL",
    "kpa": "kPa",
    "pg/dl": "pg/dL",
    "mmol/mol": "mmol/mol",
    "ng/ml feu": "ng/mL",
    "ug/ml feu": "ug/mL",
    "mg/l feu": "mg/L",
    "mm/hr": "mm/hr",
    "mm/h": "mm/hr",
    "mosm/kg": "mOsm/kg",
    "mosm/kg h2o": "mOsm/kg",
    "mosm/l": "mOsm/L",
    "mg/g": "mg/g",
    "mg/mmol": "mg/mmol",
    "{presence}": "",
    "1": "",
    "k/mcl": "K/uL",
    "units/l": "U/L",
    "mcu/ml": "mIU/mL",
    "#/hpf": "#/hpf",
    "/[hpf]": "#/hpf",
    "#/lpf": "#/lpf",
    "/[lpf]": "#/lpf",
    "u/ml": "U/mL",
    "nmol/min/ml": "nmol/min/mL",
    "ml/min/1.73 m2": "mL/min/1.73m2",
    "ml/min/1.73 m\u00b2": "mL/min/1.73m2",
    "ml/min/1.73m\u00b2": "mL/min/1.73m2",
}



# Conversion factors to normalized unit.  value_normalized = value_source * factor.
# Sources: molecular weights from PubChem/NIST; clinical factors from Tietz Clinical
# Chemistry (7th ed) and UCUM. Factor = MW / (dL-to-L or mL-to-L scale factor).
CONVERSION_TO_NORMALIZED: dict[str, dict[str, Decimal]] = {
    "glucose_serum": {  # MW 180.16; 1 mmol/L = 18.016 mg/dL (rounded to 18 per clinical convention)
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
    "tsh": {"mIU/L": Decimal("1"), "mIU/mL": Decimal("1000")},
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
    "crp": {
        "mg/L": Decimal("1"),
        "mg/dL": Decimal("10"),
    },
    # --- Wave 2: CBC ---
    "wbc": {"K/uL": Decimal("1"), "10^9/L": Decimal("1"), "#/uL": Decimal("0.001")},
    "hemoglobin": {
        "g/dL": Decimal("1"),
        "g/L": Decimal("0.1"),
    },
    "hematocrit": {
        "%": Decimal("1"),
        "L/L": Decimal("100"),
    },
    "platelets": {"K/uL": Decimal("1"), "10^9/L": Decimal("1"), "#/uL": Decimal("0.001")},
    # --- Wave 3: Vitamins ---
    "vitamin_d": {
        "ng/mL": Decimal("1"),
        "nmol/L": Decimal("1") / Decimal("2.496"),
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
    "ferritin": {"ng/mL": Decimal("1"), "ug/L": Decimal("1")},
    "magnesium": {
        "mg/dL": Decimal("1"),
        "mmol/L": Decimal("2.431"),
    },
    # --- Wave 4: CBC sub-components ---
    "rbc": {"M/uL": Decimal("1"), "10^12/L": Decimal("1"), "#/uL": Decimal("0.000001")},
    "mcv": {"fL": Decimal("1")},
    "mch": {"pg": Decimal("1")},
    "mchc": {"g/dL": Decimal("1"), "g/L": Decimal("0.1"), "%": Decimal("1")},
    "rdw": {"%": Decimal("1")},
    # --- Wave 4: Coagulation ---
    "pt": {"sec": Decimal("1")},
    "inr": {"ratio": Decimal("1"), "": Decimal("1")},
    "ptt": {"sec": Decimal("1")},
    # --- Wave 4: Other ---
    "anion_gap": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1"), "": Decimal("1")},
    "lactate": {"mmol/L": Decimal("1"), "mg/dL": Decimal("1") / Decimal("9.01")},
    # --- Wave 4: Electrolytes ---
    "sodium": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1")},
    "potassium": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1")},
    "chloride": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1")},
    "bicarbonate": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1"), "": Decimal("1")},
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
    "neutrophils": {"K/uL": Decimal("1"), "10^9/L": Decimal("1"), "#/uL": Decimal("0.001")},
    "lymphocytes": {"K/uL": Decimal("1"), "10^9/L": Decimal("1"), "#/uL": Decimal("0.001")},
    "monocytes": {"K/uL": Decimal("1"), "10^9/L": Decimal("1"), "#/uL": Decimal("0.001")},
    "eosinophils": {"K/uL": Decimal("1"), "10^9/L": Decimal("1"), "#/uL": Decimal("0.001")},
    "basophils": {"K/uL": Decimal("1"), "10^9/L": Decimal("1"), "#/uL": Decimal("0.001")},
    # --- Wave 5: Other ---
    "total_protein": {"g/dL": Decimal("1"), "g/L": Decimal("0.1")},
    "rdw_sd": {"fL": Decimal("1")},
    "mpv": {"fL": Decimal("1")},
    "pdw": {"fL": Decimal("1")},
    # NOTE: mL/min and mL/min/1.73m2 are treated as equivalent — most labs
    # report eGFR already BSA-adjusted, and the distinction is rarely preserved
    # in source data.  Accept both to avoid unnecessary review_needed rows.
    "egfr": {"mL/min/1.73m2": Decimal("1"), "mL/min": Decimal("1")},
    # --- Wave 6: Enzymes ---
    "ldh": {"U/L": Decimal("1")},
    "lipase": {"U/L": Decimal("1")},
    "ck": {"U/L": Decimal("1")},
    "ck_mb": {"ng/mL": Decimal("1")},
    "ck_mb_index": {"%": Decimal("1")},
    # --- Wave 6: Cardiac ---
    "troponin_t": {"ng/mL": Decimal("1"), "ng/L": Decimal("0.001"), "pg/mL": Decimal("0.001")},
    "vancomycin": {"ug/mL": Decimal("1"), "mg/L": Decimal("1")},
    "vancomycin_trough": {"ug/mL": Decimal("1"), "mg/L": Decimal("1")},
    "digoxin": {"ng/mL": Decimal("1")},
    "tacrolimus": {"ng/mL": Decimal("1")},
    "salicylates": {"mg/dL": Decimal("1")},
    "myoglobin": {"ng/mL": Decimal("1")},
    # --- Wave 6: Blood gases ---
    "pco2": {"mmHg": Decimal("1"), "kPa": Decimal("7.50062")},
    "po2": {"mmHg": Decimal("1"), "kPa": Decimal("7.50062")},
    "base_excess": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1")},
    "base_deficit": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1")},
    # --- Wave 6: Other ---
    "globulin": {"g/dL": Decimal("1"), "g/L": Decimal("0.1")},
    "ionized_calcium": {"mmol/L": Decimal("1"), "mg/dL": Decimal("1") / Decimal("4.008")},
    "fibrinogen": {"mg/dL": Decimal("1"), "g/L": Decimal("100")},
    "eag": {"mg/dL": Decimal("1")},
    "blood_ph": {"pH": Decimal("1"), "units": Decimal("1"), "": Decimal("1")},
    "oxygen_saturation": {"%": Decimal("1")},
    "oxyhemoglobin": {"%": Decimal("1")},
    "carboxyhemoglobin": {"%": Decimal("1")},
    "methemoglobin": {"%": Decimal("1")},
    "oxygen_content": {"mL/dL": Decimal("1")},
    # --- Urinalysis ---
    "urine_specific_gravity": {"": Decimal("1")},
    "urine_ph": {"pH": Decimal("1"), "": Decimal("1"), "units": Decimal("1")},
    "urine_protein": {"mg/dL": Decimal("1")},
    "urine_ketones": {"mg/dL": Decimal("1")},
    "urine_bilirubin": {"mg/dL": Decimal("1")},
    # --- WBC differential percentages ---
    "neutrophils_pct": {"%": Decimal("1")},
    "lymphocytes_pct": {"%": Decimal("1")},
    "monocytes_pct": {"%": Decimal("1")},
    "eosinophils_pct": {"%": Decimal("1")},
    "basophils_pct": {"%": Decimal("1")},
    "atypical_lymphocytes_pct": {"%": Decimal("1")},
    "metamyelocytes_pct": {"%": Decimal("1")},
    "myelocytes_pct": {"%": Decimal("1")},
    "blasts_pct": {"%": Decimal("1")},
    # --- Wave 7: New biomarkers ---
    "ggt": {"U/L": Decimal("1")},
    "amylase": {"U/L": Decimal("1")},
    "direct_bilirubin": {
        "mg/dL": Decimal("1"),
        "umol/L": Decimal("1") / Decimal("17.1"),
    },
    "troponin_i": {"ng/mL": Decimal("1"), "ng/L": Decimal("0.001"), "pg/mL": Decimal("0.001")},
    "bnp": {"pg/mL": Decimal("1"), "ng/L": Decimal("1"), "pg/dL": Decimal("0.01")},
    "nt_probnp": {"pg/mL": Decimal("1"), "ng/L": Decimal("1")},
    "d_dimer": {
        "ng/mL": Decimal("1"),
        "ug/mL": Decimal("1000"),
        "mg/L": Decimal("1000"),
    },
    "reticulocytes": {"%": Decimal("1")},
    "procalcitonin": {"ng/mL": Decimal("1"), "ug/L": Decimal("1")},
    # --- Wave 8: Longevity panel ---
    "apob": {"mg/dL": Decimal("1"), "g/L": Decimal("100")},
    "bun_creatinine_ratio": {"ratio": Decimal("1"), "": Decimal("1")},
    "albumin_globulin_ratio": {"ratio": Decimal("1"), "": Decimal("1")},
    "dhea_s": {"ug/dL": Decimal("1"), "umol/L": Decimal("1") / Decimal("0.02714")},
    "estradiol": {"pg/mL": Decimal("1"), "pmol/L": Decimal("1") / Decimal("3.671")},
    # LH/FSH: normalized to mIU/mL. 1 IU/L = 1 mIU/mL. 1 mIU/L = 0.001 mIU/mL.
    "lh": {"mIU/mL": Decimal("1"), "mIU/L": Decimal("0.001"), "IU/L": Decimal("1"), "U/L": Decimal("1")},
    "fsh": {"mIU/mL": Decimal("1"), "mIU/L": Decimal("0.001"), "IU/L": Decimal("1"), "U/L": Decimal("1")},
    "homocysteine": {"umol/L": Decimal("1")},
    # Insulin: normalized to uIU/mL. 1 mIU/L = 1 uIU/mL. 1 mIU/mL = 1000 uIU/mL.
    "insulin": {"uIU/mL": Decimal("1"), "mIU/L": Decimal("1"), "mIU/mL": Decimal("1000"), "pmol/L": Decimal("1") / Decimal("6.945")},
    "tibc": {"ug/dL": Decimal("1"), "umol/L": Decimal("5.585")},
    "transferrin_saturation": {"%": Decimal("1")},
    "lpa": {"nmol/L": Decimal("1"), "mg/dL": Decimal("1") / Decimal("0.4167")},
    "chol_hdl_ratio": {"ratio": Decimal("1"), "": Decimal("1")},
    "non_hdl_cholesterol": {"mg/dL": Decimal("1"), "mmol/L": Decimal("38.67")},
    "psa": {"ng/mL": Decimal("1")},
    "testosterone_total": {"ng/dL": Decimal("1"), "nmol/L": Decimal("1") / Decimal("0.03467")},
    "shbg": {"nmol/L": Decimal("1")},
    "free_testosterone": {"pg/mL": Decimal("1")},
    "bioavailable_testosterone": {"ng/dL": Decimal("1")},
    # Urinalysis (qualitative — semi-quantitative or presence-based)
    "urine_blood": {"": Decimal("1")},
    "urine_nitrite": {"": Decimal("1")},
    "urine_leukocyte_esterase": {"": Decimal("1")},
    "urobilinogen": {"mg/dL": Decimal("1")},
    "urine_rbc": {"#/uL": Decimal("1"), "#/hpf": Decimal("1")},
    "urine_wbc": {"#/uL": Decimal("1"), "#/hpf": Decimal("1")},
    "epithelial_cells_urine": {"#/hpf": Decimal("1")},
    "hyaline_casts": {"#/lpf": Decimal("1")},
    "haptoglobin": {"mg/dL": Decimal("1"), "g/L": Decimal("100")},
    "transferrin": {"mg/dL": Decimal("1"), "g/L": Decimal("100")},
    # --- Wave 9: Clinical depth ---
    "indirect_bilirubin": {"mg/dL": Decimal("1"), "umol/L": Decimal("1") / Decimal("17.1")},
    "prealbumin": {"mg/dL": Decimal("1"), "g/L": Decimal("100")},
    "cortisol": {"ug/dL": Decimal("1"), "nmol/L": Decimal("1") / Decimal("27.59")},
    "esr": {"mm/hr": Decimal("1")},
    "osmolality_serum": {"mOsm/kg": Decimal("1")},
    "albumin_urine": {"mg/L": Decimal("1"), "mg/dL": Decimal("10"), "ug/mL": Decimal("1")},
    "albumin_creatinine_ratio": {"mg/g": Decimal("1"), "mg/mmol": Decimal("8.84")},
    "total_protein_urine": {"mg/dL": Decimal("1"), "mg/L": Decimal("0.1")},
    "iga": {"mg/dL": Decimal("1"), "g/L": Decimal("100")},
    "igg": {"mg/dL": Decimal("1"), "g/L": Decimal("100")},
    "igm": {"mg/dL": Decimal("1"), "g/L": Decimal("100")},
    "reticulocyte_absolute": {"K/uL": Decimal("1"), "10^9/L": Decimal("1"), "#/uL": Decimal("0.001"), "M/uL": Decimal("1000")},
    # --- Wave 10: ICU + urine chemistry + endocrine ---
    # Bands/IG/NRBC: absolute counts only. Percentage values are dimensionally
    # incompatible (cannot convert % to K/uL without total WBC count).
    # % inputs will get status="review_needed" with reason="unsupported_unit_for_biomarker".
    "bands": {"K/uL": Decimal("1"), "10^9/L": Decimal("1"), "#/uL": Decimal("0.001")},
    "bands_pct": {"%": Decimal("1")},
    "immature_granulocytes": {"K/uL": Decimal("1"), "10^9/L": Decimal("1"), "#/uL": Decimal("0.001")},
    "immature_granulocytes_pct": {"%": Decimal("1")},
    "nrbc": {"#/uL": Decimal("1"), "K/uL": Decimal("1000")},
    "nrbc_pct": {"%": Decimal("1")},
    # Some machine exports label urine osmolality as mOsm/L even though the
    # intended analyte is urine osmolality; accept it as a pragmatic synonym.
    "osmolality_urine": {"mOsm/kg": Decimal("1"), "mOsm/L": Decimal("1")},
    "sodium_urine": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1")},
    "potassium_urine": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1")},
    "chloride_urine": {"mEq/L": Decimal("1"), "mmol/L": Decimal("1")},
    "bun_urine": {"mg/dL": Decimal("1")},
    "pth": {"pg/mL": Decimal("1"), "ng/L": Decimal("1")},
    "t3_total": {"ng/dL": Decimal("1"), "nmol/L": Decimal("1") / Decimal("0.01536")},
    "t4_total": {"ug/dL": Decimal("1"), "nmol/L": Decimal("1") / Decimal("12.87")},
    "complement_c3": {"mg/dL": Decimal("1"), "g/L": Decimal("100")},
    "complement_c4": {"mg/dL": Decimal("1"), "g/L": Decimal("100")},
    # Ammonia: 1 ug/dL = 0.5872 umol/L (MW 17.031, factor = 10/17.031)
    "ammonia": {"umol/L": Decimal("1"), "ug/dL": Decimal("0.5872")},
    # --- Wave 11: Longevity-essential ---
    "igf1": {"ng/mL": Decimal("1")},
    "cystatin_c": {"mg/L": Decimal("1"), "nmol/L": Decimal("1") / Decimal("75.19")},
    "free_t3": {"pg/mL": Decimal("1"), "pmol/L": Decimal("1") / Decimal("1.536")},
    "reverse_t3": {"ng/dL": Decimal("1")},
    "tpo_antibodies": {"IU/mL": Decimal("1")},
    "thyroglobulin_antibodies": {"IU/mL": Decimal("1")},
    "apoa1": {"mg/dL": Decimal("1"), "g/L": Decimal("100")},
    "progesterone": {"ng/mL": Decimal("1"), "nmol/L": Decimal("1") / Decimal("3.18")},
    "amh": {"ng/mL": Decimal("1"), "pmol/L": Decimal("1") / Decimal("7.143")},
    "vitamin_a": {"ug/dL": Decimal("1"), "umol/L": Decimal("1") / Decimal("0.03491")},
    "vitamin_c": {"mg/dL": Decimal("1"), "umol/L": Decimal("1") / Decimal("56.78")},
    "vitamin_e": {"mg/L": Decimal("1"), "umol/L": Decimal("1") / Decimal("2.322")},
    "zinc": {"ug/dL": Decimal("1"), "umol/L": Decimal("6.536")},
    "selenium": {"ug/L": Decimal("1"), "umol/L": Decimal("78.96")},
    "copper": {"ug/dL": Decimal("1"), "umol/L": Decimal("6.355")},
    "fructosamine": {"umol/L": Decimal("1")},
    "vldl_cholesterol": {"mg/dL": Decimal("1"), "mmol/L": Decimal("38.67")},
    # Heavy metals
    "manganese": {"ug/L": Decimal("1")},
    "mercury": {"ug/L": Decimal("1"), "nmol/L": Decimal("1") / Decimal("4.985")},
    "lead": {"ug/dL": Decimal("1"), "umol/L": Decimal("1") / Decimal("0.04826")},
    "arsenic": {"ug/L": Decimal("1")},
    "cadmium": {"ug/L": Decimal("1"), "nmol/L": Decimal("1") / Decimal("8.897")},
    # --- Wave 12: Advanced longevity ---
    "ldl_particle_number": {"nmol/L": Decimal("1")},
    "small_dense_ldl": {"mg/dL": Decimal("1")},
    "oxidized_ldl": {"U/L": Decimal("1")},
    "lp_pla2": {"nmol/min/mL": Decimal("1"), "ng/mL": Decimal("1")},
    "il6": {"pg/mL": Decimal("1")},
    "tnf_alpha": {"pg/mL": Decimal("1")},
    "leptin": {"ng/mL": Decimal("1")},
    # C-peptide: 1 nmol/L = 3.021 ng/mL (MW 3020, 1 ng/mL = 0.331 nmol/L)
    "c_peptide": {"ng/mL": Decimal("1"), "nmol/L": Decimal("3.021")},
    "prolactin": {"ng/mL": Decimal("1"), "mIU/L": Decimal("1") / Decimal("21.2"), "mIU/mL": Decimal("1000") / Decimal("21.2")},
    "free_psa": {"ng/mL": Decimal("1")},
    "psa_free_pct": {"%": Decimal("1")},
    "rheumatoid_factor": {"IU/mL": Decimal("1")},
    "ana_screen": {"": Decimal("1")},
    "methylmalonic_acid": {"nmol/L": Decimal("1")},
    "adiponectin": {"ug/mL": Decimal("1"), "mg/L": Decimal("1")},
    "tmao": {"umol/L": Decimal("1")},
    "gdf15": {"pg/mL": Decimal("1"), "ng/L": Decimal("1")},
    "dht": {"ng/dL": Decimal("1"), "nmol/L": Decimal("1") / Decimal("0.0344")},
    "omega3_index": {"%": Decimal("1")},
    "ige_total": {"IU/mL": Decimal("1")},
    # --- Wave 13: Niche ---
    "acth": {"pg/mL": Decimal("1"), "pmol/L": Decimal("1") / Decimal("0.2202")},
    "pregnenolone": {"ng/dL": Decimal("1")},
    "glycomark": {"ug/mL": Decimal("1")},
    "coq10": {"ug/mL": Decimal("1")},
    "estrone": {"pg/mL": Decimal("1"), "pmol/L": Decimal("1") / Decimal("3.699")},
    "cortisol_free": {"ug/dL": Decimal("1")},
    "igfbp3": {"ng/mL": Decimal("1"), "mg/L": Decimal("1000")},
    "anti_ccp": {"U/mL": Decimal("1")},
    "beta2_microglobulin": {"mg/L": Decimal("1"), "nmol/L": Decimal("1") / Decimal("84.9")},
    "ca125": {"U/mL": Decimal("1")},
    "cea": {"ng/mL": Decimal("1")},
    "afp": {"ng/mL": Decimal("1"), "IU/mL": Decimal("1.21")},
    "ldl_particle_size": {"nm": Decimal("1")},
    # --- NMR LipoProfile ---
    "small_ldl_particle": {"nmol/L": Decimal("1")},
    "hdl_particle": {"umol/L": Decimal("1")},
    "large_hdl_particle": {"umol/L": Decimal("1")},
    "large_vldl_particle": {"nmol/L": Decimal("1")},
    "lp_ir_score": {"": Decimal("1")},
}


@lru_cache(maxsize=256)
def normalize_unit(value: str | None) -> str:
    if value is None:
        return ""
    stripped = value.strip()
    # Collapse whitespace, remove spaces around slashes (e.g., "mg / dL" -> "mg/dl")
    key = _RE_WHITESPACE.sub(" ", stripped.lower())
    key = _RE_SLASH_SPACES.sub("/", key)
    # Fold common Unicode/mojibake variants from lab exports into the ASCII forms
    # already covered by UNIT_SYNONYMS.
    key = key.replace("âµ", "u").replace("î¼", "u").replace("µ", "u").replace("μ", "u")
    key = _RE_SUPERSCRIPT_POWER.sub(lambda m: "10^" + m.group(1).translate(_SUPERSCRIPT_DIGITS), key)
    return UNIT_SYNONYMS.get(key, stripped)


def format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    if not value.is_finite():
        return ""

    try:
        with localcontext() as ctx:
            ctx.prec = 28
            quantized = value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    except Exception:
        return str(value)
    text = format(quantized, "f").rstrip("0").rstrip(".")
    if text == "-0":
        return "0"
    return text or "0"


def supports_source_unit(biomarker_id: str, source_unit: str) -> bool:
    normalized_unit = normalize_unit(source_unit)
    if biomarker_id == "hba1c" and normalized_unit == "mmol/mol":
        return True
    return normalized_unit in CONVERSION_TO_NORMALIZED.get(biomarker_id, {})


def convert_to_normalized(value: Decimal, biomarker_id: str, source_unit: str) -> Decimal | None:
    normalized_unit = normalize_unit(source_unit)
    with localcontext() as ctx:
        ctx.prec = 28  # Isolate from external decimal context changes
        if biomarker_id == "hba1c" and normalized_unit == "mmol/mol":
            # NGSP/DCCT %HbA1c = (0.09148 * IFCC mmol/mol) + 2.152
            return (value * _HBA1C_IFCC_TO_NGSP_SLOPE) + _HBA1C_IFCC_TO_NGSP_INTERCEPT
        factor = CONVERSION_TO_NORMALIZED.get(biomarker_id, {}).get(normalized_unit)
        if factor is None:
            return None
        return value * factor


def is_inequality_value(value: str | None) -> bool:
    if value is None:
        return False
    stripped = value.strip()
    return bool(_RE_INEQUALITY.match(stripped))


def parse_decimal(value: str | None, *, locale: str = "us") -> Decimal | None:
    """Parse a decimal string. locale="us" (default) or "eu" for European comma-as-decimal."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or len(stripped) > 50:  # Reject absurdly long strings (DoS prevention)
        return None
    # European locale: treat comma as decimal separator
    if locale == "eu" and "," in stripped and "." not in stripped:
        stripped = stripped.replace(",", ".")
        try:
            result = Decimal(stripped)
            return result if result.is_finite() else None
        except Exception:
            return None
    # Detect European decimal notation: a single comma with 1-3 trailing digits
    # and no other commas (e.g., "1,5" or "5,55").  Thousands separators always
    # have groups of exactly 3 digits after each comma (e.g., "250,000" "1,000,000").
    # NOTE: "5,123" is ambiguous (5.123 European or 5123 thousands). With exactly
    # 3 trailing digits AND no other commas, we assume thousands separator (US convention).
    # Set locale="eu" to treat all single-comma values as European decimals.
    if _RE_EURO_COMMA.match(stripped):
        return None  # Ambiguous European decimal — reject rather than corrupt
    # Parse clinical lab "x 10^N" notation (e.g., "15.5 x 10^3", "250 x10^6",
    # "1.5 X10E3"). Must be handled before standard scientific notation.
    m_x10 = _RE_X10_NOTATION.match(stripped)
    if m_x10:
        mantissa = Decimal(m_x10.group(1))
        exponent = int(m_x10.group(2))
        if exponent > 15:  # Cap exponent to prevent memory exhaustion
            return None
        result = mantissa * Decimal(10) ** exponent
        return result if result.is_finite() else None

    # Accept bounded scientific notation because machine-generated lab exports
    # often use it for very small or very large values.
    m_sci = _RE_SCI_NOTATION.match(stripped)
    if m_sci:
        exponent = int(m_sci.group("exp"))
        if abs(exponent) > 100:
            return None
        try:
            result = Decimal(stripped)
            return result if result.is_finite() else None
        except Exception:
            return None
    # Reject mixed comma+dot garbage (e.g., "1.5,2" -> would become "1.52")
    if "," in stripped and "." in stripped:
        # Only valid pattern: "1,234.56" (comma before dot as thousands separator)
        if not _RE_THOUSANDS_DOT.match(stripped):
            return None
    # Strip thousands separators (e.g., "250,000" -> "250000")
    cleaned = stripped.replace(",", "")
    try:
        result = Decimal(cleaned)
        if not result.is_finite():
            return None
        return result
    except Exception:
        return None


def parse_reference_range(text: str, fallback_unit: str) -> RangeValue | None:
    stripped = text.strip()
    if not stripped:
        return None

    # Strip thousands-separator commas from the numeric portions before matching
    # e.g., "150,000-400,000 K/uL" -> "150000-400000 K/uL"
    cleaned = _RE_THOUSANDS_SEP.sub(r"\1\2", stripped)
    # Repeat to handle multi-group: "1,000,000" -> "1000,000" -> "1000000"
    cleaned = _RE_THOUSANDS_SEP.sub(r"\1\2", cleaned)

    match = _RE_RANGE.match(cleaned)
    if match:
        low = Decimal(match.group("low"))
        high = Decimal(match.group("high"))
        if low > high:
            return None
        raw_unit = (match.group("unit") or "").strip()
        unit = normalize_unit(raw_unit or fallback_unit)
        return RangeValue(low=low, high=high, unit=unit)

    # One-sided ranges: "<200", "<= 200", ">60", ">= 60"
    one_sided = _RE_ONE_SIDED.match(cleaned)
    if one_sided:
        val = Decimal(one_sided.group("val"))
        raw_unit = (one_sided.group("unit") or "").strip()
        unit = normalize_unit(raw_unit or fallback_unit)
        op = one_sided.group("op")
        if op.startswith("<"):
            return RangeValue(low=Decimal(0), high=val, unit=unit)
        else:
            return RangeValue(low=val, high=Decimal("99999"), unit=unit)

    return None


def format_range(range_value: RangeValue | None) -> str:
    if range_value is None:
        return ""
    text = f"{format_decimal(range_value.low)}-{format_decimal(range_value.high)}"
    if range_value.unit:
        return f"{text} {range_value.unit}"
    return text
