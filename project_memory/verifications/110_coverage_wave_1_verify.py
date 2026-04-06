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
        print("Usage: python 110_coverage_wave_1_verify.py <normalized_records.json>")
        return 2

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    summary = payload["summary"]

    require(summary["total_rows"] == 8, "Expected 8 rows in coverage wave 1 output")
    require(summary["mapped"] == 7, "Expected 7 mapped rows in coverage wave 1 output")
    require(summary["review_needed"] == 0, "Expected 0 review-needed rows in coverage wave 1 output")
    require(summary["unmapped"] == 1, "Expected 1 unmapped row in coverage wave 1 output")

    rows = payload["records"]

    ldl = record_by_id(rows, "101")
    require(ldl["canonical_biomarker_id"] == "ldl_cholesterol", "LDL row should map to ldl_cholesterol")
    require(ldl["normalized_value"] == "77.34", "LDL row should convert to 77.34 mg/dL")

    hdl = record_by_id(rows, "102")
    require(hdl["canonical_biomarker_id"] == "hdl_cholesterol", "HDL row should map to hdl_cholesterol")
    require(hdl["normalized_value"] == "50.271", "HDL row should convert to 50.271 mg/dL")

    triglycerides = record_by_id(rows, "103")
    require(triglycerides["canonical_biomarker_id"] == "triglycerides", "TG row should map to triglycerides")
    require(triglycerides["normalized_value"] == "88.57", "TG row should convert to 88.57 mg/dL")

    creatinine = record_by_id(rows, "104")
    require(creatinine["canonical_biomarker_id"] == "creatinine", "Creatinine row should map to creatinine")
    require(creatinine["normalized_value"] == "1", "Creatinine umol/L row should convert to 1 mg/dL")

    creatinine_urine = record_by_id(rows, "107")
    require(creatinine_urine["mapping_status"] == "mapped", "Urine creatinine row should map to creatinine_urine")
    require(creatinine_urine["canonical_biomarker_id"] == "creatinine_urine", "Urine creatinine row should map to creatinine_urine")
    require(creatinine_urine["loinc"] == "2161-8", "Urine creatinine should have LOINC 2161-8")

    unknown = record_by_id(rows, "108")
    require(unknown["mapping_status"] == "unmapped", "Unknown row should be unmapped")
    require(unknown["status_reason"] == "unknown_alias", "Unknown row should report unknown_alias")

    print("Coverage wave 1 verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
