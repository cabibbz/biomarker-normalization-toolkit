#!/usr/bin/env python3
"""Hostile CTO quality audit: try to BREAK the product."""

import json, sys
from decimal import Decimal
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from biomarker_normalization_toolkit.normalizer import normalize_rows
from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG, ALIAS_INDEX
from biomarker_normalization_toolkit.units import CONVERSION_TO_NORMALIZED
from biomarker_normalization_toolkit.plausibility import PLAUSIBILITY_RANGES
from biomarker_normalization_toolkit.fhir import build_bundle, UCUM_CODES
from biomarker_normalization_toolkit.derived import compute_derived_metrics
from biomarker_normalization_toolkit.phenoage import compute_phenoage
from biomarker_normalization_toolkit.optimal_ranges import OPTIMAL_RANGES
from biomarker_normalization_toolkit.longitudinal import compare_results

errors = []
warnings = []

print("=== HOSTILE CTO QUALITY AUDIT ===\n")

# 1. DETERMINISM
print("1. DETERMINISM")
rows = [{"source_row_id": "d1", "source_test_name": "Glucose", "raw_value": "100.5",
         "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": "70-99 mg/dL"}]
results = [json.dumps(normalize_rows(rows).to_json_dict()) for _ in range(10)]
if len(set(results)) != 1:
    errors.append("DETERMINISM: Same input produced different outputs!")
print(f"   10 identical runs: {'PASS' if len(set(results)) == 1 else 'FAIL'}")

# 2. CONVERSION IDENTITY
print("2. IDENTITY CONVERSIONS (factor=1 for normalized unit)")
for bio_id, unit_map in CONVERSION_TO_NORMALIZED.items():
    bio = BIOMARKER_CATALOG.get(bio_id)
    if not bio:
        continue
    if bio.normalized_unit in unit_map and unit_map[bio.normalized_unit] != Decimal("1"):
        errors.append(f"IDENTITY: {bio_id} normalized_unit={bio.normalized_unit} factor={unit_map[bio.normalized_unit]} (should be 1)")
print(f"   {len(CONVERSION_TO_NORMALIZED)} biomarkers: {'PASS' if not [e for e in errors if 'IDENTITY' in e] else 'FAIL'}")

# 3. OPTIMAL RANGE CONSISTENCY
print("3. OPTIMAL RANGES vs PLAUSIBILITY")
for bio_id, (opt_low, opt_high, unit, _) in OPTIMAL_RANGES.items():
    if opt_low > opt_high:
        errors.append(f"OPTIMAL_INVERTED: {bio_id} low={opt_low} > high={opt_high}")
    if bio_id not in BIOMARKER_CATALOG:
        errors.append(f"OPTIMAL_ORPHAN: {bio_id} not in catalog")
    plaus = PLAUSIBILITY_RANGES.get(bio_id)
    if plaus:
        p_low, p_high = plaus
        if float(opt_low) < float(p_low):
            warnings.append(f"OPTIMAL<PLAUSIBLE: {bio_id} opt_low={opt_low} < plaus_low={p_low}")
print(f"   {len(OPTIMAL_RANGES)} ranges: {'PASS' if not [e for e in errors if 'OPTIMAL' in e] else 'FAIL'}")

# 4. PHENOAGE MONOTONICITY
print("4. PHENOAGE (worse inputs = older age)")
def pheno_rows(crp, rdw, wbc):
    return normalize_rows([
        {"source_row_id": "1", "source_test_name": "Albumin", "raw_value": "4.2", "source_unit": "g/dL", "specimen_type": "serum", "source_reference_range": ""},
        {"source_row_id": "2", "source_test_name": "Creatinine", "raw_value": "0.9", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        {"source_row_id": "3", "source_test_name": "Glucose", "raw_value": "90", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        {"source_row_id": "4", "source_test_name": "hs-CRP", "raw_value": str(crp), "source_unit": "mg/L", "specimen_type": "serum", "source_reference_range": ""},
        {"source_row_id": "5", "source_test_name": "Lymphocytes Percent", "raw_value": "28", "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""},
        {"source_row_id": "6", "source_test_name": "MCV", "raw_value": "90", "source_unit": "fL", "specimen_type": "whole blood", "source_reference_range": ""},
        {"source_row_id": "7", "source_test_name": "RDW", "raw_value": str(rdw), "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""},
        {"source_row_id": "8", "source_test_name": "ALP", "raw_value": "60", "source_unit": "U/L", "specimen_type": "serum", "source_reference_range": ""},
        {"source_row_id": "9", "source_test_name": "WBC", "raw_value": str(wbc), "source_unit": "K/uL", "specimen_type": "whole blood", "source_reference_range": ""},
    ])
h = compute_phenoage(pheno_rows(0.5, 12, 5.5), chronological_age=50)
u = compute_phenoage(pheno_rows(15, 18, 14), chronological_age=50)
if h["phenoage"] >= u["phenoage"]:
    errors.append(f"PHENOAGE: Healthy ({h['phenoage']}) >= Unhealthy ({u['phenoage']})")
print(f"   Healthy={h['phenoage']}, Unhealthy={u['phenoage']}: {'PASS' if h['phenoage'] < u['phenoage'] else 'FAIL'}")

# 5. FHIR R4 STRUCTURE
print("5. FHIR R4 COMPLIANCE")
rows = [{"source_row_id": "f1", "source_test_name": "Glucose", "raw_value": "100",
         "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": "70-99 mg/dL"}]
bundle = build_bundle(normalize_rows(rows, input_file="test.csv"))
obs = bundle["entry"][0]["resource"]
for field in ["resourceType", "status", "code", "valueQuantity"]:
    if field not in obs:
        errors.append(f"FHIR_MISSING: {field}")
if obs["code"]["coding"][0]["system"] != "http://loinc.org":
    errors.append("FHIR: wrong code system")
if obs["valueQuantity"].get("system") != "http://unitsofmeasure.org":
    errors.append("FHIR: wrong unit system")
# Check JSON serializes cleanly
try:
    json.loads(json.dumps(bundle))
except Exception as e:
    errors.append(f"FHIR_JSON: {e}")
print(f"   Structure + JSON: {'PASS' if not [e for e in errors if 'FHIR' in e] else 'FAIL'}")

# 6. DERIVED METRICS MATH
print("6. DERIVED METRIC ACCURACY")
rows = [
    {"source_row_id": "1", "source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
    {"source_row_id": "2", "source_test_name": "Insulin", "raw_value": "10", "source_unit": "uIU/mL", "specimen_type": "serum", "source_reference_range": ""},
    {"source_row_id": "3", "source_test_name": "HDL", "raw_value": "50", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
    {"source_row_id": "4", "source_test_name": "Triglycerides", "raw_value": "150", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
    {"source_row_id": "5", "source_test_name": "AST", "raw_value": "30", "source_unit": "U/L", "specimen_type": "serum", "source_reference_range": ""},
    {"source_row_id": "6", "source_test_name": "ALT", "raw_value": "25", "source_unit": "U/L", "specimen_type": "serum", "source_reference_range": ""},
]
metrics = compute_derived_metrics(normalize_rows(rows))
checks = {"homa_ir": 100*10/405, "tg_hdl_ratio": 150/50, "de_ritis_ratio": 30/25}
for key, expected in checks.items():
    actual = float(metrics[key]["value"])
    if abs(actual - expected) > 0.05:
        errors.append(f"DERIVED: {key} expected={expected:.3f} got={actual:.3f}")
print(f"   {len(checks)} formulas: {'PASS' if not [e for e in errors if 'DERIVED' in e] else 'FAIL'}")

# 7. SPECIMEN SAFETY
print("7. SPECIMEN DISAMBIGUATION")
rows = [{"source_row_id": "s1", "source_test_name": "Glucose", "raw_value": "100",
         "source_unit": "mg/dL", "specimen_type": "CSF", "source_reference_range": ""}]
r = normalize_rows(rows).records[0]
if r.mapping_status == "mapped":
    errors.append("SPECIMEN: CSF glucose should NOT map to serum glucose")
print(f"   CSF glucose -> {r.mapping_status}: PASS")

# 8. LONGITUDINAL DELTAS
print("8. LONGITUDINAL TRACKING")
before = normalize_rows([{"source_row_id": "1", "source_test_name": "Glucose", "raw_value": "100",
                          "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}])
after = normalize_rows([{"source_row_id": "1", "source_test_name": "Glucose", "raw_value": "90",
                         "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}])
comp = compare_results(before, after, days_between=30)
d = comp["deltas"][0]
if d["absolute_delta"] != "-10" or d["percent_delta"] != -10.0:
    errors.append(f"LONGITUDINAL: wrong delta {d['absolute_delta']} / {d['percent_delta']}%")
print(f"   Delta=-10, Pct=-10%: {'PASS' if not [e for e in errors if 'LONGITUDINAL' in e] else 'FAIL'}")

# 9. COMPLETENESS: Every biomarker should have conversion + plausibility + catalog entry
print("9. COMPLETENESS")
for bio_id in BIOMARKER_CATALOG:
    if bio_id not in CONVERSION_TO_NORMALIZED:
        errors.append(f"MISSING_CONVERSION: {bio_id}")
    bio = BIOMARKER_CATALOG[bio_id]
    if bio.normalized_unit and bio_id not in PLAUSIBILITY_RANGES:
        errors.append(f"MISSING_PLAUSIBILITY: {bio_id}")
print(f"   {len(BIOMARKER_CATALOG)} biomarkers: {'PASS' if not [e for e in errors if 'MISSING' in e] else 'FAIL'}")

# 10. LOINC INTEGRITY
print("10. LOINC CHECK DIGITS")
def loinc_check(num_str):
    digits = [int(d) for d in num_str]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            doubled = d * 2
            total += doubled // 10 + doubled % 10
        else:
            total += d
    return (10 - (total % 10)) % 10

loincs = {}
for bio_id, bio in BIOMARKER_CATALOG.items():
    parts = bio.loinc.split("-")
    if len(parts) == 2:
        expected = loinc_check(parts[0])
        actual = int(parts[1])
        if expected != actual:
            errors.append(f"LOINC_INVALID: {bio_id} {bio.loinc}")
    if bio.loinc in loincs:
        errors.append(f"LOINC_DUPLICATE: {bio.loinc} on {loincs[bio.loinc]} and {bio_id}")
    loincs[bio.loinc] = bio_id
print(f"   {len(BIOMARKER_CATALOG)} LOINCs: {'PASS' if not [e for e in errors if 'LOINC' in e] else 'FAIL'}")

# VERDICT
print(f"\n{'='*50}")
print(f"ERRORS:   {len(errors)}")
print(f"WARNINGS: {len(warnings)}")
for e in errors:
    print(f"  ERROR: {e}")
for w in warnings[:3]:
    print(f"  WARN:  {w}")
if not errors:
    print(f"\n  VERDICT: #1 QUALITY - ALL 10 CHECKS PASS")
else:
    print(f"\n  VERDICT: NEEDS FIXES")
