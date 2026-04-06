from __future__ import annotations

import csv
import json
from pathlib import Path

from biomarker_normalization_toolkit.models import NormalizationResult


REQUIRED_INPUT_COLUMNS = (
    "source_row_id",
    "source_test_name",
    "raw_value",
    "source_unit",
    "specimen_type",
    "source_reference_range",
)


def read_input_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("Input CSV has no header row.")

        missing = [column for column in REQUIRED_INPUT_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise ValueError(f"Input CSV is missing required columns: {', '.join(missing)}")

        return [{key: value or "" for key, value in row.items()} for row in reader]


def write_result(result: NormalizationResult, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "normalized_records.json"
    csv_path = output_dir / "normalized_records.csv"

    json_path.write_text(
        json.dumps(result.to_json_dict(), indent=2) + "\n",
        encoding="utf-8",
    )

    fieldnames = list(result.records[0].to_csv_row().keys()) if result.records else [
        "source_row_number",
        "source_row_id",
        "source_lab_name",
        "source_panel_name",
        "source_test_name",
        "alias_key",
        "raw_value",
        "source_unit",
        "specimen_type",
        "source_reference_range",
        "canonical_biomarker_id",
        "canonical_biomarker_name",
        "loinc",
        "mapping_status",
        "match_confidence",
        "status_reason",
        "mapping_rule",
        "normalized_value",
        "normalized_unit",
        "normalized_reference_range",
        "provenance_source_row_id",
        "provenance_alias_key",
    ]

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in result.records:
            writer.writerow(record.to_csv_row())

    return json_path, csv_path

