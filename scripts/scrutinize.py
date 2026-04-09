#!/usr/bin/env python3
"""Run a public-fixture sanity check for the OSS repository."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from biomarker_normalization_toolkit.catalog import ALIAS_INDEX, BIOMARKER_CATALOG
from biomarker_normalization_toolkit.fhir import build_bundle
from biomarker_normalization_toolkit.io_utils import read_input
from biomarker_normalization_toolkit.normalizer import normalize_rows
from biomarker_normalization_toolkit.plausibility import PLAUSIBILITY_RANGES
from biomarker_normalization_toolkit.units import CONVERSION_TO_NORMALIZED


def _loinc_check_digit(num_str: str) -> int:
    digits = [int(d) for d in num_str]
    total = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 0:
            doubled = digit * 2
            total += doubled // 10 + doubled % 10
        else:
            total += digit
    return (10 - (total % 10)) % 10


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    fixture_root = project_root / "fixtures" / "input"
    errors: list[str] = []
    checked_files: list[str] = []
    total_rows = 0
    total_mapped = 0

    for biomarker_id, biomarker in BIOMARKER_CATALOG.items():
        if biomarker_id not in CONVERSION_TO_NORMALIZED:
            errors.append(f"missing conversion: {biomarker_id}")
        if biomarker.normalized_unit and biomarker_id not in PLAUSIBILITY_RANGES:
            errors.append(f"missing plausibility range: {biomarker_id}")
        parts = biomarker.loinc.split("-")
        if len(parts) != 2:
            errors.append(f"malformed LOINC: {biomarker_id} -> {biomarker.loinc}")
            continue
        if _loinc_check_digit(parts[0]) != int(parts[1]):
            errors.append(f"bad LOINC check digit: {biomarker_id} -> {biomarker.loinc}")

    seen_loincs: dict[str, str] = {}
    for biomarker_id, biomarker in BIOMARKER_CATALOG.items():
        if biomarker.loinc in seen_loincs:
            errors.append(f"duplicate LOINC: {biomarker.loinc} -> {seen_loincs[biomarker.loinc]}, {biomarker_id}")
        else:
            seen_loincs[biomarker.loinc] = biomarker_id

    for path in sorted(fixture_root.rglob("*")):
        if path.is_dir():
            continue
        if path.suffix.lower() not in {".csv", ".json", ".hl7", ".oru", ".xml"}:
            continue
        if path.name in {"v0_invalid_missing_headers.csv", "custom_aliases.json"}:
            continue
        rows = read_input(path)
        result = normalize_rows(rows, input_file=path.name)
        total_rows += result.summary["total_rows"]
        total_mapped += result.summary["mapped"]
        checked_files.append(str(path.relative_to(project_root)))
        if result.summary["total_rows"] <= 0:
            errors.append(f"empty result set: {path.name}")
        if result.summary["mapped"] <= 0 and path.name != "v0_invalid_missing_headers.csv":
            errors.append(f"no mapped rows for fixture: {path.name}")
        bundle = build_bundle(result)
        full_urls = [entry["fullUrl"] for entry in bundle["entry"]]
        if len(full_urls) != len(set(full_urls)):
            errors.append(f"duplicate FHIR fullUrl values: {path.name}")

    print("=== Public Repository Sanity Check ===")
    print(f"Biomarkers: {len(BIOMARKER_CATALOG)}")
    print(f"Aliases: {len(ALIAS_INDEX)}")
    print(f"Fixtures checked: {len(checked_files)}")
    print(f"Rows processed: {total_rows}")
    print(f"Rows mapped: {total_mapped}")
    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("\nStatus: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
