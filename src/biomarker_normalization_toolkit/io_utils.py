from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
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
    """Auto-detect format and read input file. Supports CSV, FHIR JSON, HL7v2, and C-CDA XML."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return read_fhir_input(path)
    if suffix in (".hl7", ".oru"):
        return read_hl7_input(path)
    if suffix == ".xml":
        return read_ccda_input(path)
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


def _parse_hl7_sn(value: str) -> str:
    """Parse HL7 SN (Structured Numeric) value like '<^10' or '>^500'."""
    parts = value.split("^")
    if len(parts) >= 2:
        comparator = parts[0].strip()
        number = parts[1].strip()
        if comparator and number:
            return f"{comparator}{number}"
        if number:
            return number
    return value


def read_hl7_input(path: Path) -> list[dict[str, str]]:
    """Read an HL7 v2.x file and extract OBX segments into input rows."""
    text = path.read_text(encoding="utf-8-sig")
    lines = [line.rstrip("\r") for line in text.split("\n") if line.strip()]

    # Detect field separator from MSH
    if not lines or not lines[0].startswith("MSH"):
        raise ValueError("Not a valid HL7 v2.x message: missing MSH segment.")

    field_sep = lines[0][3]  # Usually '|'
    comp_sep = lines[0][4] if len(lines[0]) > 4 else "^"  # Usually '^'

    rows: list[dict[str, str]] = []
    current_obr_name = ""
    row_id = 0

    for line in lines:
        fields = line.split(field_sep)
        segment = fields[0] if fields else ""

        if segment == "OBR" and len(fields) > 4:
            # OBR-4: Universal Service Identifier (test/panel name)
            obr4_parts = fields[4].split(comp_sep)
            current_obr_name = obr4_parts[1] if len(obr4_parts) > 1 else obr4_parts[0]

        if segment == "OBX" and len(fields) > 6:
            value_type = fields[2] if len(fields) > 2 else ""  # NM, SN, ST, CE, etc.
            # OBX-3: Observation Identifier
            obx3_parts = fields[3].split(comp_sep)
            test_name = obx3_parts[1] if len(obx3_parts) > 1 else obx3_parts[0]
            loinc_code = obx3_parts[0] if obx3_parts else ""

            # OBX-5: Observation Value
            raw_value = fields[5] if len(fields) > 5 else ""
            if value_type == "SN":
                raw_value = _parse_hl7_sn(raw_value)

            # OBX-6: Units
            unit = ""
            if len(fields) > 6 and fields[6]:
                unit_parts = fields[6].split(comp_sep)
                unit = unit_parts[0]

            # OBX-7: Reference Range
            ref_range = ""
            if len(fields) > 7 and fields[7]:
                rr = fields[7]
                if unit:
                    ref_range = f"{rr} {unit}"
                else:
                    ref_range = rr

            # OBX-8: Abnormal Flags
            abnormal_flag = fields[8].strip() if len(fields) > 8 else ""

            # OBX-11: Result Status
            result_status = fields[11].strip() if len(fields) > 11 else ""

            row_id += 1
            rows.append({
                "source_row_id": f"hl7_{row_id}",
                "source_lab_name": "",
                "source_panel_name": current_obr_name,
                "source_test_name": test_name,
                "raw_value": raw_value,
                "source_unit": unit,
                "specimen_type": "",
                "source_reference_range": ref_range,
            })

    if not rows:
        raise ValueError("No OBX segments found in HL7 input.")

    return rows


_XSI = "{http://www.w3.org/2001/XMLSchema-instance}"
_LOINC_OID = "2.16.840.1.113883.6.1"


def read_ccda_input(path: Path) -> list[dict[str, str]]:
    """Read a C-CDA XML document or fragment and extract lab observations."""
    content = path.read_text(encoding="utf-8-sig")

    # C-CDA examples are often fragments — wrap if needed
    if not content.strip().startswith("<?xml") and "<ClinicalDocument" not in content:
        content = (
            '<root xmlns:sdtc="urn:hl7-org:sdtc" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            + content
            + "</root>"
        )

    root = ET.fromstring(content)
    rows: list[dict[str, str]] = []
    row_id = 0

    for obs in root.iter("observation"):
        code_el = obs.find("code")
        value_el = obs.find("value")
        if code_el is None or value_el is None:
            continue

        # Get test name from code element
        loinc_code = code_el.attrib.get("code", "")
        display_name = code_el.attrib.get("displayName", "")
        # Check translations for LOINC
        if not display_name:
            for trans in code_el.findall("translation"):
                if trans.attrib.get("codeSystem") == _LOINC_OID:
                    display_name = trans.attrib.get("displayName", "")
                    if not loinc_code:
                        loinc_code = trans.attrib.get("code", "")

        test_name = display_name or loinc_code
        if not test_name:
            continue

        # Get value based on xsi:type
        xsi_type = value_el.attrib.get(f"{_XSI}type", "")
        raw_value = ""
        unit = ""

        if xsi_type == "PQ":
            # Physical Quantity: value + unit
            raw_value = value_el.attrib.get("value", "").strip()
            unit = value_el.attrib.get("unit", "").strip()
            # Some C-CDA docs use translation for non-UCUM units
            if not raw_value:
                trans = value_el.find("translation")
                if trans is not None:
                    raw_value = trans.attrib.get("value", "").strip()
                    unit = trans.attrib.get("unit", unit).strip()
        elif xsi_type == "IVL_PQ":
            # Interval — used for "<10" style values
            low = value_el.find("low")
            high = value_el.find("high")
            if low is not None and low.attrib.get("value"):
                raw_value = low.attrib.get("value", "").strip()
                unit = low.attrib.get("unit", "").strip()
                if low.attrib.get("inclusive") == "false":
                    raw_value = f">{raw_value}"
            elif high is not None and high.attrib.get("value"):
                raw_value = high.attrib.get("value", "").strip()
                unit = high.attrib.get("unit", "").strip()
                if high.attrib.get("inclusive") == "false":
                    raw_value = f"<{raw_value}"
        elif xsi_type in ("ST", "ED"):
            # String or encapsulated data
            raw_value = (value_el.text or "").strip()
        elif xsi_type in ("CD", "CE", "CO"):
            # Coded value (qualitative)
            raw_value = value_el.attrib.get("displayName", "")
            if not raw_value:
                raw_value = value_el.attrib.get("code", "")

        if not raw_value:
            continue

        # Get reference range
        ref_range = ""
        ref_el = obs.find(".//referenceRange/observationRange/value")
        if ref_el is not None:
            ref_low = ref_el.find("low")
            ref_high = ref_el.find("high")
            if ref_low is not None and ref_high is not None:
                low_val = ref_low.attrib.get("value", "")
                high_val = ref_high.attrib.get("value", "")
                ref_unit = ref_low.attrib.get("unit", unit)
                if low_val and high_val:
                    ref_range = f"{low_val}-{high_val}"
                    if ref_unit:
                        ref_range += f" {ref_unit}"

        # Get interpretation (abnormal flag)
        interp_el = obs.find("interpretationCode")
        abnormal_flag = ""
        if interp_el is not None:
            abnormal_flag = interp_el.attrib.get("code", "")

        row_id += 1
        rows.append({
            "source_row_id": f"ccda_{row_id}",
            "source_lab_name": "",
            "source_panel_name": "",
            "source_test_name": test_name,
            "raw_value": raw_value,
            "source_unit": unit,
            "specimen_type": "",
            "source_reference_range": ref_range,
        })

    if not rows:
        raise ValueError(
            "No completed observation values found in C-CDA input. "
            "The document may contain only pending or null-flavored results."
        )

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
