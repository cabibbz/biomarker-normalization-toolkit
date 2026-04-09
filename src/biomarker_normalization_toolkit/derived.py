"""Derived metrics calculator for longevity and clinical biomarkers.

Computes deterministic ratios and indices from normalized biomarker values.
These formulas are implemented transparently in code, but downstream users
should review their suitability for the clinical or research context.
"""

from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from biomarker_normalization_toolkit.models import NormalizationResult


def _get_value(result: NormalizationResult, biomarker_id: str) -> Decimal | None:
    """Get the first mapped normalized value for a biomarker."""
    for record in result.records:
        if record.canonical_biomarker_id == biomarker_id and record.mapping_status == "mapped":
            try:
                val = Decimal(record.normalized_value)
                return val if val.is_finite() else None
            except Exception:
                return None
    return None


def _fmt(value: Decimal, places: int = 2) -> str:
    return str(value.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP))


def compute_derived_metrics(result: NormalizationResult) -> dict[str, Any]:
    """Compute derived metrics from a NormalizationResult.

    Returns a dict of metric_id -> {value, formula, inputs, unit, category}.
    Only metrics with all required inputs present are returned.
    """
    metrics: dict[str, Any] = {}

    glucose = _get_value(result, "glucose_serum")
    insulin = _get_value(result, "insulin")
    hba1c = _get_value(result, "hba1c")
    tc = _get_value(result, "total_cholesterol")
    hdl = _get_value(result, "hdl_cholesterol")
    ldl = _get_value(result, "ldl_cholesterol")
    tg = _get_value(result, "triglycerides")
    apob = _get_value(result, "apob")
    apoa1 = _get_value(result, "apoa1")
    ast = _get_value(result, "ast")
    alt = _get_value(result, "alt")
    platelets = _get_value(result, "platelets")
    albumin = _get_value(result, "albumin")
    creatinine = _get_value(result, "creatinine")
    neutrophils_val = _get_value(result, "neutrophils")
    lymphocytes_val = _get_value(result, "lymphocytes")
    iron_val = _get_value(result, "iron")
    tibc_val = _get_value(result, "tibc")

    # --- Metabolic ---

    if glucose and insulin and glucose > 0 and insulin > 0:
        homa_ir = (glucose * insulin) / Decimal("405")
        metrics["homa_ir"] = {
            "name": "HOMA-IR",
            "value": _fmt(homa_ir),
            "formula": "(Fasting Glucose x Fasting Insulin) / 405",
            "inputs": {"glucose_serum": str(glucose), "insulin": str(insulin)},
            "unit": "",
            "category": "metabolic",
            "optimal_range": "< 1.0 (longevity optimal), < 2.5 (normal)",
        }

    if glucose and insulin and glucose > Decimal("63"):
        homa_b = (Decimal("360") * insulin) / (glucose - Decimal("63"))
        metrics["homa_beta"] = {
            "name": "HOMA-%B (Beta Cell Function)",
            "value": _fmt(homa_b, 1),
            "formula": "(360 x Insulin) / (Glucose - 63)",
            "inputs": {"glucose_serum": str(glucose), "insulin": str(insulin)},
            "unit": "%",
            "category": "metabolic",
        }

    if tg and glucose and tg > 0 and glucose > 0:
        # TyG Index: ln(TG[mg/dL] * Glucose[mg/dL] / 2)

        tyg = Decimal(str(math.log(float(tg * glucose / Decimal("2")))))
        metrics["tyg_index"] = {
            "name": "TyG Index",
            "value": _fmt(tyg),
            "formula": "ln(Triglycerides x Glucose / 2)",
            "inputs": {"triglycerides": str(tg), "glucose_serum": str(glucose)},
            "unit": "",
            "category": "metabolic",
            "optimal_range": "< 8.5",
        }

    # --- Cardiovascular ---

    if tg and hdl and hdl > 0:
        tg_hdl = tg / hdl
        metrics["tg_hdl_ratio"] = {
            "name": "TG/HDL Ratio",
            "value": _fmt(tg_hdl),
            "formula": "Triglycerides / HDL",
            "inputs": {"triglycerides": str(tg), "hdl_cholesterol": str(hdl)},
            "unit": "ratio",
            "category": "cardiovascular",
            "optimal_range": "< 2.0 (longevity optimal), < 3.5 (normal)",
        }

    if apob and apoa1 and apoa1 > 0:
        ratio = apob / apoa1
        metrics["apob_apoa1_ratio"] = {
            "name": "ApoB/ApoA1 Ratio",
            "value": _fmt(ratio),
            "formula": "ApoB / ApoA1",
            "inputs": {"apob": str(apob), "apoa1": str(apoa1)},
            "unit": "ratio",
            "category": "cardiovascular",
            "optimal_range": "< 0.7 (male), < 0.6 (female)",
        }

    if ldl and hdl and hdl > 0:
        ratio = ldl / hdl
        metrics["ldl_hdl_ratio"] = {
            "name": "LDL/HDL Ratio",
            "value": _fmt(ratio),
            "formula": "LDL / HDL",
            "inputs": {"ldl_cholesterol": str(ldl), "hdl_cholesterol": str(hdl)},
            "unit": "ratio",
            "category": "cardiovascular",
            "optimal_range": "< 2.0",
        }

    if tc and hdl and ldl:
        remnant = tc - hdl - ldl
        metrics["remnant_cholesterol"] = {
            "name": "Remnant Cholesterol",
            "value": _fmt(remnant),
            "formula": "Total Cholesterol - HDL - LDL",
            "inputs": {"total_cholesterol": str(tc), "hdl_cholesterol": str(hdl), "ldl_cholesterol": str(ldl)},
            "unit": "mg/dL",
            "category": "cardiovascular",
            "optimal_range": "< 24 mg/dL",
        }

    if tg and hdl and hdl > 0:

        # AIP = log10(TG/HDL) in mmol/L
        tg_mmol = tg / Decimal("88.57")
        hdl_mmol = hdl / Decimal("38.67")
        if tg_mmol > 0 and hdl_mmol > 0:
            aip = Decimal(str(math.log10(float(tg_mmol / hdl_mmol))))
            metrics["atherogenic_index"] = {
                "name": "Atherogenic Index of Plasma (AIP)",
                "value": _fmt(aip, 3),
                "formula": "log10(TG[mmol/L] / HDL[mmol/L])",
                "inputs": {"triglycerides": str(tg), "hdl_cholesterol": str(hdl)},
                "unit": "",
                "category": "cardiovascular",
                "optimal_range": "< 0.11 (low risk)",
            }

    # --- Liver ---

    if ast and alt and alt > 0:
        de_ritis = ast / alt
        metrics["de_ritis_ratio"] = {
            "name": "De Ritis Ratio (AST/ALT)",
            "value": _fmt(de_ritis),
            "formula": "AST / ALT",
            "inputs": {"ast": str(ast), "alt": str(alt)},
            "unit": "ratio",
            "category": "liver",
            "optimal_range": "0.8-1.2 (normal liver), > 2.0 suggests alcoholic liver disease",
        }

    if ast and alt and platelets and platelets > 0 and alt > 0:

        # FIB-4 requires age — we don't have it, but include formula without age
        fib4_no_age = (ast / (platelets * Decimal(str(math.sqrt(float(alt))))))
        metrics["fib4_no_age"] = {
            "name": "FIB-4 Index (age-adjusted)",
            "value": _fmt(fib4_no_age, 3),
            "formula": "(Age x AST) / (Platelets x sqrt(ALT)) — multiply by patient age",
            "inputs": {"ast": str(ast), "alt": str(alt), "platelets": str(platelets)},
            "unit": "",
            "category": "liver",
            "note": "Multiply this value by patient age to get FIB-4. < 1.3 = low fibrosis risk.",
        }

    # --- Kidney ---

    if albumin and creatinine and creatinine > 0:
        ag_ratio = albumin / creatinine
        metrics["albumin_creatinine_serum_ratio"] = {
            "name": "Albumin/Creatinine Serum Ratio",
            "value": _fmt(ag_ratio),
            "formula": "Serum Albumin / Serum Creatinine",
            "inputs": {"albumin": str(albumin), "creatinine": str(creatinine)},
            "unit": "ratio",
            "category": "kidney",
        }

    # --- Inflammation ---

    if neutrophils_val and lymphocytes_val and lymphocytes_val > 0:
        nlr = neutrophils_val / lymphocytes_val
        metrics["nlr"] = {
            "name": "Neutrophil-to-Lymphocyte Ratio (NLR)",
            "value": _fmt(nlr),
            "formula": "Neutrophils / Lymphocytes (absolute counts)",
            "inputs": {"neutrophils": str(neutrophils_val), "lymphocytes": str(lymphocytes_val)},
            "unit": "ratio",
            "category": "inflammation",
            "optimal_range": "1.0-2.0 (longevity optimal), < 3.0 (normal)",
        }

    # --- Iron ---

    if iron_val and tibc_val and tibc_val > 0:
        uibc = tibc_val - iron_val
        metrics["uibc"] = {
            "name": "UIBC (Unsaturated Iron Binding Capacity)",
            "value": _fmt(uibc),
            "formula": "TIBC - Iron",
            "inputs": {"tibc": str(tibc_val), "iron": str(iron_val)},
            "unit": "ug/dL",
            "category": "iron",
        }

    # --- Inflammation (additional) ---

    if platelets and lymphocytes_val and lymphocytes_val > 0:
        plr = platelets / lymphocytes_val
        metrics["plr"] = {
            "name": "Platelet-to-Lymphocyte Ratio (PLR)",
            "value": _fmt(plr, 1),
            "formula": "Platelets / Lymphocytes (absolute counts)",
            "inputs": {"platelets": str(platelets), "lymphocytes": str(lymphocytes_val)},
            "unit": "ratio",
            "category": "inflammation",
            "optimal_range": "< 150 (lower associated with better outcomes)",
        }

    if neutrophils_val and platelets and lymphocytes_val and lymphocytes_val > 0:
        sii = (neutrophils_val * platelets) / lymphocytes_val
        metrics["sii"] = {
            "name": "Systemic Immune-Inflammation Index (SII)",
            "value": _fmt(sii, 0),
            "formula": "(Neutrophils x Platelets) / Lymphocytes",
            "inputs": {"neutrophils": str(neutrophils_val), "platelets": str(platelets), "lymphocytes": str(lymphocytes_val)},
            "unit": "",
            "category": "inflammation",
            "optimal_range": "< 500 (lower associated with better outcomes)",
        }

    return metrics
