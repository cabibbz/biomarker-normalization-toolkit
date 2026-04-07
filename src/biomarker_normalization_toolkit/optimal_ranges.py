"""Optimal longevity ranges for biomarkers.

Standard lab reference ranges represent the 2.5th-97.5th percentile of the
general population (including sick people). Optimal longevity ranges are
evidence-based targets associated with healthspan and reduced all-cause mortality.

Sources: Peter Attia (Outlive), Function Health, InsideTracker, published
meta-analyses on biomarker-mortality associations.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from biomarker_normalization_toolkit.models import NormalizationResult


# (optimal_low, optimal_high, unit, source/note)
OPTIMAL_RANGES: dict[str, tuple[Decimal, Decimal, str, str]] = {
    # Metabolic
    "glucose_serum": (Decimal("72"), Decimal("85"), "mg/dL", "Fasting; Attia recommends <100, optimal 72-85"),
    "hba1c": (Decimal("4.8"), Decimal("5.2"), "%", "< 5.7 normal; < 5.2 longevity optimal"),
    "insulin": (Decimal("2"), Decimal("6"), "uIU/mL", "Fasting; low insulin = insulin sensitive"),

    # Lipids
    "total_cholesterol": (Decimal("150"), Decimal("200"), "mg/dL", ""),
    "ldl_cholesterol": (Decimal("50"), Decimal("70"), "mg/dL", "Attia: < 70 for primary prevention, lower for high risk"),
    "hdl_cholesterol": (Decimal("55"), Decimal("90"), "mg/dL", "> 40 male, > 50 female minimum; 55-90 optimal"),
    "triglycerides": (Decimal("40"), Decimal("100"), "mg/dL", "< 150 normal; < 100 optimal; fasting"),
    "apob": (Decimal("40"), Decimal("70"), "mg/dL", "Attia: best single CVD marker; < 80 good, < 60 ideal"),
    "lpa": (Decimal("0"), Decimal("30"), "nmol/L", "Genetic; < 30 nmol/L low risk; > 125 high risk"),
    "non_hdl_cholesterol": (Decimal("70"), Decimal("100"), "mg/dL", "TC - HDL; < 130 normal; < 100 optimal"),
    "vldl_cholesterol": (Decimal("5"), Decimal("30"), "mg/dL", ""),

    # Liver
    "alt": (Decimal("7"), Decimal("25"), "U/L", "< 35 normal; < 25 optimal for liver health"),
    "ast": (Decimal("10"), Decimal("25"), "U/L", "< 35 normal; < 25 optimal"),
    "ggt": (Decimal("9"), Decimal("25"), "U/L", "Low GGT associated with lower mortality"),
    "total_bilirubin": (Decimal("0.3"), Decimal("1.0"), "mg/dL", "0.1-1.2 normal; slightly elevated = antioxidant"),
    "albumin": (Decimal("4.2"), Decimal("5.0"), "g/dL", "3.5-5.0 normal; > 4.2 associated with longevity"),

    # Kidney
    "creatinine": (Decimal("0.7"), Decimal("1.1"), "mg/dL", "Age/muscle dependent"),
    "egfr": (Decimal("90"), Decimal("120"), "mL/min/1.73m2", "> 60 normal; > 90 optimal"),
    "cystatin_c": (Decimal("0.55"), Decimal("0.82"), "mg/L", "Superior to creatinine for eGFR"),
    "uric_acid": (Decimal("3.5"), Decimal("5.5"), "mg/dL", "< 7 normal; 3.5-5.5 longevity optimal"),

    # Thyroid
    "tsh": (Decimal("0.5"), Decimal("2.5"), "mIU/L", "0.4-4.0 normal; 0.5-2.5 optimal"),
    "free_t4": (Decimal("1.0"), Decimal("1.5"), "ng/dL", "0.8-1.8 normal; mid-range optimal"),
    "free_t3": (Decimal("3.0"), Decimal("4.0"), "pg/mL", "2.3-4.2 normal; mid-upper optimal"),

    # Inflammation
    "hscrp": (Decimal("0"), Decimal("0.5"), "mg/L", "< 1.0 low risk; < 0.5 optimal longevity"),
    "crp": (Decimal("0"), Decimal("1.0"), "mg/L", "< 3 low risk; < 1 optimal"),
    "esr": (Decimal("0"), Decimal("10"), "mm/hr", "Low ESR = low systemic inflammation"),
    "homocysteine": (Decimal("5"), Decimal("8"), "umol/L", "< 15 normal; < 8 optimal; B12/folate dependent"),

    # Hematology
    "hemoglobin": (Decimal("13.5"), Decimal("15.5"), "g/dL", "Male 13.5-17.5; female 12-15.5; mid-range optimal"),
    "hematocrit": (Decimal("40"), Decimal("48"), "%", "Male 41-53; female 36-46"),
    "wbc": (Decimal("4.0"), Decimal("7.0"), "K/uL", "3.8-10.8 normal; < 7.0 associated with lower CVD risk"),
    "platelets": (Decimal("150"), Decimal("300"), "K/uL", "150-400 normal"),
    "rbc": (Decimal("4.2"), Decimal("5.2"), "M/uL", "Male 4.5-5.5; female 4.0-5.0"),
    "mcv": (Decimal("82"), Decimal("94"), "fL", "80-100 normal; mid-range optimal"),
    "rdw": (Decimal("11.5"), Decimal("13.0"), "%", "< 14.5 normal; lower RDW = better longevity marker"),

    # Iron
    "ferritin": (Decimal("40"), Decimal("100"), "ng/mL", "Attia: 40-100 optimal; too high = inflammation"),
    "iron": (Decimal("60"), Decimal("150"), "ug/dL", "50-170 normal"),
    "transferrin_saturation": (Decimal("25"), Decimal("35"), "%", "20-50 normal; 25-35 optimal"),

    # Vitamins
    "vitamin_d": (Decimal("40"), Decimal("60"), "ng/mL", "30-100 normal; 40-60 optimal for bone/immune"),
    "vitamin_b12": (Decimal("500"), Decimal("1000"), "pg/mL", "> 200 normal; > 500 optimal for neurological health"),
    "folate": (Decimal("10"), Decimal("25"), "ng/mL", "> 3 normal; > 10 optimal"),

    # Hormones
    "testosterone_total": (Decimal("500"), Decimal("900"), "ng/dL", "Male: 300-1000 normal; 500-900 optimal"),
    "free_testosterone": (Decimal("10"), Decimal("25"), "pg/mL", "Male: age-dependent; mid-upper optimal"),
    "dhea_s": (Decimal("200"), Decimal("500"), "ug/dL", "Declines with age; higher = younger biological age"),
    "igf1": (Decimal("100"), Decimal("180"), "ng/mL", "U-shaped mortality curve; mid-range optimal"),
    "cortisol": (Decimal("6"), Decimal("18"), "ug/dL", "AM cortisol; too high = chronic stress"),

    # Electrolytes
    "sodium": (Decimal("137"), Decimal("142"), "mEq/L", "135-145 normal; mild hypernatremia associated with aging"),
    "potassium": (Decimal("4.0"), Decimal("4.8"), "mEq/L", "3.5-5.0 normal"),
    "magnesium": (Decimal("2.0"), Decimal("2.5"), "mg/dL", "1.7-2.2 normal; most people are deficient"),
    "calcium": (Decimal("9.0"), Decimal("10.0"), "mg/dL", "8.5-10.5 normal"),

    # Cardiac
    "bnp": (Decimal("0"), Decimal("50"), "pg/mL", "< 100 normal; < 50 optimal cardiac function"),
    "troponin_i": (Decimal("0"), Decimal("0.01"), "ng/mL", "High sensitivity; < 0.01 = no myocardial injury"),

    # Micronutrients
    "zinc": (Decimal("80"), Decimal("120"), "ug/dL", "60-120 normal; 80-120 optimal for immune function"),
    "selenium": (Decimal("110"), Decimal("150"), "ug/L", "70-150 normal; 110-150 optimal for thyroid/antioxidant"),
    "copper": (Decimal("70"), Decimal("120"), "ug/dL", "70-155 normal; copper/zinc ratio matters"),

    # Advanced longevity (Wave 12)
    "ldl_particle_number": (Decimal("500"), Decimal("1000"), "nmol/L", "Attia: < 1000; < 700 ideal for primary prevention"),
    "small_dense_ldl": (Decimal("0"), Decimal("20"), "mg/dL", "< 30 normal; < 20 optimal"),
    "oxidized_ldl": (Decimal("0"), Decimal("40"), "U/L", "< 60 normal; < 40 optimal"),
    "lp_pla2": (Decimal("0"), Decimal("175"), "nmol/min/mL", "< 200 normal; < 175 optimal"),
    "il6": (Decimal("0"), Decimal("1.8"), "pg/mL", "< 7 normal; < 1.8 longevity optimal"),
    "tnf_alpha": (Decimal("0"), Decimal("4"), "pg/mL", "< 8.1 normal; < 4 optimal"),
    "leptin": (Decimal("1"), Decimal("6"), "ng/mL", "Male: 2-5.6; lower = more insulin sensitive"),
    "c_peptide": (Decimal("0.8"), Decimal("1.8"), "ng/mL", "0.8-3.1 normal; < 1.8 optimal insulin sensitivity"),
    "omega3_index": (Decimal("8"), Decimal("12"), "%", "< 4% deficient; 8-12% optimal (cardioprotective)"),
    "gdf15": (Decimal("0"), Decimal("750"), "pg/mL", "Age-dependent; < 750 associated with slower aging"),
    "tmao": (Decimal("0"), Decimal("4"), "umol/L", "< 6.2 normal; < 4 optimal (gut-heart axis)"),
    "methylmalonic_acid": (Decimal("0"), Decimal("200"), "nmol/L", "73-271 normal; < 200 suggests adequate B12"),
    "dht": (Decimal("30"), Decimal("85"), "ng/dL", "Male: 30-85; mid-range optimal"),
    "adiponectin": (Decimal("5"), Decimal("20"), "ug/mL", "Higher = better insulin sensitivity"),
}


def evaluate_optimal_ranges(result: NormalizationResult) -> list[dict[str, Any]]:
    """Evaluate each mapped biomarker against longevity-optimal ranges.

    Returns a list of evaluations, one per mapped biomarker that has an optimal range.
    """
    evaluations: list[dict[str, Any]] = []

    for record in result.records:
        if record.mapping_status != "mapped" or not record.normalized_value:
            continue

        bio_id = record.canonical_biomarker_id
        optimal = OPTIMAL_RANGES.get(bio_id)
        if optimal is None:
            continue

        opt_low, opt_high, unit, note = optimal
        try:
            value = Decimal(record.normalized_value)
        except Exception:
            continue

        if value < opt_low:
            status = "below_optimal"
        elif value > opt_high:
            status = "above_optimal"
        else:
            status = "optimal"

        evaluations.append({
            "biomarker_id": bio_id,
            "biomarker_name": record.canonical_biomarker_name,
            "value": str(value),
            "unit": record.normalized_unit,
            "optimal_low": str(opt_low),
            "optimal_high": str(opt_high),
            "status": status,
            "note": note,
        })

    return evaluations


def summarize_optimal(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize optimal range evaluations."""
    total = len(evaluations)
    optimal = sum(1 for e in evaluations if e["status"] == "optimal")
    below = sum(1 for e in evaluations if e["status"] == "below_optimal")
    above = sum(1 for e in evaluations if e["status"] == "above_optimal")
    pct = round(optimal / total * 100, 1) if total else 0

    return {
        "total_evaluated": total,
        "optimal": optimal,
        "below_optimal": below,
        "above_optimal": above,
        "optimal_percentage": pct,
        "evaluations": evaluations,
    }
