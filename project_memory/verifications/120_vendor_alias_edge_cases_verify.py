from __future__ import annotations

import json
import sys
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def row(records: list[dict], source_row_id: str) -> dict:
    for record in records:
        if record["source_row_id"] == source_row_id:
            return record
    raise AssertionError(f"Missing source row id {source_row_id}")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python 120_vendor_alias_edge_cases_verify.py <normalized_records.json>")
        return 2

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    summary = payload["summary"]
    require(summary["total_rows"] == 8, "Expected 8 vendor-alias rows")
    require(summary["mapped"] == 7, "Expected 7 mapped vendor-alias rows")
    require(summary["review_needed"] == 0, "Expected 0 review-needed rows")
    require(summary["unmapped"] == 1, "Expected 1 unmapped row")

    records = payload["records"]

    require(row(records, "201")["canonical_biomarker_id"] == "ldl_cholesterol", "LDL Chol Calc should map to LDL cholesterol")
    require(row(records, "202")["canonical_biomarker_id"] == "hdl_cholesterol", "HDL CHOL should map to HDL cholesterol")
    require(row(records, "203")["canonical_biomarker_id"] == "triglycerides", "TRIG should map to triglycerides")
    require(row(records, "204")["canonical_biomarker_id"] == "glucose_serum", "Fasting Glucose should map to serum glucose")
    require(row(records, "205")["canonical_biomarker_id"] == "creatinine", "CREA should map to creatinine")
    require(row(records, "205")["normalized_value"] == "1.1991", "CREA 106 umol/L should normalize to 1.1991 mg/dL")
    require(row(records, "206")["canonical_biomarker_id"] == "hba1c", "Hgb A1C should map to hemoglobin A1c")
    require(row(records, "207")["canonical_biomarker_id"] == "glucose_urine", "Urine GLU should map to urine glucose")
    require(row(records, "208")["mapping_status"] == "unmapped", "LDL/HDL Ratio should remain unmapped")

    print("Vendor alias and edge-case verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
