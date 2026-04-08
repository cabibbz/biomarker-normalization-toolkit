"""PhenoAge biological age calculator.

Implements the Levine 2018 phenotypic age formula using 9 standard clinical
chemistry biomarkers. Published in: Levine ME et al. "An epigenetic biomarker
of aging for lifespan and healthspan." Aging (2018) 10(4):573-591.

All 9 required biomarkers are already in BNT's catalog:
  albumin, creatinine, glucose_serum, crp (or hscrp), lymphocytes_pct,
  mcv, rdw, alp, wbc
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from biomarker_normalization_toolkit.models import NormalizationResult


def _get_value(result: NormalizationResult, *biomarker_ids: str) -> float | None:
    """Get the first mapped normalized value for any of the given biomarker IDs."""
    for record in result.records:
        if record.canonical_biomarker_id in biomarker_ids and record.mapping_status == "mapped":
            try:
                val = float(record.normalized_value)
                if not math.isfinite(val):
                    continue
                return val
            except (ValueError, TypeError):
                continue
    return None


# Levine 2018 PhenoAge coefficients
# Source: Levine ME et al. "An epigenetic biomarker of aging for lifespan and
# healthspan." Aging (2018) 10(4):573-591. Table S6, Supplementary Materials.
# These are the Gompertz proportional hazard model parameters from NHANES III
# mortality-linked cohort (n=9,926, 20+ years follow-up).
# Glucose enters as ln(glucose_mg_dL) per the log-linear mortality model.
_COEFFICIENTS = {
    "albumin_g_dl": -0.0336,       # Table S6 row 1
    "creatinine_mg_dl": 0.0095,    # Table S6 row 2
    "glucose_mg_dl": 0.1953,       # Table S6 row 3 (applied to ln(glucose))
    "crp_ln_mg_dl": 0.0954,       # Table S6 row 4 (ln(CRP in mg/dL))
    "lymphocyte_pct": -0.0120,     # Table S6 row 5
    "mcv_fl": 0.0268,             # Table S6 row 6
    "rdw_pct": 0.3306,            # Table S6 row 7
    "alp_u_l": 0.0019,            # Table S6 row 8
    "wbc_1000_ul": 0.0554,        # Table S6 row 9
    "age": 0.0804,                # Table S6 row 10
}
_INTERCEPT = -19.9067             # Table S6 intercept

# Gompertz inversion constants (derived from NHANES III mortality parameters)
# Used to convert the linear predictor (xb) back to a biological age.
# gamma = Gompertz shape parameter from the mortality model
# 141.50225, -0.00553, 0.090165 are the PhenoAge inversion constants from
# the supplementary R code (BioAge package, function phenoage()).


def compute_phenoage(
    result: NormalizationResult,
    chronological_age: float | None = None,
) -> dict[str, Any] | None:
    """Compute PhenoAge biological age from a NormalizationResult.

    Args:
        result: NormalizationResult containing mapped biomarker records.
        chronological_age: Patient's chronological age in years. If None,
            only the mortality score (xb) is returned, not the age estimate.

    Returns:
        Dict with phenoage results, or None if required biomarkers are missing.
        Keys: phenoage, chronological_age, age_acceleration, mortality_score,
              inputs, missing_inputs, formula_reference.
    """
    # Extract required biomarker values
    albumin = _get_value(result, "albumin")
    creatinine = _get_value(result, "creatinine")
    glucose = _get_value(result, "glucose_serum")
    # Accept either CRP or hs-CRP (both in mg/L; need mg/dL for formula)
    crp_mg_l = _get_value(result, "crp", "hscrp")
    lymph_pct = _get_value(result, "lymphocytes_pct")
    mcv = _get_value(result, "mcv")
    rdw = _get_value(result, "rdw")
    alp = _get_value(result, "alp")
    wbc = _get_value(result, "wbc")

    inputs_found = {
        "albumin": albumin,
        "creatinine": creatinine,
        "glucose": glucose,
        "crp": crp_mg_l,
        "lymphocytes_pct": lymph_pct,
        "mcv": mcv,
        "rdw": rdw,
        "alp": alp,
        "wbc": wbc,
    }
    missing = [k for k, v in inputs_found.items() if v is None]

    if missing:
        return {
            "phenoage": None,
            "error": f"Missing required biomarkers: {', '.join(missing)}",
            "inputs_found": {k: v for k, v in inputs_found.items() if v is not None},
            "missing_inputs": missing,
        }

    # Validate inputs are physiologically plausible
    if glucose <= 0:
        return {"phenoage": None, "error": "Glucose must be > 0 for PhenoAge calculation."}
    if albumin <= 0 or creatinine <= 0 or wbc <= 0:
        return {"phenoage": None, "error": "Albumin, creatinine, and WBC must be > 0."}

    # Convert CRP from mg/L to mg/dL for the formula, then take ln
    crp_mg_dl = crp_mg_l / 10.0
    # CRP=0 is valid (very healthy). Use minimum detectable level for ln calculation.
    # Levine 2018 R code uses max(CRP, 0.01 mg/L) = 0.001 mg/dL as floor.
    if crp_mg_dl <= 0:
        crp_mg_dl = 0.001
    ln_crp = math.log(crp_mg_dl)

    # Levine 2018: glucose enters as ln(glucose_mg_dL)
    ln_glucose = math.log(glucose)

    xb_no_age = (
        _INTERCEPT
        + _COEFFICIENTS["albumin_g_dl"] * albumin
        + _COEFFICIENTS["creatinine_mg_dl"] * creatinine
        + _COEFFICIENTS["glucose_mg_dl"] * ln_glucose
        + _COEFFICIENTS["crp_ln_mg_dl"] * ln_crp
        + _COEFFICIENTS["lymphocyte_pct"] * lymph_pct
        + _COEFFICIENTS["mcv_fl"] * mcv
        + _COEFFICIENTS["rdw_pct"] * rdw
        + _COEFFICIENTS["alp_u_l"] * alp
        + _COEFFICIENTS["wbc_1000_ul"] * wbc
    )

    # The actual Levine formula uses a Gompertz proportional hazard:
    # mortality_score = 1 - exp(-exp(xb) * (exp(120 * gamma) - 1) / gamma)
    # where gamma = shape parameter
    # PhenoAge = inverse of the Gompertz CDF at the mortality_score for a given age

    # Simplified PhenoAge calculation using the published coefficients
    # xb with age term
    if chronological_age is not None:
        xb = xb_no_age + _COEFFICIENTS["age"] * chronological_age

        # Gompertz parameters from Levine 2018 supplementary R code
        gamma = 0.0076927
        # Compute at runtime instead of hardcoding to avoid truncation error
        gompertz_num = math.exp(120 * gamma) - 1  # ~1.51714
        mortality_score = 1.0 - math.exp(
            -gompertz_num * math.exp(xb) / gamma
        )

        # Invert: find the age that would give this mortality score for an
        # average person. PhenoAge formula from the paper:
        # PhenoAge = 141.50225 + ln(-0.00553 * ln(1 - mortality_score)) / 0.090165
        if mortality_score > 0 and mortality_score < 1:
            phenoage = 141.50225 + math.log(-0.00553 * math.log(1 - mortality_score)) / 0.090165
            # Clamp to physiologically meaningful range
            phenoage = max(0, min(phenoage, 200))
        else:
            phenoage = chronological_age  # Edge case
    else:
        phenoage = None
        mortality_score = None

    result_dict: dict[str, Any] = {
        "phenoage": round(phenoage, 1) if phenoage is not None else None,
        "chronological_age": chronological_age,
        "age_acceleration": round(phenoage - chronological_age, 1) if phenoage is not None and chronological_age is not None else None,
        "mortality_score": round(xb_no_age, 4),
        "inputs": {
            "albumin_g_dl": albumin,
            "creatinine_mg_dl": creatinine,
            "glucose_mg_dl": glucose,
            "crp_mg_l": crp_mg_l,
            "ln_crp_mg_dl": round(ln_crp, 4),
            "lymphocytes_pct": lymph_pct,
            "mcv_fl": mcv,
            "rdw_pct": rdw,
            "alp_u_l": alp,
            "wbc_k_ul": wbc,
        },
        "formula_reference": "Levine ME et al. Aging (2018) 10(4):573-591",
    }

    if phenoage is not None and chronological_age is not None:
        accel = result_dict["age_acceleration"]
        if accel <= -5:
            result_dict["interpretation"] = "Significantly younger biological age"
        elif accel <= -2:
            result_dict["interpretation"] = "Younger biological age"
        elif accel <= 2:
            result_dict["interpretation"] = "Biological age matches chronological age"
        elif accel <= 5:
            result_dict["interpretation"] = "Older biological age"
        else:
            result_dict["interpretation"] = "Significantly older biological age"

    return result_dict
