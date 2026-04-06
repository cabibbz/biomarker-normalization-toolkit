from __future__ import annotations

import json
import sys
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def record_by_id(records: list[dict], source_row_id: str) -> dict:
    for record in records:
        if record["source_row_id"] == source_row_id:
            return record
    raise AssertionError(f"Missing record for source_row_id={source_row_id}")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python 140_coverage_wave_2_verify.py <normalized_records.json>")
        return 2

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    summary = payload["summary"]

    require(summary["total_rows"] == 25, "Expected 25 rows")
    require(summary["mapped"] == 24, "Expected 24 mapped rows")
    require(summary["review_needed"] == 0, "Expected 0 review-needed rows")
    require(summary["unmapped"] == 1, "Expected 1 unmapped row")

    rows = payload["records"]

    # Liver panel
    require(record_by_id(rows, "301")["canonical_biomarker_id"] == "alt", "ALT should map")
    require(record_by_id(rows, "303")["canonical_biomarker_id"] == "ast", "AST should map")
    require(record_by_id(rows, "304")["canonical_biomarker_id"] == "alp", "ALP should map")
    require(record_by_id(rows, "306")["normalized_value"] == "1", "Bilirubin 17.1 umol/L should convert to 1 mg/dL")
    require(record_by_id(rows, "308")["normalized_value"] == "4", "Albumin 40 g/L should convert to 4 g/dL")

    # Thyroid
    require(record_by_id(rows, "309")["canonical_biomarker_id"] == "tsh", "TSH should map")
    require(record_by_id(rows, "312")["normalized_value"] == "0.1987", "FT4 15.4 pmol/L should convert to 0.1987 ng/dL")

    # Renal
    require(record_by_id(rows, "314")["normalized_value"] == "14", "BUN 5.0 mmol/L should convert to 14 mg/dL")

    # Inflammation
    require(record_by_id(rows, "316")["normalized_value"] == "1.5", "CRP 0.15 mg/dL should convert to 1.5 mg/L")

    # CBC
    require(record_by_id(rows, "320")["normalized_value"] == "14", "Hgb 140 g/L should convert to 14 g/dL")
    require(record_by_id(rows, "322")["normalized_value"] == "42", "HCT 0.42 L/L should convert to 42 %")
    require(record_by_id(rows, "324")["canonical_biomarker_id"] == "platelets", "Thrombocytes should map to platelets")

    # Unmapped
    require(record_by_id(rows, "325")["mapping_status"] == "unmapped", "Mystery Enzyme should be unmapped")

    print("Coverage wave 2 verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
