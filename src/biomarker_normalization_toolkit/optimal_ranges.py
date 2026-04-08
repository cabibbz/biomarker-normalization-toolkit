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
    "vldl_cholesterol": (Decimal("5"), Decimal("30"), "mg/dL", "< 30 normal"),

    # Liver
    "alt": (Decimal("7"), Decimal("25"), "U/L", "< 35 normal; < 25 optimal for liver health"),
    "ast": (Decimal("10"), Decimal("25"), "U/L", "< 35 normal; < 25 optimal"),
    "ggt": (Decimal("9"), Decimal("20"), "U/L", "Low GGT associated with lower mortality; UK Biobank 2024"),
    "total_bilirubin": (Decimal("0.3"), Decimal("1.0"), "mg/dL", "0.1-1.2 normal; slightly elevated = antioxidant"),
    "albumin": (Decimal("4.2"), Decimal("5.0"), "g/dL", "3.5-5.0 normal; > 4.2 associated with longevity"),
    "prealbumin": (Decimal("20"), Decimal("40"), "mg/dL", "20-40 normal; lower values track malnutrition/inflammation"),

    # Kidney
    "creatinine": (Decimal("0.7"), Decimal("1.1"), "mg/dL", "Age/muscle dependent"),
    "egfr": (Decimal("90"), Decimal("120"), "mL/min/1.73m2", "> 60 normal; > 90 optimal"),
    "cystatin_c": (Decimal("0.55"), Decimal("0.82"), "mg/L", "Superior kidney marker; more sensitive than creatinine for eGFR"),
    "uric_acid": (Decimal("3.5"), Decimal("5.5"), "mg/dL", "< 7 normal; 3.5-5.5 longevity optimal"),

    # Thyroid
    "tsh": (Decimal("0.5"), Decimal("2.5"), "mIU/L", "0.4-4.0 normal; 0.5-2.5 optimal"),
    "free_t4": (Decimal("1.0"), Decimal("1.5"), "ng/dL", "0.8-1.8 normal; mid-range optimal"),
    "free_t3": (Decimal("3.0"), Decimal("4.0"), "pg/mL", "2.3-4.2 normal; mid-upper optimal"),

    # Inflammation
    "hscrp": (Decimal("0"), Decimal("0.5"), "mg/L", "< 1.0 low risk; < 0.5 optimal longevity"),
    "crp": (Decimal("0"), Decimal("1.0"), "mg/L", "< 3 low risk; < 1 optimal"),
    "esr": (Decimal("0"), Decimal("10"), "mm/hr", "Lower = less systemic inflammation"),
    "homocysteine": (Decimal("5"), Decimal("8"), "umol/L", "< 15 normal; < 8 longevity optimal; B12/folate dependent"),

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
    "testosterone_total": (Decimal("15"), Decimal("900"), "ng/dL", "Unisex range; use sex param for specific ranges"),
    "free_testosterone": (Decimal("10"), Decimal("25"), "pg/mL", "Male: age-dependent; mid-upper optimal"),
    "dhea_s": (Decimal("200"), Decimal("500"), "ug/dL", "Age-dependent decline; higher = younger biological age"),
    "igf1": (Decimal("100"), Decimal("180"), "ng/mL", "Age-dependent; U-shaped mortality curve; mid-range optimal"),
    "cortisol": (Decimal("6"), Decimal("18"), "ug/dL", "AM cortisol; too high = chronic stress"),

    # Electrolytes
    "sodium": (Decimal("137"), Decimal("142"), "mEq/L", "135-145 normal; mild hypernatremia associated with aging"),
    "potassium": (Decimal("4.0"), Decimal("4.8"), "mEq/L", "3.5-5.0 normal"),
    "magnesium": (Decimal("2.0"), Decimal("2.3"), "mg/dL", "1.7-2.2 normal; upper bound within standard reference range"),
    "calcium": (Decimal("9.0"), Decimal("10.0"), "mg/dL", "8.5-10.5 normal"),

    # Cardiac
    "bnp": (Decimal("0"), Decimal("50"), "pg/mL", "< 100 normal; < 50 optimal cardiac function"),
    "troponin_i": (Decimal("0"), Decimal("0.01"), "ng/mL", "High sensitivity; < 0.01 = no myocardial injury"),
    "ck_mb_index": (Decimal("0"), Decimal("3"), "%", "< 3% normal"),

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
    # Liver / GI
    "alp": (Decimal("30"), Decimal("80"), "U/L", "35-104 normal; lower in longevity studies"),
    "direct_bilirubin": (Decimal("0"), Decimal("0.3"), "mg/dL", "0-0.3 normal"),
    "indirect_bilirubin": (Decimal("0.1"), Decimal("0.8"), "mg/dL", "Mild elevation = antioxidant"),
    "globulin": (Decimal("2.0"), Decimal("3.2"), "g/dL", "2.0-3.5 normal"),
    "albumin_globulin_ratio": (Decimal("1.2"), Decimal("2.2"), "ratio", "1.0-2.5 normal"),
    "amylase": (Decimal("25"), Decimal("85"), "U/L", "25-125 normal"),
    "lipase": (Decimal("10"), Decimal("55"), "U/L", "10-60 normal"),
    "ldh": (Decimal("100"), Decimal("200"), "U/L", "120-246 normal; lower = less tissue damage"),
    # Renal
    "bun": (Decimal("8"), Decimal("18"), "mg/dL", "7-20 normal; lower = less protein catabolism"),
    "bun_creatinine_ratio": (Decimal("10"), Decimal("18"), "ratio", "10-20 normal"),
    "osmolality_serum": (Decimal("275"), Decimal("295"), "mOsm/kg", "275-295 normal"),
    "albumin_urine": (Decimal("0"), Decimal("20"), "mg/L", "< 30 normal; < 20 optimal"),
    "albumin_creatinine_ratio": (Decimal("0"), Decimal("30"), "mg/g", "< 30 normal"),
    # Thyroid
    "reverse_t3": (Decimal("10"), Decimal("24"), "ng/dL", "9.2-24.1 normal"),
    "tpo_antibodies": (Decimal("0"), Decimal("9"), "IU/mL", "< 9 negative"),
    "thyroglobulin_antibodies": (Decimal("0"), Decimal("4"), "IU/mL", "< 4 negative"),
    "t3_total": (Decimal("80"), Decimal("180"), "ng/dL", "80-200 normal"),
    "t4_total": (Decimal("5"), Decimal("11"), "ug/dL", "4.5-12 normal"),
    # Electrolytes
    "chloride": (Decimal("100"), Decimal("106"), "mEq/L", "98-107 normal"),
    "bicarbonate": (Decimal("22"), Decimal("28"), "mEq/L", "22-29 normal"),
    "anion_gap": (Decimal("4"), Decimal("12"), "mEq/L", "3-11 normal"),
    "phosphate": (Decimal("2.5"), Decimal("4.0"), "mg/dL", "2.5-4.5 normal"),
    "ionized_calcium": (Decimal("1.15"), Decimal("1.30"), "mmol/L", "1.12-1.32 normal"),
    # CBC
    "mpv": (Decimal("7.5"), Decimal("11.0"), "fL", "7.5-11.5 normal"),
    "mch": (Decimal("27"), Decimal("33"), "pg", "27-33 normal"),
    "mchc": (Decimal("32"), Decimal("36"), "g/dL", "32-36 normal"),
    "pdw": (Decimal("9"), Decimal("17"), "fL", "9-17 normal"),
    "reticulocytes": (Decimal("0.5"), Decimal("2.0"), "%", "0.5-2.5 normal"),
    # Coagulation
    "pt": (Decimal("11"), Decimal("13.5"), "sec", "11-13.5 normal"),
    "inr": (Decimal("0.8"), Decimal("1.1"), "ratio", "0.8-1.1 normal (not on anticoagulant)"),
    "ptt": (Decimal("25"), Decimal("35"), "sec", "25-35 normal"),
    "ptt_ratio": (Decimal("0.8"), Decimal("1.2"), "ratio", "0.8-1.2 typical when not anticoagulated"),
    "fibrinogen": (Decimal("200"), Decimal("400"), "mg/dL", "200-400 normal"),
    "d_dimer": (Decimal("0"), Decimal("250"), "ng/mL", "< 500 normal; < 250 optimal"),
    # Cardiac
    "troponin_t": (Decimal("0"), Decimal("0.01"), "ng/mL", "< 0.01 = no myocardial injury"),
    "ck": (Decimal("30"), Decimal("170"), "U/L", "Male 39-308; lower = less muscle damage"),
    "ck_mb": (Decimal("0"), Decimal("5"), "ng/mL", "< 5 normal"),
    "nt_probnp": (Decimal("0"), Decimal("125"), "pg/mL", "< 125 (< 75yo); < 450 (> 75yo)"),
    # Blood gas
    "blood_ph": (Decimal("7.38"), Decimal("7.42"), "pH", "7.35-7.45 normal"),
    "pco2": (Decimal("38"), Decimal("42"), "mmHg", "35-45 normal"),
    "po2": (Decimal("85"), Decimal("100"), "mmHg", "80-100 normal on room air"),
    "base_excess": (Decimal("-2"), Decimal("2"), "mEq/L", "-2 to +2 normal"),
    "base_deficit": (Decimal("0"), Decimal("2"), "mEq/L", "0-2 normal"),
    "oxygen_saturation": (Decimal("96"), Decimal("100"), "%", "> 95% normal"),
    "oxyhemoglobin": (Decimal("95"), Decimal("100"), "%", "Fractional oxyhemoglobin typically parallels arterial oxygenation"),
    "carboxyhemoglobin": (Decimal("0"), Decimal("2"), "%", "< 2% typical in non-smokers"),
    "methemoglobin": (Decimal("0"), Decimal("1.5"), "%", "< 1.5% normal"),
    "oxygen_content": (Decimal("16"), Decimal("22"), "mL/dL", "Calculated arterial oxygen content is typically ~16-22 mL/dL"),
    "alveolar_arterial_gradient": (Decimal("5"), Decimal("20"), "mmHg", "Typical room-air A-a gradient is low and rises with age"),
    "lactate": (Decimal("0.5"), Decimal("1.5"), "mmol/L", "0.5-2.0 normal; < 1.5 optimal"),
    # Hormones
    "progesterone": (Decimal("0.1"), Decimal("0.5"), "ng/mL", "Male/follicular phase baseline"),
    "amh": (Decimal("1"), Decimal("10"), "ng/mL", "Female age-dependent; higher = more reserve"),
    "lh": (Decimal("1.5"), Decimal("9"), "mIU/mL", "Male: 1.5-9.3; female: cycle-dependent"),
    "fsh": (Decimal("1.5"), Decimal("12"), "mIU/mL", "Male: 1.5-12.4; female: cycle-dependent"),
    "estradiol": (Decimal("10"), Decimal("40"), "pg/mL", "Male: 10-40; female: cycle-dependent"),
    "prolactin": (Decimal("2"), Decimal("15"), "ng/mL", "Male: 2-18; Female: 2-29"),
    "acth": (Decimal("7"), Decimal("50"), "pg/mL", "AM: 7.2-63.3; lower = less stress"),
    "pth": (Decimal("15"), Decimal("65"), "pg/mL", "15-65 normal"),
    # Minerals / Micronutrients
    "tibc": (Decimal("250"), Decimal("370"), "ug/dL", "250-370 normal"),
    "transferrin": (Decimal("200"), Decimal("360"), "mg/dL", "200-360 normal"),
    "vitamin_a": (Decimal("30"), Decimal("65"), "ug/dL", "30-65 normal"),
    "vitamin_c": (Decimal("0.4"), Decimal("1.5"), "mg/dL", "0.4-1.5 normal"),
    "vitamin_e": (Decimal("5"), Decimal("20"), "mg/L", "5-20 normal"),
    "fructosamine": (Decimal("190"), Decimal("270"), "umol/L", "200-285 normal; < 250 optimal"),
    # Advanced
    "apoa1": (Decimal("120"), Decimal("175"), "mg/dL", "Male: 100-175; Female: 110-200"),
    "shbg": (Decimal("20"), Decimal("60"), "nmol/L", "Male: 10-57; Female: 18-144"),
    "haptoglobin": (Decimal("30"), Decimal("200"), "mg/dL", "30-200 normal"),
    "procalcitonin": (Decimal("0"), Decimal("0.05"), "ng/mL", "< 0.05 normal; > 0.5 suggests bacterial infection"),
    "vancomycin_trough": (Decimal("10"), Decimal("20"), "ug/mL", "Common therapeutic trough target for serious infections"),
    # Cancer screening
    "psa": (Decimal("0"), Decimal("2.5"), "ng/mL", "< 4 normal; < 2.5 optimal for longevity screening"),
    # Urinalysis
    "urine_specific_gravity": (Decimal("1.010"), Decimal("1.025"), "", "1.005-1.030 normal"),
    "urine_ph": (Decimal("5.5"), Decimal("7.0"), "pH", "4.5-8.0 normal; 6-7 optimal"),
    # Heavy metals (lower is better)
    "mercury": (Decimal("0"), Decimal("5"), "ug/L", "< 10 normal; < 5 optimal"),
    "lead": (Decimal("0"), Decimal("3.5"), "ug/dL", "< 5 normal; CDC reference < 3.5"),
    "cadmium": (Decimal("0"), Decimal("0.5"), "ug/L", "< 1 normal; < 0.5 optimal"),
    "arsenic": (Decimal("0"), Decimal("15"), "ug/L", "< 50 normal; < 15 background level"),
    "manganese": (Decimal("4"), Decimal("15"), "ug/L", "4-15 normal"),
    # WBC differentials (absolute — ranges are approximate)
    "neutrophils": (Decimal("1.8"), Decimal("7.0"), "K/uL", "1.8-7.7 normal"),
    "lymphocytes": (Decimal("1.0"), Decimal("4.0"), "K/uL", "1.0-4.8 normal"),
    "monocytes": (Decimal("0.2"), Decimal("0.8"), "K/uL", "0.2-1.0 normal"),
    "eosinophils": (Decimal("0.0"), Decimal("0.4"), "K/uL", "0.0-0.5 normal"),
    "basophils": (Decimal("0.0"), Decimal("0.1"), "K/uL", "0.0-0.2 normal"),
    # WBC differential percentages
    "neutrophils_pct": (Decimal("40"), Decimal("70"), "%", "40-70% normal"),
    "lymphocytes_pct": (Decimal("20"), Decimal("40"), "%", "20-40% normal"),
    "monocytes_pct": (Decimal("2"), Decimal("8"), "%", "2-10% normal"),
    "eosinophils_pct": (Decimal("1"), Decimal("4"), "%", "1-4% normal"),
    "basophils_pct": (Decimal("0"), Decimal("1"), "%", "0-1% normal"),
    "atypical_lymphocytes_pct": (Decimal("0"), Decimal("0"), "%", "Normally absent"),
    "metamyelocytes_pct": (Decimal("0"), Decimal("0"), "%", "Normally absent"),
    "myelocytes_pct": (Decimal("0"), Decimal("0"), "%", "Normally absent"),
    "promyelocytes_pct": (Decimal("0"), Decimal("0"), "%", "Normally absent"),
    "other_cells_pct": (Decimal("0"), Decimal("0"), "%", "Normally absent"),
    "blasts_pct": (Decimal("0"), Decimal("0"), "%", "Normally absent"),
    # Other
    "eag": (Decimal("70"), Decimal("100"), "mg/dL", "Estimated from HbA1c; < 117 = normal A1c"),
    "rdw_sd": (Decimal("36"), Decimal("46"), "fL", "36-47 normal"),
    "reticulocyte_absolute": (Decimal("20"), Decimal("100"), "K/uL", "25-75 normal"),
    "total_protein_urine": (Decimal("0"), Decimal("150"), "mg/dL", "< 150 mg/day normal"),
    "creatinine_urine": (Decimal("20"), Decimal("300"), "mg/dL", "Varies with muscle mass and hydration"),
    "glucose_urine": (Decimal("0"), Decimal("15"), "mg/dL", "< 15 normal (trace)"),
    "urine_protein": (Decimal("0"), Decimal("15"), "mg/dL", "< 20 normal dipstick"),
    "urine_ketones": (Decimal("0"), Decimal("5"), "mg/dL", "< 5 normal; trace acceptable"),
    "urine_bilirubin": (Decimal("0"), Decimal("0.2"), "mg/dL", "Negative normal"),
    "urobilinogen": (Decimal("0.1"), Decimal("1.0"), "mg/dL", "0.1-1.0 normal"),
    "total_protein": (Decimal("6.3"), Decimal("7.9"), "g/dL", "6.0-8.3 normal"),
    "chol_hdl_ratio": (Decimal("1.5"), Decimal("3.5"), "ratio", "< 5 normal; < 3.5 optimal"),
    "coq10": (Decimal("0.5"), Decimal("1.5"), "ug/mL", "0.5-1.5 normal; supplementation target > 1.0"),
    "glycomark": (Decimal("10"), Decimal("30"), "ug/mL", "10-32 normal; lower = more glucose spikes"),
    "igfbp3": (Decimal("2000"), Decimal("5000"), "ng/mL", "Age-dependent; correlates with IGF-1"),
    "cortisol_free": (Decimal("0.07"), Decimal("0.93"), "ug/dL", "AM: 0.07-0.93"),
    "estrone": (Decimal("10"), Decimal("60"), "pg/mL", "Male: 10-60; Female: cycle-dependent"),
    "pregnenolone": (Decimal("10"), Decimal("200"), "ng/dL", "Age-dependent; declines with age"),
    "bioavailable_testosterone": (Decimal("100"), Decimal("350"), "ng/dL", "Male range"),
    # Remaining biomarkers
    "afp": (Decimal("0"), Decimal("8"), "ng/mL", "< 10 normal; > 400 suggests liver cancer"),
    "ammonia": (Decimal("10"), Decimal("35"), "umol/L", "15-45 normal"),
    "anti_ccp": (Decimal("0"), Decimal("20"), "U/mL", "< 20 negative"),
    "bands": (Decimal("0"), Decimal("0.5"), "K/uL", "0-0.5 K/uL normal"),
    "bands_pct": (Decimal("0"), Decimal("5"), "%", "0-5% normal"),
    "beta2_microglobulin": (Decimal("0.7"), Decimal("1.8"), "mg/L", "0.7-1.8 normal"),
    "ca125": (Decimal("0"), Decimal("35"), "U/mL", "< 35 normal"),
    "cea": (Decimal("0"), Decimal("2.5"), "ng/mL", "< 3.0 non-smoker; < 2.5 optimal"),
    "complement_c3": (Decimal("80"), Decimal("160"), "mg/dL", "90-180 normal"),
    "complement_c4": (Decimal("15"), Decimal("40"), "mg/dL", "10-40 normal"),
    "free_psa": (Decimal("0"), Decimal("1.0"), "ng/mL", "Context with total PSA"),
    "psa_free_pct": (Decimal("25"), Decimal("100"), "%", "> 25% lower cancer risk"),
    "iga": (Decimal("70"), Decimal("400"), "mg/dL", "70-400 normal"),
    "igg": (Decimal("700"), Decimal("1600"), "mg/dL", "700-1600 normal"),
    "igm": (Decimal("40"), Decimal("230"), "mg/dL", "40-230 normal"),
    "ige_total": (Decimal("0"), Decimal("100"), "IU/mL", "< 100 normal"),
    "immature_granulocytes": (Decimal("0"), Decimal("0.5"), "K/uL", "< 1% normal"),
    "ldl_particle_size": (Decimal("21"), Decimal("23"), "nm", "> 20.5 = Pattern A (large buoyant)"),
    "nrbc": (Decimal("0"), Decimal("0"), "#/uL", "0 normal in adults"),
    "nrbc_pct": (Decimal("0"), Decimal("0"), "%", "0 normal in adults"),
    "osmolality_urine": (Decimal("300"), Decimal("900"), "mOsm/kg", "300-900 normal"),
    "sodium_urine": (Decimal("40"), Decimal("220"), "mEq/L", "40-220 normal"),
    "potassium_urine": (Decimal("25"), Decimal("125"), "mEq/L", "25-125 normal"),
    "chloride_urine": (Decimal("110"), Decimal("250"), "mEq/L", "110-250 normal"),
    "bun_urine": (Decimal("120"), Decimal("200"), "mg/dL", "Varies with diet and hydration"),
    "rheumatoid_factor": (Decimal("0"), Decimal("14"), "IU/mL", "< 14 negative"),
    "urine_rbc": (Decimal("0"), Decimal("3"), "#/uL", "0-2 normal"),
    "urine_wbc": (Decimal("0"), Decimal("5"), "#/uL", "0-5 normal"),
    "epithelial_cells_urine": (Decimal("0"), Decimal("5"), "#/hpf", "0-5 normal"),
    "hyaline_casts": (Decimal("0"), Decimal("2"), "#/lpf", "0-2 normal"),
    # NMR LipoProfile
    "small_ldl_particle": (Decimal("0"), Decimal("500"), "nmol/L", "< 500 longevity target; fewer small LDL = less atherogenic"),
    "hdl_particle": (Decimal("30"), Decimal("45"), "umol/L", "30-45 umol/L optimal; higher HDL-P = better cholesterol efflux"),
    "large_hdl_particle": (Decimal("7"), Decimal("15"), "umol/L", "7-15 umol/L optimal; large HDL = more cardioprotective"),
    "large_vldl_particle": (Decimal("0"), Decimal("2"), "nmol/L", "< 2 nmol/L optimal; lower = less insulin resistance"),
    "lp_ir_score": (Decimal("0"), Decimal("27"), "", "< 27 low insulin resistance; 0-100 scale"),
}

# Sex-specific overrides (when sex is provided)
OPTIMAL_RANGES_MALE: dict[str, tuple[Decimal, Decimal, str, str]] = {
    "testosterone_total": (Decimal("500"), Decimal("900"), "ng/dL", "Male optimal"),
    "free_testosterone": (Decimal("10"), Decimal("25"), "pg/mL", "Male optimal"),
    "hemoglobin": (Decimal("14.0"), Decimal("16.5"), "g/dL", "Male 14-17.5"),
    "hematocrit": (Decimal("42"), Decimal("50"), "%", "Male 41-53"),
    "ferritin": (Decimal("40"), Decimal("150"), "ng/mL", "Male: higher normal range"),
    "rbc": (Decimal("4.5"), Decimal("5.5"), "M/uL", "Male range"),
    "leptin": (Decimal("1"), Decimal("6"), "ng/mL", "Male: 2-5.6"),
    "uric_acid": (Decimal("4.0"), Decimal("6.0"), "mg/dL", "Male: U-shaped mortality (NHANES/CHARLS 2025)"),
    "ggt": (Decimal("9"), Decimal("20"), "U/L", "Male: mortality inflection ~16 U/L (UK Biobank 2024)"),
}

OPTIMAL_RANGES_FEMALE: dict[str, tuple[Decimal, Decimal, str, str]] = {
    "testosterone_total": (Decimal("15"), Decimal("70"), "ng/dL", "Female optimal"),
    "free_testosterone": (Decimal("0.5"), Decimal("5"), "pg/mL", "Female optimal"),
    "hemoglobin": (Decimal("12.5"), Decimal("15.0"), "g/dL", "Female 12-15.5"),
    "hematocrit": (Decimal("37"), Decimal("45"), "%", "Female 36-46"),
    "ferritin": (Decimal("30"), Decimal("100"), "ng/mL", "Female: lower normal range"),
    "rbc": (Decimal("4.0"), Decimal("5.0"), "M/uL", "Female range"),
    "leptin": (Decimal("3"), Decimal("12"), "ng/mL", "Female: 3.7-11.1"),
    "hdl_cholesterol": (Decimal("60"), Decimal("100"), "mg/dL", "Female: higher target"),
    "uric_acid": (Decimal("3.0"), Decimal("5.5"), "mg/dL", "Female: optimal range (NHANES/CHARLS 2025)"),
    "ggt": (Decimal("5"), Decimal("15"), "U/L", "Female: mortality inflection ~9 U/L (UK Biobank 2024)"),
}


def evaluate_optimal_ranges(
    result: NormalizationResult,
    sex: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate each mapped biomarker against longevity-optimal ranges.

    Args:
        result: NormalizationResult with mapped records.
        sex: "male", "female", or None for unisex ranges.

    Returns a list of evaluations, one per mapped biomarker that has an optimal range.
    """
    # Build effective ranges: start with base, overlay sex-specific
    effective = dict(OPTIMAL_RANGES)
    if sex and sex.lower() in ("male", "m"):
        effective.update(OPTIMAL_RANGES_MALE)
    elif sex and sex.lower() in ("female", "f"):
        effective.update(OPTIMAL_RANGES_FEMALE)
    evaluations: list[dict[str, Any]] = []

    for record in result.records:
        if record.mapping_status != "mapped" or not record.normalized_value:
            continue

        bio_id = record.canonical_biomarker_id
        optimal = effective.get(bio_id)
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
