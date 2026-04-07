"""Physiological plausibility checks for normalized biomarker values.

These ranges are deliberately wide — they catch data entry errors (decimal point
in the wrong place) and unit conversion bugs, NOT clinical abnormalities.
A value outside these ranges is almost certainly a data error.
"""

from __future__ import annotations

from decimal import Decimal


# (min, max) in normalized units. Ranges are 2-5x wider than clinical reference ranges.
PLAUSIBILITY_RANGES: dict[str, tuple[Decimal, Decimal]] = {
    # Endocrine
    "glucose_serum":    (Decimal("0"),    Decimal("1500")),
    "glucose_urine":    (Decimal("0"),    Decimal("5000")),
    "hba1c":            (Decimal("2"),    Decimal("20")),
    "eag":              (Decimal("20"),   Decimal("600")),
    # Lipids
    "total_cholesterol":(Decimal("20"),   Decimal("1000")),
    "ldl_cholesterol":  (Decimal("5"),    Decimal("600")),
    "hdl_cholesterol":  (Decimal("2"),    Decimal("300")),
    "triglycerides":    (Decimal("10"),   Decimal("5000")),
    # Renal
    "creatinine":       (Decimal("0"),    Decimal("50")),
    "creatinine_urine": (Decimal("1"),    Decimal("1000")),
    "bun":              (Decimal("1"),    Decimal("300")),
    "egfr":             (Decimal("1"),    Decimal("200")),
    "uric_acid":        (Decimal("0"),    Decimal("30")),
    # Liver
    "alt":              (Decimal("0"),    Decimal("10000")),
    "ast":              (Decimal("0"),    Decimal("50000")),
    "alp":              (Decimal("5"),    Decimal("5000")),
    "ggt":              (Decimal("1"),    Decimal("5000")),
    "total_bilirubin":  (Decimal("0"),    Decimal("50")),
    "direct_bilirubin": (Decimal("0"),    Decimal("30")),
    "albumin":          (Decimal("0.5"),  Decimal("7")),
    "total_protein":    (Decimal("1"),    Decimal("15")),
    "globulin":         (Decimal("0.1"),  Decimal("10")),
    "amylase":          (Decimal("1"),    Decimal("5000")),
    "lipase":           (Decimal("1"),    Decimal("10000")),
    # Thyroid
    "tsh":              (Decimal("0.001"),Decimal("500")),
    "free_t4":          (Decimal("0.1"),  Decimal("50")),
    # Inflammation
    "hscrp":            (Decimal("0"),    Decimal("500")),
    "crp":              (Decimal("0"),    Decimal("500")),
    "procalcitonin":    (Decimal("0"),    Decimal("1000")),
    # Hematology
    "wbc":              (Decimal("0.1"),  Decimal("500")),
    "hemoglobin":       (Decimal("1"),    Decimal("25")),
    "hematocrit":       (Decimal("5"),    Decimal("75")),
    "platelets":        (Decimal("1"),    Decimal("3000")),
    "rbc":              (Decimal("0.5"),  Decimal("10")),
    "mcv":              (Decimal("30"),   Decimal("150")),
    "mch":              (Decimal("10"),   Decimal("50")),
    "mchc":             (Decimal("20"),   Decimal("45")),
    "rdw":              (Decimal("5"),    Decimal("35")),
    "rdw_sd":           (Decimal("20"),   Decimal("120")),
    "mpv":              (Decimal("3"),    Decimal("20")),
    "pdw":              (Decimal("5"),    Decimal("600")),
    "reticulocytes":    (Decimal("0"),    Decimal("30")),
    # WBC differentials (absolute)
    "neutrophils":      (Decimal("0"),    Decimal("100")),
    "lymphocytes":      (Decimal("0"),    Decimal("500")),
    "monocytes":        (Decimal("0"),    Decimal("100")),
    "eosinophils":      (Decimal("0"),    Decimal("10")),
    "basophils":        (Decimal("0"),    Decimal("20")),
    # WBC differentials (percentage)
    "neutrophils_pct":  (Decimal("0"),    Decimal("100")),
    "lymphocytes_pct":  (Decimal("0"),    Decimal("100")),
    "monocytes_pct":    (Decimal("0"),    Decimal("100")),
    "eosinophils_pct":  (Decimal("0"),    Decimal("100")),
    "basophils_pct":    (Decimal("0"),    Decimal("100")),
    # Electrolytes
    "sodium":           (Decimal("80"),   Decimal("200")),
    "potassium":        (Decimal("1"),    Decimal("12")),
    "chloride":         (Decimal("60"),   Decimal("150")),
    "bicarbonate":      (Decimal("0"),    Decimal("60")),
    "calcium":          (Decimal("1"),    Decimal("20")),
    "phosphate":        (Decimal("0.5"),  Decimal("20")),
    "magnesium":        (Decimal("0.3"),  Decimal("10")),
    "anion_gap":        (Decimal("-5"),   Decimal("40")),
    "ionized_calcium":  (Decimal("0.3"),  Decimal("3")),
    # Coagulation
    "pt":               (Decimal("5"),    Decimal("200")),
    "inr":              (Decimal("0.5"),  Decimal("15")),
    "ptt":              (Decimal("10"),   Decimal("200")),
    "fibrinogen":       (Decimal("10"),   Decimal("2000")),
    "d_dimer":          (Decimal("0"),    Decimal("100000")),
    # Cardiac
    "troponin_t":       (Decimal("0"),    Decimal("50")),
    "troponin_i":       (Decimal("0"),    Decimal("50")),
    "bnp":              (Decimal("0"),    Decimal("50000")),
    "nt_probnp":        (Decimal("0"),    Decimal("100000")),
    "ck":               (Decimal("1"),    Decimal("50000")),
    "ck_mb":            (Decimal("0"),    Decimal("5000")),
    "ldh":              (Decimal("10"),   Decimal("50000")),
    # Vitamins & minerals
    "vitamin_d":        (Decimal("1"),    Decimal("200")),
    "vitamin_b12":      (Decimal("50"),   Decimal("5000")),
    "folate":           (Decimal("0.5"),  Decimal("1000")),  # RBC folate can be 150-800 ng/mL
    "iron":             (Decimal("0"),    Decimal("1000")),
    "ferritin":         (Decimal("1"),    Decimal("100000")),
    # Blood gases
    "blood_ph":         (Decimal("6.5"),  Decimal("8.0")),
    "pco2":             (Decimal("5"),    Decimal("150")),
    "po2":              (Decimal("10"),   Decimal("700")),
    "base_excess":      (Decimal("-30"),  Decimal("30")),
    "oxygen_saturation":(Decimal("20"),   Decimal("100")),
    "lactate":          (Decimal("0"),    Decimal("30")),
    # Urinalysis
    "urine_specific_gravity": (Decimal("1.000"), Decimal("1.050")),
    "urine_ph":         (Decimal("3"),    Decimal("10")),
    "urine_protein":    (Decimal("0"),    Decimal("1000")),
    "urine_ketones":    (Decimal("0"),    Decimal("500")),
    "urine_bilirubin":  (Decimal("0"),    Decimal("20")),
    # Longevity panel
    "apob":             (Decimal("10"),   Decimal("300")),
    "bun_creatinine_ratio": (Decimal("1"), Decimal("100")),
    "albumin_globulin_ratio": (Decimal("0.1"), Decimal("5")),
    "dhea_s":           (Decimal("5"),    Decimal("1500")),
    "estradiol":        (Decimal("0"),    Decimal("10000")),
    "lh":               (Decimal("0"),    Decimal("200")),
    "fsh":              (Decimal("0"),    Decimal("200")),
    "homocysteine":     (Decimal("1"),    Decimal("100")),
    "insulin":          (Decimal("0"),    Decimal("1000")),  # Extreme insulin resistance
    "tibc":             (Decimal("50"),   Decimal("700")),
    "transferrin_saturation": (Decimal("0"), Decimal("100")),
    "lpa":              (Decimal("0"),    Decimal("1000")),
    "chol_hdl_ratio":   (Decimal("0.5"),  Decimal("20")),
    "non_hdl_cholesterol": (Decimal("10"), Decimal("600")),
    "psa":              (Decimal("0"),    Decimal("200")),
    "testosterone_total": (Decimal("1"),  Decimal("2000")),
    "shbg":             (Decimal("1"),    Decimal("500")),
    "free_testosterone": (Decimal("0"),   Decimal("100")),
    "bioavailable_testosterone": (Decimal("0"), Decimal("500")),
    "urobilinogen":     (Decimal("0"),    Decimal("20")),
    "haptoglobin":      (Decimal("0"),    Decimal("1000")),
    "transferrin":      (Decimal("50"),   Decimal("600")),
    "indirect_bilirubin": (Decimal("0"), Decimal("30")),
    "cortisol":         (Decimal("0.1"), Decimal("100")),
    "esr":              (Decimal("0"),   Decimal("150")),
    "osmolality_serum": (Decimal("200"), Decimal("400")),
    "albumin_urine":    (Decimal("0"),   Decimal("5000")),
    "albumin_creatinine_ratio": (Decimal("0"), Decimal("10000")),
    "total_protein_urine": (Decimal("0"), Decimal("5000")),
    "iga":              (Decimal("10"),  Decimal("1000")),
    "igg":              (Decimal("100"), Decimal("5000")),
    "igm":              (Decimal("10"),  Decimal("1000")),
    "reticulocyte_absolute": (Decimal("0"), Decimal("500")),
    "bands":                (Decimal("0"),    Decimal("50")),
    "immature_granulocytes":(Decimal("0"),    Decimal("20")),
    "nrbc":                 (Decimal("0"),    Decimal("10000")),
    "urine_rbc":            (Decimal("0"),    Decimal("100000")),
    "urine_wbc":            (Decimal("0"),    Decimal("100000")),
    "osmolality_urine":     (Decimal("50"),   Decimal("1400")),
    "sodium_urine":         (Decimal("0"),    Decimal("500")),
    "potassium_urine":      (Decimal("0"),    Decimal("300")),
    "chloride_urine":       (Decimal("0"),    Decimal("500")),
    "bun_urine":            (Decimal("50"),   Decimal("5000")),
    "pth":                  (Decimal("0"),    Decimal("5000")),
    "t3_total":             (Decimal("20"),   Decimal("500")),
    "t4_total":             (Decimal("0.5"),  Decimal("30")),
    "complement_c3":        (Decimal("10"),   Decimal("400")),
    "complement_c4":        (Decimal("1"),    Decimal("100")),
    "ammonia":              (Decimal("0"),    Decimal("500")),
    # Longevity-essential
    "igf1":                 (Decimal("10"),   Decimal("1000")),
    "cystatin_c":           (Decimal("0.1"),  Decimal("10")),
    "free_t3":              (Decimal("0.5"),  Decimal("20")),
    "reverse_t3":           (Decimal("1"),    Decimal("100")),
    "tpo_antibodies":       (Decimal("0"),    Decimal("10000")),
    "thyroglobulin_antibodies": (Decimal("0"), Decimal("10000")),
    "apoa1":                (Decimal("20"),   Decimal("400")),
    "progesterone":         (Decimal("0"),    Decimal("300")),
    "amh":                  (Decimal("0"),    Decimal("30")),
    "vitamin_a":            (Decimal("5"),    Decimal("200")),
    "vitamin_c":            (Decimal("0"),    Decimal("5")),
    "vitamin_e":            (Decimal("1"),    Decimal("50")),
    "zinc":                 (Decimal("20"),   Decimal("300")),
    "selenium":             (Decimal("20"),   Decimal("1000")),
    "copper":               (Decimal("20"),   Decimal("300")),
    "fructosamine":         (Decimal("100"),  Decimal("500")),
    "vldl_cholesterol":     (Decimal("1"),    Decimal("200")),
    "manganese":            (Decimal("0"),    Decimal("200")),
    "mercury":              (Decimal("0"),    Decimal("200")),
    "lead":                 (Decimal("0"),    Decimal("100")),
    "arsenic":              (Decimal("0"),    Decimal("500")),
    "cadmium":              (Decimal("0"),    Decimal("50")),
    # Advanced longevity
    "ldl_particle_number":  (Decimal("200"),  Decimal("3000")),
    "small_dense_ldl":      (Decimal("0"),    Decimal("100")),
    "oxidized_ldl":         (Decimal("0"),    Decimal("200")),
    "lp_pla2":              (Decimal("0"),    Decimal("500")),
    "il6":                  (Decimal("0"),    Decimal("100")),
    "tnf_alpha":            (Decimal("0"),    Decimal("50")),
    "leptin":               (Decimal("0"),    Decimal("100")),
    "c_peptide":            (Decimal("0"),    Decimal("20")),
    "prolactin":            (Decimal("0"),    Decimal("200")),
    "free_psa":             (Decimal("0"),    Decimal("50")),
    "psa_free_pct":         (Decimal("0"),    Decimal("100")),
    "rheumatoid_factor":    (Decimal("0"),    Decimal("500")),
    "methylmalonic_acid":   (Decimal("0"),    Decimal("2000")),
    "adiponectin":          (Decimal("0"),    Decimal("50")),
    "tmao":                 (Decimal("0"),    Decimal("50")),
    "gdf15":                (Decimal("0"),    Decimal("10000")),
    "dht":                  (Decimal("0"),    Decimal("500")),
    "omega3_index":         (Decimal("0"),    Decimal("20")),
    "ige_total":            (Decimal("0"),    Decimal("5000")),
    "acth":                 (Decimal("0"),    Decimal("500")),
    "pregnenolone":         (Decimal("0"),    Decimal("1000")),
    "glycomark":            (Decimal("1"),    Decimal("50")),
    "coq10":                (Decimal("0.1"),  Decimal("5")),
    "estrone":              (Decimal("0"),    Decimal("500")),
    "cortisol_free":        (Decimal("0"),    Decimal("10")),
    "igfbp3":               (Decimal("500"),  Decimal("10000")),
    "anti_ccp":             (Decimal("0"),    Decimal("1000")),
    "beta2_microglobulin":  (Decimal("0.5"),  Decimal("20")),
    "ca125":                (Decimal("0"),    Decimal("1000")),
    "cea":                  (Decimal("0"),    Decimal("100")),
    "afp":                  (Decimal("0"),    Decimal("500")),
    "ldl_particle_size":    (Decimal("15"),   Decimal("25")),
}


def check_plausibility(biomarker_id: str, normalized_value: Decimal, normalized_unit: str) -> str | None:
    """Return a warning string if the value is outside plausible physiological range, else None."""
    bounds = PLAUSIBILITY_RANGES.get(biomarker_id)
    if bounds is None:
        return None
    low, high = bounds
    if normalized_value < low or normalized_value > high:
        return (
            f"Implausible {biomarker_id} value {normalized_value} {normalized_unit} "
            f"(expected {low}-{high})"
        )
    return None
