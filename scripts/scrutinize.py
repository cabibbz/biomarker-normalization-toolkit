#!/usr/bin/env python3
"""Automated scrutiny agent for the Biomarker Normalization Toolkit.

Run with: python scripts/scrutinize.py
Checks catalog integrity, runs all sample data, reports every issue.
"""

import sys
from pathlib import Path
from collections import Counter
from decimal import Decimal

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from biomarker_normalization_toolkit.io_utils import read_input
from biomarker_normalization_toolkit.normalizer import normalize_rows
from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG, ALIAS_INDEX
from biomarker_normalization_toolkit.units import CONVERSION_TO_NORMALIZED
from biomarker_normalization_toolkit.plausibility import PLAUSIBILITY_RANGES
from biomarker_normalization_toolkit.fhir import UCUM_CODES, build_bundle


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Catalog integrity
    for bio_id, bio in BIOMARKER_CATALOG.items():
        if bio_id not in CONVERSION_TO_NORMALIZED:
            errors.append(f"MISSING_CONVERSION: {bio_id}")
        if bio.normalized_unit and bio_id not in PLAUSIBILITY_RANGES:
            errors.append(f"MISSING_PLAUSIBILITY: {bio_id}")
        if bio.normalized_unit and bio.normalized_unit not in UCUM_CODES and bio.normalized_unit != "":
            warnings.append(f"MISSING_UCUM: unit '{bio.normalized_unit}' for {bio_id}")

    # LOINC uniqueness
    loincs: dict[str, str] = {}
    for bio_id, bio in BIOMARKER_CATALOG.items():
        if bio.loinc in loincs:
            errors.append(f"DUPLICATE_LOINC: {bio.loinc} used by {loincs[bio.loinc]} AND {bio_id}")
        loincs[bio.loinc] = bio_id

    # LOINC check digit validation
    def loinc_check(num_str: str) -> int:
        digits = [int(d) for d in num_str]
        total = 0
        for i, d in enumerate(reversed(digits)):
            if i % 2 == 0:
                doubled = d * 2
                total += doubled // 10 + doubled % 10
            else:
                total += d
        return (10 - (total % 10)) % 10

    for bio_id, bio in BIOMARKER_CATALOG.items():
        parts = bio.loinc.split("-")
        if len(parts) == 2:
            expected = loinc_check(parts[0])
            actual = int(parts[1])
            if expected != actual:
                errors.append(f"INVALID_LOINC_CHECK_DIGIT: {bio_id} {bio.loinc} (expected -{expected})")

    # 2. Run all sample data
    root = Path(__file__).resolve().parents[1]
    sample_dirs = [
        root / "sample data" / "converted",
        root / "sample data" / "hl7-examples",
        root / "sample data" / "fhir-examples",
        root / "sample data" / "ccda-examples",
        root / "fixtures" / "input",
    ]

    total_rows = 0
    total_mapped = 0
    all_unmapped: Counter[str] = Counter()
    all_units_failed: Counter[str] = Counter()

    for d in sample_dirs:
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.is_dir() or f.suffix.lower() not in (".csv", ".json", ".hl7", ".xml"):
                continue
            try:
                rows = read_input(f)
                result = normalize_rows(rows, input_file=f.name)
                total_rows += result.summary["total_rows"]
                total_mapped += result.summary["mapped"]
                for r in result.records:
                    if r.mapping_status == "unmapped":
                        all_unmapped[r.source_test_name] += 1
                    if r.status_reason == "unsupported_unit_for_biomarker":
                        all_units_failed[f"{r.canonical_biomarker_id}|{r.source_unit}"] += 1
                # FHIR UUID check
                bundle = build_bundle(result)
                uuids = set()
                for entry in bundle["entry"]:
                    if entry["fullUrl"] in uuids:
                        errors.append(f"DUPLICATE_UUID in {f.name}")
                    uuids.add(entry["fullUrl"])
                # Plausibility warnings
                plaus = [w for w in result.warnings if "Implausible" in w]
                if plaus:
                    warnings.append(f"PLAUSIBILITY: {f.name} has {len(plaus)} warnings")
            except Exception as e:
                if "No " not in str(e) and "missing required" not in str(e).lower():
                    warnings.append(f"PARSE_ERROR: {f.name}: {e}")

    rate = total_mapped / total_rows * 100 if total_rows else 0

    # 3. Report
    print(f"=== BNT SCRUTINY REPORT ===")
    print(f"Biomarkers:  {len(BIOMARKER_CATALOG)}")
    print(f"Aliases:     {len(ALIAS_INDEX)}")
    print(f"Rows tested: {total_rows}")
    print(f"Mapped:      {total_mapped} ({rate:.1f}%)")
    print(f"Errors:      {len(errors)}")
    print(f"Warnings:    {len(warnings)}")

    if errors:
        print(f"\nERRORS:")
        for e in errors:
            print(f"  {e}")

    if warnings:
        print(f"\nWARNINGS:")
        for w in warnings:
            print(f"  {w}")

    if all_units_failed:
        print(f"\nUNSUPPORTED UNITS ({len(all_units_failed)}):")
        for key, count in all_units_failed.most_common(10):
            print(f"  {count:>5d}  {key}")

    status = "PASS" if not errors else "FAIL"
    print(f"\n{status}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
