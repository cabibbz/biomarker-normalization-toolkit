from __future__ import annotations

import csv
import json
from pathlib import Path

from biomarker_normalization_toolkit.fhir import build_bundle
from biomarker_normalization_toolkit.models import NormalizationResult
from biomarker_normalization_toolkit.reporting import build_summary_report


REQUIRED_INPUT_COLUMNS = (
    "source_row_id",
    "source_test_name",
    "raw_value",
    "source_unit",
    "specimen_type",
    "source_reference_range",
)


def read_input(path: Path) -> list[dict[str, str]]:
    """Auto-detect format and read input file. Supports CSV and FHIR JSON."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return read_fhir_input(path)
    return read_input_csv(path)


def read_fhir_input(path: Path) -> list[dict[str, str]]:
    """Read a FHIR Bundle JSON and extract Observation resources into input rows."""
    data = json.loads(path.read_text(encoding="utf-8"))

    if data.get("resourceType") == "Observation":
        entries = [{"resource": data}]
    elif data.get("resourceType") == "Bundle":
        entries = data.get("entry", [])
    else:
        raise ValueError(f"Unrecognized FHIR resourceType: {data.get('resourceType', 'none')}")

    rows: list[dict[str, str]] = []
    for index, entry in enumerate(entries, start=1):
        resource = entry.get("resource", entry)
        if resource.get("resourceType") != "Observation":
            continue

        code_obj = resource.get("code", {})
        coding = code_obj.get("coding", [{}])
        test_name = code_obj.get("text", "")
        if not test_name and coding:
            test_name = coding[0].get("display", "")
        if not test_name:
            continue

        vq = resource.get("valueQuantity", {})
        value = vq.get("value")
        if value is None:
            continue

        unit = vq.get("unit", vq.get("code", ""))

        ref_range = ""
        ref_ranges = resource.get("referenceRange", [])
        if ref_ranges:
            rr = ref_ranges[0]
            low = rr.get("low", {}).get("value")
            high = rr.get("high", {}).get("value")
            rr_unit = rr.get("low", {}).get("unit", unit)
            if low is not None and high is not None:
                ref_range = f"{low}-{high}"
                if rr_unit:
                    ref_range += f" {rr_unit}"

        specimen = ""
        spec_obj = resource.get("specimen", {})
        if spec_obj:
            specimen = spec_obj.get("display", "")

        row_id = resource.get("id", "")
        if not row_id:
            identifiers = resource.get("identifier", [])
            row_id = identifiers[0].get("value", "") if identifiers else f"fhir_{index}"

        rows.append({
            "source_row_id": str(row_id),
            "source_lab_name": "",
            "source_panel_name": "",
            "source_test_name": test_name,
            "raw_value": str(value),
            "source_unit": unit,
            "specimen_type": specimen,
            "source_reference_range": ref_range,
        })

    if not rows:
        raise ValueError("No Observation resources with numeric values found in FHIR input.")

    return rows


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


def write_fhir_bundle(result: NormalizationResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    fhir_path = output_dir / "fhir_observations.json"
    fhir_path.write_text(
        json.dumps(build_bundle(result), indent=2) + "\n",
        encoding="utf-8",
    )
    return fhir_path


def write_summary_report(result: NormalizationResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "normalization_summary.md"
    report_path.write_text(build_summary_report(result), encoding="utf-8")
    return report_path
