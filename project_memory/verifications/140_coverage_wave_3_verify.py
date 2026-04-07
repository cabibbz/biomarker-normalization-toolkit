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
        print("Usage: python 140_coverage_wave_3_verify.py <normalized_records.json>")
        return 2

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    summary = payload["summary"]

    require(summary["total_rows"] == 12, "Expected 12 rows")
    require(summary["mapped"] == 11, "Expected 11 mapped rows")
    require(summary["review_needed"] == 0, "Expected 0 review-needed rows")
    require(summary["unmapped"] == 1, "Expected 1 unmapped row")

    rows = payload["records"]

    # Vitamins
    require(record_by_id(rows, "402")["normalized_value"].startswith("30.04"), "Vitamin D 75 nmol/L should convert to ~30.05 ng/mL")
    require(record_by_id(rows, "404")["normalized_value"] == "499.995", "B12 369 pmol/L should convert to 499.995 pg/mL")
    require(record_by_id(rows, "406")["canonical_biomarker_id"] == "folate", "Folic Acid should map to folate")

    # Minerals
    require(record_by_id(rows, "408")["normalized_value"].startswith("79.865"), "Iron 14.3 umol/L should convert to ~79.8655 ug/dL")
    require(record_by_id(rows, "409")["canonical_biomarker_id"] == "ferritin", "Ferritin should map")
    require(record_by_id(rows, "411")["normalized_value"].startswith("2.01"), "Mag 0.83 mmol/L should convert to ~2.018 mg/dL")

    # Unmapped
    require(record_by_id(rows, "412")["mapping_status"] == "unmapped", "Strange Vitamin should be unmapped")

    print("Coverage wave 3 verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
