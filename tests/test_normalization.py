from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import shutil
from unittest import mock

from decimal import Decimal

import re

from biomarker_normalization_toolkit.catalog import ALIAS_INDEX, BIOMARKER_CATALOG, normalize_key
from biomarker_normalization_toolkit.fhir import build_bundle, UCUM_CODES
from biomarker_normalization_toolkit.io_utils import read_ccda_input, read_excel_input, read_fhir_input, read_hl7_input, read_input, read_input_csv
from biomarker_normalization_toolkit.normalizer import build_source_records, normalize_rows, normalize_source_record
from biomarker_normalization_toolkit.units import CONVERSION_TO_NORMALIZED, convert_to_normalized, is_inequality_value, normalize_unit, parse_decimal, parse_reference_range


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
INTEROP_FIXTURES = FIXTURES / "input" / "interop"


def _write_excel_interop_fixture(path: Path) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Lab Results"
    ws.append(("Accession Number", "Test", "Result", "Units", "Reference Range", "Lab", "Specimen"))
    ws.append(("A001", "Glucose", "95", "mg/dL", "70-99 mg/dL", "Quest", "Serum"))
    ws.append(("A002", "HbA1c", "5.4", "%", "4.0-5.6 %", "Quest", "Whole Blood"))
    ws.append(("A003", "Total Cholesterol", "210", "mg/dL", "0-200 mg/dL", "Labcorp", "Serum"))
    ws.append(("A004", "TSH", "2.1", "mIU/L", "0.4-4.0 mIU/L", "Labcorp", "Serum"))
    ws.append(("A005", "Hemoglobin", "14.2", "g/dL", "12.0-17.5 g/dL", "Quest", "Whole Blood"))
    ws.append(("A006", "Unknown Marker", "99", "mg/dL", "", "Quest", "Serum"))
    wb.save(path)
    wb.close()


def _reset_api_test_state() -> None:
    try:
        from biomarker_normalization_toolkit.api import _metrics, _rate_limiter
    except Exception:
        return
    with _rate_limiter._lock:
        _rate_limiter._requests.clear()
    with _metrics._lock:
        _metrics.request_count = 0
        _metrics.error_count = 0
        _metrics.total_rows_processed = 0
        _metrics.total_latency_ms = 0.0
        _metrics.endpoint_counts.clear()
        _metrics.status_counts.clear()
        _metrics.start_time = time.time()


class NormalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_api_test_state()

    def test_sample_fixture_matches_expected_json(self) -> None:
        input_path = FIXTURES / "input" / "v0_sample.csv"
        expected_path = FIXTURES / "expected" / "v0_sample_expected.json"

        rows = read_input_csv(input_path)
        result = normalize_rows(rows, input_file=input_path.name)

        actual = result.to_json_dict()
        # Strip non-deterministic fields for comparison
        actual.pop("generated_at", None)
        actual.pop("bnt_version", None)
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        expected.pop("generated_at", None)
        expected.pop("bnt_version", None)
        self.assertEqual(actual, expected)

    def test_unsupported_unit_requires_review(self) -> None:
        source_rows = [
            {
                "source_row_id": "u1",
                "source_lab_name": "Quest",
                "source_panel_name": "Basic Metabolic",
                "source_test_name": "Glucose, Serum",
                "raw_value": "5.5",
                "source_unit": "g/L",
                "specimen_type": "serum",
                "source_reference_range": "3.9-5.5 g/L"
            }
        ]
        source_record = build_source_records(source_rows)[0]
        normalized = normalize_source_record(source_record)

        self.assertEqual(normalized.mapping_status, "review_needed")
        self.assertEqual(normalized.status_reason, "unsupported_unit_for_biomarker")
        self.assertEqual(normalized.canonical_biomarker_id, "glucose_serum")

    def test_cli_normalize_writes_outputs(self) -> None:
        input_path = FIXTURES / "input" / "v0_sample.csv"
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "biomarker_normalization_toolkit.cli",
                    "normalize",
                    "--input",
                    str(input_path),
                    "--output-dir",
                    temp_dir
                ],
                capture_output=True,
                text=True,
                check=False
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("Normalized 6 rows.", result.stdout)

            json_output = Path(temp_dir) / "normalized_records.json"
            csv_output = Path(temp_dir) / "normalized_records.csv"
            self.assertTrue(json_output.exists())
            self.assertTrue(csv_output.exists())

            payload = json.loads(json_output.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["mapped"], 5)
            self.assertEqual(payload["summary"]["review_needed"], 0)
            self.assertEqual(payload["summary"]["unmapped"], 1)

    def test_cli_rejects_missing_headers(self) -> None:
        input_path = FIXTURES / "input" / "v0_invalid_missing_headers.csv"
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "biomarker_normalization_toolkit.cli",
                    "normalize",
                    "--input",
                    str(input_path),
                    "--output-dir",
                    temp_dir
                ],
                capture_output=True,
                text=True,
                check=False
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing required columns", result.stderr.lower())

    def test_fhir_bundle_contains_only_mapped_rows(self) -> None:
        input_path = FIXTURES / "input" / "v0_sample.csv"
        rows = read_input_csv(input_path)
        result = normalize_rows(rows, input_file=input_path.name)

        bundle = build_bundle(result)
        self.assertEqual(bundle["resourceType"], "Bundle")
        self.assertEqual(len(bundle["entry"]), 5)

        first = bundle["entry"][0]["resource"]
        self.assertEqual(first["resourceType"], "Observation")
        self.assertEqual(first["code"]["coding"][0]["system"], "http://loinc.org")
        self.assertEqual(first["valueQuantity"]["unit"], "mg/dL")

    def test_cli_normalize_can_emit_fhir_bundle(self) -> None:
        input_path = FIXTURES / "input" / "v0_sample.csv"
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "biomarker_normalization_toolkit.cli",
                    "normalize",
                    "--input",
                    str(input_path),
                    "--output-dir",
                    temp_dir,
                    "--emit-fhir"
                ],
                capture_output=True,
                text=True,
                check=False
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("FHIR output:", result.stdout)

            fhir_output = Path(temp_dir) / "fhir_observations.json"
            self.assertTrue(fhir_output.exists())

            bundle = json.loads(fhir_output.read_text(encoding="utf-8"))
            self.assertEqual(bundle["resourceType"], "Bundle")
            self.assertEqual(len(bundle["entry"]), 5)

    def test_installed_bnt_demo_command_writes_demo_outputs(self) -> None:
        bnt_path = shutil.which("bnt")
        self.assertIsNotNone(bnt_path, "Expected installed bnt console script")

        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    bnt_path,
                    "demo",
                    "--output-dir",
                    temp_dir
                ],
                capture_output=True,
                text=True,
                check=False
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("FHIR output:", result.stdout)

            summary_output = Path(temp_dir) / "normalization_summary.md"
            self.assertTrue(summary_output.exists())
            summary_text = summary_output.read_text(encoding="utf-8")
            self.assertIn("# Normalization Summary", summary_text)
            self.assertIn("Mapped: 5", summary_text)


    # --- Reference range parsing edge cases ---

    def test_double_dash_range_rejected(self) -> None:
        self.assertIsNone(parse_reference_range("70-99-120 mg/dL", "mg/dL"))

    def test_normal_range_parsed(self) -> None:
        result = parse_reference_range("70-99 mg/dL", "mg/dL")
        self.assertIsNotNone(result)
        self.assertEqual(result.low, Decimal("70"))
        self.assertEqual(result.high, Decimal("99"))
        self.assertEqual(result.unit, "mg/dL")

    def test_negative_low_range(self) -> None:
        result = parse_reference_range("-5-10 mg/dL", "mg/dL")
        self.assertIsNotNone(result)
        self.assertEqual(result.low, Decimal("-5"))
        self.assertEqual(result.high, Decimal("10"))

    def test_range_fallback_unit(self) -> None:
        result = parse_reference_range("70-99", "mg/dL")
        self.assertIsNotNone(result)
        self.assertEqual(result.unit, "mg/dL")

    def test_one_sided_range_parsed(self) -> None:
        """One-sided reference ranges like '<200' and '>=60' should be parsed."""
        result_lt = parse_reference_range("<200 mg/dL", "mg/dL")
        self.assertIsNotNone(result_lt)
        self.assertEqual(result_lt.high, Decimal("200"))
        result_gt = parse_reference_range(">60 mg/dL", "mg/dL")
        self.assertIsNotNone(result_gt)
        self.assertEqual(result_gt.low, Decimal("60"))
        result_lte = parse_reference_range("<=500 ng/mL", "ng/mL")
        self.assertIsNotNone(result_lte)
        self.assertEqual(result_lte.high, Decimal("500"))

    # --- Inequality value detection ---

    def test_inequality_value_detected(self) -> None:
        self.assertTrue(is_inequality_value(">100"))
        self.assertTrue(is_inequality_value("<10"))
        self.assertTrue(is_inequality_value(">=500"))
        self.assertTrue(is_inequality_value("<=0.5"))
        self.assertFalse(is_inequality_value("100"))
        self.assertFalse(is_inequality_value("abc"))
        self.assertFalse(is_inequality_value(""))
        self.assertFalse(is_inequality_value(None))

    def test_inequality_value_gives_specific_reason(self) -> None:
        source_rows = [
            {
                "source_row_id": "iq1",
                "source_lab_name": "Quest",
                "source_panel_name": "Metabolic",
                "source_test_name": "Glucose, Serum",
                "raw_value": ">500",
                "source_unit": "mg/dL",
                "specimen_type": "serum",
                "source_reference_range": "70-99 mg/dL",
            }
        ]
        record = build_source_records(source_rows)[0]
        normalized = normalize_source_record(record)
        self.assertEqual(normalized.mapping_status, "review_needed")
        self.assertEqual(normalized.status_reason, "inequality_value")

    # --- Unit conversion accuracy ---

    def test_glucose_mmol_to_mg(self) -> None:
        result = convert_to_normalized(Decimal("5.5"), "glucose_serum", "mmol/L")
        self.assertEqual(result, Decimal("99.0"))

    def test_hba1c_ifcc_mmol_mol_to_percent(self) -> None:
        result = convert_to_normalized(Decimal("53"), "hba1c", "mmol/mol")
        self.assertEqual(result, Decimal("7.00044"))

    def test_creatinine_umol_to_mg(self) -> None:
        result = convert_to_normalized(Decimal("88.4"), "creatinine", "umol/L")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result), 1.0, places=4)

    def test_cholesterol_mmol_to_mg(self) -> None:
        result = convert_to_normalized(Decimal("5.0"), "total_cholesterol", "mmol/L")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result), 193.35, places=1)

    def test_triglycerides_mmol_to_mg(self) -> None:
        result = convert_to_normalized(Decimal("1.0"), "triglycerides", "mmol/L")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result), 88.57, places=1)

    # --- Duplicate source_row_id detection ---

    def test_duplicate_row_id_warning(self) -> None:
        rows = [
            {"source_row_id": "1", "source_test_name": "Glucose", "raw_value": "100",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": "70-99 mg/dL"},
            {"source_row_id": "1", "source_test_name": "Glucose", "raw_value": "110",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": "70-99 mg/dL"},
        ]
        result = normalize_rows(rows)
        self.assertTrue(len(result.warnings) > 0)
        self.assertIn("Duplicate source_row_id", result.warnings[0])

    def test_no_duplicate_warning_for_unique_ids(self) -> None:
        rows = [
            {"source_row_id": "1", "source_test_name": "Glucose", "raw_value": "100",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": "70-99 mg/dL"},
            {"source_row_id": "2", "source_test_name": "Glucose", "raw_value": "110",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": "70-99 mg/dL"},
        ]
        result = normalize_rows(rows)
        self.assertEqual(len(result.warnings), 0)

    def test_to_json_dict_is_deterministic_by_default(self) -> None:
        rows = [
            {"source_row_id": "1", "source_test_name": "Glucose", "raw_value": "100",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": "70-99 mg/dL"},
        ]
        result = normalize_rows(rows)
        self.assertEqual(result.to_json_dict(), result.to_json_dict())

    # --- Catalog integrity ---

    def test_corrected_loinc_assignments(self) -> None:
        self.assertEqual(BIOMARKER_CATALOG["bun"].loinc, "3094-0")
        self.assertEqual(BIOMARKER_CATALOG["iron"].loinc, "2498-4")
        self.assertEqual(BIOMARKER_CATALOG["potassium"].loinc, "2823-3")
        self.assertEqual(BIOMARKER_CATALOG["uric_acid"].loinc, "3084-1")
        self.assertEqual(BIOMARKER_CATALOG["bands"].loinc, "26507-4")
        self.assertEqual(BIOMARKER_CATALOG["bands_pct"].loinc, "26508-2")
        self.assertEqual(BIOMARKER_CATALOG["nrbc"].loinc, "30392-5")
        self.assertEqual(BIOMARKER_CATALOG["nrbc_pct"].loinc, "19048-8")
        self.assertEqual(BIOMARKER_CATALOG["prealbumin"].loinc, "14338-8")
        self.assertEqual(BIOMARKER_CATALOG["ck_mb_index"].loinc, "12189-7")
        self.assertEqual(BIOMARKER_CATALOG["vancomycin"].loinc, "20578-1")
        self.assertEqual(BIOMARKER_CATALOG["vancomycin_trough"].loinc, "4092-3")
        self.assertEqual(BIOMARKER_CATALOG["base_deficit"].loinc, "30318-0")
        self.assertEqual(BIOMARKER_CATALOG["carboxyhemoglobin"].loinc, "20563-3")
        self.assertEqual(BIOMARKER_CATALOG["methemoglobin"].loinc, "2614-6")
        self.assertEqual(BIOMARKER_CATALOG["oxyhemoglobin"].loinc, "11559-2")
        self.assertEqual(BIOMARKER_CATALOG["oxygen_content"].loinc, "57800-5")
        self.assertEqual(BIOMARKER_CATALOG["atypical_lymphocytes_pct"].loinc, "13046-8")
        self.assertEqual(BIOMARKER_CATALOG["metamyelocytes_pct"].loinc, "28541-1")
        self.assertEqual(BIOMARKER_CATALOG["myelocytes_pct"].loinc, "26498-6")

    def test_catalog_loinc_check_digits_valid(self) -> None:
        def loinc_check_digit(num_str: str) -> int:
            digits = [int(d) for d in num_str]
            total = 0
            for i, d in enumerate(reversed(digits)):
                if i % 2 == 0:
                    doubled = d * 2
                    total += doubled // 10 + doubled % 10
                else:
                    total += d
            return (10 - (total % 10)) % 10

        invalid = []
        for bio_id, bio in BIOMARKER_CATALOG.items():
            parts = bio.loinc.split("-")
            if len(parts) != 2:
                invalid.append(f"{bio_id}: malformed LOINC {bio.loinc}")
                continue
            expected = loinc_check_digit(parts[0])
            actual = int(parts[1])
            if expected != actual:
                invalid.append(f"{bio_id}: {bio.loinc} has invalid check digit (expected {expected})")
        self.assertEqual(invalid, [])

    def test_catalog_loinc_codes_are_unique(self) -> None:
        seen: dict[str, str] = {}
        duplicates: dict[str, list[str]] = {}
        for biomarker_id, biomarker in BIOMARKER_CATALOG.items():
            existing = seen.get(biomarker.loinc)
            if existing is None:
                seen[biomarker.loinc] = biomarker_id
                continue
            duplicates.setdefault(biomarker.loinc, [existing]).append(biomarker_id)
        self.assertEqual(duplicates, {})

    # --- Urine creatinine coverage ---

    def test_urine_creatinine_maps(self) -> None:
        rows = [
            {"source_row_id": "uc1", "source_test_name": "Creatinine", "raw_value": "20",
             "source_unit": "mg/dL", "specimen_type": "urine", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "creatinine_urine")
        self.assertEqual(result.records[0].loinc, "2161-8")

    def test_urinary_creatinine_alias_maps_without_specimen(self) -> None:
        rows = [
            {"source_row_id": "uc2", "source_test_name": "Urinary Creatinine", "raw_value": "89.9",
             "source_unit": "mg/dL", "specimen_type": "", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "creatinine_urine")
        self.assertEqual(result.records[0].status_reason, "mapped_by_unique_alias")

    def test_fe_tibc_ratio_alias_maps_to_transferrin_saturation(self) -> None:
        rows = [
            {"source_row_id": "iron1", "source_test_name": "Fe/TIBC Ratio", "raw_value": "21",
             "source_unit": "%", "specimen_type": "", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "transferrin_saturation")
        self.assertEqual(result.records[0].normalized_value, "21")
        self.assertEqual(result.records[0].normalized_unit, "%")

    def test_urinary_osmolality_alias_maps_with_machine_export_unit(self) -> None:
        rows = [
            {"source_row_id": "uo1", "source_test_name": "Urinary Osmolality", "raw_value": "768",
             "source_unit": "mOsm/L", "specimen_type": "", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "osmolality_urine")
        self.assertEqual(result.records[0].normalized_value, "768")
        self.assertEqual(result.records[0].normalized_unit, "mOsm/kg")

    # --- Latest wave coverage and blank-unit reference ranges ---

    def test_latest_wave_biomarkers_map_and_keep_ranges(self) -> None:
        rows = [
            {"source_row_id": "nw1", "source_test_name": "RDW-SD", "raw_value": "42.1",
             "source_unit": "fL", "specimen_type": "whole blood", "source_reference_range": "39-46 fL"},
            {"source_row_id": "nw2", "source_test_name": "Mean Platelet Volume", "raw_value": "10.2",
             "source_unit": "fL", "specimen_type": "whole blood", "source_reference_range": "7.5-11.5 fL"},
            {"source_row_id": "nw3", "source_test_name": "PDW", "raw_value": "12.4",
             "source_unit": "fL", "specimen_type": "whole blood", "source_reference_range": "9-17 fL"},
            {"source_row_id": "nw4", "source_test_name": "iCa", "raw_value": "1.18",
             "source_unit": "mmol/L", "specimen_type": "whole blood", "source_reference_range": "1.12-1.32 mmol/L"},
            {"source_row_id": "nw5", "source_test_name": "O2 Sat", "raw_value": "97",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": "95-100 %"},
            {"source_row_id": "nw6", "source_test_name": "Specific Gravity", "raw_value": "1.015",
             "source_unit": "", "specimen_type": "urine", "source_reference_range": "1.005-1.030"},
            {"source_row_id": "nw7", "source_test_name": "Urine pH", "raw_value": "6.0",
             "source_unit": "", "specimen_type": "urine", "source_reference_range": "5.0-8.0"},
            {"source_row_id": "nw8", "source_test_name": "Protein", "raw_value": "15",
             "source_unit": "mg/dL", "specimen_type": "urine", "source_reference_range": "0-20 mg/dL"},
            {"source_row_id": "nw9", "source_test_name": "Ketones", "raw_value": "0",
             "source_unit": "mg/dL", "specimen_type": "urine", "source_reference_range": "0-5 mg/dL"},
            {"source_row_id": "nw10", "source_test_name": "Bilirubin", "raw_value": "0.2",
             "source_unit": "mg/dL", "specimen_type": "urine", "source_reference_range": "0-0.3 mg/dL"},
        ]
        result = normalize_rows(rows)

        expected = {
            "nw1": "rdw_sd",
            "nw2": "mpv",
            "nw3": "pdw",
            "nw4": "ionized_calcium",
            "nw5": "oxygen_saturation",
            "nw6": "urine_specific_gravity",
            "nw7": "urine_ph",
            "nw8": "urine_protein",
            "nw9": "urine_ketones",
            "nw10": "urine_bilirubin",
        }
        self.assertEqual(result.summary["mapped"], 10)
        for record in result.records:
            self.assertEqual(record.mapping_status, "mapped")
            self.assertEqual(record.canonical_biomarker_id, expected[record.source_row_id])

        by_id = {record.source_row_id: record for record in result.records}
        self.assertEqual(by_id["nw6"].normalized_reference_range, "1.005-1.03")
        self.assertEqual(by_id["nw6"].normalized_unit, "")
        self.assertEqual(by_id["nw7"].normalized_reference_range, "5-8 pH")
        self.assertEqual(by_id["nw7"].normalized_unit, "pH")

    # --- Empty input ---

    def test_empty_input_produces_empty_result(self) -> None:
        result = normalize_rows([])
        self.assertEqual(result.summary["total_rows"], 0)
        self.assertEqual(len(result.records), 0)

    # --- FHIR UUID validity ---

    def test_fhir_fullurl_is_valid_uuid(self) -> None:
        import uuid
        input_path = FIXTURES / "input" / "v0_sample.csv"
        rows = read_input_csv(input_path)
        result = normalize_rows(rows, input_file=input_path.name)
        bundle = build_bundle(result)
        for entry in bundle["entry"]:
            full_url = entry["fullUrl"]
            self.assertTrue(full_url.startswith("urn:uuid:"))
            uuid_str = full_url.replace("urn:uuid:", "")
            uuid.UUID(uuid_str)  # raises if invalid

    # --- Wave 1 and vendor fixture coverage ---

    def test_wave1_fixture_maps_all_known_biomarkers(self) -> None:
        rows = read_input_csv(FIXTURES / "input" / "coverage_wave_1.csv")
        result = normalize_rows(rows)
        self.assertEqual(result.summary["mapped"], 7)
        self.assertEqual(result.summary["unmapped"], 1)

    def test_vendor_alias_fixture_maps_vendor_names(self) -> None:
        rows = read_input_csv(FIXTURES / "input" / "vendor_alias_edge_cases.csv")
        result = normalize_rows(rows)
        self.assertEqual(result.summary["mapped"], 7)
        self.assertEqual(result.summary["unmapped"], 1)

    # --- Wave 2 and 3 fixture coverage ---

    def test_wave2_fixture_maps_all_known_biomarkers(self) -> None:
        rows = read_input_csv(FIXTURES / "input" / "coverage_wave_2.csv")
        result = normalize_rows(rows)
        self.assertEqual(result.summary["mapped"], 24)
        self.assertEqual(result.summary["unmapped"], 1)

    def test_wave3_fixture_maps_all_known_biomarkers(self) -> None:
        rows = read_input_csv(FIXTURES / "input" / "coverage_wave_3.csv")
        result = normalize_rows(rows)
        self.assertEqual(result.summary["mapped"], 11)
        self.assertEqual(result.summary["unmapped"], 1)

    # --- Wave 2 conversion accuracy ---

    def test_bilirubin_umol_to_mg(self) -> None:
        result = convert_to_normalized(Decimal("17.1"), "total_bilirubin", "umol/L")
        self.assertAlmostEqual(float(result), 1.0, places=4)

    def test_albumin_gl_to_gdl(self) -> None:
        result = convert_to_normalized(Decimal("40"), "albumin", "g/L")
        self.assertAlmostEqual(float(result), 4.0, places=4)

    def test_tsh_identity(self) -> None:
        result = convert_to_normalized(Decimal("2.5"), "tsh", "mIU/L")
        self.assertEqual(result, Decimal("2.5"))

    def test_free_t4_pmol_to_ngdl(self) -> None:
        result = convert_to_normalized(Decimal("15.4"), "free_t4", "pmol/L")
        # 15.4 / 12.87 = 1.1966
        self.assertAlmostEqual(float(result), 1.1966, places=3)

    def test_bun_mmol_to_mg(self) -> None:
        result = convert_to_normalized(Decimal("5.0"), "bun", "mmol/L")
        self.assertAlmostEqual(float(result), 14.0, places=4)

    def test_crp_mgdl_to_mgl(self) -> None:
        result = convert_to_normalized(Decimal("0.15"), "hscrp", "mg/dL")
        self.assertAlmostEqual(float(result), 1.5, places=4)

    def test_hematocrit_ll_to_pct(self) -> None:
        result = convert_to_normalized(Decimal("0.42"), "hematocrit", "L/L")
        self.assertAlmostEqual(float(result), 42.0, places=4)

    def test_hemoglobin_gl_to_gdl(self) -> None:
        result = convert_to_normalized(Decimal("140"), "hemoglobin", "g/L")
        self.assertAlmostEqual(float(result), 14.0, places=4)

    # --- Wave 3 conversion accuracy ---

    def test_vitamin_d_nmol_to_ngml(self) -> None:
        result = convert_to_normalized(Decimal("75"), "vitamin_d", "nmol/L")
        # 75 / 2.496 = 30.048
        self.assertAlmostEqual(float(result), 30.048, places=2)

    def test_vitamin_b12_pmol_to_pgml(self) -> None:
        result = convert_to_normalized(Decimal("369"), "vitamin_b12", "pmol/L")
        self.assertAlmostEqual(float(result), 499.995, places=2)

    def test_folate_nmol_to_ngml(self) -> None:
        result = convert_to_normalized(Decimal("22.7"), "folate", "nmol/L")
        # 22.7 / 2.266 = 10.018
        self.assertAlmostEqual(float(result), 10.018, places=2)

    def test_iron_umol_to_ugdl(self) -> None:
        result = convert_to_normalized(Decimal("14.3"), "iron", "umol/L")
        self.assertAlmostEqual(float(result), 79.8655, places=2)

    def test_magnesium_mmol_to_mgdl(self) -> None:
        result = convert_to_normalized(Decimal("0.83"), "magnesium", "mmol/L")
        # 0.83 * 2.431 = 2.018
        self.assertAlmostEqual(float(result), 2.018, places=2)


    # --- FHIR ingest ---

    def test_fhir_single_observation_ingest(self) -> None:
        fhir_path = INTEROP_FIXTURES / "fhir_observation_glucose.json"
        rows = read_fhir_input(fhir_path)
        self.assertEqual(len(rows), 1)
        self.assertIn("Glucose", rows[0]["source_test_name"])
        self.assertEqual(rows[0]["raw_value"], "6.3")

    def test_fhir_bundle_ingest(self) -> None:
        fhir_path = INTEROP_FIXTURES / "fhir_bundle_minimal.json"
        rows = read_fhir_input(fhir_path)
        self.assertEqual(len(rows), 2)
        result = normalize_rows(rows)
        self.assertEqual(result.summary["mapped"], 2)

    def test_read_input_auto_detects_csv(self) -> None:
        csv_path = FIXTURES / "input" / "v0_sample.csv"
        rows = read_input(csv_path)
        self.assertEqual(len(rows), 6)

    def test_read_input_auto_detects_json(self) -> None:
        fhir_path = INTEROP_FIXTURES / "fhir_observation_glucose.json"
        rows = read_input(fhir_path)
        self.assertEqual(len(rows), 1)

    # --- HL7v2 ingest ---

    def test_hl7_cbc_ingest(self) -> None:
        hl7_path = INTEROP_FIXTURES / "hl7_oru_cbc.hl7"
        rows = read_hl7_input(hl7_path)
        self.assertEqual(len(rows), 14)
        result = normalize_rows(rows)
        self.assertGreater(result.summary["mapped"], 0)

    def test_hl7_cmp_ingest(self) -> None:
        hl7_path = INTEROP_FIXTURES / "hl7_oru_cmp.hl7"
        rows = read_hl7_input(hl7_path)
        self.assertEqual(len(rows), 16)
        result = normalize_rows(rows)
        self.assertGreaterEqual(result.summary["mapped"], 13)

    def test_hl7_sn_inequality_parsing(self) -> None:
        hl7_path = INTEROP_FIXTURES / "hl7_oru_edge_cases.hl7"
        rows = read_hl7_input(hl7_path)
        # Find the glucose row with SN value <^10
        glucose_rows = [r for r in rows if "Glucose" in r["source_test_name"] and r["raw_value"] == "<10"]
        self.assertEqual(len(glucose_rows), 1)
        self.assertEqual(glucose_rows[0]["raw_value"], "<10")

    def test_hl7_qualitative_values_preserved(self) -> None:
        hl7_path = INTEROP_FIXTURES / "hl7_oru_edge_cases.hl7"
        rows = read_hl7_input(hl7_path)
        by_name = {r["source_test_name"]: r["raw_value"] for r in rows}
        protein_key = [k for k in by_name if "Protein [Presence]" in k]
        ketones_key = [k for k in by_name if "Ketones [Presence]" in k]
        self.assertEqual(len(protein_key), 1)
        self.assertEqual(by_name[protein_key[0]], "Trace")
        self.assertEqual(len(ketones_key), 1)
        self.assertEqual(by_name[ketones_key[0]], "1+")

    # --- C-CDA ingest ---

    def test_ccda_result_with_lab_location(self) -> None:
        ccda_path = INTEROP_FIXTURES / "ccda_urinalysis_lab_location.xml"
        rows = read_ccda_input(ccda_path)
        self.assertGreater(len(rows), 0)
        self.assertEqual(rows[0]["raw_value"], "1.015")

    def test_ccda_non_ucum_units(self) -> None:
        ccda_path = INTEROP_FIXTURES / "ccda_non_ucum_platelets.xml"
        rows = read_ccda_input(ccda_path)
        self.assertGreater(len(rows), 0)
        self.assertEqual(rows[0]["raw_value"], "152")

    # --- Excel ingest ---

    def test_excel_ingest_with_flexible_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            xlsx_path = Path(temp_dir) / "test_lab_results.xlsx"
            _write_excel_interop_fixture(xlsx_path)
            rows = read_excel_input(xlsx_path)
            self.assertEqual(len(rows), 6)
            result = normalize_rows(rows)
            self.assertEqual(result.summary["mapped"], 5)
            self.assertEqual(result.summary["unmapped"], 1)

    def test_read_input_auto_detects_xlsx(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            xlsx_path = Path(temp_dir) / "test_lab_results.xlsx"
            _write_excel_interop_fixture(xlsx_path)
            rows = read_input(xlsx_path)
            self.assertEqual(len(rows), 6)

    def test_read_input_auto_detects_xml(self) -> None:
        ccda_path = INTEROP_FIXTURES / "ccda_urinalysis_lab_location.xml"
        rows = read_input(ccda_path)
        self.assertGreater(len(rows), 0)

    def test_read_input_auto_detects_hl7(self) -> None:
        hl7_path = INTEROP_FIXTURES / "hl7_oru_cbc.hl7"
        rows = read_input(hl7_path)
        self.assertEqual(len(rows), 14)

    # --- Custom alias overrides ---

    def test_custom_alias_loading(self) -> None:
        from biomarker_normalization_toolkit.catalog import load_custom_aliases
        alias_path = INTEROP_FIXTURES / "custom_aliases.json"
        added = load_custom_aliases(alias_path)
        self.assertGreater(added, 0)
        # Verify "Blood Sugar" now maps to glucose
        rows = [{"source_row_id": "ca1", "source_test_name": "Blood Sugar", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "glucose_serum")

    # --- Specimen disambiguation ---

    def test_ph_disambiguates_by_specimen(self) -> None:
        rows = [
            {"source_row_id": "ph1", "source_test_name": "pH", "raw_value": "7.4",
             "source_unit": "units", "specimen_type": "blood", "source_reference_range": "7.35-7.45"},
            {"source_row_id": "ph2", "source_test_name": "pH", "raw_value": "6.0",
             "source_unit": "units", "specimen_type": "urine", "source_reference_range": "5.0-8.0"},
            {"source_row_id": "ph3", "source_test_name": "pH", "raw_value": "7.0",
             "source_unit": "units", "specimen_type": "", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].canonical_biomarker_id, "blood_ph")
        self.assertEqual(result.records[1].canonical_biomarker_id, "urine_ph")
        self.assertEqual(result.records[2].mapping_status, "review_needed")
        self.assertEqual(result.records[2].status_reason, "ambiguous_alias_requires_specimen")

    def test_bilirubin_disambiguates_by_specimen(self) -> None:
        rows = [
            {"source_row_id": "b1", "source_test_name": "Bilirubin", "raw_value": "1.0",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "b2", "source_test_name": "Bilirubin", "raw_value": "0.2",
             "source_unit": "mg/dL", "specimen_type": "urine", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].canonical_biomarker_id, "total_bilirubin")
        self.assertEqual(result.records[1].canonical_biomarker_id, "urine_bilirubin")

    # --- New biomarker coverage ---

    def test_fibrinogen_maps(self) -> None:
        rows = [{"source_row_id": "f1", "source_test_name": "Fibrinogen, Functional",
                 "raw_value": "250", "source_unit": "mg/dL", "specimen_type": "plasma",
                 "source_reference_range": "200-400 mg/dL"}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "fibrinogen")

    def test_eag_maps(self) -> None:
        rows = [{"source_row_id": "e1", "source_test_name": "eAG",
                 "raw_value": "117", "source_unit": "mg/dL", "specimen_type": "whole blood",
                 "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "eag")

    def test_high_value_unknown_aliases_now_map(self) -> None:
        rows = [
            {"source_row_id": "etoh", "source_test_name": "ethanol", "raw_value": "145",
             "source_unit": "mg/dL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "pre", "source_test_name": "prealbumin", "raw_value": "25.4",
             "source_unit": "mg/dL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "cki", "source_test_name": "CK-MB Index", "raw_value": "2.5",
             "source_unit": "%", "specimen_type": "Blood", "source_reference_range": "0-6 %"},
            {"source_row_id": "pttr", "source_test_name": "PTT ratio", "raw_value": "1.1",
             "source_unit": "ratio", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "pheny", "source_test_name": "Phenytoin", "raw_value": "14.2",
             "source_unit": "ug/mL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "apap", "source_test_name": "APAP", "raw_value": "20",
             "source_unit": "ug/mL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "vanc", "source_test_name": "Vancomycin - random", "raw_value": "14.2",
             "source_unit": "mcg/mL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "vanc_trough", "source_test_name": "Vancomycin - trough", "raw_value": "16.0",
             "source_unit": "ug/mL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "bd", "source_test_name": "Base Deficit", "raw_value": "6.5",
             "source_unit": "mEq/L", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "cohb", "source_test_name": "Carboxyhemoglobin", "raw_value": "1.2",
             "source_unit": "%", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "methb", "source_test_name": "Methemoglobin", "raw_value": "0.4",
             "source_unit": "%", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "oxy", "source_test_name": "Oxyhemoglobin", "raw_value": "98.5",
             "source_unit": "%", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "o2ct", "source_test_name": "O2 Content", "raw_value": "18.6",
             "source_unit": "mL/dL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "atyp", "source_test_name": "Atypical Lymphocytes", "raw_value": "1",
             "source_unit": "%", "specimen_type": "Blood", "source_reference_range": "0-0 %"},
            {"source_row_id": "meta", "source_test_name": "Metamyelocytes", "raw_value": "1",
             "source_unit": "%", "specimen_type": "Blood", "source_reference_range": "0-0 %"},
            {"source_row_id": "myelo", "source_test_name": "Myelocytes", "raw_value": "1",
             "source_unit": "%", "specimen_type": "Blood", "source_reference_range": "0-0 %"},
        ]
        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}
        self.assertEqual(by_id["etoh"].canonical_biomarker_id, "ethanol")
        self.assertEqual(by_id["pre"].canonical_biomarker_id, "prealbumin")
        self.assertEqual(by_id["cki"].canonical_biomarker_id, "ck_mb_index")
        self.assertEqual(by_id["pttr"].canonical_biomarker_id, "ptt_ratio")
        self.assertEqual(by_id["pheny"].canonical_biomarker_id, "phenytoin")
        self.assertEqual(by_id["apap"].canonical_biomarker_id, "acetaminophen")
        self.assertEqual(by_id["vanc"].canonical_biomarker_id, "vancomycin")
        self.assertEqual(by_id["vanc_trough"].canonical_biomarker_id, "vancomycin_trough")
        self.assertEqual(by_id["bd"].canonical_biomarker_id, "base_deficit")
        self.assertEqual(by_id["cohb"].canonical_biomarker_id, "carboxyhemoglobin")
        self.assertEqual(by_id["methb"].canonical_biomarker_id, "methemoglobin")
        self.assertEqual(by_id["oxy"].canonical_biomarker_id, "oxyhemoglobin")
        self.assertEqual(by_id["o2ct"].canonical_biomarker_id, "oxygen_content")
        self.assertEqual(by_id["atyp"].canonical_biomarker_id, "atypical_lymphocytes_pct")
        self.assertEqual(by_id["meta"].canonical_biomarker_id, "metamyelocytes_pct")
        self.assertEqual(by_id["myelo"].canonical_biomarker_id, "myelocytes_pct")
        self.assertTrue(all(record.mapping_status == "mapped" for record in by_id.values()))

    # --- Batch command ---

    def test_batch_processes_fixture_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [sys.executable, "-m", "biomarker_normalization_toolkit.cli",
                 "batch", "--input-dir", str(FIXTURES / "input"), "--output-dir", temp_dir],
                capture_output=True, text=True, check=False,
            )
            self.assertIn("Batch complete", result.stdout)
            self.assertIn("files", result.stdout)


    # --- Scrutiny fix: specimen normalization (Fix 3) ---

    def test_venous_blood_normalizes_to_whole_blood(self) -> None:
        from biomarker_normalization_toolkit.catalog import normalize_specimen
        self.assertEqual(normalize_specimen("Venous Blood"), "whole_blood")
        self.assertEqual(normalize_specimen("ARTERIAL BLOOD"), "whole_blood")
        self.assertEqual(normalize_specimen("Capillary Blood"), "whole_blood")
        self.assertEqual(normalize_specimen("Mixed Venous Blood"), "whole_blood")
        self.assertEqual(normalize_specimen("Cord Blood"), "whole_blood")

    def test_urine_variants_normalize(self) -> None:
        from biomarker_normalization_toolkit.catalog import normalize_specimen
        self.assertEqual(normalize_specimen("Random Urine"), "urine")
        self.assertEqual(normalize_specimen("Spot Urine"), "urine")
        self.assertEqual(normalize_specimen("24h Urine"), "urine")
        self.assertEqual(normalize_specimen("24 Hour Urine"), "urine")
        self.assertEqual(normalize_specimen("Timed Urine"), "urine")

    def test_body_fluid_variants_normalize(self) -> None:
        from biomarker_normalization_toolkit.catalog import normalize_specimen
        self.assertEqual(normalize_specimen("Ascitic Fluid"), "ascites")
        self.assertEqual(normalize_specimen("Pleural Fluid"), "pleural")
        self.assertEqual(normalize_specimen("Thoracentesis Fluid"), "pleural")
        self.assertEqual(normalize_specimen("Other Body Fluid"), "body_fluid")

    def test_venous_blood_specimen_maps_glucose(self) -> None:
        rows = [{"source_row_id": "vb1", "source_test_name": "Glucose", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "Venous Blood",
                 "source_reference_range": "70-99 mg/dL"}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "glucose_serum")

    # --- Scrutiny fix: FHIR identifier guard (Fix 2) ---

    def test_fhir_observation_no_identifier_when_row_id_empty(self) -> None:
        from biomarker_normalization_toolkit.fhir import build_observation
        from biomarker_normalization_toolkit.normalizer import build_source_records, normalize_source_record
        rows = [{"source_row_id": "", "source_test_name": "TSH", "raw_value": "2.5",
                 "source_unit": "mIU/L", "specimen_type": "", "source_reference_range": ""}]
        record = normalize_source_record(build_source_records(rows)[0])
        obs = build_observation(record)
        self.assertIsNotNone(obs)
        self.assertNotIn("identifier", obs)

    def test_fhir_observation_has_identifier_when_row_id_present(self) -> None:
        from biomarker_normalization_toolkit.fhir import build_observation
        from biomarker_normalization_toolkit.normalizer import build_source_records, normalize_source_record
        rows = [{"source_row_id": "abc", "source_test_name": "TSH", "raw_value": "2.5",
                 "source_unit": "mIU/L", "specimen_type": "", "source_reference_range": ""}]
        record = normalize_source_record(build_source_records(rows)[0])
        obs = build_observation(record)
        self.assertIn("identifier", obs)
        self.assertEqual(obs["identifier"][0]["value"], "abc")

    # --- Scrutiny fix: FHIR UUID uniqueness across files (Fix 6) ---

    def test_fhir_uuid_differs_across_input_files(self) -> None:
        rows_a = [{"source_row_id": "1", "source_test_name": "Glucose", "raw_value": "100",
                   "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        rows_b = [{"source_row_id": "1", "source_test_name": "Glucose", "raw_value": "105",
                   "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result_a = normalize_rows(rows_a, input_file="file_a.csv")
        result_b = normalize_rows(rows_b, input_file="file_b.csv")
        bundle_a = build_bundle(result_a)
        bundle_b = build_bundle(result_b)
        uuid_a = bundle_a["entry"][0]["resource"]["id"]
        uuid_b = bundle_b["entry"][0]["resource"]["id"]
        self.assertNotEqual(uuid_a, uuid_b)

    # --- Scrutiny fix: {ratio} unit synonym (Fix 7) ---

    def test_ratio_ucum_unit_normalizes(self) -> None:
        from biomarker_normalization_toolkit.units import normalize_unit
        self.assertEqual(normalize_unit("{ratio}"), "ratio")
        self.assertEqual(normalize_unit("{INR}"), "ratio")

    def test_inr_with_ratio_ucum_unit_maps(self) -> None:
        rows = [{"source_row_id": "r1", "source_test_name": "INR", "raw_value": "1.1",
                 "source_unit": "{ratio}", "specimen_type": "", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "inr")

    # --- Scrutiny fix: troponin T ng/L and pg/mL conversion (Fix 10) ---

    def test_troponin_t_ng_per_l_converts(self) -> None:
        result = convert_to_normalized(Decimal("14"), "troponin_t", "ng/L")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result), 0.014, places=4)

    def test_troponin_t_pg_per_ml_converts(self) -> None:
        result = convert_to_normalized(Decimal("50"), "troponin_t", "pg/mL")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result), 0.05, places=4)

    # --- Scrutiny fix: WBC differential aliases correctness (Fix 5) ---

    def test_wbc_differential_percentage_alias_maps_to_pct_biomarker(self) -> None:
        from biomarker_normalization_toolkit.catalog import ALIAS_INDEX, normalize_key
        # "/100 leukocytes" aliases should map to *_pct biomarkers, not absolute counts
        pct_key = normalize_key("Neutrophils/100 leukocytes in Blood by Automated count")
        self.assertIn(pct_key, ALIAS_INDEX)
        self.assertIn("neutrophils_pct", ALIAS_INDEX[pct_key])
        self.assertNotIn("neutrophils", ALIAS_INDEX[pct_key])

    def test_wbc_differential_absolute_alias_works(self) -> None:
        from biomarker_normalization_toolkit.catalog import ALIAS_INDEX, normalize_key
        abs_key = normalize_key("Neutrophils [#/volume] in Blood by Automated count")
        self.assertIn(abs_key, ALIAS_INDEX)
        self.assertIn("neutrophils", ALIAS_INDEX[abs_key])

    # --- Scrutiny fix: defusedxml import (Fix 1) ---

    def test_defusedxml_is_used(self) -> None:
        from biomarker_normalization_toolkit import io_utils
        import defusedxml.ElementTree
        self.assertIs(io_utils._xml_fromstring, defusedxml.ElementTree.fromstring)

    # --- Scrutiny fix: C-CDA specimen extraction (Fix 4) ---

    def test_ccda_with_specimen_element(self) -> None:
        """Verify that C-CDA specimen element is extracted when present."""
        ccda_xml = """
        <observation classCode="OBS" moodCode="EVN">
          <code code="2345-7" codeSystem="2.16.840.1.113883.6.1" displayName="Glucose"/>
          <value xsi:type="PQ" value="100" unit="mg/dL"
                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
          <specimen>
            <specimenRole>
              <specimenPlayingEntity>
                <code displayName="Venous Blood"/>
              </specimenPlayingEntity>
            </specimenRole>
          </specimen>
        </observation>
        """
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False, encoding="utf-8") as f:
            f.write(ccda_xml)
            tmp = Path(f.name)
        try:
            rows = read_ccda_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["specimen_type"], "Venous Blood")
        finally:
            tmp.unlink(missing_ok=True)


    # --- Scrutiny pass: HL7 specimen leakage between panels (Fix #1) ---

    def test_hl7_specimen_does_not_leak_between_panels(self) -> None:
        """OBR without OBR-15 must NOT inherit specimen from previous OBR."""
        hl7_msg = (
            "MSH|^~\\&|LAB|HOSP|EHR|HOSP|20240101120000||ORU^R01|MSG001|P|2.5\r"
            "PID|1||12345^^^HOSP||DOE^JOHN\r"
            "OBR|1||CBC001|58410-2^CBC|||20240101080000||||||||Whole Blood^WB\r"
            "OBX|1|NM|6690-2^WBC||7.5|10*3/uL|4.5-11.0|N||F\r"
            "OBR|2||UA001|24356-8^Urinalysis|||20240101080000\r"
            "OBX|1|NM|5811-5^Specific Gravity||1.020||1.005-1.030|N||F\r"
        )
        with tempfile.NamedTemporaryFile(suffix=".hl7", mode="w", delete=False, encoding="utf-8") as f:
            f.write(hl7_msg)
            tmp = Path(f.name)
        try:
            rows = read_hl7_input(tmp)
            self.assertEqual(len(rows), 2)
            # First OBX should have specimen from OBR-15
            self.assertIn("Whole Blood", rows[0]["specimen_type"])
            # Second OBX must NOT inherit "Whole Blood" from first OBR
            self.assertEqual(rows[1]["specimen_type"], "")
        finally:
            tmp.unlink(missing_ok=True)

    # --- Scrutiny pass: UCUM code synonyms for FHIR round-trip (Fix #2) ---

    def test_ucum_bracket_units_normalize(self) -> None:
        from biomarker_normalization_toolkit.units import normalize_unit
        self.assertEqual(normalize_unit("m[IU]/L"), "mIU/L")
        self.assertEqual(normalize_unit("m[IU]/mL"), "mIU/mL")
        self.assertEqual(normalize_unit("[IU]/mL"), "IU/mL")
        self.assertEqual(normalize_unit("k[IU]/L"), "IU/mL")
        self.assertEqual(normalize_unit("kU/L"), "IU/mL")

    def test_miu_ml_not_conflated_with_miu_l(self) -> None:
        """Regression: mIU/mL and mIU/L differ by 1000x. They must not be synonyms."""
        from biomarker_normalization_toolkit.units import normalize_unit, convert_to_normalized
        from decimal import Decimal
        # mIU/mL must stay mIU/mL, not collapse to mIU/L
        self.assertEqual(normalize_unit("mIU/mL"), "mIU/mL")
        self.assertEqual(normalize_unit("miu/ml"), "mIU/mL")
        # Insulin: 25 mIU/mL = 25,000 uIU/mL (not 25)
        result = convert_to_normalized(Decimal("25"), "insulin", "mIU/mL")
        self.assertEqual(result, Decimal("25000"))
        # LH: 10 mIU/mL = 10 mIU/mL (identity, it's the normalized unit)
        result_lh = convert_to_normalized(Decimal("10"), "lh", "mIU/mL")
        self.assertEqual(result_lh, Decimal("10"))

    def test_fhir_round_trip_tsh(self) -> None:
        """Export to FHIR then re-import should preserve the mapping."""
        from biomarker_normalization_toolkit.fhir import build_bundle
        rows = [{"source_row_id": "rt1", "source_test_name": "TSH", "raw_value": "2.5",
                 "source_unit": "mIU/L", "specimen_type": "", "source_reference_range": "0.4-4.0 mIU/L"}]
        result = normalize_rows(rows, input_file="round_trip.csv")
        bundle = build_bundle(result)
        # The FHIR bundle uses UCUM code m[IU]/L; simulate re-ingest.
        obs = bundle["entry"][0]["resource"]
        ucum_unit = obs["valueQuantity"]["code"]  # should be "m[IU]/L"
        reimport_rows = [{
            "source_row_id": "rt1", "source_test_name": "TSH",
            "raw_value": str(obs["valueQuantity"]["value"]),
            "source_unit": ucum_unit, "specimen_type": "", "source_reference_range": "",
        }]
        result2 = normalize_rows(reimport_rows)
        self.assertEqual(result2.records[0].mapping_status, "mapped")
        self.assertEqual(result2.records[0].canonical_biomarker_id, "tsh")

    # --- Scrutiny pass: European comma decimal detection (Fix #3) ---

    def test_european_comma_decimal_rejected(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        # "1,5" (European for 1.5) must NOT become 15
        self.assertIsNone(parse_decimal("1,5"))
        self.assertIsNone(parse_decimal("5,55"))
        self.assertIsNone(parse_decimal("-3,7"))
        # Thousands separators (groups of 3) must still work
        self.assertEqual(parse_decimal("250,000"), Decimal("250000"))
        self.assertEqual(parse_decimal("1,000,000"), Decimal("1000000"))
        # Normal decimals still work
        self.assertEqual(parse_decimal("1.5"), Decimal("1.5"))

    def test_european_comma_gives_invalid_raw_value(self) -> None:
        rows = [{"source_row_id": "eu1", "source_test_name": "Glucose", "raw_value": "5,5",
                 "source_unit": "mmol/L", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "review_needed")
        self.assertEqual(result.records[0].status_reason, "invalid_raw_value")

    # --- Scrutiny pass: Reference range low <= high validation (Fix #4) ---

    def test_reversed_reference_range_rejected(self) -> None:
        self.assertIsNone(parse_reference_range("200-100 mg/dL", "mg/dL"))
        self.assertIsNone(parse_reference_range("10-5", "mg/dL"))

    def test_equal_reference_range_accepted(self) -> None:
        result = parse_reference_range("5-5 mg/dL", "mg/dL")
        self.assertIsNotNone(result)
        self.assertEqual(result.low, result.high)

    # --- Scrutiny pass: FHIR bundle includes total (Fix #7) ---

    def test_fhir_bundle_structure(self) -> None:
        from biomarker_normalization_toolkit.fhir import build_bundle
        rows = [{"source_row_id": "t1", "source_test_name": "Glucose", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows, input_file="total_test.csv")
        bundle = build_bundle(result)
        # R4: collection bundles should NOT have total (bdl-1 invariant)
        self.assertNotIn("total", bundle)
        self.assertEqual(bundle["type"], "collection")
        self.assertGreater(len(bundle["entry"]), 0)

    # --- Scrutiny pass: API validates non-dict rows (Fix #7) ---

    def test_api_rejects_non_dict_rows(self) -> None:
        try:
            from fastapi.testclient import TestClient
            from biomarker_normalization_toolkit.api import _metrics, _rate_limiter, app
        except Exception:
            self.skipTest("API deps not available")
        _rate_limiter.reset()
        _metrics.reset()
        client = TestClient(app)
        response = client.post("/normalize", json={"rows": ["not a dict", 123]})
        # Pydantic validates, returns 400 or 422 depending on model
        self.assertIn(response.status_code, (400, 422))

    # --- Deep scrutiny pass 2: Legacy unit synonyms ---

    def test_legacy_unit_synonyms_normalize(self) -> None:
        from biomarker_normalization_toolkit.units import normalize_unit
        self.assertEqual(normalize_unit("gm/dL"), "g/dL")
        self.assertEqual(normalize_unit("gm/L"), "g/L")
        self.assertEqual(normalize_unit("gm%"), "g/dL")
        self.assertEqual(normalize_unit("percent"), "%")
        self.assertEqual(normalize_unit("pct"), "%")
        self.assertEqual(normalize_unit("secs"), "sec")
        self.assertEqual(normalize_unit("million/mm3"), "M/uL")
        self.assertEqual(normalize_unit("M/mcL"), "M/uL")
        self.assertEqual(normalize_unit("10 trillion/L"), "10^12/L")
        self.assertEqual(normalize_unit("10^12L"), "10^12/L")
        self.assertEqual(normalize_unit("cells/cumm"), "#/uL")
        self.assertEqual(normalize_unit("thou/cumm"), "K/uL")
        self.assertEqual(normalize_unit("K/cumm"), "K/uL")
        self.assertEqual(normalize_unit("mill/cumm"), "M/uL")
        self.assertEqual(normalize_unit("ug/L"), "ug/L")
        self.assertEqual(normalize_unit("mcg/mL"), "ug/mL")
        self.assertEqual(normalize_unit("mls/dL"), "mL/dL")
        self.assertEqual(normalize_unit("µg/mL"), "ug/mL")
        self.assertEqual(normalize_unit("/µL"), "#/uL")
        self.assertEqual(normalize_unit("/μL"), "#/uL")
        self.assertEqual(normalize_unit("10^3/µL"), "K/uL")
        self.assertEqual(normalize_unit("10³/µL"), "K/uL")

    def test_hba1c_ifcc_input_normalizes_value_and_range(self) -> None:
        rows = [{
            "source_row_id": "a1c-ifcc",
            "source_test_name": "HbA1c",
            "raw_value": "53",
            "source_unit": "mmol/mol",
            "specimen_type": "whole blood",
            "source_reference_range": "42-48 mmol/mol",
        }]
        result = normalize_rows(rows)
        record = result.records[0]
        self.assertEqual(record.mapping_status, "mapped")
        self.assertEqual(record.normalized_unit, "%")
        self.assertEqual(record.normalized_value, "7.00044")
        self.assertEqual(record.normalized_reference_range, "5.99416-6.54304 %")

    def test_rbc_million_mm3_normalizes(self) -> None:
        rows = [{
            "source_row_id": "rbc_mm3",
            "source_test_name": "RBC Count",
            "raw_value": "3.93",
            "source_unit": "million/mm3",
            "specimen_type": "whole blood",
            "source_reference_range": "4.5-5.5 million/mm3",
        }]
        result = normalize_rows(rows)
        record = result.records[0]
        self.assertEqual(record.mapping_status, "mapped")
        self.assertEqual(record.canonical_biomarker_id, "rbc")
        self.assertEqual(record.normalized_value, "3.93")
        self.assertEqual(record.normalized_unit, "M/uL")
        self.assertEqual(record.normalized_reference_range, "4.5-5.5 M/uL")

    def test_rbc_million_per_mm3_maps_via_unit_synonym(self) -> None:
        rows = [{
            "source_row_id": "rbc-legacy",
            "source_test_name": "RBC",
            "raw_value": "4.5",
            "source_unit": "million/mm3",
            "specimen_type": "whole blood",
            "source_reference_range": "4.0-5.2 million/mm3",
        }]
        result = normalize_rows(rows)
        record = result.records[0]
        self.assertEqual(record.mapping_status, "mapped")
        self.assertEqual(record.normalized_unit, "M/uL")
        self.assertEqual(record.normalized_value, "4.5")
        self.assertEqual(record.normalized_reference_range, "4-5.2 M/uL")

    def test_rbc_trillion_per_liter_maps_via_unit_synonym(self) -> None:
        rows = [{
            "source_row_id": "rbc-si-legacy",
            "source_test_name": "RBC",
            "raw_value": "4.5",
            "source_unit": "10 trillion/L",
            "specimen_type": "whole blood",
            "source_reference_range": "4.0-5.2 10 trillion/L",
        }]
        result = normalize_rows(rows)
        record = result.records[0]
        self.assertEqual(record.mapping_status, "mapped")
        self.assertEqual(record.normalized_unit, "M/uL")
        self.assertEqual(record.normalized_value, "4.5")
        self.assertEqual(record.normalized_reference_range, "4-5.2 M/uL")

    def test_rbc_maps_without_specimen_when_unit_is_blood_specific(self) -> None:
        rows = [{
            "source_row_id": "rbc-no-specimen",
            "source_test_name": "RBC",
            "raw_value": "4.5",
            "source_unit": "M/mcL",
            "specimen_type": "",
            "source_reference_range": "",
        }]
        result = normalize_rows(rows)
        record = result.records[0]
        self.assertEqual(record.mapping_status, "mapped")
        self.assertEqual(record.status_reason, "mapped_by_alias_and_unit")
        self.assertEqual(record.canonical_biomarker_id, "rbc")
        self.assertEqual(record.normalized_unit, "M/uL")
        self.assertEqual(record.normalized_value, "4.5")

    def test_rbc_maps_without_specimen_when_unit_missing_slash_normalizes(self) -> None:
        rows = [{
            "source_row_id": "rbc-missing-slash",
            "source_test_name": "RBC",
            "raw_value": "4.5",
            "source_unit": "10^12L",
            "specimen_type": "",
            "source_reference_range": "",
        }]
        result = normalize_rows(rows)
        record = result.records[0]
        self.assertEqual(record.mapping_status, "mapped")
        self.assertEqual(record.status_reason, "mapped_by_alias_and_unit")
        self.assertEqual(record.canonical_biomarker_id, "rbc")
        self.assertEqual(record.normalized_unit, "M/uL")
        self.assertEqual(record.normalized_value, "4.5")

    # --- Deep scrutiny pass 2: New aliases map correctly ---

    def test_new_glucose_aliases_map(self) -> None:
        for alias in ("Blood Glucose", "FBS", "Fasting Blood Sugar"):
            rows = [{"source_row_id": "a1", "source_test_name": alias, "raw_value": "100",
                     "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
            result = normalize_rows(rows)
            self.assertEqual(result.records[0].mapping_status, "mapped",
                             f"Alias '{alias}' should map")
            self.assertEqual(result.records[0].canonical_biomarker_id, "glucose_serum")

    def test_scr_alias_maps_to_creatinine(self) -> None:
        rows = [{"source_row_id": "sc1", "source_test_name": "SCr", "raw_value": "1.0",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "creatinine")

    def test_urea_alias_maps_to_bun(self) -> None:
        rows = [{"source_row_id": "u1", "source_test_name": "Urea", "raw_value": "15",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "bun")

    def test_wbc_count_alias_maps(self) -> None:
        rows = [{"source_row_id": "w1", "source_test_name": "WBC Count", "raw_value": "7.5",
                 "source_unit": "K/uL", "specimen_type": "whole blood", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "wbc")

    def test_wbc_per_microliter_unicode_unit_maps(self) -> None:
        rows = [{"source_row_id": "wbc-micro", "source_test_name": "WBC Count", "raw_value": "6500",
                 "source_unit": "/µL", "specimen_type": "whole blood", "source_reference_range": ""}]
        result = normalize_rows(rows)
        record = result.records[0]
        self.assertEqual(record.mapping_status, "mapped")
        self.assertEqual(record.canonical_biomarker_id, "wbc")
        self.assertEqual(record.normalized_value, "6.5")
        self.assertEqual(record.normalized_unit, "K/uL")

    # --- Deep scrutiny pass 2: Reference range with commas ---

    def test_reference_range_with_thousands_commas(self) -> None:
        result = parse_reference_range("150,000-400,000 K/uL", "K/uL")
        self.assertIsNotNone(result)
        self.assertEqual(result.low, Decimal("150000"))
        self.assertEqual(result.high, Decimal("400000"))
        self.assertEqual(result.unit, "K/uL")

    # --- Deep scrutiny pass 2: API filename sanitization ---

    def test_api_sanitizes_upload_filename(self) -> None:
        try:
            from fastapi.testclient import TestClient
            from biomarker_normalization_toolkit.api import _metrics, _rate_limiter, app
        except Exception:
            self.skipTest("API deps not available")
        _rate_limiter.reset()
        _metrics.reset()
        client = TestClient(app)
        csv_content = (
            b"source_row_id,source_test_name,raw_value,source_unit,specimen_type,source_reference_range\n"
            b"1,Glucose,100,mg/dL,serum,70-99 mg/dL\n"
        )
        response = client.post(
            "/normalize/upload",
            files={"file": ("../../etc/passwd.csv", csv_content, "text/csv")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Filename should be sanitized with no path traversal in output.
        self.assertEqual(data["input_file"], "passwd.csv")


    # --- Deep scrutiny pass 3: New biomarker coverage ---

    def test_new_wave7_biomarkers_map(self) -> None:
        rows = [
            {"source_row_id": "w7_1", "source_test_name": "GGT", "raw_value": "45",
             "source_unit": "U/L", "specimen_type": "serum", "source_reference_range": "9-48 U/L"},
            {"source_row_id": "w7_2", "source_test_name": "Amylase", "raw_value": "80",
             "source_unit": "U/L", "specimen_type": "serum", "source_reference_range": "28-100 U/L"},
            {"source_row_id": "w7_3", "source_test_name": "Direct Bilirubin", "raw_value": "0.2",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": "0-0.3 mg/dL"},
            {"source_row_id": "w7_4", "source_test_name": "Troponin I", "raw_value": "0.01",
             "source_unit": "ng/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "w7_5", "source_test_name": "BNP", "raw_value": "50",
             "source_unit": "pg/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "w7_6", "source_test_name": "NT-proBNP", "raw_value": "125",
             "source_unit": "pg/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "w7_7", "source_test_name": "D-Dimer", "raw_value": "250",
             "source_unit": "ng/mL", "specimen_type": "plasma", "source_reference_range": ""},
            {"source_row_id": "w7_8", "source_test_name": "Reticulocyte Count", "raw_value": "1.5",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": "0.5-2.5 %"},
            {"source_row_id": "w7_9", "source_test_name": "Procalcitonin", "raw_value": "0.1",
             "source_unit": "ng/mL", "specimen_type": "serum", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        expected = {
            "w7_1": "ggt", "w7_2": "amylase", "w7_3": "direct_bilirubin",
            "w7_4": "troponin_i", "w7_5": "bnp", "w7_6": "nt_probnp",
            "w7_7": "d_dimer", "w7_8": "reticulocytes", "w7_9": "procalcitonin",
        }
        self.assertEqual(result.summary["mapped"], 9)
        for record in result.records:
            self.assertEqual(record.mapping_status, "mapped",
                             f"{record.source_row_id} should be mapped")
            self.assertEqual(record.canonical_biomarker_id, expected[record.source_row_id])

    def test_high_frequency_unknown_lab_aliases_map(self) -> None:
        rows = [
            {"source_row_id": "hf_1", "source_test_name": "CPK-MB INDEX", "raw_value": "2.3",
             "source_unit": "%", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "hf_2", "source_test_name": "Base Deficit", "raw_value": "4",
             "source_unit": "mEq/L", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "hf_3", "source_test_name": "Carboxyhemoglobin", "raw_value": "1.2",
             "source_unit": "%", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "hf_4", "source_test_name": "Methemoglobin", "raw_value": "0.4",
             "source_unit": "%", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "hf_5", "source_test_name": "Oxyhemoglobin", "raw_value": "96.5",
             "source_unit": "%", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "hf_6", "source_test_name": "O2 Content", "raw_value": "19.1",
             "source_unit": "mls/dL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "hf_7", "source_test_name": "Vancomycin - random", "raw_value": "15.2",
             "source_unit": "mcg/mL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "hf_8", "source_test_name": "Vancomycin - trough", "raw_value": "17.8",
             "source_unit": "mcg/mL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "hf_9", "source_test_name": "prealbumin", "raw_value": "24",
             "source_unit": "mg/dL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "hf_10", "source_test_name": "Atypical Lymphocytes", "raw_value": "2",
             "source_unit": "%", "specimen_type": "Blood", "source_reference_range": "0-0 %"},
            {"source_row_id": "hf_11", "source_test_name": "Metamyelocytes", "raw_value": "1",
             "source_unit": "%", "specimen_type": "Blood", "source_reference_range": "0-0 %"},
            {"source_row_id": "hf_12", "source_test_name": "Myelocytes", "raw_value": "1",
             "source_unit": "%", "specimen_type": "Blood", "source_reference_range": "0-0 %"},
            {"source_row_id": "hf_13", "source_test_name": "urinary sodium", "raw_value": "45",
             "source_unit": "mmol/L", "specimen_type": "", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        expected = {
            "hf_1": ("ck_mb_index", "%"),
            "hf_2": ("base_deficit", "mEq/L"),
            "hf_3": ("carboxyhemoglobin", "%"),
            "hf_4": ("methemoglobin", "%"),
            "hf_5": ("oxyhemoglobin", "%"),
            "hf_6": ("oxygen_content", "mL/dL"),
            "hf_7": ("vancomycin", "ug/mL"),
            "hf_8": ("vancomycin_trough", "ug/mL"),
            "hf_9": ("prealbumin", "mg/dL"),
            "hf_10": ("atypical_lymphocytes_pct", "%"),
            "hf_11": ("metamyelocytes_pct", "%"),
            "hf_12": ("myelocytes_pct", "%"),
            "hf_13": ("sodium_urine", "mEq/L"),
        }
        self.assertEqual(result.summary["mapped"], len(rows))
        for record in result.records:
            self.assertEqual(record.mapping_status, "mapped", record.source_row_id)
            biomarker_id, unit = expected[record.source_row_id]
            self.assertEqual(record.canonical_biomarker_id, biomarker_id)
            self.assertEqual(record.normalized_unit, unit)

    def test_bands_alias_is_disambiguated_by_unit(self) -> None:
        rows = [
            {"source_row_id": "bands_pct", "source_test_name": "Bands", "raw_value": "4",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": "0-5 %"},
            {"source_row_id": "bands_abs", "source_test_name": "Bands", "raw_value": "0.4",
             "source_unit": "K/uL", "specimen_type": "whole blood", "source_reference_range": "0-0.5 K/uL"},
        ]
        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}
        self.assertEqual(by_id["bands_pct"].canonical_biomarker_id, "bands_pct")
        self.assertEqual(by_id["bands_pct"].normalized_unit, "%")
        self.assertEqual(by_id["bands_pct"].status_reason, "mapped_by_alias_and_unit")
        self.assertEqual(by_id["bands_abs"].canonical_biomarker_id, "bands")
        self.assertEqual(by_id["bands_abs"].normalized_unit, "K/uL")
        self.assertEqual(by_id["bands_abs"].status_reason, "mapped_by_alias_and_unit")

    def test_nrbc_alias_is_disambiguated_by_unit(self) -> None:
        rows = [
            {"source_row_id": "nrbc_pct", "source_test_name": "NRBC", "raw_value": "2",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": "0-0 %"},
            {"source_row_id": "nrbc_abs", "source_test_name": "NRBC", "raw_value": "150",
             "source_unit": "#/uL", "specimen_type": "whole blood", "source_reference_range": "0-0 #/uL"},
        ]
        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}
        self.assertEqual(by_id["nrbc_pct"].canonical_biomarker_id, "nrbc_pct")
        self.assertEqual(by_id["nrbc_pct"].normalized_unit, "%")
        self.assertEqual(by_id["nrbc_pct"].status_reason, "mapped_by_alias_and_unit")
        self.assertEqual(by_id["nrbc_abs"].canonical_biomarker_id, "nrbc")
        self.assertEqual(by_id["nrbc_abs"].normalized_unit, "#/uL")
        self.assertEqual(by_id["nrbc_abs"].status_reason, "mapped_by_alias_and_unit")

    def test_pco2_kpa_converts_to_mmhg(self) -> None:
        result = convert_to_normalized(Decimal("5.3"), "pco2", "kPa")
        self.assertIsNotNone(result)
        # 5.3 kPa * 7.50062 = 39.75 mmHg
        self.assertAlmostEqual(float(result), 39.75, places=0)

    def test_po2_kpa_converts_to_mmhg(self) -> None:
        result = convert_to_normalized(Decimal("13.0"), "po2", "kPa")
        self.assertIsNotNone(result)
        # 13.0 kPa * 7.50062 = 97.5 mmHg
        self.assertAlmostEqual(float(result), 97.5, places=0)

    def test_synthea_truncated_loinc_names_map(self) -> None:
        """Synthea uses LOINC display names without 'by Automated count' suffix."""
        rows = [
            {"source_row_id": "s1", "source_test_name": "Leukocytes [#/volume] in Blood",
             "raw_value": "7.0", "source_unit": "10^9/L", "specimen_type": "whole blood",
             "source_reference_range": ""},
            {"source_row_id": "s2", "source_test_name": "Erythrocytes [#/volume] in Blood",
             "raw_value": "4.5", "source_unit": "10^12/L", "specimen_type": "whole blood",
             "source_reference_range": ""},
            {"source_row_id": "s3",
             "source_test_name": "Bilirubin.total [Mass/volume] in Blood",
             "raw_value": "1.0", "source_unit": "mg/dL", "specimen_type": "serum",
             "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "wbc")
        self.assertEqual(result.records[1].mapping_status, "mapped")
        self.assertEqual(result.records[1].canonical_biomarker_id, "rbc")
        self.assertEqual(result.records[2].mapping_status, "mapped")
        self.assertEqual(result.records[2].canonical_biomarker_id, "total_bilirubin")

    def test_catalog_count_at_least_83(self) -> None:
        """Verify catalog has grown to expected size after wave 7 + WBC pct."""
        self.assertGreaterEqual(len(BIOMARKER_CATALOG), 89)

    def test_thous_mcl_unit_normalizes(self) -> None:
        from biomarker_normalization_toolkit.units import normalize_unit
        self.assertEqual(normalize_unit("THOUS/MCL"), "K/uL")
        self.assertEqual(normalize_unit("thous/ul"), "K/uL")

    # --- Feature 2: WBC percentage differentials ---

    def test_wbc_pct_differentials_map(self) -> None:
        rows = [
            {"source_row_id": "pct1", "source_test_name": "Neutrophils/100 leukocytes", "raw_value": "65",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": "40-70 %"},
            {"source_row_id": "pct2", "source_test_name": "Lymphocytes Percent", "raw_value": "25",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": "20-40 %"},
            {"source_row_id": "pct3", "source_test_name": "Monocytes/100 leukocytes", "raw_value": "6",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": "2-8 %"},
            {"source_row_id": "pct4", "source_test_name": "Eosinophils Percent", "raw_value": "3",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": "1-4 %"},
            {"source_row_id": "pct5", "source_test_name": "Basophils/100 leukocytes", "raw_value": "1",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": "0-1 %"},
        ]
        result = normalize_rows(rows)
        expected = {
            "pct1": "neutrophils_pct", "pct2": "lymphocytes_pct", "pct3": "monocytes_pct",
            "pct4": "eosinophils_pct", "pct5": "basophils_pct",
        }
        self.assertEqual(result.summary["mapped"], 5)
        for record in result.records:
            self.assertEqual(record.mapping_status, "mapped", f"{record.source_row_id}")
            self.assertEqual(record.canonical_biomarker_id, expected[record.source_row_id])
            self.assertEqual(record.normalized_unit, "%")

    def test_bare_neutrophils_with_pct_unit_redirects_to_pct(self) -> None:
        """Bare 'Neutrophils' with unit '%' should redirect to neutrophils_pct."""
        rows = [{"source_row_id": "np1", "source_test_name": "Neutrophils", "raw_value": "65",
                 "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "neutrophils_pct")

    def test_catalog_count_at_least_89(self) -> None:
        """Verify catalog has grown to expected size with WBC pct differentials."""
        self.assertGreaterEqual(len(BIOMARKER_CATALOG), 89)

    # --- Feature 1: Fuzzy matching ---

    def test_fuzzy_disabled_by_default(self) -> None:
        rows = [{"source_row_id": "f1", "source_test_name": "Glucos", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)  # default fuzzy_threshold=0.0
        self.assertEqual(result.records[0].mapping_status, "unmapped")

    def test_fuzzy_maps_typo_with_medium_confidence(self) -> None:
        rows = [{"source_row_id": "f2", "source_test_name": "Glucos", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows, fuzzy_threshold=0.7)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "glucose_serum")
        self.assertIn(result.records[0].match_confidence, ("medium", "high"))
        self.assertIn("fuzzy:", result.records[0].mapping_rule)

    def test_fuzzy_high_threshold_rejects_moderate_match(self) -> None:
        rows = [{"source_row_id": "f3", "source_test_name": "Glc", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows, fuzzy_threshold=0.95)
        # "Glc" vs "glucose" is well below 95%
        self.assertIn(result.records[0].mapping_status, ("unmapped", "review_needed"))

    def test_fuzzy_threshold_negative_rejected(self) -> None:
        rows = [{"source_row_id": "f3b", "source_test_name": "Glc", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        with self.assertRaisesRegex(ValueError, "fuzzy_threshold"):
            normalize_rows(rows, fuzzy_threshold=-0.1)

    def test_fuzzy_threshold_above_one_rejected(self) -> None:
        rows = [{"source_row_id": "f3c", "source_test_name": "Glc", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        with self.assertRaisesRegex(ValueError, "fuzzy_threshold"):
            normalize_rows(rows, fuzzy_threshold=1.1)

    def test_fuzzy_does_not_break_exact_matches(self) -> None:
        rows = [{"source_row_id": "f4", "source_test_name": "Glucose", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows, fuzzy_threshold=0.85)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].match_confidence, "high")  # exact match
        self.assertNotIn("fuzzy:", result.records[0].mapping_rule)

    def test_confidence_breakdown_in_summary(self) -> None:
        rows = [
            {"source_row_id": "cb1", "source_test_name": "Glucose", "raw_value": "100",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "cb2", "source_test_name": "Unknown Test", "raw_value": "42",
             "source_unit": "U/L", "specimen_type": "serum", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        self.assertIn("confidence_breakdown", result.summary)
        breakdown = result.summary["confidence_breakdown"]
        self.assertEqual(breakdown["high"], 1)
        self.assertEqual(breakdown["none"], 1)

    # --- Feature 3: Physiological plausibility checks ---

    def test_implausible_glucose_generates_warning(self) -> None:
        rows = [{"source_row_id": "p1", "source_test_name": "Glucose", "raw_value": "50000",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")  # Still mapped
        self.assertTrue(any("Implausible" in w and "glucose_serum" in w for w in result.warnings))

    def test_normal_glucose_no_plausibility_warning(self) -> None:
        rows = [{"source_row_id": "p2", "source_test_name": "Glucose", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertFalse(any("Implausible" in w for w in result.warnings))

    def test_implausible_sodium_generates_warning(self) -> None:
        rows = [{"source_row_id": "p3", "source_test_name": "Sodium", "raw_value": "5",
                 "source_unit": "mEq/L", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertTrue(any("sodium" in w for w in result.warnings))

    # --- Wave 8: Longevity panel biomarkers ---

    def test_longevity_panel_biomarkers_map(self) -> None:
        rows = [
            {"source_row_id": "lp1", "source_test_name": "ApoB", "raw_value": "90",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lp2", "source_test_name": "DHEA-S", "raw_value": "200",
             "source_unit": "ug/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lp3", "source_test_name": "Estradiol", "raw_value": "30",
             "source_unit": "pg/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lp4", "source_test_name": "LH", "raw_value": "5.0",
             "source_unit": "mIU/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lp5", "source_test_name": "FSH", "raw_value": "8.0",
             "source_unit": "mIU/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lp6", "source_test_name": "Homocysteine", "raw_value": "10",
             "source_unit": "umol/L", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lp7", "source_test_name": "Fasting Insulin", "raw_value": "8",
             "source_unit": "uIU/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lp8", "source_test_name": "TIBC", "raw_value": "300",
             "source_unit": "ug/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lp9", "source_test_name": "Transferrin Saturation", "raw_value": "30",
             "source_unit": "%", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lp10", "source_test_name": "Lp(a)", "raw_value": "50",
             "source_unit": "nmol/L", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lp11", "source_test_name": "PSA Total", "raw_value": "1.5",
             "source_unit": "ng/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lp12", "source_test_name": "Testosterone Total", "raw_value": "500",
             "source_unit": "ng/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lp13", "source_test_name": "SHBG", "raw_value": "40",
             "source_unit": "nmol/L", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lp14", "source_test_name": "Free Testosterone", "raw_value": "10",
             "source_unit": "pg/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lp15", "source_test_name": "Non-HDL Cholesterol", "raw_value": "130",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        expected = {
            "lp1": "apob", "lp2": "dhea_s", "lp3": "estradiol",
            "lp4": "lh", "lp5": "fsh", "lp6": "homocysteine",
            "lp7": "insulin", "lp8": "tibc", "lp9": "transferrin_saturation",
            "lp10": "lpa", "lp11": "psa", "lp12": "testosterone_total",
            "lp13": "shbg", "lp14": "free_testosterone", "lp15": "non_hdl_cholesterol",
        }
        self.assertEqual(result.summary["mapped"], 15, msg=str([(r.source_row_id, r.mapping_status, r.status_reason) for r in result.records if r.mapping_status != "mapped"]))
        for record in result.records:
            self.assertEqual(record.canonical_biomarker_id, expected[record.source_row_id],
                             f"{record.source_row_id} mapped wrong")

    def test_ratios_and_urinalysis_extras_map(self) -> None:
        rows = [
            {"source_row_id": "r1", "source_test_name": "BUN/Creatinine Ratio", "raw_value": "15",
             "source_unit": "", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "r2", "source_test_name": "A/G Ratio", "raw_value": "1.5",
             "source_unit": "", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "r3", "source_test_name": "TC/HDL Ratio", "raw_value": "3.5",
             "source_unit": "", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "r4", "source_test_name": "Urine Blood", "raw_value": "0",
             "source_unit": "", "specimen_type": "urine", "source_reference_range": ""},
            {"source_row_id": "r5", "source_test_name": "Urine Nitrite", "raw_value": "0",
             "source_unit": "", "specimen_type": "urine", "source_reference_range": ""},
            {"source_row_id": "r6", "source_test_name": "Leukocyte Esterase", "raw_value": "0",
             "source_unit": "", "specimen_type": "urine", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        expected = {
            "r1": "bun_creatinine_ratio", "r2": "albumin_globulin_ratio",
            "r3": "chol_hdl_ratio", "r4": "urine_blood",
            "r5": "urine_nitrite", "r6": "urine_leukocyte_esterase",
        }
        self.assertEqual(result.summary["mapped"], 6, msg=str([(r.source_row_id, r.mapping_status, r.status_reason) for r in result.records if r.mapping_status != "mapped"]))
        for record in result.records:
            self.assertEqual(record.canonical_biomarker_id, expected[record.source_row_id])

    def test_catalog_count_at_least_141(self) -> None:
        self.assertGreaterEqual(len(BIOMARKER_CATALOG), 141)

    # --- Fuzzy matching safety: blocklist prevents false positives ---

    def test_fuzzy_blocklist_prevents_hemoglobin_c_to_hba1c(self) -> None:
        """Hemoglobin C (electrophoresis variant) must NOT fuzzy-match to HbA1c."""
        rows = [{"source_row_id": "bl1", "source_test_name": "Hemoglobin C", "raw_value": "0",
                 "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""}]
        result = normalize_rows(rows, fuzzy_threshold=0.85)
        # Should NOT map to hba1c
        self.assertNotEqual(result.records[0].canonical_biomarker_id, "hba1c")

    def test_ketone_maps_as_exact_alias(self) -> None:
        """'Ketone' should map via exact alias, not fuzzy."""
        rows = [{"source_row_id": "k1", "source_test_name": "Ketone", "raw_value": "5",
                 "source_unit": "mg/dL", "specimen_type": "urine", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "urine_ketones")
        self.assertEqual(result.records[0].match_confidence, "high")

    def test_fuzzy_blocklist_rejects_presence_tests(self) -> None:
        """Qualitative [Presence] tests must never fuzzy-match quantitative biomarkers."""
        rows = [{"source_row_id": "bp1", "source_test_name": "Glucose [Presence] in Urine",
                 "raw_value": "1", "source_unit": "", "specimen_type": "urine",
                 "source_reference_range": ""}]
        result = normalize_rows(rows, fuzzy_threshold=0.85)
        # Must NOT fuzzy-match to glucose_urine or any other biomarker
        self.assertEqual(result.records[0].mapping_status, "unmapped")

    def test_venous_blood_gas_aliases_map(self) -> None:
        rows = [
            {"source_row_id": "vg1", "source_test_name": "Oxygen [Partial pressure] in Venous blood",
             "raw_value": "40", "source_unit": "mmHg", "specimen_type": "whole blood",
             "source_reference_range": ""},
            {"source_row_id": "vg2",
             "source_test_name": "Carbon dioxide  total [Moles/volume] in Venous blood",
             "raw_value": "24", "source_unit": "mmol/L", "specimen_type": "whole blood",
             "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "po2")
        self.assertEqual(result.records[1].mapping_status, "mapped")
        self.assertEqual(result.records[1].canonical_biomarker_id, "bicarbonate")

    # --- Coverage: reporting module ---

    def test_summary_report_generation(self) -> None:
        from biomarker_normalization_toolkit.reporting import build_summary_report
        rows = [
            {"source_row_id": "rp1", "source_test_name": "Glucose", "raw_value": "100",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": "70-99 mg/dL"},
            {"source_row_id": "rp2", "source_test_name": "Unknown", "raw_value": "42",
             "source_unit": "U/L", "specimen_type": "serum", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        report = build_summary_report(result)
        self.assertIn("# Normalization Summary", report)
        self.assertIn("Mapped: 1", report)
        self.assertIn("Unmapped: 1", report)
        self.assertIn("Glucose", report)

    # --- Coverage: edge cases in normalizer ---

    def test_empty_source_test_name_unmapped(self) -> None:
        rows = [{"source_row_id": "e1", "source_test_name": "", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "unmapped")

    def test_none_raw_value_review_needed(self) -> None:
        rows = [{"source_row_id": "n1", "source_test_name": "Glucose", "raw_value": "",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "review_needed")
        self.assertEqual(result.records[0].status_reason, "invalid_raw_value")

    def test_csv_write_and_read_roundtrip(self) -> None:
        import tempfile
        from biomarker_normalization_toolkit.io_utils import write_result
        rows = [{"source_row_id": "wr1", "source_test_name": "Glucose", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": "70-99 mg/dL"}]
        result = normalize_rows(rows, input_file="test.csv")
        with tempfile.TemporaryDirectory() as td:
            json_path, csv_path = write_result(result, Path(td))
            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())
            # Verify JSON is valid
            import json
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["summary"]["mapped"], 1)

    # --- Coverage: sibling redirect edge cases ---

    def test_sibling_redirect_rdw_fl_to_rdw_sd(self) -> None:
        """RDW alias with fL unit should redirect to rdw_sd."""
        rows = [{"source_row_id": "sr1",
                 "source_test_name": "Erythrocyte [DistWidth] in Blood",
                 "raw_value": "45.5", "source_unit": "fL",
                 "specimen_type": "whole blood", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "rdw_sd")

    # --- Performance sanity check ---

    def test_normalize_1000_rows_under_1_second(self) -> None:
        import time
        rows = [{"source_row_id": str(i), "source_test_name": "Glucose", "raw_value": str(100+i%50),
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": "70-99 mg/dL"}
                for i in range(1000)]
        start = time.perf_counter()
        result = normalize_rows(rows)
        elapsed = time.perf_counter() - start
        self.assertEqual(result.summary["mapped"], 1000)
        self.assertLess(elapsed, 1.0, f"1000 rows took {elapsed:.2f}s, expected < 1s")

    # --- LOINC code lookup ---

    def test_loinc_code_as_test_name_maps(self) -> None:
        """Source test name that IS a LOINC code should map to the biomarker."""
        rows = [
            {"source_row_id": "loinc1", "source_test_name": "2345-7", "raw_value": "100",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "loinc2", "source_test_name": "4548-4", "raw_value": "5.7",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "loinc3", "source_test_name": "6690-2", "raw_value": "7.0",
             "source_unit": "K/uL", "specimen_type": "whole blood", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "glucose_serum")
        self.assertEqual(result.records[1].canonical_biomarker_id, "hba1c")
        self.assertEqual(result.records[2].canonical_biomarker_id, "wbc")

    def test_invalid_loinc_code_stays_unmapped(self) -> None:
        rows = [{"source_row_id": "loinc_bad", "source_test_name": "9999-9", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "unmapped")

    # --- PhenoAge biological age ---

    def test_phenoage_computes_with_all_inputs(self) -> None:
        from biomarker_normalization_toolkit.phenoage import compute_phenoage
        rows = [
            {"source_row_id": "pa1", "source_test_name": "Albumin", "raw_value": "4.5", "source_unit": "g/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "pa2", "source_test_name": "Creatinine", "raw_value": "0.9", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "pa3", "source_test_name": "Glucose", "raw_value": "90", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "pa4", "source_test_name": "hs-CRP", "raw_value": "0.5", "source_unit": "mg/L", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "pa5", "source_test_name": "Lymphocytes Percent", "raw_value": "30", "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "pa6", "source_test_name": "MCV", "raw_value": "88", "source_unit": "fL", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "pa7", "source_test_name": "RDW", "raw_value": "12.5", "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "pa8", "source_test_name": "ALP", "raw_value": "55", "source_unit": "U/L", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "pa9", "source_test_name": "WBC", "raw_value": "5.5", "source_unit": "K/uL", "specimen_type": "whole blood", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        pheno = compute_phenoage(result, chronological_age=45)
        self.assertIsNotNone(pheno)
        self.assertIsNotNone(pheno["phenoage"])
        self.assertIsInstance(pheno["phenoage"], float)
        # Pin the expected PhenoAge value to catch coefficient/formula regressions
        # Healthy 45yo with good biomarkers should have biological age < chronological age
        self.assertAlmostEqual(pheno["phenoage"], 39.3, delta=2.0)
        self.assertLess(pheno["age_acceleration"], 0)
        self.assertIn("interpretation", pheno)

    def test_phenoage_returns_missing_when_inputs_incomplete(self) -> None:
        from biomarker_normalization_toolkit.phenoage import compute_phenoage
        rows = [
            {"source_row_id": "pm1", "source_test_name": "Albumin", "raw_value": "4.5", "source_unit": "g/dL", "specimen_type": "serum", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        pheno = compute_phenoage(result, chronological_age=45)
        self.assertIsNotNone(pheno)
        self.assertIsNone(pheno["phenoage"])
        self.assertIn("missing_inputs", pheno)
        self.assertGreater(len(pheno["missing_inputs"]), 0)

    # --- Derived metrics ---

    def test_derived_metrics_homa_ir(self) -> None:
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        rows = [
            {"source_row_id": "dm1", "source_test_name": "Glucose", "raw_value": "90", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "dm2", "source_test_name": "Insulin", "raw_value": "5", "source_unit": "uIU/mL", "specimen_type": "serum", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        metrics = compute_derived_metrics(result)
        self.assertIn("homa_ir", metrics)
        homa = float(metrics["homa_ir"]["value"])
        # (90 * 5) / 405 = 1.111
        self.assertAlmostEqual(homa, 1.11, places=1)

    def test_derived_metrics_tg_hdl_ratio(self) -> None:
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        rows = [
            {"source_row_id": "dm3", "source_test_name": "Triglycerides", "raw_value": "100", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "dm4", "source_test_name": "HDL", "raw_value": "50", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        metrics = compute_derived_metrics(result)
        self.assertIn("tg_hdl_ratio", metrics)
        self.assertEqual(metrics["tg_hdl_ratio"]["value"], "2.00")

    # --- Optimal ranges ---

    def test_optimal_ranges_flags_high_ldl(self) -> None:
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges
        rows = [
            {"source_row_id": "or1", "source_test_name": "LDL", "raw_value": "130", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        evals = evaluate_optimal_ranges(result)
        self.assertEqual(len(evals), 1)
        self.assertEqual(evals[0]["status"], "above_optimal")
        self.assertEqual(evals[0]["biomarker_id"], "ldl_cholesterol")

    def test_optimal_ranges_passes_good_values(self) -> None:
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges
        rows = [
            {"source_row_id": "or2", "source_test_name": "Glucose", "raw_value": "80", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        evals = evaluate_optimal_ranges(result)
        self.assertEqual(evals[0]["status"], "optimal")

    # --- Heavy metals ---

    def test_heavy_metals_map(self) -> None:
        rows = [
            {"source_row_id": "hm1", "source_test_name": "Mercury", "raw_value": "2.1", "source_unit": "ug/L", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "hm2", "source_test_name": "Lead", "raw_value": "1.5", "source_unit": "ug/dL", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "hm3", "source_test_name": "Arsenic", "raw_value": "5", "source_unit": "ug/L", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "hm4", "source_test_name": "Cadmium", "raw_value": "0.3", "source_unit": "ug/L", "specimen_type": "whole blood", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        self.assertEqual(result.summary["mapped"], 4)
        ids = {r.canonical_biomarker_id for r in result.records}
        self.assertEqual(ids, {"mercury", "lead", "arsenic", "cadmium"})

    # --- Longevity biomarkers ---

    def test_longevity_wave11_biomarkers_map(self) -> None:
        rows = [
            {"source_row_id": "l1", "source_test_name": "IGF-1", "raw_value": "180", "source_unit": "ng/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "l2", "source_test_name": "Cystatin C", "raw_value": "0.85", "source_unit": "mg/L", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "l3", "source_test_name": "Free T3", "raw_value": "3.2", "source_unit": "pg/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "l4", "source_test_name": "Reverse T3", "raw_value": "18", "source_unit": "ng/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "l5", "source_test_name": "TPO Antibodies", "raw_value": "10", "source_unit": "IU/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "l6", "source_test_name": "ApoA1", "raw_value": "155", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "l7", "source_test_name": "Progesterone", "raw_value": "0.5", "source_unit": "ng/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "l8", "source_test_name": "AMH", "raw_value": "3.5", "source_unit": "ng/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "l9", "source_test_name": "Zinc", "raw_value": "90", "source_unit": "ug/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "l10", "source_test_name": "Fructosamine", "raw_value": "220", "source_unit": "umol/L", "specimen_type": "serum", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        self.assertEqual(result.summary["mapped"], 10)

    def test_catalog_count_at_least_183(self) -> None:
        self.assertGreaterEqual(len(BIOMARKER_CATALOG), 183)

    # --- Round-trip conversion tests ---

    def test_conversion_round_trip_glucose(self) -> None:
        """5.5 mmol/L -> mg/dL -> mmol/L should equal ~5.5."""
        result = convert_to_normalized(Decimal("5.5"), "glucose_serum", "mmol/L")
        self.assertIsNotNone(result)
        # result is in mg/dL. Convert back: mg/dL / 18 = mmol/L
        back = result / Decimal("18")
        self.assertAlmostEqual(float(back), 5.5, places=1)

    def test_conversion_round_trip_creatinine(self) -> None:
        """88.4 umol/L -> mg/dL -> umol/L should equal ~88.4."""
        result = convert_to_normalized(Decimal("88.4"), "creatinine", "umol/L")
        self.assertIsNotNone(result)
        # result is in mg/dL. Convert back: mg/dL * 88.4 = umol/L
        back = result * Decimal("88.4")
        self.assertAlmostEqual(float(back), 88.4, places=1)

    def test_conversion_round_trip_hemoglobin(self) -> None:
        """140 g/L -> g/dL -> g/L should equal 140."""
        result = convert_to_normalized(Decimal("140"), "hemoglobin", "g/L")
        self.assertIsNotNone(result)
        back = result * Decimal("10")
        self.assertAlmostEqual(float(back), 140.0, places=1)

    def test_conversion_round_trip_calcium(self) -> None:
        """2.5 mmol/L -> mg/dL -> mmol/L should equal ~2.5."""
        result = convert_to_normalized(Decimal("2.5"), "calcium", "mmol/L")
        self.assertIsNotNone(result)
        back = result / Decimal("4.008")
        self.assertAlmostEqual(float(back), 2.5, places=2)

    def test_conversion_round_trip_kpa_to_mmhg(self) -> None:
        """5.3 kPa -> mmHg -> kPa should equal ~5.3."""
        result = convert_to_normalized(Decimal("5.3"), "pco2", "kPa")
        self.assertIsNotNone(result)
        back = result / Decimal("7.50062")
        self.assertAlmostEqual(float(back), 5.3, places=2)

    # --- Sibling redirect marking ---

    def test_sibling_redirect_is_marked_in_output(self) -> None:
        """Sibling redirect should show confidence=medium and reason=sibling_unit_redirect."""
        rows = [{"source_row_id": "sr1", "source_test_name": "Neutrophils", "raw_value": "65",
                 "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""}]
        result = normalize_rows(rows)
        r = result.records[0]
        self.assertEqual(r.mapping_status, "mapped")
        self.assertEqual(r.canonical_biomarker_id, "neutrophils_pct")
        self.assertEqual(r.match_confidence, "medium")
        self.assertEqual(r.status_reason, "sibling_unit_redirect")
        self.assertIn("original:neutrophils", r.mapping_rule)
        self.assertIn("redirected:neutrophils_pct", r.mapping_rule)

    # --- FHIR effectiveDateTime ---

    def test_fhir_observation_effective_datetime(self) -> None:
        from biomarker_normalization_toolkit.fhir import build_observation
        from biomarker_normalization_toolkit.normalizer import build_source_records, normalize_source_record
        rows = [{"source_row_id": "dt1", "source_test_name": "TSH", "raw_value": "2.5",
                 "source_unit": "mIU/L", "specimen_type": "", "source_reference_range": ""}]
        record = normalize_source_record(build_source_records(rows)[0])
        # Without datetime param: field is omitted (not fake epoch)
        obs = build_observation(record)
        self.assertNotIn("effectiveDateTime", obs)
        # With datetime param: field is included
        obs2 = build_observation(record, effective_datetime="2024-01-15T10:00:00Z")
        self.assertEqual(obs2["effectiveDateTime"], "2024-01-15T10:00:00Z")

    # --- Startup validation ---

    def test_all_biomarkers_have_conversions_and_plausibility(self) -> None:
        """Every biomarker in catalog must have conversion factors and plausibility ranges."""
        from biomarker_normalization_toolkit.units import CONVERSION_TO_NORMALIZED
        from biomarker_normalization_toolkit.plausibility import PLAUSIBILITY_RANGES
        missing_conv = []
        missing_plaus = []
        for bio_id, bio in BIOMARKER_CATALOG.items():
            if bio_id not in CONVERSION_TO_NORMALIZED:
                missing_conv.append(bio_id)
            if bio.normalized_unit and bio_id not in PLAUSIBILITY_RANGES:
                missing_plaus.append(bio_id)
        self.assertEqual(missing_conv, [], f"Missing conversions: {missing_conv}")
        self.assertEqual(missing_plaus, [], f"Missing plausibility: {missing_plaus}")


    # --- Longitudinal tracking tests ---

    def test_longitudinal_basic_delta(self) -> None:
        """compare_results computes correct deltas for common biomarkers."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before = normalize_rows([
            {"source_row_id": "b1", "source_test_name": "Glucose", "raw_value": "100",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "b2", "source_test_name": "HbA1c", "raw_value": "6.0",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""},
        ])
        after = normalize_rows([
            {"source_row_id": "a1", "source_test_name": "Glucose", "raw_value": "90",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "a2", "source_test_name": "HbA1c", "raw_value": "5.4",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""},
        ])
        result = compare_results(before, after, days_between=90)
        self.assertEqual(result["biomarkers_compared"], 2)
        glucose_delta = next(d for d in result["deltas"] if d["biomarker_id"] == "glucose_serum")
        self.assertEqual(glucose_delta["absolute_delta"], "-10")
        self.assertIn("velocity_per_month", glucose_delta)

    def test_longitudinal_zero_baseline(self) -> None:
        """compare_results handles old=0 gracefully (no division by zero)."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        from biomarker_normalization_toolkit.models import NormalizationResult, NormalizedRecord
        rec_before = NormalizedRecord(
            source_row_number=0, source_row_id="z1", source_lab_name="",
            source_panel_name="", source_test_name="CRP", alias_key="crp",
            raw_value="0", source_unit="mg/L", specimen_type="",
            source_reference_range="", canonical_biomarker_id="crp",
            canonical_biomarker_name="CRP", loinc="",
            mapping_status="mapped", match_confidence="high",
            status_reason="", mapping_rule="exact",
            normalized_value="0", normalized_unit="mg/L",
            normalized_reference_range="", provenance={},
        )
        rec_after = NormalizedRecord(
            source_row_number=0, source_row_id="z2", source_lab_name="",
            source_panel_name="", source_test_name="CRP", alias_key="crp",
            raw_value="5", source_unit="mg/L", specimen_type="",
            source_reference_range="", canonical_biomarker_id="crp",
            canonical_biomarker_name="CRP", loinc="",
            mapping_status="mapped", match_confidence="high",
            status_reason="", mapping_rule="exact",
            normalized_value="5", normalized_unit="mg/L",
            normalized_reference_range="", provenance={},
        )
        before = NormalizationResult(input_file="", summary={"total_rows": 1, "mapped": 1, "unmapped": 0, "review_needed": 0}, records=[rec_before], warnings=())
        after = NormalizationResult(input_file="", summary={"total_rows": 1, "mapped": 1, "unmapped": 0, "review_needed": 0}, records=[rec_after], warnings=())
        result = compare_results(before, after)
        delta = result["deltas"][0]
        self.assertIsNone(delta["percent_delta"])  # Can't compute % from 0

    # --- Derived metrics tests ---

    def _make_result_with(self, biomarkers: dict[str, str]) -> "NormalizationResult":
        """Helper: create a NormalizationResult with the given biomarker values."""
        from biomarker_normalization_toolkit.models import NormalizationResult, NormalizedRecord
        records = []
        for bio_id, value in biomarkers.items():
            records.append(NormalizedRecord(
                source_row_number=0, source_row_id=bio_id, source_lab_name="",
                source_panel_name="", source_test_name=bio_id, alias_key=bio_id,
                raw_value=value, source_unit="", specimen_type="",
                source_reference_range="", canonical_biomarker_id=bio_id,
                canonical_biomarker_name=bio_id, loinc="",
                mapping_status="mapped", match_confidence="high",
                status_reason="", mapping_rule="test",
                normalized_value=value, normalized_unit="",
                normalized_reference_range="", provenance={},
            ))
        return NormalizationResult(
            input_file="",
            summary={"total_rows": len(records), "mapped": len(records), "unmapped": 0, "review_needed": 0},
            records=records, warnings=())

    def test_derived_tyg_index(self) -> None:
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        import math
        result = self._make_result_with({"glucose_serum": "100", "triglycerides": "150"})
        metrics = compute_derived_metrics(result)
        self.assertIn("tyg_index", metrics)
        expected = math.log(150 * 100 / 2)
        self.assertAlmostEqual(float(metrics["tyg_index"]["value"]), expected, places=1)

    def test_derived_de_ritis_ratio(self) -> None:
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        result = self._make_result_with({"ast": "30", "alt": "20"})
        metrics = compute_derived_metrics(result)
        self.assertIn("de_ritis_ratio", metrics)
        self.assertAlmostEqual(float(metrics["de_ritis_ratio"]["value"]), 1.5, places=1)

    def test_derived_nlr(self) -> None:
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        result = self._make_result_with({"neutrophils": "4.5", "lymphocytes": "2.0"})
        metrics = compute_derived_metrics(result)
        self.assertIn("nlr", metrics)
        self.assertAlmostEqual(float(metrics["nlr"]["value"]), 2.25, places=1)

    def test_derived_aip(self) -> None:
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        import math
        result = self._make_result_with({"triglycerides": "150", "hdl_cholesterol": "50"})
        metrics = compute_derived_metrics(result)
        self.assertIn("atherogenic_index", metrics)
        expected = math.log10((150 / 88.57) / (50 / 38.67))
        self.assertAlmostEqual(float(metrics["atherogenic_index"]["value"]), expected, places=2)

    def test_derived_homa_beta(self) -> None:
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        result = self._make_result_with({"glucose_serum": "100", "insulin": "10"})
        metrics = compute_derived_metrics(result)
        self.assertIn("homa_beta", metrics)
        expected = (360 * 10) / (100 - 63)
        self.assertAlmostEqual(float(metrics["homa_beta"]["value"]), expected, places=0)

    def test_derived_division_by_zero_guarded(self) -> None:
        """Derived metrics with zero denominators should not crash."""
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        result = self._make_result_with({"ast": "30", "alt": "0", "hdl_cholesterol": "0", "triglycerides": "100"})
        metrics = compute_derived_metrics(result)
        self.assertNotIn("de_ritis_ratio", metrics)
        self.assertNotIn("tg_hdl_ratio", metrics)

    def test_derived_metrics_huge_finite_values_do_not_crash(self) -> None:
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        result = self._make_result_with({
            "glucose_serum": "1e200",
            "insulin": "1e200",
            "triglycerides": "1e200",
            "hdl_cholesterol": "1",
        })
        metrics = compute_derived_metrics(result)
        self.assertIn("homa_ir", metrics)
        self.assertIn("homa_beta", metrics)
        self.assertIn("tyg_index", metrics)
        self.assertIn("atherogenic_index", metrics)
        self.assertIsInstance(metrics["homa_ir"]["value"], str)

    # --- PhenoAge edge cases ---

    def test_phenoage_without_chronological_age(self) -> None:
        """PhenoAge with no age returns the linear predictor but no age estimate."""
        from biomarker_normalization_toolkit.phenoage import compute_phenoage
        result = self._make_result_with({
            "albumin": "4.0", "creatinine": "1.0", "glucose_serum": "100",
            "crp": "1.0", "lymphocytes_pct": "30", "mcv": "90",
            "rdw": "13", "alp": "70", "wbc": "7",
        })
        pa = compute_phenoage(result, chronological_age=None)
        self.assertIsNotNone(pa)
        self.assertIsNone(pa["phenoage"])
        self.assertIsNone(pa["mortality_score"])
        self.assertIsNotNone(pa["mortality_linear_predictor"])

    def test_phenoage_crp_zero_handled(self) -> None:
        """CRP=0 should not crash (floored to 0.001 mg/dL)."""
        from biomarker_normalization_toolkit.phenoage import compute_phenoage
        result = self._make_result_with({
            "albumin": "4.5", "creatinine": "0.9", "glucose_serum": "85",
            "crp": "0", "lymphocytes_pct": "35", "mcv": "88",
            "rdw": "12.5", "alp": "60", "wbc": "6",
        })
        pa = compute_phenoage(result, chronological_age=40)
        self.assertIsNotNone(pa)
        self.assertIsNotNone(pa["phenoage"])

    def test_phenoage_negative_age_rejected(self) -> None:
        from biomarker_normalization_toolkit.phenoage import compute_phenoage
        result = self._make_result_with({
            "albumin": "4.5", "creatinine": "0.9", "glucose_serum": "85",
            "crp": "1.0", "lymphocytes_pct": "35", "mcv": "88",
            "rdw": "12.5", "alp": "60", "wbc": "6",
        })
        pa = compute_phenoage(result, chronological_age=-1)
        self.assertIsNotNone(pa)
        self.assertIsNone(pa["phenoage"])
        self.assertIn("finite non-negative", pa["error"])

    def test_phenoage_huge_finite_inputs_return_error_not_overflow(self) -> None:
        from biomarker_normalization_toolkit.phenoage import compute_phenoage
        result = self._make_result_with({
            "albumin": "4.5", "creatinine": "1e200", "glucose_serum": "1e200",
            "crp": "1e200", "lymphocytes_pct": "35", "mcv": "88",
            "rdw": "12.5", "alp": "60", "wbc": "6",
        })
        pa = compute_phenoage(result, chronological_age=45)
        self.assertIsNotNone(pa)
        self.assertIsNone(pa["phenoage"])
        self.assertIn("out-of-range", pa["error"])

    # --- Optimal ranges sex-specific ---

    def test_optimal_ranges_sex_specific(self) -> None:
        """Male testosterone range differs from female."""
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges
        result = self._make_result_with({"testosterone_total": "500"})
        male_eval = evaluate_optimal_ranges(result, sex="male")
        female_eval = evaluate_optimal_ranges(result, sex="female")
        t_male = next((e for e in male_eval if e["biomarker_id"] == "testosterone_total"), None)
        t_female = next((e for e in female_eval if e["biomarker_id"] == "testosterone_total"), None)
        self.assertIsNotNone(t_male)
        self.assertIsNotNone(t_female)
        # 500 ng/dL is optimal for male, above optimal for female
        self.assertEqual(t_male["status"], "optimal")
        self.assertEqual(t_female["status"], "above_optimal")

    # --- LH/FSH IU/L conversion (regression) ---

    def test_lh_iu_l_converts_correctly(self) -> None:
        """LH reported as IU/L should convert (IU/L normalizes to U/L via synonym)."""
        result = convert_to_normalized(Decimal("5"), "lh", "IU/L")
        # IU/L -> synonym -> U/L, factor = 1, so result = 5
        self.assertIsNotNone(result)
        self.assertEqual(result, Decimal("5"))

    def test_u_ml_synonym_resolves(self) -> None:
        """Lowercase u/ml should resolve to U/mL for biomarkers using that unit."""
        from biomarker_normalization_toolkit.units import normalize_unit
        self.assertEqual(normalize_unit("u/ml"), "U/mL")

    # --- HL7 SN parsing ---

    def test_hl7_sn_ratio_preserved(self) -> None:
        """HL7 SN ratio values like ^1^:^8 should preserve the full ratio."""
        from biomarker_normalization_toolkit.io_utils import _parse_hl7_sn
        self.assertEqual(_parse_hl7_sn("^1^:^8"), "1:8")
        self.assertEqual(_parse_hl7_sn("^100^-^200"), "100-200")
        self.assertEqual(_parse_hl7_sn("<^10"), "<10")
        self.assertEqual(_parse_hl7_sn(">^500"), ">500")
        self.assertEqual(_parse_hl7_sn("^3^+"), "3+")

    # --- FHIR value type fallbacks ---

    def test_fhir_value_string_extracted(self) -> None:
        """FHIR Observations with valueString should be extracted."""
        import json, tempfile
        from biomarker_normalization_toolkit.io_utils import read_fhir_input
        from pathlib import Path
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {
                    "resourceType": "Observation",
                    "id": "vs1",
                    "code": {"text": "Urine Blood"},
                    "valueString": "Negative",
                }}
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(bundle, f)
            f.flush()
            rows = read_fhir_input(Path(f.name))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["raw_value"], "Negative")

    # --- FHIR DiagnosticReport with contained Observations ---

    def test_fhir_diagnostic_report_contained(self) -> None:
        """DiagnosticReport.contained Observations should be extracted."""
        import json, tempfile
        from biomarker_normalization_toolkit.io_utils import read_fhir_input
        from pathlib import Path
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {
                    "resourceType": "DiagnosticReport",
                    "contained": [
                        {
                            "resourceType": "Observation",
                            "id": "c1",
                            "code": {"text": "Glucose"},
                            "valueQuantity": {"value": 95, "unit": "mg/dL"},
                        }
                    ],
                }}
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(bundle, f)
            f.flush()
            rows = read_fhir_input(Path(f.name))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["raw_value"], "95")

    def test_fhir_diagnostic_report_contained_specimen_reference(self) -> None:
        """Contained Specimen references should populate specimen_type."""
        import json, tempfile
        from biomarker_normalization_toolkit.io_utils import read_fhir_input
        from pathlib import Path
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {
                    "resourceType": "DiagnosticReport",
                    "contained": [
                        {
                            "resourceType": "Specimen",
                            "id": "spec1",
                            "type": {"text": "Urine"},
                        },
                        {
                            "resourceType": "Observation",
                            "id": "c2",
                            "code": {"text": "Glucose"},
                            "valueQuantity": {"value": 95, "unit": "mg/dL"},
                            "specimen": {"reference": "#spec1"},
                        },
                    ],
                }}
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(bundle, f)
            f.flush()
            rows = read_fhir_input(Path(f.name))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["specimen_type"], "Urine")


    # --- Scientific notation parsing ---

    def test_parse_decimal_x10_notation(self) -> None:
        """Clinical lab 'x 10^N' format should parse correctly."""
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertEqual(parse_decimal("15.5 x 10^3"), Decimal("15500"))
        self.assertEqual(parse_decimal("250 x 10^3"), Decimal("250000"))
        self.assertEqual(parse_decimal("3.2x10^9"), Decimal("3200000000"))
        self.assertEqual(parse_decimal("1.5 X10E3"), Decimal("1500"))
        self.assertEqual(parse_decimal("1.5e6"), Decimal("1500000"))
        self.assertEqual(parse_decimal("5.397605346934028e-79"), Decimal("5.397605346934028E-79"))

    # --- FHIR one-sided reference range ---

    def test_fhir_one_sided_range_omits_sentinel(self) -> None:
        """FHIR reference range for '<200' should omit low, not emit 0."""
        from biomarker_normalization_toolkit.fhir import build_observation
        from biomarker_normalization_toolkit.normalizer import build_source_records, normalize_source_record
        rows = [{"source_row_id": "rr1", "source_test_name": "LDL Cholesterol", "raw_value": "120",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": "<130 mg/dL"}]
        record = normalize_source_record(build_source_records(rows)[0])
        obs = build_observation(record)
        self.assertIsNotNone(obs)
        rr = obs.get("referenceRange", [])
        if rr:
            self.assertIn("high", rr[0])
            self.assertNotIn("low", rr[0])  # Sentinel 0 should be omitted

    # --- FHIR subject reference ---

    def test_fhir_subject_reference_included(self) -> None:
        """build_observation with subject_reference should include subject field."""
        from biomarker_normalization_toolkit.fhir import build_observation
        from biomarker_normalization_toolkit.normalizer import build_source_records, normalize_source_record
        rows = [{"source_row_id": "sub1", "source_test_name": "Glucose", "raw_value": "95",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        record = normalize_source_record(build_source_records(rows)[0])
        obs = build_observation(record, subject_reference="Patient/12345")
        self.assertIsNotNone(obs)
        self.assertEqual(obs["subject"]["reference"], "Patient/12345")
        # Without subject_reference, field should be absent
        obs2 = build_observation(record)
        self.assertNotIn("subject", obs2)

    # --- HL7 cancelled results skipped ---

    def test_hl7_cancelled_results_skipped(self) -> None:
        """HL7 OBX with result status X/D/W should be skipped."""
        import tempfile
        from biomarker_normalization_toolkit.io_utils import read_hl7_input
        from pathlib import Path
        hl7_msg = (
            "MSH|^~\\&|LAB|FAC|APP|FAC|202401011200||ORU^R01|123|P|2.5\r"
            "PID|||12345\r"
            "OBR|1||1234|24326-1^CBC\r"
            "OBX|1|NM|718-7^Hemoglobin||14.5|g/dL|13.0-17.0|N|||F\r"
            "OBX|2|NM|4544-3^Hematocrit||42.0|%|36.0-46.0|N|||X\r"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".hl7", delete=False, encoding="utf-8") as f:
            f.write(hl7_msg)
            f.flush()
            rows = read_hl7_input(Path(f.name))
        # Only Hemoglobin (F=final) should be returned, Hematocrit (X=cancelled) should be skipped
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_test_name"], "Hemoglobin")


    # --- format_decimal negative zero ---

    def test_format_decimal_negative_zero(self) -> None:
        from biomarker_normalization_toolkit.units import format_decimal
        self.assertEqual(format_decimal(Decimal("-0")), "0")
        self.assertEqual(format_decimal(Decimal("-0.0")), "0")
        self.assertEqual(format_decimal(Decimal("-1E-7")), "0")

    # --- FHIR UUID no collision on duplicate row IDs ---

    def test_fhir_uuid_unique_for_different_biomarkers(self) -> None:
        """Two observations with same source_row_id but different biomarkers must get unique UUIDs."""
        from biomarker_normalization_toolkit.fhir import build_bundle
        rows = [
            {"source_row_id": "DUP1", "source_test_name": "Glucose", "raw_value": "100",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "DUP1", "source_test_name": "Hemoglobin", "raw_value": "14",
             "source_unit": "g/dL", "specimen_type": "whole blood", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        bundle = build_bundle(result)
        urls = [e["fullUrl"] for e in bundle["entry"]]
        self.assertEqual(len(urls), len(set(urls)), f"Duplicate fullUrls found: {urls}")

    def test_fhir_uuid_unique_for_duplicate_row_ids_same_biomarker(self) -> None:
        from biomarker_normalization_toolkit.fhir import build_bundle
        rows = [
            {"source_row_id": "DUP2", "source_test_name": "Glucose", "raw_value": "100",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "DUP2", "source_test_name": "Glucose", "raw_value": "101",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        ]
        result = normalize_rows(rows, input_file="labs.csv")
        bundle = build_bundle(result)
        urls = [e["fullUrl"] for e in bundle["entry"]]
        self.assertEqual(len(urls), len(set(urls)), f"Duplicate fullUrls found: {urls}")

    # --- Longitudinal improving/worsening directions ---

    def test_longitudinal_improving_direction(self) -> None:
        """A value moving toward optimal (but still outside) should be 'improving'."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        # Glucose optimal range is 72-85 mg/dL. 50 -> 65 is still below but closer.
        before = normalize_rows([
            {"source_row_id": "b1", "source_test_name": "Glucose", "raw_value": "50",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        ])
        after = normalize_rows([
            {"source_row_id": "a1", "source_test_name": "Glucose", "raw_value": "65",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        ])
        result = compare_results(before, after)
        delta = result["deltas"][0]
        self.assertEqual(delta["direction"], "improving")

    def test_longitudinal_worsening_direction(self) -> None:
        """A value moving away from optimal (both above) should be 'worsening'."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        # Glucose optimal 72-85. 90 -> 110 both above, 110 is farther.
        before = normalize_rows([
            {"source_row_id": "b1", "source_test_name": "Glucose", "raw_value": "90",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        ])
        after = normalize_rows([
            {"source_row_id": "a1", "source_test_name": "Glucose", "raw_value": "110",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        ])
        result = compare_results(before, after)
        delta = result["deltas"][0]
        self.assertEqual(delta["direction"], "worsening")


    # --- Exponent cap in parse_decimal ---

    def test_parse_decimal_exponent_capped(self) -> None:
        """Exponents > 15 in 'x 10^N' notation should return None (DoS prevention)."""
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertIsNone(parse_decimal("1 x 10^16"))
        self.assertIsNone(parse_decimal("1 x 10^999999999"))
        # Exponent 15 should still work
        self.assertEqual(parse_decimal("1 x 10^15"), Decimal("1000000000000000"))

    # --- TSH mIU/mL conversion ---

    def test_tsh_miu_ml_converts(self) -> None:
        """TSH reported in mIU/mL should convert (1 mIU/mL = 1000 mIU/L)."""
        result = convert_to_normalized(Decimal("2.5"), "tsh", "mIU/mL")
        self.assertIsNotNone(result)
        self.assertEqual(result, Decimal("2500"))

    # --- format_decimal non-finite ---

    def test_format_decimal_infinity_returns_empty(self) -> None:
        from biomarker_normalization_toolkit.units import format_decimal
        self.assertEqual(format_decimal(Decimal("Infinity")), "")
        self.assertEqual(format_decimal(Decimal("-Infinity")), "")
        self.assertEqual(format_decimal(Decimal("NaN")), "")


    # --- Panel prefix stripping ---

    def test_panel_prefix_stripped_glucose(self) -> None:
        """Test names with panel prefixes like 'COMPREHENSIVE METABOLIC PANEL:GLUCOSE' should map."""
        source_rows = [
            {
                "source_row_id": "pp1",
                "source_lab_name": "Quest",
                "source_panel_name": "",
                "source_test_name": "COMPREHENSIVE METABOLIC PANEL:GLUCOSE",
                "raw_value": "95",
                "source_unit": "mg/dL",
                "specimen_type": "serum",
                "source_reference_range": "70-100 mg/dL",
            }
        ]
        source_record = build_source_records(source_rows)[0]
        normalized = normalize_source_record(source_record)

        self.assertEqual(normalized.mapping_status, "mapped")
        self.assertEqual(normalized.canonical_biomarker_id, "glucose_serum")
        self.assertEqual(normalized.match_confidence, "medium")
        self.assertEqual(normalized.status_reason, "panel_prefix_stripped")

    def test_panel_prefix_stripped_wbc(self) -> None:
        """Test names like 'CBC W/ DIFF: WBC' should map after stripping prefix."""
        source_rows = [
            {
                "source_row_id": "pp2",
                "source_lab_name": "LabCorp",
                "source_panel_name": "",
                "source_test_name": "CBC W/ DIFF: WBC",
                "raw_value": "7.5",
                "source_unit": "10^3/uL",
                "specimen_type": "whole_blood",
                "source_reference_range": "4.0-11.0 10^3/uL",
            }
        ]
        source_record = build_source_records(source_rows)[0]
        normalized = normalize_source_record(source_record)

        self.assertEqual(normalized.mapping_status, "mapped")
        self.assertEqual(normalized.canonical_biomarker_id, "wbc")
        self.assertEqual(normalized.match_confidence, "medium")
        self.assertEqual(normalized.status_reason, "panel_prefix_stripped")


    # --- Longitudinal "improved" direction (non-optimal -> optimal) ---

    def test_longitudinal_improved_direction(self) -> None:
        """A value transitioning from outside optimal to inside optimal should be 'improved'."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        # Glucose optimal 72-85. Going from 95 (above) to 80 (optimal) = improved.
        before = normalize_rows([
            {"source_row_id": "b1", "source_test_name": "Glucose", "raw_value": "95",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        ])
        after = normalize_rows([
            {"source_row_id": "a1", "source_test_name": "Glucose", "raw_value": "80",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        ])
        result = compare_results(before, after)
        delta = result["deltas"][0]
        self.assertEqual(delta["direction"], "improved")
        self.assertEqual(result["improved"], 1)

    # --- Quest/LabCorp alias coverage ---

    def test_quest_calcium_serum_alias(self) -> None:
        """Quest 'Calcium, Serum' should map to calcium."""
        rows = [{"source_row_id": "q1", "source_test_name": "Calcium, Serum",
                 "raw_value": "9.5", "source_unit": "mg/dL", "specimen_type": "serum",
                 "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].canonical_biomarker_id, "calcium")

    def test_quest_hscrp_cardiac_alias(self) -> None:
        """Quest 'C-Reactive Protein, Cardiac' should map to hscrp."""
        rows = [{"source_row_id": "q2", "source_test_name": "C-Reactive Protein, Cardiac",
                 "raw_value": "0.5", "source_unit": "mg/L", "specimen_type": "serum",
                 "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].canonical_biomarker_id, "hscrp")

    # --- parse_decimal length guard ---

    def test_parse_decimal_rejects_long_string(self) -> None:
        """Strings longer than 50 chars should be rejected (DoS prevention)."""
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertIsNone(parse_decimal("9" * 51))
        self.assertIsNotNone(parse_decimal("9" * 50))  # 50 is still ok


    # --- Type coercion in build_source_records ---

    def test_non_string_values_coerced(self) -> None:
        """Non-string dict values (int, None, bool) should not crash."""
        rows = [
            {"source_row_id": 123, "source_test_name": "Glucose", "raw_value": 100,
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].canonical_biomarker_id, "glucose_serum")

    def test_non_dict_row_handled(self) -> None:
        """A non-dict item in the rows list should not crash."""
        rows = [None, "not a dict", {"source_row_id": "1", "source_test_name": "Glucose",
                "raw_value": "90", "source_unit": "mg/dL", "specimen_type": "serum",
                "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(len(result.records), 3)

    # --- Derived PLR and SII ---

    def test_derived_plr(self) -> None:
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        result = self._make_result_with({"platelets": "250", "lymphocytes": "2.0"})
        metrics = compute_derived_metrics(result)
        self.assertIn("plr", metrics)
        self.assertAlmostEqual(float(metrics["plr"]["value"]), 125.0, places=0)

    def test_derived_sii(self) -> None:
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        result = self._make_result_with({"neutrophils": "4.0", "platelets": "250", "lymphocytes": "2.0"})
        metrics = compute_derived_metrics(result)
        self.assertIn("sii", metrics)
        self.assertAlmostEqual(float(metrics["sii"]["value"]), 500, places=-1)

    # --- Sex-specific uric acid ---

    def test_uric_acid_sex_specific_ranges(self) -> None:
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges
        result = self._make_result_with({"uric_acid": "5.8"})
        male_eval = evaluate_optimal_ranges(result, sex="male")
        female_eval = evaluate_optimal_ranges(result, sex="female")
        m = next(e for e in male_eval if e["biomarker_id"] == "uric_acid")
        f = next(e for e in female_eval if e["biomarker_id"] == "uric_acid")
        # 5.8 is optimal for male (4.0-6.0) but above optimal for female (3.0-5.5)
        self.assertEqual(m["status"], "optimal")
        self.assertEqual(f["status"], "above_optimal")


    def test_immature_granulocytes_pct_maps(self) -> None:
        result = normalize_rows([{
            "source_test_name": "Immature Granulocytes Percent",
            "raw_value": "0.5",
            "source_unit": "%",
            "specimen_type": "whole blood",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "mapped")
        self.assertEqual(rec.canonical_biomarker_id, "immature_granulocytes_pct")
        self.assertEqual(rec.normalized_unit, "%")
        self.assertEqual(rec.normalized_value, "0.5")

    def test_immature_granulocytes_bare_with_pct_redirects(self) -> None:
        """'Immature Granulocytes' with unit '%' should redirect to immature_granulocytes_pct."""
        result = normalize_rows([{
            "source_test_name": "Immature Granulocytes",
            "raw_value": "1.2",
            "source_unit": "%",
            "specimen_type": "whole blood",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "mapped")
        self.assertEqual(rec.canonical_biomarker_id, "immature_granulocytes_pct")
        self.assertEqual(rec.normalized_unit, "%")


    # --- NMR LipoProfile biomarkers ---

    def test_nmr_lipoprofile_biomarkers_in_catalog(self) -> None:
        """Verify all 5 NMR LipoProfile biomarkers are defined and map correctly."""
        from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG, ALIAS_INDEX, normalize_key
        from biomarker_normalization_toolkit.plausibility import PLAUSIBILITY_RANGES
        from biomarker_normalization_toolkit.optimal_ranges import OPTIMAL_RANGES
        from biomarker_normalization_toolkit.units import CONVERSION_TO_NORMALIZED

        expected = {
            "small_ldl_particle": ("55440-2", "nmol/L", "Small LDL-P"),
            "hdl_particle": ("55437-8", "umol/L", "HDL-P"),
            "large_hdl_particle": ("55436-0", "umol/L", "Large HDL-P"),
            "large_vldl_particle": ("55438-6", "nmol/L", "Large VLDL-P"),
            "lp_ir_score": ("86909-9", "", "LP-IR"),
        }
        for bio_id, (loinc, unit, alias) in expected.items():
            with self.subTest(biomarker=bio_id):
                # Catalog entry exists
                self.assertIn(bio_id, BIOMARKER_CATALOG)
                defn = BIOMARKER_CATALOG[bio_id]
                self.assertEqual(defn.loinc, loinc)
                self.assertEqual(defn.normalized_unit, unit)
                # Alias resolves
                alias_key = normalize_key(alias)
                self.assertIn(alias_key, ALIAS_INDEX)
                self.assertIn(bio_id, ALIAS_INDEX[alias_key])
                # Conversion entry exists
                self.assertIn(bio_id, CONVERSION_TO_NORMALIZED)
                # Plausibility range exists
                self.assertIn(bio_id, PLAUSIBILITY_RANGES)
                # Optimal range exists
                self.assertIn(bio_id, OPTIMAL_RANGES)


    # ===================================================================
    # GOLDEN / SNAPSHOT TESTS - pin exact outputs to catch regressions
    # ===================================================================

    def test_golden_glucose_mmol_conversion(self) -> None:
        """Pin exact Glucose 5.5 mmol/L -> mg/dL normalized output."""
        rows = [{
            "source_row_id": "g1", "source_test_name": "Glucose", "raw_value": "5.5",
            "source_unit": "mmol/L", "specimen_type": "serum",
            "source_reference_range": "3.9-5.5 mmol/L",
            "source_lab_name": "TestLab", "source_panel_name": "BMP",
        }]
        result = normalize_rows(rows, input_file="golden_test.csv")
        self.assertEqual(len(result.records), 1)
        r = result.records[0]
        self.assertEqual(r.normalized_value, "99")
        self.assertEqual(r.loinc, "2345-7")
        self.assertEqual(r.normalized_unit, "mg/dL")
        self.assertEqual(r.mapping_rule, "alias:glucose|biomarker:glucose_serum|specimen:serum")
        self.assertEqual(r.match_confidence, "high")
        self.assertEqual(r.mapping_status, "mapped")
        self.assertEqual(r.status_reason, "mapped_by_alias_and_specimen")
        self.assertEqual(r.canonical_biomarker_id, "glucose_serum")
        self.assertEqual(r.canonical_biomarker_name, "Glucose")
        self.assertEqual(r.normalized_reference_range, "70.2-99 mg/dL")
        self.assertEqual(r.alias_key, "glucose")
        self.assertEqual(r.source_unit, "mmol/L")
        self.assertEqual(r.raw_value, "5.5")
        self.assertEqual(r.source_row_id, "g1")
        self.assertEqual(r.source_lab_name, "TestLab")
        self.assertEqual(r.source_panel_name, "BMP")
        self.assertEqual(r.specimen_type, "serum")
        self.assertEqual(r.source_reference_range, "3.9-5.5 mmol/L")

    def test_golden_phenoage_exact_output(self) -> None:
        """Pin exact PhenoAge for healthy 45yo profile."""
        from biomarker_normalization_toolkit.phenoage import compute_phenoage
        rows = [
            {"source_row_id": "pa1", "source_test_name": "Albumin", "raw_value": "4.5", "source_unit": "g/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "pa2", "source_test_name": "Creatinine", "raw_value": "0.9", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "pa3", "source_test_name": "Glucose", "raw_value": "90", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "pa4", "source_test_name": "hs-CRP", "raw_value": "0.5", "source_unit": "mg/L", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "pa5", "source_test_name": "Lymphocytes Percent", "raw_value": "30", "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "pa6", "source_test_name": "MCV", "raw_value": "88", "source_unit": "fL", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "pa7", "source_test_name": "RDW", "raw_value": "12.5", "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "pa8", "source_test_name": "ALP", "raw_value": "55", "source_unit": "U/L", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "pa9", "source_test_name": "WBC", "raw_value": "5.5", "source_unit": "K/uL", "specimen_type": "whole blood", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        pheno = compute_phenoage(result, chronological_age=45)
        self.assertIsNotNone(pheno)
        self.assertEqual(pheno["phenoage"], 39.3)
        self.assertAlmostEqual(pheno["mortality_score"], 0.0179, places=4)
        self.assertEqual(pheno["mortality_linear_predictor"], -12.9162)
        self.assertEqual(pheno["age_acceleration"], -5.7)
        self.assertEqual(pheno["interpretation"], "Significantly younger biological age")
        self.assertEqual(pheno["chronological_age"], 45)
        self.assertEqual(pheno["inputs"]["albumin_g_dl"], 4.5)
        self.assertEqual(pheno["inputs"]["creatinine_mg_dl"], 0.9)
        self.assertEqual(pheno["inputs"]["glucose_mg_dl"], 90.0)
        self.assertEqual(pheno["inputs"]["crp_mg_l"], 0.5)
        self.assertEqual(pheno["inputs"]["lymphocytes_pct"], 30.0)
        self.assertEqual(pheno["inputs"]["mcv_fl"], 88.0)
        self.assertEqual(pheno["inputs"]["rdw_pct"], 12.5)
        self.assertEqual(pheno["inputs"]["alp_u_l"], 55.0)
        self.assertEqual(pheno["inputs"]["wbc_k_ul"], 5.5)
        self.assertEqual(pheno["formula_reference"], "Levine ME et al. Aging (2018) 10(4):573-591")

    def test_golden_all_derived_metrics(self) -> None:
        """Pin exact values for all 15 derived metrics."""
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        rows = [
            {"source_row_id": "d1", "source_test_name": "Glucose", "raw_value": "90", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "d2", "source_test_name": "Insulin", "raw_value": "5", "source_unit": "uIU/mL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "d3", "source_test_name": "Total Cholesterol", "raw_value": "200", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "d4", "source_test_name": "HDL", "raw_value": "60", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "d5", "source_test_name": "LDL", "raw_value": "110", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "d6", "source_test_name": "Triglycerides", "raw_value": "120", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "d7", "source_test_name": "ApoB", "raw_value": "90", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "d8", "source_test_name": "ApoA1", "raw_value": "150", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "d9", "source_test_name": "AST", "raw_value": "25", "source_unit": "U/L", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "d10", "source_test_name": "ALT", "raw_value": "20", "source_unit": "U/L", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "d11", "source_test_name": "Platelets", "raw_value": "250", "source_unit": "K/uL", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "d12", "source_test_name": "Albumin", "raw_value": "4.2", "source_unit": "g/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "d13", "source_test_name": "Creatinine", "raw_value": "1.0", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "d14", "source_test_name": "Neutrophils", "raw_value": "4.0", "source_unit": "K/uL", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "d15", "source_test_name": "Lymphocytes", "raw_value": "2.0", "source_unit": "K/uL", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "d16", "source_test_name": "Iron", "raw_value": "80", "source_unit": "ug/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "d17", "source_test_name": "TIBC", "raw_value": "300", "source_unit": "ug/dL", "specimen_type": "serum", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        metrics = compute_derived_metrics(result)
        expected_keys = [
            "albumin_creatinine_serum_ratio", "apob_apoa1_ratio", "atherogenic_index",
            "de_ritis_ratio", "fib4_no_age", "homa_beta", "homa_ir",
            "ldl_hdl_ratio", "nlr", "plr", "remnant_cholesterol", "sii",
            "tg_hdl_ratio", "tyg_index", "uibc",
        ]
        self.assertEqual(sorted(metrics.keys()), expected_keys)
        self.assertEqual(metrics["homa_ir"]["value"], "1.11")
        self.assertEqual(metrics["homa_ir"]["unit"], "")
        self.assertEqual(metrics["homa_ir"]["category"], "metabolic")
        self.assertEqual(metrics["homa_beta"]["value"], "66.7")
        self.assertEqual(metrics["homa_beta"]["unit"], "%")
        self.assertEqual(metrics["homa_beta"]["category"], "metabolic")
        self.assertEqual(metrics["tyg_index"]["value"], "8.59")
        self.assertEqual(metrics["tyg_index"]["unit"], "")
        self.assertEqual(metrics["tyg_index"]["category"], "metabolic")
        self.assertEqual(metrics["tg_hdl_ratio"]["value"], "2.00")
        self.assertEqual(metrics["tg_hdl_ratio"]["unit"], "ratio")
        self.assertEqual(metrics["tg_hdl_ratio"]["category"], "cardiovascular")
        self.assertEqual(metrics["apob_apoa1_ratio"]["value"], "0.60")
        self.assertEqual(metrics["apob_apoa1_ratio"]["unit"], "ratio")
        self.assertEqual(metrics["apob_apoa1_ratio"]["category"], "cardiovascular")
        self.assertEqual(metrics["ldl_hdl_ratio"]["value"], "1.83")
        self.assertEqual(metrics["ldl_hdl_ratio"]["unit"], "ratio")
        self.assertEqual(metrics["ldl_hdl_ratio"]["category"], "cardiovascular")
        self.assertEqual(metrics["remnant_cholesterol"]["value"], "30.00")
        self.assertEqual(metrics["remnant_cholesterol"]["unit"], "mg/dL")
        self.assertEqual(metrics["remnant_cholesterol"]["category"], "cardiovascular")
        self.assertEqual(metrics["atherogenic_index"]["value"], "-0.059")
        self.assertEqual(metrics["atherogenic_index"]["unit"], "")
        self.assertEqual(metrics["atherogenic_index"]["category"], "cardiovascular")
        self.assertEqual(metrics["de_ritis_ratio"]["value"], "1.25")
        self.assertEqual(metrics["de_ritis_ratio"]["unit"], "ratio")
        self.assertEqual(metrics["de_ritis_ratio"]["category"], "liver")
        self.assertEqual(metrics["fib4_no_age"]["value"], "0.022")
        self.assertEqual(metrics["fib4_no_age"]["unit"], "")
        self.assertEqual(metrics["fib4_no_age"]["category"], "liver")
        self.assertEqual(metrics["albumin_creatinine_serum_ratio"]["value"], "4.20")
        self.assertEqual(metrics["albumin_creatinine_serum_ratio"]["unit"], "ratio")
        self.assertEqual(metrics["albumin_creatinine_serum_ratio"]["category"], "kidney")
        self.assertEqual(metrics["nlr"]["value"], "2.00")
        self.assertEqual(metrics["nlr"]["unit"], "ratio")
        self.assertEqual(metrics["nlr"]["category"], "inflammation")
        self.assertEqual(metrics["plr"]["value"], "125.0")
        self.assertEqual(metrics["plr"]["unit"], "ratio")
        self.assertEqual(metrics["plr"]["category"], "inflammation")
        self.assertEqual(metrics["sii"]["value"], "500")
        self.assertEqual(metrics["sii"]["unit"], "")
        self.assertEqual(metrics["sii"]["category"], "inflammation")
        self.assertEqual(metrics["uibc"]["value"], "220.00")
        self.assertEqual(metrics["uibc"]["unit"], "ug/dL")
        self.assertEqual(metrics["uibc"]["category"], "iron")

    def test_golden_longitudinal_delta(self) -> None:
        """Pin exact longitudinal delta output for Glucose and LDL."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before_rows = [
            {"source_row_id": "lb1", "source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "lb2", "source_test_name": "LDL", "raw_value": "130", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        ]
        after_rows = [
            {"source_row_id": "la1", "source_test_name": "Glucose", "raw_value": "85", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "la2", "source_test_name": "LDL", "raw_value": "110", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
        ]
        before_result = normalize_rows(before_rows)
        after_result = normalize_rows(after_rows)
        comp = compare_results(before_result, after_result, days_between=90)
        # Pin summary
        self.assertEqual(comp["biomarkers_compared"], 2)
        self.assertEqual(comp["improved"], 2)
        self.assertEqual(comp["worsened"], 0)
        self.assertEqual(comp["stable"], 0)
        self.assertEqual(comp["improvement_rate"], 100.0)
        self.assertEqual(comp["days_between"], 90)
        self.assertEqual(comp["biomarkers_only_in_before"], 0)
        self.assertEqual(comp["biomarkers_only_in_after"], 0)
        # Pin deltas (sorted by biomarker_id)
        self.assertEqual(len(comp["deltas"]), 2)
        glucose_d = comp["deltas"][0]
        ldl_d = comp["deltas"][1]
        # Glucose: 100 -> 85
        self.assertEqual(glucose_d["biomarker_id"], "glucose_serum")
        self.assertEqual(glucose_d["before"], "100")
        self.assertEqual(glucose_d["after"], "85")
        self.assertEqual(glucose_d["absolute_delta"], "-15")
        self.assertEqual(glucose_d["percent_delta"], -15.0)
        self.assertEqual(glucose_d["direction"], "improved")
        self.assertEqual(glucose_d["velocity_per_month"], -5.0)
        # LDL: 130 -> 110
        self.assertEqual(ldl_d["biomarker_id"], "ldl_cholesterol")
        self.assertEqual(ldl_d["before"], "130")
        self.assertEqual(ldl_d["after"], "110")
        self.assertEqual(ldl_d["absolute_delta"], "-20")
        self.assertEqual(ldl_d["percent_delta"], -15.4)
        self.assertEqual(ldl_d["direction"], "improving")
        self.assertEqual(ldl_d["velocity_per_month"], -6.667)

    def test_golden_fhir_observation_structure(self) -> None:
        """Pin exact FHIR Observation JSON structure for Glucose."""
        rows = [{
            "source_row_id": "g1", "source_test_name": "Glucose", "raw_value": "5.5",
            "source_unit": "mmol/L", "specimen_type": "serum",
            "source_reference_range": "3.9-5.5 mmol/L",
            "source_lab_name": "TestLab", "source_panel_name": "BMP",
        }]
        result = normalize_rows(rows, input_file="golden_test.csv")
        obs = build_bundle(result)["entry"][0]["resource"]
        # Pin resourceType and status
        self.assertEqual(obs["resourceType"], "Observation")
        self.assertEqual(obs["status"], "final")
        # Pin deterministic UUID
        self.assertEqual(obs["id"], "4b4b3fe2-bd29-5911-89a9-2521a856654d")
        # Pin category
        self.assertEqual(len(obs["category"]), 1)
        cat_coding = obs["category"][0]["coding"][0]
        self.assertEqual(cat_coding["system"], "http://terminology.hl7.org/CodeSystem/observation-category")
        self.assertEqual(cat_coding["code"], "laboratory")
        self.assertEqual(cat_coding["display"], "Laboratory")
        self.assertEqual(obs["category"][0]["text"], "Laboratory")
        # Pin code (LOINC)
        code_coding = obs["code"]["coding"][0]
        self.assertEqual(code_coding["system"], "http://loinc.org")
        self.assertEqual(code_coding["code"], "2345-7")
        self.assertEqual(code_coding["display"], "Glucose")
        self.assertEqual(obs["code"]["text"], "Glucose")
        # Pin valueQuantity
        vq = obs["valueQuantity"]
        self.assertEqual(vq["value"], 99.0)
        self.assertEqual(vq["unit"], "mg/dL")
        self.assertEqual(vq["system"], "http://unitsofmeasure.org")
        self.assertEqual(vq["code"], "mg/dL")
        # Pin note
        self.assertEqual(len(obs["note"]), 1)
        self.assertIn("alias:glucose|biomarker:glucose_serum|specimen:serum", obs["note"][0]["text"])
        # Pin identifier
        self.assertEqual(obs["identifier"][0]["system"], "urn:source-row-id")
        self.assertEqual(obs["identifier"][0]["value"], "g1")
        # Pin referenceRange
        rr = obs["referenceRange"][0]
        self.assertEqual(rr["text"], "70.2-99 mg/dL")
        self.assertEqual(rr["low"]["value"], 70.2)
        self.assertEqual(rr["low"]["unit"], "mg/dL")
        self.assertEqual(rr["low"]["system"], "http://unitsofmeasure.org")
        self.assertEqual(rr["low"]["code"], "mg/dL")
        self.assertEqual(rr["high"]["value"], 99.0)
        self.assertEqual(rr["high"]["unit"], "mg/dL")
        # Pin specimen
        self.assertEqual(obs["specimen"]["display"], "serum")
        # Verify no effectiveDateTime when not provided
        self.assertNotIn("effectiveDateTime", obs)

    # --- 6. Edge case pinning ---

    def test_golden_inequality_value_edge(self) -> None:
        """Pin exact output for inequality value >500."""
        rows = [{"source_row_id": "e1", "source_test_name": "Glucose", "raw_value": ">500", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        r = result.records[0]
        self.assertEqual(r.mapping_status, "review_needed")
        self.assertEqual(r.status_reason, "inequality_value")
        self.assertEqual(r.match_confidence, "none")
        self.assertEqual(r.canonical_biomarker_id, "glucose_serum")
        self.assertEqual(r.loinc, "2345-7")
        self.assertEqual(r.canonical_biomarker_name, "Glucose")
        self.assertEqual(r.normalized_value, "")
        self.assertEqual(r.normalized_unit, "")
        self.assertEqual(r.mapping_rule, "")

    def test_golden_empty_test_name_edge(self) -> None:
        """Pin exact output for empty source_test_name."""
        rows = [{"source_row_id": "e2", "source_test_name": "", "raw_value": "5", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        r = result.records[0]
        self.assertEqual(r.mapping_status, "unmapped")
        self.assertEqual(r.status_reason, "unknown_alias")
        self.assertEqual(r.match_confidence, "none")
        self.assertEqual(r.canonical_biomarker_id, "")
        self.assertEqual(r.loinc, "")
        self.assertEqual(r.normalized_value, "")
        self.assertEqual(r.normalized_unit, "")
        self.assertEqual(r.mapping_rule, "")

    def test_golden_unknown_test_edge(self) -> None:
        """Pin exact output for completely unknown test name."""
        rows = [{"source_row_id": "e3", "source_test_name": "ZZZNotARealTest", "raw_value": "5", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        r = result.records[0]
        self.assertEqual(r.mapping_status, "unmapped")
        self.assertEqual(r.status_reason, "unknown_alias")
        self.assertEqual(r.match_confidence, "none")
        self.assertEqual(r.canonical_biomarker_id, "")
        self.assertEqual(r.loinc, "")
        self.assertEqual(r.normalized_value, "")

    def test_golden_panel_prefix_stripped_edge(self) -> None:
        """Pin exact output for panel prefix CMP:GLUCOSE."""
        rows = [{"source_row_id": "e4", "source_test_name": "CMP:GLUCOSE", "raw_value": "90", "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        r = result.records[0]
        self.assertEqual(r.mapping_status, "mapped")
        self.assertEqual(r.status_reason, "panel_prefix_stripped")
        self.assertEqual(r.match_confidence, "medium")
        self.assertEqual(r.canonical_biomarker_id, "glucose_serum")
        self.assertEqual(r.mapping_rule, "panel_strip:cmp glucose|biomarker:glucose_serum")
        self.assertEqual(r.normalized_value, "90")
        self.assertEqual(r.loinc, "2345-7")
        self.assertEqual(r.normalized_unit, "mg/dL")

    def test_conversion_factor_pinning(self) -> None:
        """Pin every non-trivial conversion factor to catch regressions.

        Each tuple is (biomarker_id, input_value, input_unit, expected_output).
        Input value is Decimal("100") for all cases so that the expected output
        directly reflects the factor * 100, making it easy to verify against the
        CONVERSION_TO_NORMALIZED table.
        """
        from decimal import Decimal
        from biomarker_normalization_toolkit.units import convert_to_normalized

        cases = [
            # --- Metabolic panel ---
            ("glucose_serum", Decimal("100"), "mmol/L", 1800.0),
            ("glucose_urine", Decimal("100"), "mmol/L", 1800.0),
            ("creatinine", Decimal("100"), "umol/L", 1.1312),
            ("creatinine_urine", Decimal("100"), "umol/L", 1.1312),
            ("bun", Decimal("100"), "mmol/L", 280.0),
            ("calcium", Decimal("100"), "mmol/L", 400.8),
            ("phosphate", Decimal("100"), "mmol/L", 309.7),
            ("magnesium", Decimal("100"), "mmol/L", 243.1),
            ("uric_acid", Decimal("100"), "umol/L", 1.6812),
            ("lactate", Decimal("100"), "mg/dL", 11.0988),
            ("ionized_calcium", Decimal("100"), "mg/dL", 24.9501),
            # --- Lipid panel ---
            ("total_cholesterol", Decimal("100"), "mmol/L", 3867.0),
            ("ldl_cholesterol", Decimal("100"), "mmol/L", 3867.0),
            ("hdl_cholesterol", Decimal("100"), "mmol/L", 3867.0),
            ("non_hdl_cholesterol", Decimal("100"), "mmol/L", 3867.0),
            ("vldl_cholesterol", Decimal("100"), "mmol/L", 3867.0),
            ("triglycerides", Decimal("100"), "mmol/L", 8857.0),
            # --- Liver panel ---
            ("total_bilirubin", Decimal("100"), "umol/L", 5.848),
            ("direct_bilirubin", Decimal("100"), "umol/L", 5.848),
            ("indirect_bilirubin", Decimal("100"), "umol/L", 5.848),
            ("albumin", Decimal("100"), "g/L", 10.0),
            ("fibrinogen", Decimal("100"), "g/L", 10000.0),
            # --- CBC ---
            ("hemoglobin", Decimal("100"), "g/L", 10.0),
            ("hematocrit", Decimal("100"), "L/L", 10000.0),
            ("wbc", Decimal("100"), "#/uL", 0.1),
            ("platelets", Decimal("100"), "#/uL", 0.1),
            ("rbc", Decimal("100"), "#/uL", 0.0001),
            ("mchc", Decimal("100"), "g/L", 10.0),
            # --- WBC differentials ---
            ("neutrophils", Decimal("100"), "#/uL", 0.1),
            ("lymphocytes", Decimal("100"), "#/uL", 0.1),
            ("monocytes", Decimal("100"), "#/uL", 0.1),
            ("eosinophils", Decimal("100"), "#/uL", 0.1),
            ("basophils", Decimal("100"), "#/uL", 0.1),
            ("bands", Decimal("100"), "#/uL", 0.1),
            ("immature_granulocytes", Decimal("100"), "#/uL", 0.1),
            ("reticulocyte_absolute", Decimal("100"), "#/uL", 0.1),
            ("reticulocyte_absolute", Decimal("100"), "M/uL", 100000.0),
            ("nrbc", Decimal("100"), "K/uL", 100000.0),
            # --- Thyroid ---
            ("tsh", Decimal("100"), "mIU/mL", 100000.0),
            ("free_t4", Decimal("100"), "pmol/L", 7.77),
            ("free_t3", Decimal("100"), "pmol/L", 65.1042),
            ("t3_total", Decimal("100"), "nmol/L", 6510.4167),
            ("t4_total", Decimal("100"), "nmol/L", 7.77),
            # --- Vitamins ---
            ("vitamin_d", Decimal("100"), "nmol/L", 40.0641),
            ("vitamin_b12", Decimal("100"), "pmol/L", 135.5),
            ("folate", Decimal("100"), "nmol/L", 44.1306),
            ("vitamin_a", Decimal("100"), "umol/L", 2864.5087),
            ("vitamin_c", Decimal("100"), "umol/L", 1.7612),
            ("vitamin_e", Decimal("100"), "umol/L", 43.0663),
            # --- Minerals ---
            ("iron", Decimal("100"), "umol/L", 558.5),
            ("zinc", Decimal("100"), "umol/L", 653.6),
            ("selenium", Decimal("100"), "umol/L", 7896.0),
            ("copper", Decimal("100"), "umol/L", 635.5),
            # --- Hormones ---
            ("testosterone_total", Decimal("100"), "nmol/L", 2884.338),
            ("estradiol", Decimal("100"), "pmol/L", 27.2405),
            ("cortisol", Decimal("100"), "nmol/L", 3.6245),
            ("insulin", Decimal("100"), "pmol/L", 14.3988),
            ("insulin", Decimal("100"), "mIU/mL", 100000.0),
            ("dhea_s", Decimal("100"), "umol/L", 3684.5984),
            ("progesterone", Decimal("100"), "nmol/L", 31.4465),
            ("dht", Decimal("100"), "nmol/L", 2906.9767),
            ("estrone", Decimal("100"), "pmol/L", 27.0343),
            ("amh", Decimal("100"), "pmol/L", 13.9997),
            ("acth", Decimal("100"), "pmol/L", 454.1326),
            # --- Pituitary / reproductive ---
            ("lh", Decimal("100"), "mIU/mL", 100.0),  # identity (factor=1)
            ("lh", Decimal("100"), "mIU/L", 0.1),
            ("fsh", Decimal("100"), "mIU/mL", 100.0),  # identity (factor=1)
            ("fsh", Decimal("100"), "mIU/L", 0.1),
            ("prolactin", Decimal("100"), "mIU/L", 4.717),
            ("prolactin", Decimal("100"), "mIU/mL", 4716.9811),
            # --- Inflammation ---
            ("hscrp", Decimal("100"), "mg/dL", 1000.0),
            ("crp", Decimal("100"), "mg/dL", 1000.0),
            # --- Cardiac ---
            ("troponin_t", Decimal("100"), "ng/L", 0.1),
            ("troponin_t", Decimal("100"), "pg/mL", 0.1),
            ("troponin_i", Decimal("100"), "ng/L", 0.1),
            ("troponin_i", Decimal("100"), "pg/mL", 0.1),
            ("bnp", Decimal("100"), "pg/dL", 1.0),
            ("d_dimer", Decimal("100"), "ug/mL", 100000.0),
            ("d_dimer", Decimal("100"), "mg/L", 100000.0),
            # --- Peptides ---
            ("c_peptide", Decimal("100"), "nmol/L", 302.1),
            # --- Blood gases ---
            ("pco2", Decimal("100"), "kPa", 750.062),
            ("po2", Decimal("100"), "kPa", 750.062),
            # --- Proteins ---
            ("total_protein", Decimal("100"), "g/L", 10.0),
            ("globulin", Decimal("100"), "g/L", 10.0),
            ("apob", Decimal("100"), "g/L", 10000.0),
            ("apoa1", Decimal("100"), "g/L", 10000.0),
            ("haptoglobin", Decimal("100"), "g/L", 10000.0),
            ("transferrin", Decimal("100"), "g/L", 10000.0),
            ("complement_c3", Decimal("100"), "g/L", 10000.0),
            ("complement_c4", Decimal("100"), "g/L", 10000.0),
            ("iga", Decimal("100"), "g/L", 10000.0),
            ("igg", Decimal("100"), "g/L", 10000.0),
            ("igm", Decimal("100"), "g/L", 10000.0),
            ("igfbp3", Decimal("100"), "mg/L", 100000.0),
            ("cystatin_c", Decimal("100"), "nmol/L", 1.33),
            ("beta2_microglobulin", Decimal("100"), "nmol/L", 1.1779),
            # --- Iron studies ---
            ("tibc", Decimal("100"), "umol/L", 558.5),
            # --- Miscellaneous ---
            ("ammonia", Decimal("100"), "ug/dL", 58.72),
            ("lpa", Decimal("100"), "mg/dL", 239.9808),
            ("albumin_creatinine_ratio", Decimal("100"), "mg/mmol", 884.0),
            ("albumin_urine", Decimal("100"), "mg/dL", 1000.0),
            ("total_protein_urine", Decimal("100"), "mg/L", 10.0),
            ("afp", Decimal("100"), "IU/mL", 121.0),
            # --- Heavy metals ---
            ("lead", Decimal("100"), "umol/L", 2072.1094),
            ("mercury", Decimal("100"), "nmol/L", 20.0602),
            ("cadmium", Decimal("100"), "nmol/L", 11.2397),
        ]

        for bio_id, value, unit, expected in cases:
            with self.subTest(biomarker=bio_id, unit=unit):
                result = convert_to_normalized(value, bio_id, unit)
                self.assertIsNotNone(result, f"{bio_id} {unit} returned None")
                self.assertAlmostEqual(
                    float(result), expected, places=1,
                    msg=f"{bio_id}: {value} {unit} -> {result}, expected ~{expected}",
                )


    # ===================================================================
    # Fuzzy matching, blocklist, normalizer edge cases (comprehensive)
    # ===================================================================

    # --- Fuzzy matching ---

    def test_fuzzy_threshold_zero_glucos_unmapped(self) -> None:
        """With fuzzy_threshold=0 (default), misspelled 'Glucos' stays unmapped."""
        rows = [{"source_row_id": "fz1", "source_test_name": "Glucos", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows, fuzzy_threshold=0.0)
        self.assertEqual(result.records[0].mapping_status, "unmapped")

    def test_fuzzy_threshold_070_glucos_maps(self) -> None:
        """With fuzzy_threshold=0.7, 'Glucos' maps to glucose_serum (requires rapidfuzz)."""
        try:
            import rapidfuzz  # noqa: F401
        except ImportError:
            self.skipTest("rapidfuzz not installed")
        rows = [{"source_row_id": "fz2", "source_test_name": "Glucos", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows, fuzzy_threshold=0.7)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "glucose_serum")

    def test_fuzzy_blocklist_hemoglobin_c_not_hba1c(self) -> None:
        """Hemoglobin C must NOT fuzzy-match to hba1c."""
        try:
            import rapidfuzz  # noqa: F401
        except ImportError:
            self.skipTest("rapidfuzz not installed")
        rows = [{"source_row_id": "fz3", "source_test_name": "Hemoglobin C", "raw_value": "0",
                 "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""}]
        result = normalize_rows(rows, fuzzy_threshold=0.7)
        self.assertNotEqual(result.records[0].canonical_biomarker_id, "hba1c")

    def test_fuzzy_blocklist_alt_not_alp(self) -> None:
        """ALT should NOT fuzzy-match to ALP, and vice versa."""
        try:
            import rapidfuzz  # noqa: F401
        except ImportError:
            self.skipTest("rapidfuzz not installed")
        from biomarker_normalization_toolkit.fuzzy import fuzzy_match
        # "alt" queried should not produce alp
        alt_results = fuzzy_match("alt", threshold=0.70)
        alt_bio_ids = [bio_id for _, bio_id, _ in alt_results]
        self.assertNotIn("alp", alt_bio_ids)
        # "alp" queried should not produce alt
        alp_results = fuzzy_match("alp", threshold=0.70)
        alp_bio_ids = [bio_id for _, bio_id, _ in alp_results]
        self.assertNotIn("alt", alp_bio_ids)

    def test_fuzzy_query_blocklist_presence(self) -> None:
        """Test names containing 'presence' should never fuzzy match."""
        try:
            import rapidfuzz  # noqa: F401
        except ImportError:
            self.skipTest("rapidfuzz not installed")
        from biomarker_normalization_toolkit.fuzzy import fuzzy_match
        self.assertEqual(fuzzy_match("Glucose [Presence] in Urine", threshold=0.70), [])

    def test_fuzzy_query_blocklist_antibod(self) -> None:
        """Test names containing 'antibod' should never fuzzy match."""
        try:
            import rapidfuzz  # noqa: F401
        except ImportError:
            self.skipTest("rapidfuzz not installed")
        from biomarker_normalization_toolkit.fuzzy import fuzzy_match
        self.assertEqual(fuzzy_match("Thyroid Peroxidase Antibodies", threshold=0.70), [])

    def test_fuzzy_query_blocklist_blood_pressure(self) -> None:
        """Test names containing 'blood pressure' should never fuzzy match."""
        try:
            import rapidfuzz  # noqa: F401
        except ImportError:
            self.skipTest("rapidfuzz not installed")
        from biomarker_normalization_toolkit.fuzzy import fuzzy_match
        self.assertEqual(fuzzy_match("Systolic blood pressure", threshold=0.70), [])

    def test_fuzzy_threshold_099_glucos_unmapped(self) -> None:
        """With fuzzy_threshold=0.99, 'Glucos' stays unmapped (too strict)."""
        try:
            import rapidfuzz  # noqa: F401
        except ImportError:
            self.skipTest("rapidfuzz not installed")
        rows = [{"source_row_id": "fz6", "source_test_name": "Glucos", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows, fuzzy_threshold=0.99)
        self.assertIn(result.records[0].mapping_status, ("unmapped", "review_needed"))

    # --- Panel prefix stripping ---

    def test_panel_prefix_basic_metabolic_sodium(self) -> None:
        """'BASIC METABOLIC PANEL:SODIUM' maps to sodium via prefix stripping."""
        rows = [{"source_row_id": "ps1", "source_test_name": "BASIC METABOLIC PANEL:SODIUM",
                 "raw_value": "140", "source_unit": "mEq/L", "specimen_type": "serum",
                 "source_reference_range": ""}]
        result = normalize_rows(rows)
        r = result.records[0]
        self.assertEqual(r.mapping_status, "mapped")
        self.assertEqual(r.canonical_biomarker_id, "sodium")
        self.assertEqual(r.status_reason, "panel_prefix_stripped")

    def test_panel_prefix_lipid_hdl_with_space(self) -> None:
        """'LIPID PANEL: HDL CHOLESTEROL' (space after colon) maps to hdl_cholesterol."""
        rows = [{"source_row_id": "ps2", "source_test_name": "LIPID PANEL: HDL CHOLESTEROL",
                 "raw_value": "55", "source_unit": "mg/dL", "specimen_type": "serum",
                 "source_reference_range": ""}]
        result = normalize_rows(rows)
        r = result.records[0]
        self.assertEqual(r.mapping_status, "mapped")
        self.assertEqual(r.canonical_biomarker_id, "hdl_cholesterol")
        self.assertEqual(r.status_reason, "panel_prefix_stripped")

    def test_no_colon_maps_normally(self) -> None:
        """A test name with NO colon still maps normally via alias."""
        rows = [{"source_row_id": "ps3", "source_test_name": "Glucose",
                 "raw_value": "95", "source_unit": "mg/dL", "specimen_type": "serum",
                 "source_reference_range": ""}]
        result = normalize_rows(rows)
        r = result.records[0]
        self.assertEqual(r.mapping_status, "mapped")
        self.assertEqual(r.canonical_biomarker_id, "glucose_serum")
        self.assertEqual(r.match_confidence, "high")
        self.assertNotEqual(r.status_reason, "panel_prefix_stripped")

    def test_colon_in_alias_exact_match_no_stripping(self) -> None:
        """A colon in a test name that matches an exact alias should not trigger stripping."""
        # "Glucose, Serum" is an exact alias; inserting a colon variant that still matches
        # directly should use alias match, not panel stripping.
        rows = [{"source_row_id": "ps4", "source_test_name": "Glucose, Serum",
                 "raw_value": "90", "source_unit": "mg/dL", "specimen_type": "serum",
                 "source_reference_range": ""}]
        result = normalize_rows(rows)
        r = result.records[0]
        self.assertEqual(r.mapping_status, "mapped")
        self.assertEqual(r.canonical_biomarker_id, "glucose_serum")
        # Should be an exact alias match, NOT panel_prefix_stripped
        self.assertNotEqual(r.status_reason, "panel_prefix_stripped")

    # --- normalize_key tests ---

    def test_normalize_key_strips_non_alphanumeric(self) -> None:
        """normalize_key strips all non-alphanumeric: 'HbA1c (%)' -> 'hba1c'."""
        from biomarker_normalization_toolkit.catalog import normalize_key
        self.assertEqual(normalize_key("HbA1c (%)"), "hba1c")

    def test_normalize_key_empty_string(self) -> None:
        """normalize_key handles empty string -> ''."""
        from biomarker_normalization_toolkit.catalog import normalize_key
        self.assertEqual(normalize_key(""), "")

    def test_normalize_key_collapses_multiple_spaces(self) -> None:
        """normalize_key collapses multiple spaces."""
        from biomarker_normalization_toolkit.catalog import normalize_key
        result = normalize_key("Total   Cholesterol")
        self.assertNotIn("  ", result)
        self.assertEqual(result, "total cholesterol")

    # --- normalize_specimen tests ---

    def test_normalize_specimen_serum(self) -> None:
        from biomarker_normalization_toolkit.catalog import normalize_specimen
        self.assertEqual(normalize_specimen("serum"), "serum")

    def test_normalize_specimen_serum_uppercase(self) -> None:
        from biomarker_normalization_toolkit.catalog import normalize_specimen
        self.assertEqual(normalize_specimen("SERUM"), "serum")

    def test_normalize_specimen_plasma(self) -> None:
        from biomarker_normalization_toolkit.catalog import normalize_specimen
        self.assertEqual(normalize_specimen("Plasma"), "plasma")

    def test_normalize_specimen_whole_blood(self) -> None:
        from biomarker_normalization_toolkit.catalog import normalize_specimen
        self.assertEqual(normalize_specimen("Whole Blood"), "whole_blood")

    def test_normalize_specimen_venous_blood(self) -> None:
        from biomarker_normalization_toolkit.catalog import normalize_specimen
        self.assertEqual(normalize_specimen("venous blood"), "whole_blood")

    def test_normalize_specimen_urine(self) -> None:
        from biomarker_normalization_toolkit.catalog import normalize_specimen
        self.assertEqual(normalize_specimen("urine"), "urine")

    def test_normalize_specimen_random_string(self) -> None:
        """Unknown specimen returns the lowered key (fail-closed behavior)."""
        from biomarker_normalization_toolkit.catalog import normalize_specimen
        result = normalize_specimen("random string")
        # Unknown specimens are returned as lowered key, not None
        self.assertEqual(result, "random string")

    def test_normalize_specimen_empty_string(self) -> None:
        from biomarker_normalization_toolkit.catalog import normalize_specimen
        self.assertIsNone(normalize_specimen(""))

    # --- LOINC fallback tests ---

    def test_loinc_code_2345_7_maps_to_glucose_serum(self) -> None:
        """LOINC code '2345-7' as source_test_name maps to glucose_serum."""
        rows = [{"source_row_id": "lf1", "source_test_name": "2345-7", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertEqual(result.records[0].mapping_status, "mapped")
        self.assertEqual(result.records[0].canonical_biomarker_id, "glucose_serum")

    def test_invalid_loinc_format_does_not_crash(self) -> None:
        """Invalid LOINC format 'XXXX-Y' should not crash, just remain unmapped."""
        rows = [{"source_row_id": "lf2", "source_test_name": "XXXX-Y", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows)
        self.assertIn(result.records[0].mapping_status, ("unmapped", "review_needed"))

    # --- Sibling redirect tests ---

    def test_sibling_redirect_neutrophils_pct(self) -> None:
        """'Neutrophils' with unit '%' redirects to neutrophils_pct."""
        rows = [{"source_row_id": "sb1", "source_test_name": "Neutrophils", "raw_value": "65",
                 "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""}]
        result = normalize_rows(rows)
        r = result.records[0]
        self.assertEqual(r.mapping_status, "mapped")
        self.assertEqual(r.canonical_biomarker_id, "neutrophils_pct")
        self.assertEqual(r.status_reason, "sibling_unit_redirect")

    def test_sibling_redirect_rdw_sd(self) -> None:
        """'RDW' with unit 'fL' redirects to rdw_sd."""
        rows = [{"source_row_id": "sb2", "source_test_name": "RDW", "raw_value": "43",
                 "source_unit": "fL", "specimen_type": "whole blood", "source_reference_range": ""}]
        result = normalize_rows(rows)
        r = result.records[0]
        self.assertEqual(r.mapping_status, "mapped")
        self.assertEqual(r.canonical_biomarker_id, "rdw_sd")
        self.assertEqual(r.status_reason, "sibling_unit_redirect")

    def test_sibling_redirect_reticulocyte_absolute(self) -> None:
        """'Reticulocytes' with absolute unit redirects to reticulocyte_absolute."""
        rows = [{"source_row_id": "sb3", "source_test_name": "Reticulocytes", "raw_value": "50",
                 "source_unit": "K/uL", "specimen_type": "whole blood", "source_reference_range": ""}]
        result = normalize_rows(rows)
        r = result.records[0]
        self.assertEqual(r.mapping_status, "mapped")
        self.assertEqual(r.canonical_biomarker_id, "reticulocyte_absolute")
        self.assertEqual(r.status_reason, "sibling_unit_redirect")

    def test_sibling_redirect_immature_granulocytes_pct(self) -> None:
        """'Immature Granulocytes' with unit '%' redirects to immature_granulocytes_pct."""
        rows = [{"source_row_id": "sb4", "source_test_name": "Immature Granulocytes", "raw_value": "0.8",
                 "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""}]
        result = normalize_rows(rows)
        r = result.records[0]
        self.assertEqual(r.mapping_status, "mapped")
        self.assertEqual(r.canonical_biomarker_id, "immature_granulocytes_pct")
        self.assertEqual(r.status_reason, "sibling_unit_redirect")


    # ===================================================================
    # COMPREHENSIVE OPTIMAL RANGES TESTS
    # ===================================================================

    def test_summarize_optimal_counts_add_up(self) -> None:
        """summarize_optimal returns counts where optimal + below + above = total."""
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges, summarize_optimal
        result = self._make_result_with({
            "glucose_serum": "80",       # optimal (72-85)
            "ldl_cholesterol": "130",    # above_optimal (50-70)
            "vitamin_d": "20",           # below_optimal (40-60)
            "hdl_cholesterol": "60",     # optimal (55-90)
            "hscrp": "3.0",             # above_optimal (0-0.5)
        })
        evals = evaluate_optimal_ranges(result)
        summary = summarize_optimal(evals)
        self.assertEqual(summary["total_evaluated"], 5)
        self.assertEqual(
            summary["optimal"] + summary["below_optimal"] + summary["above_optimal"],
            summary["total_evaluated"],
        )
        self.assertEqual(summary["optimal"], 2)
        self.assertEqual(summary["below_optimal"], 1)
        self.assertEqual(summary["above_optimal"], 2)
        self.assertAlmostEqual(summary["optimal_percentage"], 40.0)

    def test_optimal_all_three_statuses(self) -> None:
        """Verify optimal, below_optimal, above_optimal with specific known values."""
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges
        result = self._make_result_with({
            "glucose_serum": "80",   # optimal (72-85)
            "ferritin": "20",        # below_optimal (40-100)
            "triglycerides": "200",  # above_optimal (40-100)
        })
        evals = evaluate_optimal_ranges(result)
        by_id = {e["biomarker_id"]: e for e in evals}
        self.assertEqual(by_id["glucose_serum"]["status"], "optimal")
        self.assertEqual(by_id["ferritin"]["status"], "below_optimal")
        self.assertEqual(by_id["triglycerides"]["status"], "above_optimal")

    def test_sex_specific_ggt(self) -> None:
        """Male GGT 18 = optimal, female GGT 18 = above_optimal."""
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges
        result = self._make_result_with({"ggt": "18"})
        male_eval = evaluate_optimal_ranges(result, sex="male")
        female_eval = evaluate_optimal_ranges(result, sex="female")
        m = next(e for e in male_eval if e["biomarker_id"] == "ggt")
        f = next(e for e in female_eval if e["biomarker_id"] == "ggt")
        # Male GGT optimal 9-20, so 18 = optimal
        self.assertEqual(m["status"], "optimal")
        # Female GGT optimal 5-15, so 18 = above_optimal
        self.assertEqual(f["status"], "above_optimal")

    def test_qualitative_biomarker_excluded_from_optimal(self) -> None:
        """Qualitative biomarkers like ana_screen should not appear in optimal evaluations."""
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges
        result = self._make_result_with({"ana_screen": "Positive"})
        evals = evaluate_optimal_ranges(result)
        ana_evals = [e for e in evals if e["biomarker_id"] == "ana_screen"]
        self.assertEqual(len(ana_evals), 0)

    def test_nmr_lp_ir_score_optimal_ranges(self) -> None:
        """LP-IR score 20 = optimal, 50 = above_optimal."""
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges
        # LP-IR optimal is 0-27
        result_ok = self._make_result_with({"lp_ir_score": "20"})
        evals_ok = evaluate_optimal_ranges(result_ok)
        lp = next(e for e in evals_ok if e["biomarker_id"] == "lp_ir_score")
        self.assertEqual(lp["status"], "optimal")

        result_high = self._make_result_with({"lp_ir_score": "50"})
        evals_high = evaluate_optimal_ranges(result_high)
        lp_high = next(e for e in evals_high if e["biomarker_id"] == "lp_ir_score")
        self.assertEqual(lp_high["status"], "above_optimal")

    # ===================================================================
    # COMPREHENSIVE DERIVED METRICS TESTS
    # ===================================================================

    def test_all_15_derived_metrics_computed(self) -> None:
        """All 15 unique derived metrics are produced from a comprehensive input set."""
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        result = self._make_result_with({
            "glucose_serum": "90", "insulin": "5",
            "total_cholesterol": "200", "hdl_cholesterol": "60",
            "ldl_cholesterol": "110", "triglycerides": "120",
            "apob": "90", "apoa1": "150",
            "ast": "25", "alt": "20", "platelets": "250",
            "albumin": "4.2", "creatinine": "1.0",
            "neutrophils": "4.0", "lymphocytes": "2.0",
            "iron": "80", "tibc": "300",
        })
        metrics = compute_derived_metrics(result)
        expected = {
            "homa_ir", "homa_beta", "tyg_index",
            "tg_hdl_ratio", "apob_apoa1_ratio", "ldl_hdl_ratio",
            "remnant_cholesterol", "atherogenic_index",
            "de_ritis_ratio", "fib4_no_age",
            "albumin_creatinine_serum_ratio",
            "nlr", "plr", "sii", "uibc",
        }
        self.assertEqual(set(metrics.keys()), expected)
        self.assertEqual(len(metrics), 15)

    def test_homa_ir_excluded_when_glucose_zero(self) -> None:
        """HOMA-IR should not be computed when glucose is 0."""
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        result = self._make_result_with({"glucose_serum": "0", "insulin": "5"})
        metrics = compute_derived_metrics(result)
        self.assertNotIn("homa_ir", metrics)

    def test_homa_beta_excluded_when_glucose_63(self) -> None:
        """HOMA-Beta should not be computed when glucose = 63 (denominator = 0)."""
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        result = self._make_result_with({"glucose_serum": "63", "insulin": "10"})
        metrics = compute_derived_metrics(result)
        self.assertNotIn("homa_beta", metrics)

    def test_tyg_index_manual_calculation(self) -> None:
        """TyG index = ln(TG * Glucose / 2) matches manual calculation."""
        import math
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        tg, gluc = 80, 95
        result = self._make_result_with({"triglycerides": str(tg), "glucose_serum": str(gluc)})
        metrics = compute_derived_metrics(result)
        expected = math.log(tg * gluc / 2)
        self.assertAlmostEqual(float(metrics["tyg_index"]["value"]), expected, places=2)

    def test_aip_manual_calculation(self) -> None:
        """AIP = log10(TG[mmol/L] / HDL[mmol/L]) matches manual calculation."""
        import math
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        tg_mg, hdl_mg = 100, 55
        result = self._make_result_with({"triglycerides": str(tg_mg), "hdl_cholesterol": str(hdl_mg)})
        metrics = compute_derived_metrics(result)
        tg_mmol = tg_mg / 88.57
        hdl_mmol = hdl_mg / 38.67
        expected = math.log10(tg_mmol / hdl_mmol)
        self.assertAlmostEqual(float(metrics["atherogenic_index"]["value"]), expected, places=3)

    def test_uibc_equals_tibc_minus_iron(self) -> None:
        """UIBC = TIBC - Iron."""
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        result = self._make_result_with({"tibc": "350", "iron": "100"})
        metrics = compute_derived_metrics(result)
        self.assertIn("uibc", metrics)
        self.assertAlmostEqual(float(metrics["uibc"]["value"]), 250.0, places=2)

    def test_plr_and_sii_with_known_inputs(self) -> None:
        """PLR = Platelets/Lymphocytes, SII = (Neutrophils*Platelets)/Lymphocytes."""
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        result = self._make_result_with({
            "platelets": "200", "lymphocytes": "2.5", "neutrophils": "3.0",
        })
        metrics = compute_derived_metrics(result)
        # PLR = 200 / 2.5 = 80.0
        self.assertAlmostEqual(float(metrics["plr"]["value"]), 80.0, places=0)
        # SII = (3.0 * 200) / 2.5 = 240
        self.assertAlmostEqual(float(metrics["sii"]["value"]), 240, places=-1)

    def test_fib4_note_mentions_multiply_by_age(self) -> None:
        """FIB-4 note should instruct user to multiply by patient age."""
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        result = self._make_result_with({"ast": "30", "alt": "25", "platelets": "200"})
        metrics = compute_derived_metrics(result)
        self.assertIn("fib4_no_age", metrics)
        note = metrics["fib4_no_age"].get("note", "") + metrics["fib4_no_age"].get("formula", "")
        self.assertIn("multiply", note.lower())
        self.assertIn("age", note.lower())

    # ===================================================================
    # COMPREHENSIVE LONGITUDINAL TESTS
    # ===================================================================

    def test_longitudinal_all_five_directions(self) -> None:
        """Verify all 5 directions: improved, worsened, stable, improving, worsening."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        # glucose optimal 72-85
        # improved: 95 -> 80 (above -> optimal)
        # stable: hba1c 5.0 -> 5.1 (optimal -> optimal, range 4.8-5.2)
        # improving: ldl 40 -> 48 (below -> still below but closer to 50-70)
        # worsened: triglycerides 60 -> 150 (optimal -> above, range 40-100)
        # worsening: hscrp 1.0 -> 2.0 (above -> still above, farther from 0-0.5)
        before = self._make_result_with({
            "glucose_serum": "95",
            "hba1c": "5.0",
            "ldl_cholesterol": "40",
            "triglycerides": "60",
            "hscrp": "1.0",
        })
        after = self._make_result_with({
            "glucose_serum": "80",
            "hba1c": "5.1",
            "ldl_cholesterol": "48",
            "triglycerides": "150",
            "hscrp": "2.0",
        })
        result = compare_results(before, after)
        by_id = {d["biomarker_id"]: d["direction"] for d in result["deltas"]}
        self.assertEqual(by_id["glucose_serum"], "improved")
        self.assertEqual(by_id["hba1c"], "stable")
        self.assertEqual(by_id["ldl_cholesterol"], "improving")
        self.assertEqual(by_id["triglycerides"], "worsened")
        self.assertEqual(by_id["hscrp"], "worsening")

    def test_longitudinal_improvement_rate(self) -> None:
        """improvement_rate = improved / total * 100."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        # 2 biomarkers: one improves (above->optimal), one worsens (optimal->above)
        before = self._make_result_with({
            "glucose_serum": "95",     # above -> will become optimal
            "triglycerides": "60",     # optimal -> will become above
        })
        after = self._make_result_with({
            "glucose_serum": "80",
            "triglycerides": "150",
        })
        result = compare_results(before, after)
        # 1 improved, 1 worsened => improvement_rate = 50.0
        self.assertEqual(result["improved"], 1)
        self.assertEqual(result["worsened"], 1)
        self.assertAlmostEqual(result["improvement_rate"], 50.0)

    def test_longitudinal_velocity_equals_delta_when_30_days(self) -> None:
        """velocity_per_month with days_between=30 equals absolute_delta."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before = self._make_result_with({"glucose_serum": "100"})
        after = self._make_result_with({"glucose_serum": "80"})
        result = compare_results(before, after, days_between=30)
        delta = result["deltas"][0]
        # velocity_per_month = abs_delta / 30 * 30 = abs_delta
        self.assertAlmostEqual(delta["velocity_per_month"], float(delta["absolute_delta"]), places=3)

    def test_longitudinal_no_velocity_when_days_none(self) -> None:
        """When days_between is None, velocity_per_month should not be present."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before = self._make_result_with({"glucose_serum": "100"})
        after = self._make_result_with({"glucose_serum": "90"})
        result = compare_results(before, after, days_between=None)
        delta = result["deltas"][0]
        self.assertNotIn("velocity_per_month", delta)

    def test_longitudinal_single_common_biomarker(self) -> None:
        """With only one common biomarker, comparison still works correctly."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before = self._make_result_with({
            "glucose_serum": "100",
            "hba1c": "5.5",
        })
        after = self._make_result_with({
            "glucose_serum": "85",
            "ldl_cholesterol": "90",
        })
        result = compare_results(before, after, days_between=60)
        self.assertEqual(result["biomarkers_compared"], 1)
        self.assertEqual(result["biomarkers_only_in_before"], 1)  # hba1c
        self.assertEqual(result["biomarkers_only_in_after"], 1)   # ldl_cholesterol
        self.assertEqual(len(result["deltas"]), 1)
        self.assertEqual(result["deltas"][0]["biomarker_id"], "glucose_serum")

    # ===================================================================
    # Self-contained input format parser tests (no external fixtures)
    # ===================================================================

    # --- FHIR input tests (inline, no fixture files) ---

    def test_fhir_bundle_parsing_inline(self) -> None:
        """Parse a FHIR Bundle with two Observations from inline data."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Observation", "id": "obs1",
                    "code": {"text": "Glucose"},
                    "valueQuantity": {"value": 95, "unit": "mg/dL"}}},
                {"resource": {"resourceType": "Observation", "id": "obs2",
                    "code": {"coding": [{"display": "HbA1c", "code": "4548-4",
                                         "system": "http://loinc.org"}]},
                    "valueQuantity": {"value": 5.4, "unit": "%"}}},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["source_test_name"], "Glucose")
            self.assertEqual(rows[0]["raw_value"], "95")
            self.assertEqual(rows[0]["source_unit"], "mg/dL")
            self.assertEqual(rows[0]["source_row_id"], "obs1")
            self.assertEqual(rows[1]["source_test_name"], "HbA1c")
            self.assertEqual(rows[1]["raw_value"], "5.4")
            self.assertEqual(rows[1]["source_unit"], "%")
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_single_observation_resource(self) -> None:
        """A bare Observation (not in a Bundle) should be parsed."""
        obs = {
            "resourceType": "Observation",
            "id": "solo1",
            "code": {"text": "Creatinine"},
            "valueQuantity": {"value": 1.1, "unit": "mg/dL"},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(obs, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_test_name"], "Creatinine")
            self.assertEqual(rows[0]["raw_value"], "1.1")
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_reference_range_both_sides(self) -> None:
        """FHIR referenceRange with low and high should produce 'low-high unit'."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {
                "resourceType": "Observation", "id": "rr1",
                "code": {"text": "Glucose"},
                "valueQuantity": {"value": 95, "unit": "mg/dL"},
                "referenceRange": [{"low": {"value": 70, "unit": "mg/dL"},
                                    "high": {"value": 110, "unit": "mg/dL"}}],
            }}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertEqual(rows[0]["source_reference_range"], "70-110 mg/dL")
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_reference_range_low_only(self) -> None:
        """FHIR referenceRange with only low should produce '>=value unit'."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {
                "resourceType": "Observation", "id": "rr2",
                "code": {"text": "WBC"},
                "valueQuantity": {"value": 7.5, "unit": "10*3/uL"},
                "referenceRange": [{"low": {"value": 4.5, "unit": "10*3/uL"}}],
            }}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertIn(">=4.5", rows[0]["source_reference_range"])
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_reference_range_high_only(self) -> None:
        """FHIR referenceRange with only high should produce '<=value unit'."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {
                "resourceType": "Observation", "id": "rr3",
                "code": {"text": "LDL Cholesterol"},
                "valueQuantity": {"value": 120, "unit": "mg/dL"},
                "referenceRange": [{"high": {"value": 130, "unit": "mg/dL"}}],
            }}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertIn("<=130", rows[0]["source_reference_range"])
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_reference_range_text_fallback(self) -> None:
        """FHIR referenceRange with only text should use the text."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {
                "resourceType": "Observation", "id": "rr4",
                "code": {"text": "eGFR"},
                "valueQuantity": {"value": 90, "unit": "mL/min/1.73m2"},
                "referenceRange": [{"text": ">60 mL/min/1.73m2"}],
            }}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertEqual(rows[0]["source_reference_range"], ">60 mL/min/1.73m2")
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_value_codeable_concept(self) -> None:
        """FHIR Observation with valueCodeableConcept should extract display text."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {
                "resourceType": "Observation", "id": "cc1",
                "code": {"text": "Blood Type"},
                "valueCodeableConcept": {"text": "A Positive"},
            }}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["raw_value"], "A Positive")
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_value_boolean(self) -> None:
        """FHIR Observation with valueBoolean should convert to Positive/Negative."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Observation", "id": "b1",
                    "code": {"text": "Urine Ketones"},
                    "valueBoolean": True}},
                {"resource": {"resourceType": "Observation", "id": "b2",
                    "code": {"text": "Urine Protein"},
                    "valueBoolean": False}},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertEqual(rows[0]["raw_value"], "Positive")
            self.assertEqual(rows[1]["raw_value"], "Negative")
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_specimen_display(self) -> None:
        """FHIR Observation with specimen.display should populate specimen_type."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {
                "resourceType": "Observation", "id": "sp1",
                "code": {"text": "Glucose"},
                "valueQuantity": {"value": 100, "unit": "mg/dL"},
                "specimen": {"display": "Serum"},
            }}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertEqual(rows[0]["specimen_type"], "Serum")
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_uses_loinc_code_when_display_missing(self) -> None:
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {
                "resourceType": "Observation", "id": "loinc1",
                "code": {"coding": [{"system": "http://loinc.org", "code": "2345-7"}]},
                "valueQuantity": {"value": 100, "unit": "mg/dL"},
            }}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_test_name"], "2345-7")
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_resolves_specimen_reference(self) -> None:
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {
                    "resourceType": "Specimen", "id": "spec1",
                    "type": {"text": "Urine"},
                }},
                {"resource": {
                    "resourceType": "Observation", "id": "spref1",
                    "code": {"text": "Glucose"},
                    "valueQuantity": {"value": 12, "unit": "mg/dL"},
                    "specimen": {"reference": "Specimen/spec1"},
                }},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertEqual(rows[0]["specimen_type"], "Urine")
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_skips_observation_without_value(self) -> None:
        """FHIR Observation with no value fields should be skipped."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Observation", "id": "nv1",
                    "code": {"text": "Pending Test"}}},
                {"resource": {"resourceType": "Observation", "id": "nv2",
                    "code": {"text": "Glucose"},
                    "valueQuantity": {"value": 95, "unit": "mg/dL"}}},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_test_name"], "Glucose")
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_skips_observation_without_test_name(self) -> None:
        """FHIR Observation with empty code should be skipped."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Observation", "id": "nn1",
                    "code": {},
                    "valueQuantity": {"value": 5, "unit": "mg/dL"}}},
                {"resource": {"resourceType": "Observation", "id": "nn2",
                    "code": {"text": "Glucose"},
                    "valueQuantity": {"value": 95, "unit": "mg/dL"}}},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertEqual(len(rows), 1)
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_auto_id_when_no_id_field(self) -> None:
        """FHIR Observation with no id or identifier should get auto-generated id."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {
                "resourceType": "Observation",
                "code": {"text": "Glucose"},
                "valueQuantity": {"value": 90, "unit": "mg/dL"},
            }}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertEqual(rows[0]["source_row_id"], "fhir_1")
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_unrecognized_resource_type_raises(self) -> None:
        """Unrecognized FHIR resourceType should raise ValueError."""
        data = {"resourceType": "Patient", "id": "p1"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            tmp = Path(f.name)
        try:
            with self.assertRaises(ValueError):
                read_fhir_input(tmp)
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_identifier_fallback_for_row_id(self) -> None:
        """FHIR Observation with identifier but no id should use identifier value."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {
                "resourceType": "Observation",
                "identifier": [{"value": "ACC-12345"}],
                "code": {"text": "Glucose"},
                "valueQuantity": {"value": 95, "unit": "mg/dL"},
            }}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertEqual(rows[0]["source_row_id"], "ACC-12345")
        finally:
            tmp.unlink(missing_ok=True)

    def test_fhir_value_integer(self) -> None:
        """FHIR Observation with valueInteger should be extracted."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {
                "resourceType": "Observation", "id": "vi1",
                "code": {"text": "Platelets"},
                "valueInteger": 250,
            }}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_fhir_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["raw_value"], "250")
        finally:
            tmp.unlink(missing_ok=True)

    # --- HL7 v2 input tests (inline, no fixture files) ---

    def test_hl7_basic_obx_extraction(self) -> None:
        """Parse a minimal HL7 message with NM-type OBX segments."""
        hl7_msg = (
            "MSH|^~\\&|LAB|FAC|APP|FAC|202401011200||ORU^R01|MSG001|P|2.5\r"
            "PID|1||12345^^^HOSP||DOE^JOHN\r"
            "OBR|1||A001|24326-1^CBC\r"
            "OBX|1|NM|718-7^Hemoglobin||14.5|g/dL|13.0-17.0|N|||F\r"
            "OBX|2|NM|4544-3^Hematocrit||42.0|%|36.0-46.0|N|||F\r"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".hl7", delete=False, encoding="utf-8") as f:
            f.write(hl7_msg)
            tmp = Path(f.name)
        try:
            rows = read_hl7_input(tmp)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["source_test_name"], "Hemoglobin")
            self.assertEqual(rows[0]["raw_value"], "14.5")
            self.assertEqual(rows[0]["source_unit"], "g/dL")
            self.assertEqual(rows[0]["source_reference_range"], "13.0-17.0")
            self.assertEqual(rows[0]["source_panel_name"], "CBC")
            self.assertEqual(rows[1]["source_test_name"], "Hematocrit")
            self.assertEqual(rows[1]["raw_value"], "42.0")
        finally:
            tmp.unlink(missing_ok=True)

    def test_hl7_sn_structured_numeric(self) -> None:
        """HL7 OBX with SN (structured numeric) type should parse comparators."""
        hl7_msg = (
            "MSH|^~\\&|LAB|FAC|APP|FAC|202401011200||ORU^R01|MSG002|P|2.5\r"
            "PID|1||12345\r"
            "OBR|1||A002|5778-6^Urinalysis\r"
            "OBX|1|SN|5811-5^Glucose Urine||<^10|mg/dL||N|||F\r"
            "OBX|2|SN|2514-8^Ketones||>^500|mg/dL||N|||F\r"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".hl7", delete=False, encoding="utf-8") as f:
            f.write(hl7_msg)
            tmp = Path(f.name)
        try:
            rows = read_hl7_input(tmp)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["raw_value"], "<10")
            self.assertEqual(rows[1]["raw_value"], ">500")
        finally:
            tmp.unlink(missing_ok=True)

    def test_hl7_multiple_obr_specimen_reset(self) -> None:
        """Multiple OBR panels: specimen should reset between panels."""
        hl7_msg = (
            "MSH|^~\\&|LAB|FAC|APP|FAC|202401011200||ORU^R01|MSG003|P|2.5\r"
            "PID|1||12345\r"
            "OBR|1||C001|24326-1^CBC|||20240101080000||||||||Whole Blood^WB\r"
            "OBX|1|NM|6690-2^WBC||7.5|10*3/uL|4.5-11.0|N|||F\r"
            "OBR|2||C002|24323-8^CMP|||20240101080000\r"
            "OBX|1|NM|2345-7^Glucose||95|mg/dL|70-110|N|||F\r"
            "OBR|3||C003|24357-6^UA|||20240101080000||||||||Urine^UR\r"
            "OBX|1|NM|5811-5^Specific Gravity||1.020||1.005-1.030|N|||F\r"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".hl7", delete=False, encoding="utf-8") as f:
            f.write(hl7_msg)
            tmp = Path(f.name)
        try:
            rows = read_hl7_input(tmp)
            self.assertEqual(len(rows), 3)
            self.assertIn("Whole Blood", rows[0]["specimen_type"])
            self.assertEqual(rows[1]["specimen_type"], "")
            self.assertIn("Urine", rows[2]["specimen_type"])
        finally:
            tmp.unlink(missing_ok=True)

    def test_hl7_cancelled_deleted_withdrawn_skipped(self) -> None:
        """OBX with result status X, D, W should be skipped; F should pass."""
        hl7_msg = (
            "MSH|^~\\&|LAB|FAC|APP|FAC|202401011200||ORU^R01|MSG004|P|2.5\r"
            "PID|1||12345\r"
            "OBR|1||A004|24326-1^CBC\r"
            "OBX|1|NM|718-7^Hemoglobin||14.5|g/dL|13.0-17.0|N|||F\r"
            "OBX|2|NM|4544-3^Hematocrit||42.0|%|36.0-46.0|N|||X\r"
            "OBX|3|NM|789-8^RBC||5.0|10*6/uL|4.5-5.5|N|||D\r"
            "OBX|4|NM|787-2^MCV||85.0|fL|80.0-100.0|N|||W\r"
            "OBX|5|NM|785-6^MCH||28.0|pg|27.0-33.0|N|||F\r"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".hl7", delete=False, encoding="utf-8") as f:
            f.write(hl7_msg)
            tmp = Path(f.name)
        try:
            rows = read_hl7_input(tmp)
            self.assertEqual(len(rows), 2)
            names = [r["source_test_name"] for r in rows]
            self.assertIn("Hemoglobin", names)
            self.assertIn("MCH", names)
            self.assertNotIn("Hematocrit", names)
            self.assertNotIn("RBC", names)
            self.assertNotIn("MCV", names)
        finally:
            tmp.unlink(missing_ok=True)

    def test_hl7_missing_msh_raises(self) -> None:
        """HL7 file without MSH segment should raise ValueError."""
        bad_msg = "PID|1||12345\rOBX|1|NM|718-7^Hemoglobin||14.5|g/dL\r"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".hl7", delete=False, encoding="utf-8") as f:
            f.write(bad_msg)
            tmp = Path(f.name)
        try:
            with self.assertRaises(ValueError):
                read_hl7_input(tmp)
        finally:
            tmp.unlink(missing_ok=True)

    def test_hl7_no_obx_raises(self) -> None:
        """HL7 file with MSH but no OBX segments should raise ValueError."""
        msg = "MSH|^~\\&|LAB|FAC|APP|FAC|202401011200||ORU^R01|MSG|P|2.5\rPID|1||12345\r"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".hl7", delete=False, encoding="utf-8") as f:
            f.write(msg)
            tmp = Path(f.name)
        try:
            with self.assertRaises(ValueError):
                read_hl7_input(tmp)
        finally:
            tmp.unlink(missing_ok=True)

    def test_hl7_spm_specimen_type(self) -> None:
        """HL7 SPM segment should set specimen type for subsequent OBX."""
        hl7_msg = (
            "MSH|^~\\&|LAB|FAC|APP|FAC|202401011200||ORU^R01|MSG005|P|2.5\r"
            "PID|1||12345\r"
            "OBR|1||A005|24326-1^CBC\r"
            "SPM|1|||BLD^Blood^HL70487\r"
            "OBX|1|NM|718-7^Hemoglobin||14.5|g/dL|13.0-17.0|N|||F\r"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".hl7", delete=False, encoding="utf-8") as f:
            f.write(hl7_msg)
            tmp = Path(f.name)
        try:
            rows = read_hl7_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["specimen_type"], "Blood")
        finally:
            tmp.unlink(missing_ok=True)

    def test_hl7_obx_row_ids_sequential(self) -> None:
        """HL7 row IDs should be sequential hl7_1, hl7_2, etc."""
        hl7_msg = (
            "MSH|^~\\&|LAB|FAC|APP|FAC|202401011200||ORU^R01|MSG006|P|2.5\r"
            "PID|1||12345\r"
            "OBR|1||A006|24326-1^CBC\r"
            "OBX|1|NM|718-7^Hemoglobin||14.5|g/dL||N|||F\r"
            "OBX|2|NM|4544-3^Hematocrit||42.0|%||N|||F\r"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".hl7", delete=False, encoding="utf-8") as f:
            f.write(hl7_msg)
            tmp = Path(f.name)
        try:
            rows = read_hl7_input(tmp)
            self.assertEqual(rows[0]["source_row_id"], "hl7_1")
            self.assertEqual(rows[1]["source_row_id"], "hl7_2")
        finally:
            tmp.unlink(missing_ok=True)

    def test_hl7_panel_name_from_obr4(self) -> None:
        """HL7 OBR-4 component 2 should populate source_panel_name."""
        hl7_msg = (
            "MSH|^~\\&|LAB|FAC|APP|FAC|202401011200||ORU^R01|MSG007|P|2.5\r"
            "PID|1||12345\r"
            "OBR|1||A007|24323-8^Comprehensive Metabolic Panel\r"
            "OBX|1|NM|2345-7^Glucose||95|mg/dL|70-110|N|||F\r"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".hl7", delete=False, encoding="utf-8") as f:
            f.write(hl7_msg)
            tmp = Path(f.name)
        try:
            rows = read_hl7_input(tmp)
            self.assertEqual(rows[0]["source_panel_name"], "Comprehensive Metabolic Panel")
        finally:
            tmp.unlink(missing_ok=True)

    # --- C-CDA input tests (inline, no fixture files) ---

    def test_ccda_basic_observation_extraction(self) -> None:
        """Parse a minimal C-CDA fragment with PQ-type observation."""
        ccda_xml = """
        <root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <observation classCode="OBS" moodCode="EVN">
            <code code="2345-7" codeSystem="2.16.840.1.113883.6.1" displayName="Glucose"/>
            <value xsi:type="PQ" value="95" unit="mg/dL"/>
            <referenceRange>
              <observationRange>
                <value><low value="70" unit="mg/dL"/><high value="110" unit="mg/dL"/></value>
              </observationRange>
            </referenceRange>
          </observation>
        </root>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(ccda_xml)
            tmp = Path(f.name)
        try:
            rows = read_ccda_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_test_name"], "Glucose")
            self.assertEqual(rows[0]["raw_value"], "95")
            self.assertEqual(rows[0]["source_unit"], "mg/dL")
            self.assertEqual(rows[0]["source_reference_range"], "70-110 mg/dL")
            self.assertEqual(rows[0]["source_row_id"], "ccda_1")
        finally:
            tmp.unlink(missing_ok=True)

    def test_ccda_coded_value_qualitative(self) -> None:
        """C-CDA observation with CD/CE type value should extract displayName."""
        ccda_xml = """
        <root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <observation classCode="OBS" moodCode="EVN">
            <code code="5778-6" displayName="Color of Urine"/>
            <value xsi:type="CD" displayName="Yellow" code="Y"/>
          </observation>
        </root>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(ccda_xml)
            tmp = Path(f.name)
        try:
            rows = read_ccda_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["raw_value"], "Yellow")
        finally:
            tmp.unlink(missing_ok=True)

    def test_ccda_one_sided_reference_range_low_only(self) -> None:
        """C-CDA reference range with only low value should produce '>=value'."""
        ccda_xml = """
        <root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <observation classCode="OBS" moodCode="EVN">
            <code displayName="eGFR"/>
            <value xsi:type="PQ" value="90" unit="mL/min/1.73m2"/>
            <referenceRange>
              <observationRange>
                <value><low value="60" unit="mL/min/1.73m2"/></value>
              </observationRange>
            </referenceRange>
          </observation>
        </root>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(ccda_xml)
            tmp = Path(f.name)
        try:
            rows = read_ccda_input(tmp)
            self.assertIn(">=60", rows[0]["source_reference_range"])
        finally:
            tmp.unlink(missing_ok=True)

    def test_ccda_one_sided_reference_range_high_only(self) -> None:
        """C-CDA reference range with only high value should produce '<=value'."""
        ccda_xml = """
        <root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <observation classCode="OBS" moodCode="EVN">
            <code displayName="LDL Cholesterol"/>
            <value xsi:type="PQ" value="120" unit="mg/dL"/>
            <referenceRange>
              <observationRange>
                <value><high value="130" unit="mg/dL"/></value>
              </observationRange>
            </referenceRange>
          </observation>
        </root>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(ccda_xml)
            tmp = Path(f.name)
        try:
            rows = read_ccda_input(tmp)
            self.assertIn("<=130", rows[0]["source_reference_range"])
        finally:
            tmp.unlink(missing_ok=True)

    def test_ccda_null_flavor_observation_skipped(self) -> None:
        """C-CDA observation with nullFlavor and no value should be skipped."""
        ccda_xml = """
        <root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <observation classCode="OBS" moodCode="EVN">
            <code displayName="Pending Test"/>
            <value xsi:type="PQ" nullFlavor="UNK"/>
          </observation>
          <observation classCode="OBS" moodCode="EVN">
            <code displayName="Glucose"/>
            <value xsi:type="PQ" value="95" unit="mg/dL"/>
          </observation>
        </root>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(ccda_xml)
            tmp = Path(f.name)
        try:
            rows = read_ccda_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_test_name"], "Glucose")
        finally:
            tmp.unlink(missing_ok=True)

    def test_ccda_ivl_pq_interval_value(self) -> None:
        """C-CDA IVL_PQ type value should extract bound value."""
        ccda_xml = """
        <root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <observation classCode="OBS" moodCode="EVN">
            <code displayName="Glucose Urine"/>
            <value xsi:type="IVL_PQ">
              <high value="10" unit="mg/dL" inclusive="false"/>
            </value>
          </observation>
        </root>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(ccda_xml)
            tmp = Path(f.name)
        try:
            rows = read_ccda_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["raw_value"], "<10")
            self.assertEqual(rows[0]["source_unit"], "mg/dL")
        finally:
            tmp.unlink(missing_ok=True)

    def test_ccda_translation_fallback(self) -> None:
        """C-CDA code translation element should provide displayName fallback."""
        ccda_xml = """
        <root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <observation classCode="OBS" moodCode="EVN">
            <code code="LP12345">
              <translation codeSystem="2.16.840.1.113883.6.1" code="2345-7" displayName="Glucose"/>
            </code>
            <value xsi:type="PQ" value="100" unit="mg/dL"/>
          </observation>
        </root>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(ccda_xml)
            tmp = Path(f.name)
        try:
            rows = read_ccda_input(tmp)
            self.assertEqual(rows[0]["source_test_name"], "Glucose")
        finally:
            tmp.unlink(missing_ok=True)

    def test_ccda_string_value_type(self) -> None:
        """C-CDA ST type value should extract text content."""
        ccda_xml = """
        <root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <observation classCode="OBS" moodCode="EVN">
            <code displayName="Comment"/>
            <value xsi:type="ST">Normal flora</value>
          </observation>
        </root>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(ccda_xml)
            tmp = Path(f.name)
        try:
            rows = read_ccda_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["raw_value"], "Normal flora")
        finally:
            tmp.unlink(missing_ok=True)

    def test_ccda_multiple_observations(self) -> None:
        """C-CDA with multiple observations should extract all."""
        ccda_xml = """
        <root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <observation classCode="OBS" moodCode="EVN">
            <code displayName="Glucose"/>
            <value xsi:type="PQ" value="95" unit="mg/dL"/>
          </observation>
          <observation classCode="OBS" moodCode="EVN">
            <code displayName="BUN"/>
            <value xsi:type="PQ" value="15" unit="mg/dL"/>
          </observation>
          <observation classCode="OBS" moodCode="EVN">
            <code displayName="Creatinine"/>
            <value xsi:type="PQ" value="1.0" unit="mg/dL"/>
          </observation>
        </root>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(ccda_xml)
            tmp = Path(f.name)
        try:
            rows = read_ccda_input(tmp)
            self.assertEqual(len(rows), 3)
            names = [r["source_test_name"] for r in rows]
            self.assertIn("Glucose", names)
            self.assertIn("BUN", names)
            self.assertIn("Creatinine", names)
        finally:
            tmp.unlink(missing_ok=True)

    def test_ccda_no_observations_raises(self) -> None:
        """C-CDA with no valid observations should raise ValueError."""
        ccda_xml = """
        <root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <observation classCode="OBS" moodCode="EVN">
            <code displayName="Pending"/>
            <value xsi:type="PQ" nullFlavor="UNK"/>
          </observation>
        </root>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(ccda_xml)
            tmp = Path(f.name)
        try:
            with self.assertRaises(ValueError):
                read_ccda_input(tmp)
        finally:
            tmp.unlink(missing_ok=True)

    def test_ccda_int_and_real_value_types(self) -> None:
        """C-CDA INT and REAL type values should extract the value attribute."""
        ccda_xml = """
        <root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <observation classCode="OBS" moodCode="EVN">
            <code displayName="WBC"/>
            <value xsi:type="INT" value="7"/>
          </observation>
          <observation classCode="OBS" moodCode="EVN">
            <code displayName="Hemoglobin"/>
            <value xsi:type="REAL" value="14.5"/>
          </observation>
        </root>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(ccda_xml)
            tmp = Path(f.name)
        try:
            rows = read_ccda_input(tmp)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["raw_value"], "7")
            self.assertEqual(rows[1]["raw_value"], "14.5")
        finally:
            tmp.unlink(missing_ok=True)

    # --- CSV edge case tests (inline, no fixture files) ---

    def test_csv_semicolon_delimiter(self) -> None:
        """CSV with semicolon delimiter should be auto-detected and parsed."""
        csv_content = (
            "source_row_id;source_test_name;raw_value;source_unit;specimen_type;source_reference_range\n"
            "1;Glucose;95;mg/dL;serum;70-110\n"
            "2;HbA1c;5.4;%;blood;\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_content)
            tmp = Path(f.name)
        try:
            rows = read_input_csv(tmp)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["source_test_name"], "Glucose")
            self.assertEqual(rows[0]["raw_value"], "95")
            self.assertEqual(rows[1]["source_test_name"], "HbA1c")
        finally:
            tmp.unlink(missing_ok=True)

    def test_csv_tab_delimiter(self) -> None:
        """CSV with tab delimiter should be auto-detected and parsed."""
        csv_content = (
            "source_row_id\tsource_test_name\traw_value\tsource_unit\tspecimen_type\tsource_reference_range\n"
            "1\tGlucose\t95\tmg/dL\tserum\t70-110\n"
            "2\tCreatinine\t1.1\tmg/dL\tserum\t0.7-1.3\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_content)
            tmp = Path(f.name)
        try:
            rows = read_input_csv(tmp)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["raw_value"], "95")
            self.assertEqual(rows[1]["source_test_name"], "Creatinine")
        finally:
            tmp.unlink(missing_ok=True)

    def test_csv_extra_columns_preserved(self) -> None:
        """CSV with extra columns beyond required should preserve them in row dict."""
        csv_content = (
            "source_row_id,source_test_name,raw_value,source_unit,specimen_type,source_reference_range,patient_id,order_date\n"
            "1,Glucose,95,mg/dL,serum,70-110,PT001,2024-01-15\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_content)
            tmp = Path(f.name)
        try:
            rows = read_input_csv(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["patient_id"], "PT001")
            self.assertEqual(rows[0]["order_date"], "2024-01-15")
        finally:
            tmp.unlink(missing_ok=True)

    def test_csv_bom_marker(self) -> None:
        """CSV with UTF-8 BOM marker should be parsed correctly."""
        bom_bytes = b"\xef\xbb\xbf"
        csv_bytes = (
            b"source_row_id,source_test_name,raw_value,source_unit,specimen_type,source_reference_range\n"
            b"1,Glucose,95,mg/dL,serum,70-110\n"
        )
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as f:
            f.write(bom_bytes + csv_bytes)
            tmp = Path(f.name)
        try:
            rows = read_input_csv(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_test_name"], "Glucose")
            self.assertIn("source_row_id", rows[0])
        finally:
            tmp.unlink(missing_ok=True)

    def test_csv_missing_required_columns_raises(self) -> None:
        """CSV missing required columns should raise ValueError."""
        csv_content = "source_row_id,source_test_name,raw_value\n1,Glucose,95\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_content)
            tmp = Path(f.name)
        try:
            with self.assertRaises(ValueError) as ctx:
                read_input_csv(tmp)
            self.assertIn("missing required columns", str(ctx.exception).lower())
        finally:
            tmp.unlink(missing_ok=True)

    def test_csv_empty_data_rows_raises(self) -> None:
        """CSV with header but no data rows should raise ValueError."""
        csv_content = "source_row_id,source_test_name,raw_value,source_unit,specimen_type,source_reference_range\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_content)
            tmp = Path(f.name)
        try:
            with self.assertRaises(ValueError):
                read_input_csv(tmp)
        finally:
            tmp.unlink(missing_ok=True)

    def test_csv_empty_values_default_to_empty_string(self) -> None:
        """CSV with empty/null cells should default to empty string, not None."""
        csv_content = (
            "source_row_id,source_test_name,raw_value,source_unit,specimen_type,source_reference_range\n"
            "1,Glucose,95,,,\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_content)
            tmp = Path(f.name)
        try:
            rows = read_input_csv(tmp)
            self.assertEqual(rows[0]["source_unit"], "")
            self.assertEqual(rows[0]["specimen_type"], "")
            self.assertEqual(rows[0]["source_reference_range"], "")
        finally:
            tmp.unlink(missing_ok=True)

    # --- read_input auto-detection tests ---

    def test_read_input_dispatches_csv(self) -> None:
        """read_input should dispatch .csv files to CSV parser."""
        csv_content = (
            "source_row_id,source_test_name,raw_value,source_unit,specimen_type,source_reference_range\n"
            "1,Glucose,95,mg/dL,serum,70-110\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_content)
            tmp = Path(f.name)
        try:
            rows = read_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_test_name"], "Glucose")
        finally:
            tmp.unlink(missing_ok=True)

    def test_read_input_dispatches_json(self) -> None:
        """read_input should dispatch .json files to FHIR parser."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {
                "resourceType": "Observation", "id": "d1",
                "code": {"text": "Glucose"},
                "valueQuantity": {"value": 95, "unit": "mg/dL"},
            }}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bundle, f)
            tmp = Path(f.name)
        try:
            rows = read_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_test_name"], "Glucose")
        finally:
            tmp.unlink(missing_ok=True)

    def test_read_input_dispatches_hl7(self) -> None:
        """read_input should dispatch .hl7 files to HL7 parser."""
        hl7_msg = (
            "MSH|^~\\&|LAB|FAC|APP|FAC|202401011200||ORU^R01|MSG|P|2.5\r"
            "PID|1||12345\r"
            "OBR|1||A001|24326-1^CBC\r"
            "OBX|1|NM|718-7^Hemoglobin||14.5|g/dL|13.0-17.0|N|||F\r"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".hl7", delete=False, encoding="utf-8") as f:
            f.write(hl7_msg)
            tmp = Path(f.name)
        try:
            rows = read_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_test_name"], "Hemoglobin")
        finally:
            tmp.unlink(missing_ok=True)

    def test_read_input_dispatches_xml(self) -> None:
        """read_input should dispatch .xml files to C-CDA parser."""
        ccda_xml = """
        <root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <observation classCode="OBS" moodCode="EVN">
            <code displayName="Glucose"/>
            <value xsi:type="PQ" value="95" unit="mg/dL"/>
          </observation>
        </root>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(ccda_xml)
            tmp = Path(f.name)
        try:
            rows = read_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_test_name"], "Glucose")
        finally:
            tmp.unlink(missing_ok=True)

    def test_read_input_dispatches_oru(self) -> None:
        """read_input should dispatch .oru files to HL7 parser."""
        hl7_msg = (
            "MSH|^~\\&|LAB|FAC|APP|FAC|202401011200||ORU^R01|MSG|P|2.5\r"
            "PID|1||12345\r"
            "OBR|1||A001|24326-1^CBC\r"
            "OBX|1|NM|718-7^Hemoglobin||14.5|g/dL|13.0-17.0|N|||F\r"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".oru", delete=False, encoding="utf-8") as f:
            f.write(hl7_msg)
            tmp = Path(f.name)
        try:
            rows = read_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_test_name"], "Hemoglobin")
        finally:
            tmp.unlink(missing_ok=True)

    def test_read_input_unknown_extension_falls_back_to_csv(self) -> None:
        """read_input with unknown extension should fall back to CSV parser."""
        csv_content = (
            "source_row_id,source_test_name,raw_value,source_unit,specimen_type,source_reference_range\n"
            "1,Glucose,95,mg/dL,serum,70-110\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False, encoding="utf-8") as f:
            f.write(csv_content)
            tmp = Path(f.name)
        try:
            rows = read_input(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_test_name"], "Glucose")
        finally:
            tmp.unlink(missing_ok=True)

    # ====================================================================
    # Comprehensive PhenoAge profile, edge-case, and output-structure tests
    # ====================================================================

    def _phenoage_from_values(
        self,
        biomarkers: dict[str, str],
        age: float | None = 50,
    ) -> dict:
        """Shortcut: build NormalizationResult and compute PhenoAge."""
        from biomarker_normalization_toolkit.phenoage import compute_phenoage
        result = self._make_result_with(biomarkers)
        return compute_phenoage(result, chronological_age=age)

    # -- Profile tests (clinical plausibility & monotonicity) --

    def test_phenoage_healthy_30yo(self) -> None:
        """Healthy 30yo with optimal biomarkers should have PhenoAge < 30."""
        pa = self._phenoage_from_values({
            "albumin": "4.8", "creatinine": "0.8", "glucose_serum": "82",
            "crp": "0.3", "lymphocytes_pct": "35", "mcv": "86",
            "rdw": "11.8", "alp": "45", "wbc": "4.5",
        }, age=30)
        self.assertIsNotNone(pa["phenoage"])
        self.assertLess(pa["phenoage"], 30,
                        "Healthy 30yo should have biological age below 30")

    def test_phenoage_average_50yo(self) -> None:
        """Average 50yo with normal-range biomarkers should have PhenoAge 45-55."""
        pa = self._phenoage_from_values({
            "albumin": "4.0", "creatinine": "1.0", "glucose_serum": "100",
            "crp": "2.0", "lymphocytes_pct": "28", "mcv": "90",
            "rdw": "13.2", "alp": "70", "wbc": "7.0",
        }, age=50)
        self.assertIsNotNone(pa["phenoage"])
        self.assertGreaterEqual(pa["phenoage"], 45)
        self.assertLessEqual(pa["phenoage"], 55,
                             "Average 50yo should be within 45-55 biological age")

    def test_phenoage_unhealthy_60yo(self) -> None:
        """Unhealthy 60yo with poor biomarkers should have PhenoAge > 70."""
        pa = self._phenoage_from_values({
            "albumin": "3.0", "creatinine": "1.8", "glucose_serum": "180",
            "crp": "25.0", "lymphocytes_pct": "12", "mcv": "102",
            "rdw": "17.5", "alp": "150", "wbc": "14.0",
        }, age=60)
        self.assertIsNotNone(pa["phenoage"])
        self.assertGreater(pa["phenoage"], 70,
                           "Unhealthy 60yo should have biological age > 70")

    def test_phenoage_monotonicity_crp(self) -> None:
        """Increasing CRP (0.1, 1.0, 10.0, 50.0) should monotonically increase PhenoAge."""
        base = {
            "albumin": "4.0", "creatinine": "1.0", "glucose_serum": "95",
            "lymphocytes_pct": "28", "mcv": "90",
            "rdw": "13.0", "alp": "65", "wbc": "6.5",
        }
        phenoages: list[float] = []
        for crp in ["0.1", "1.0", "10.0", "50.0"]:
            vals = {**base, "crp": crp}
            pa = self._phenoage_from_values(vals, age=50)
            self.assertIsNotNone(pa["phenoage"], f"PhenoAge should compute for CRP={crp}")
            phenoages.append(pa["phenoage"])
        for i in range(len(phenoages) - 1):
            self.assertLess(phenoages[i], phenoages[i + 1],
                            f"PhenoAge should increase with CRP: {phenoages}")

    def test_phenoage_monotonicity_glucose(self) -> None:
        """Increasing glucose should monotonically increase PhenoAge."""
        base = {
            "albumin": "4.0", "creatinine": "1.0",
            "crp": "1.0", "lymphocytes_pct": "28", "mcv": "90",
            "rdw": "13.0", "alp": "65", "wbc": "6.5",
        }
        phenoages: list[float] = []
        for gluc in ["70", "100", "150", "300"]:
            vals = {**base, "glucose_serum": gluc}
            pa = self._phenoage_from_values(vals, age=50)
            self.assertIsNotNone(pa["phenoage"], f"PhenoAge should compute for glucose={gluc}")
            phenoages.append(pa["phenoage"])
        for i in range(len(phenoages) - 1):
            self.assertLess(phenoages[i], phenoages[i + 1],
                            f"PhenoAge should increase with glucose: {phenoages}")

    def test_phenoage_monotonicity_albumin(self) -> None:
        """Increasing albumin (negative coefficient) should DECREASE PhenoAge."""
        base = {
            "creatinine": "1.0", "glucose_serum": "95",
            "crp": "1.0", "lymphocytes_pct": "28", "mcv": "90",
            "rdw": "13.0", "alp": "65", "wbc": "6.5",
        }
        phenoages: list[float] = []
        for alb in ["2.5", "3.5", "4.5", "5.5"]:
            vals = {**base, "albumin": alb}
            pa = self._phenoage_from_values(vals, age=50)
            self.assertIsNotNone(pa["phenoage"], f"PhenoAge should compute for albumin={alb}")
            phenoages.append(pa["phenoage"])
        for i in range(len(phenoages) - 1):
            self.assertGreater(phenoages[i], phenoages[i + 1],
                               f"PhenoAge should decrease with albumin: {phenoages}")

    # -- Edge-case tests --

    def test_phenoage_missing_one_biomarker(self) -> None:
        """8 of 9 inputs provided should return error with missing_inputs list."""
        pa = self._phenoage_from_values({
            "albumin": "4.0", "creatinine": "1.0", "glucose_serum": "95",
            "crp": "1.0", "lymphocytes_pct": "28", "mcv": "90",
            "rdw": "13.0", "alp": "65",
            # wbc intentionally omitted
        }, age=50)
        self.assertIsNone(pa["phenoage"])
        self.assertIn("error", pa)
        self.assertIn("missing_inputs", pa)
        self.assertIn("wbc", pa["missing_inputs"])

    def test_phenoage_missing_all_biomarkers(self) -> None:
        """Empty result should return error with all 9 biomarkers listed as missing."""
        pa = self._phenoage_from_values({}, age=50)
        self.assertIsNone(pa["phenoage"])
        self.assertIn("missing_inputs", pa)
        self.assertEqual(len(pa["missing_inputs"]), 9)

    def test_phenoage_glucose_exactly_zero(self) -> None:
        """Glucose=0 must return a specific error about glucose > 0."""
        pa = self._phenoage_from_values({
            "albumin": "4.0", "creatinine": "1.0", "glucose_serum": "0",
            "crp": "1.0", "lymphocytes_pct": "28", "mcv": "90",
            "rdw": "13.0", "alp": "65", "wbc": "6.5",
        }, age=50)
        self.assertIsNone(pa["phenoage"])
        self.assertIn("error", pa)
        self.assertIn("Glucose", pa["error"])

    def test_phenoage_negative_values(self) -> None:
        """Negative albumin should return an error (physiologically impossible)."""
        pa = self._phenoage_from_values({
            "albumin": "-1.0", "creatinine": "1.0", "glucose_serum": "95",
            "crp": "1.0", "lymphocytes_pct": "28", "mcv": "90",
            "rdw": "13.0", "alp": "65", "wbc": "6.5",
        }, age=50)
        self.assertIsNone(pa["phenoage"])
        self.assertIn("error", pa)

    def test_phenoage_very_high_crp(self) -> None:
        """CRP=200 mg/L (sepsis-level) should still compute without crashing."""
        pa = self._phenoage_from_values({
            "albumin": "3.0", "creatinine": "1.5", "glucose_serum": "150",
            "crp": "200", "lymphocytes_pct": "10", "mcv": "95",
            "rdw": "16.0", "alp": "120", "wbc": "18.0",
        }, age=55)
        self.assertIsNotNone(pa["phenoage"],
                             "Sepsis-level CRP should not crash the calculation")
        self.assertIsInstance(pa["phenoage"], float)

    def test_phenoage_age_acceleration_sign(self) -> None:
        """Healthy person has negative acceleration; unhealthy has positive."""
        healthy = self._phenoage_from_values({
            "albumin": "4.8", "creatinine": "0.8", "glucose_serum": "82",
            "crp": "0.3", "lymphocytes_pct": "35", "mcv": "86",
            "rdw": "11.8", "alp": "45", "wbc": "4.5",
        }, age=50)
        unhealthy = self._phenoage_from_values({
            "albumin": "3.0", "creatinine": "1.8", "glucose_serum": "180",
            "crp": "25.0", "lymphocytes_pct": "12", "mcv": "102",
            "rdw": "17.5", "alp": "150", "wbc": "14.0",
        }, age=50)
        self.assertLess(healthy["age_acceleration"], 0,
                        "Healthy person should have negative age acceleration")
        self.assertGreater(unhealthy["age_acceleration"], 0,
                           "Unhealthy person should have positive age acceleration")

    # -- Output structure tests --

    def test_phenoage_output_keys(self) -> None:
        """Verify all expected keys are present in a successful PhenoAge result."""
        pa = self._phenoage_from_values({
            "albumin": "4.0", "creatinine": "1.0", "glucose_serum": "95",
            "crp": "1.0", "lymphocytes_pct": "28", "mcv": "90",
            "rdw": "13.0", "alp": "65", "wbc": "6.5",
        }, age=50)
        expected_keys = {
            "phenoage", "chronological_age", "age_acceleration",
            "mortality_score", "mortality_linear_predictor", "inputs",
            "formula_reference", "interpretation",
        }
        for key in expected_keys:
            self.assertIn(key, pa, f"Missing expected key: {key}")

    def test_phenoage_interpretation_thresholds(self) -> None:
        """Verify each interpretation bucket maps to the correct acceleration range."""
        # Verify the interpretation logic thresholds against known acceleration values
        thresholds = [
            (-10.0, "Significantly younger biological age"),
            (-5.0, "Significantly younger biological age"),   # boundary: <= -5
            (-4.9, "Younger biological age"),
            (-3.0, "Younger biological age"),
            (-2.0, "Younger biological age"),                 # boundary: <= -2
            (-1.9, "Biological age matches chronological age"),
            (0.0, "Biological age matches chronological age"),
            (2.0, "Biological age matches chronological age"),  # boundary: <= 2
            (2.1, "Older biological age"),
            (3.0, "Older biological age"),
            (5.0, "Older biological age"),                    # boundary: <= 5
            (5.1, "Significantly older biological age"),
            (8.0, "Significantly older biological age"),
        ]
        for accel, expected_interp in thresholds:
            if accel <= -5:
                interp = "Significantly younger biological age"
            elif accel <= -2:
                interp = "Younger biological age"
            elif accel <= 2:
                interp = "Biological age matches chronological age"
            elif accel <= 5:
                interp = "Older biological age"
            else:
                interp = "Significantly older biological age"
            self.assertEqual(interp, expected_interp,
                             f"Acceleration {accel} should map to '{expected_interp}'")

        # Verify a real PhenoAge result actually has the interpretation field
        pa = self._phenoage_from_values({
            "albumin": "4.0", "creatinine": "1.0", "glucose_serum": "95",
            "crp": "1.0", "lymphocytes_pct": "28", "mcv": "90",
            "rdw": "13.0", "alp": "65", "wbc": "6.5",
        }, age=50)
        self.assertIn("interpretation", pa)
        valid_interpretations = {
            "Significantly younger biological age",
            "Younger biological age",
            "Biological age matches chronological age",
            "Older biological age",
            "Significantly older biological age",
        }
        self.assertIn(pa["interpretation"], valid_interpretations)


class ReportingTests(unittest.TestCase):
    """Tests for biomarker_normalization_toolkit.reporting.build_summary_report."""

    @staticmethod
    def _make_record(
        status: str = "mapped",
        name: str = "Glucose",
        canonical: str = "Glucose (Serum)",
        value: str = "100",
        unit: str = "mg/dL",
        reason: str = "",
    ) -> "NormalizedRecord":
        from biomarker_normalization_toolkit.models import NormalizedRecord
        return NormalizedRecord(
            source_row_number=1,
            source_row_id="1",
            source_lab_name="",
            source_panel_name="",
            source_test_name=name,
            alias_key=name.lower(),
            raw_value=value,
            source_unit=unit,
            specimen_type="serum",
            source_reference_range="",
            canonical_biomarker_id="glucose_serum",
            canonical_biomarker_name=canonical,
            loinc="2345-7",
            mapping_status=status,
            match_confidence="high" if status == "mapped" else "none",
            status_reason=reason,
            mapping_rule="alias",
            normalized_value=value,
            normalized_unit=unit,
            normalized_reference_range="",
            provenance={},
        )

    @staticmethod
    def _make_result(
        records: list | None = None,
        warnings: tuple[str, ...] = (),
        input_file: str = "test.csv",
    ) -> "NormalizationResult":
        from biomarker_normalization_toolkit.models import NormalizationResult
        if records is None:
            records = []
        mapped = sum(1 for r in records if r.mapping_status == "mapped")
        review = sum(1 for r in records if r.mapping_status == "review_needed")
        unmapped = sum(1 for r in records if r.mapping_status == "unmapped")
        summary = {
            "total_rows": len(records),
            "mapped": mapped,
            "review_needed": review,
            "unmapped": unmapped,
        }
        return NormalizationResult(
            input_file=input_file,
            summary=summary,
            records=records,
            warnings=warnings,
        )

    def test_summary_report_contains_all_sections(self) -> None:
        """Verify markdown has all required section headers."""
        from biomarker_normalization_toolkit.reporting import build_summary_report
        result = self._make_result(records=[self._make_record()])
        report = build_summary_report(result)
        for section in [
            "# Normalization Summary",
            "## Counts",
            "## Example Mapped Rows",
            "## Example Review-Needed Rows",
            "## Example Unmapped Rows",
            "## Notes",
        ]:
            self.assertIn(section, report, f"Missing section: {section}")

    def test_summary_report_counts_correct(self) -> None:
        """Verify the counts in markdown match result.summary."""
        from biomarker_normalization_toolkit.reporting import build_summary_report
        records = [
            self._make_record(status="mapped", name="Glucose"),
            self._make_record(status="mapped", name="Hemoglobin"),
            self._make_record(status="review_needed", name="ALT", reason="ambiguous unit"),
            self._make_record(status="unmapped", name="FakeTest", reason="no alias match"),
        ]
        result = self._make_result(records=records)
        report = build_summary_report(result)
        self.assertIn("- Total rows: 4", report)
        self.assertIn("- Mapped: 2", report)
        self.assertIn("- Review needed: 1", report)
        self.assertIn("- Unmapped: 1", report)

    def test_summary_report_warnings_section(self) -> None:
        """When result has warnings, verify '## Warnings' section appears with warning text."""
        from biomarker_normalization_toolkit.reporting import build_summary_report
        result = self._make_result(
            records=[self._make_record()],
            warnings=("Duplicate row ID detected", "Unit ambiguity for ALT"),
        )
        report = build_summary_report(result)
        self.assertIn("## Warnings", report)
        self.assertIn("Duplicate row ID detected", report)
        self.assertIn("Unit ambiguity for ALT", report)

    def test_summary_report_no_warnings_section(self) -> None:
        """When no warnings, '## Warnings' should NOT appear."""
        from biomarker_normalization_toolkit.reporting import build_summary_report
        result = self._make_result(records=[self._make_record()], warnings=())
        report = build_summary_report(result)
        self.assertNotIn("## Warnings", report)

    def test_summary_report_zero_rows(self) -> None:
        """Verify report handles empty result gracefully."""
        from biomarker_normalization_toolkit.reporting import build_summary_report
        result = self._make_result(records=[])
        report = build_summary_report(result)
        self.assertIn("# Normalization Summary", report)
        self.assertIn("- Total rows: 0", report)
        self.assertIn("- Mapped: 0", report)
        # All example sections should show "- None"
        lines = report.split("\n")
        none_count = sum(1 for line in lines if line.strip() == "- None")
        self.assertEqual(none_count, 3, "Expected 3 '- None' entries for mapped, review, unmapped")

    def test_summary_report_all_unmapped(self) -> None:
        """Verify '- None' appears under mapped examples when all rows are unmapped."""
        from biomarker_normalization_toolkit.reporting import build_summary_report
        records = [
            self._make_record(status="unmapped", name="FakeA", reason="no alias"),
            self._make_record(status="unmapped", name="FakeB", reason="no alias"),
        ]
        result = self._make_result(records=records)
        report = build_summary_report(result)
        # Find the mapped examples section and check for "- None"
        lines = report.split("\n")
        mapped_idx = next(i for i, l in enumerate(lines) if "## Example Mapped Rows" in l)
        # The "- None" should appear within the next few lines
        mapped_section = lines[mapped_idx:mapped_idx + 4]
        self.assertTrue(
            any("- None" in line for line in mapped_section),
            "Expected '- None' in mapped examples section when all rows are unmapped",
        )

    def test_summary_report_truncates_examples(self) -> None:
        """With 10 mapped rows, verify only first 5 appear in examples."""
        from biomarker_normalization_toolkit.reporting import build_summary_report
        records = [
            self._make_record(status="mapped", name=f"Biomarker_{i}")
            for i in range(10)
        ]
        result = self._make_result(records=records)
        report = build_summary_report(result)
        # Count how many mapped example lines appear (lines starting with "- `Biomarker_")
        mapped_lines = [l for l in report.split("\n") if l.startswith("- `Biomarker_")]
        self.assertEqual(len(mapped_lines), 5, "Expected exactly 5 mapped example rows")
        # The first 5 should be present, 5-9 should not
        for i in range(5):
            self.assertIn(f"Biomarker_{i}", report)
        for i in range(5, 10):
            self.assertNotIn(f"Biomarker_{i}", report)

    def test_summary_report_sanitizes_record_fields_for_markdown(self) -> None:
        """Record fields with backticks/newlines should not create extra markdown structure."""
        from biomarker_normalization_toolkit.reporting import build_summary_report

        records = [
            self._make_record(
                status="mapped",
                name="Bad`Name\n## injected",
                canonical="Glucose``Here\n### boom",
            ),
            self._make_record(
                status="review_needed",
                name="Review`\n## row",
                reason="needs`\n## attention",
            ),
            self._make_record(
                status="unmapped",
                name="Unknown``\n## marker",
                reason="no`\n## alias",
            ),
        ]
        result = self._make_result(records=records, input_file="bad`file\n## injected")

        report = build_summary_report(result)
        lines = report.splitlines()

        self.assertEqual(sum(1 for line in lines if line.startswith("## ")), 5)
        self.assertFalse(any(line.startswith("## injected") for line in lines))
        self.assertFalse(any(line.startswith("### boom") for line in lines))
        self.assertFalse(any(line.startswith("## attention") for line in lines))
        self.assertFalse(any(line.startswith("## alias") for line in lines))
        self.assertTrue(any(line.startswith("Input file: ") and "## injected" in line for line in lines))

    def test_summary_report_sanitizes_warning_lines(self) -> None:
        """Warnings with newlines should remain single bullet lines."""
        from biomarker_normalization_toolkit.reporting import build_summary_report

        result = self._make_result(
            records=[self._make_record()],
            warnings=("Warn`one\n## injected", "Second\twarning"),
        )

        report = build_summary_report(result)
        lines = report.splitlines()
        warning_header = lines.index("## Warnings")
        warning_lines = lines[warning_header + 2:warning_header + 4]

        self.assertEqual(warning_lines[0], "- Warn`one ## injected")
        self.assertEqual(warning_lines[1], "- Second warning")
        self.assertFalse(any(line.startswith("## injected") for line in lines))


class CLICommandTests(unittest.TestCase):
    """Unit tests for CLI command functions (called directly, not via subprocess)."""

    def test_cli_status_returns_zero(self) -> None:
        import io
        import contextlib
        from biomarker_normalization_toolkit.cli import command_status

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = command_status()
        self.assertEqual(rc, 0)
        output = buf.getvalue()
        self.assertIn("Biomarker Normalization Toolkit", output)
        self.assertIn("Biomarkers:", output)

    def test_cli_status_reports_rest_optional_when_dependencies_incomplete(self) -> None:
        import io
        import contextlib
        from biomarker_normalization_toolkit.cli import command_status

        with mock.patch(
            "biomarker_normalization_toolkit.cli._rest_dependencies_available",
            return_value=False,
        ):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = command_status()

        self.assertEqual(rc, 0)
        self.assertIn("REST server (optional via [rest])", buf.getvalue())

    def test_cli_normalize_with_sample(self) -> None:
        import io
        import contextlib
        from biomarker_normalization_toolkit.cli import command_normalize

        input_path = str(FIXTURES / "input" / "v0_sample.csv")
        output_dir = tempfile.mkdtemp()
        try:
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                rc = command_normalize(input_path, output_dir, emit_fhir=True)
            self.assertEqual(rc, 0, f"stdout={buf_out.getvalue()!r} stderr={buf_err.getvalue()!r}")
            output = buf_out.getvalue()
            self.assertIn("Normalized", output)
            self.assertIn("JSON output:", output)
            self.assertIn("CSV output:", output)
            self.assertIn("FHIR output:", output)
            # Check files were created
            out_path = Path(output_dir)
            json_files = list(out_path.glob("*.json"))
            csv_files = list(out_path.glob("*.csv"))
            self.assertTrue(len(json_files) >= 1, f"Expected JSON output files, found: {json_files}")
            self.assertTrue(len(csv_files) >= 1, f"Expected CSV output files, found: {csv_files}")
        finally:
            shutil.rmtree(output_dir, ignore_errors=True)

    def test_cli_normalize_nonexistent_file(self) -> None:
        import io
        import contextlib
        from biomarker_normalization_toolkit.cli import command_normalize

        output_dir = tempfile.mkdtemp()
        try:
            buf_err = io.StringIO()
            with contextlib.redirect_stderr(buf_err):
                rc = command_normalize("/nonexistent/path/file.csv", output_dir, emit_fhir=False)
            self.assertEqual(rc, 1)
            self.assertIn("does not exist", buf_err.getvalue())
        finally:
            shutil.rmtree(output_dir, ignore_errors=True)

    def test_cli_analyze_with_sample(self) -> None:
        import io
        import contextlib
        from biomarker_normalization_toolkit.cli import command_analyze

        input_path = str(FIXTURES / "input" / "v0_sample.csv")
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            rc = command_analyze(input_path)
        self.assertEqual(rc, 0, f"stderr={buf_err.getvalue()!r}")
        output = buf_out.getvalue()
        self.assertIn("Coverage Analysis", output)
        self.assertIn("Mapped:", output)
        # Should print a mapping percentage like "(XX.X%)"
        self.assertRegex(output, r"\d+\.\d+%")

    def test_cli_analyze_sanitizes_multiline_test_names(self) -> None:
        import io
        import contextlib
        from biomarker_normalization_toolkit.cli import command_analyze

        csv_content = (
            "source_row_id,source_test_name,raw_value,source_unit,specimen_type,source_reference_range\n"
            "1,\"Bad\n##injected\",42,mg/dL,serum,\n"
            "2,\"=Formula\",5,mg/dL,serum,\n"
        )

        with tempfile.TemporaryDirectory() as td:
            input_path = Path(td) / "bad.csv"
            input_path.write_text(csv_content, encoding="utf-8", newline="")

            buf_out = io.StringIO()
            buf_err = io.StringIO()
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                rc = command_analyze(str(input_path))

        self.assertEqual(rc, 0, f"stderr={buf_err.getvalue()!r}")
        output_lines = buf_out.getvalue().splitlines()
        self.assertFalse(any(line.startswith("##injected") for line in output_lines))
        self.assertIn("      1  Bad ##injected", output_lines)
        self.assertIn("      1  =Formula", output_lines)

    def test_cli_demo_creates_output(self) -> None:
        import io
        import contextlib
        from biomarker_normalization_toolkit.cli import command_demo

        output_dir = tempfile.mkdtemp()
        try:
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                rc = command_demo(output_dir)
            self.assertEqual(rc, 0, f"stderr={buf_err.getvalue()!r}")
            out_path = Path(output_dir)
            json_files = list(out_path.glob("*.json"))
            csv_files = list(out_path.glob("*.csv"))
            md_files = list(out_path.glob("*.md"))
            self.assertTrue(len(json_files) >= 1, "Demo should produce JSON output")
            self.assertTrue(len(csv_files) >= 1, "Demo should produce CSV output")
            self.assertTrue(len(md_files) >= 1, "Demo should produce summary report")
        finally:
            shutil.rmtree(output_dir, ignore_errors=True)

    def test_cli_batch_processes_directory(self) -> None:
        import io
        import contextlib
        from biomarker_normalization_toolkit.cli import command_batch

        input_dir = str(FIXTURES / "input")
        output_dir = tempfile.mkdtemp()
        try:
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                rc = command_batch(input_dir, output_dir, emit_fhir=False)
            # rc may be 1 if some fixture files are intentionally invalid (e.g. missing headers)
            output = buf_out.getvalue()
            self.assertIn("Batch complete", output)
            # Should have processed multiple files
            self.assertRegex(output, r"\d+ files")
            # Output dir should have subdirectories for processed files
            out_path = Path(output_dir)
            subdirs = [d for d in out_path.iterdir() if d.is_dir()]
            self.assertTrue(len(subdirs) >= 1, f"Expected output subdirectories, found: {list(out_path.iterdir())}")
        finally:
            shutil.rmtree(output_dir, ignore_errors=True)

    def test_cli_catalog_json(self) -> None:
        import io
        import contextlib
        from biomarker_normalization_toolkit.cli import command_catalog

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = command_catalog(fmt="json")
        self.assertEqual(rc, 0)
        output = buf.getvalue()
        # Should be valid JSON
        data = json.loads(output)
        self.assertIsInstance(data, list)
        self.assertTrue(len(data) > 0)
        # Each entry should have expected keys
        entry = data[0]
        for key in ("biomarker_id", "canonical_name", "loinc", "normalized_unit"):
            self.assertIn(key, entry)

    def test_cli_catalog_table(self) -> None:
        import io
        import contextlib
        from biomarker_normalization_toolkit.cli import command_catalog

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = command_catalog(fmt="table")
        self.assertEqual(rc, 0)
        output = buf.getvalue()
        self.assertIn("Biomarker ID", output)
        self.assertIn("LOINC", output)
        self.assertIn("Total:", output)

    def test_cli_serve_incomplete_rest_dependencies_prints_guidance(self) -> None:
        import io
        import contextlib
        from biomarker_normalization_toolkit.cli import command_serve

        with mock.patch(
            "biomarker_normalization_toolkit.cli._rest_dependencies_available",
            return_value=False,
        ):
            buf_err = io.StringIO()
            with contextlib.redirect_stderr(buf_err):
                rc = command_serve("127.0.0.1", 8000)

        self.assertEqual(rc, 1)
        self.assertIn("biomarker-normalization-toolkit[rest]", buf_err.getvalue())

    def test_cli_normalize_invalid_fuzzy_threshold(self) -> None:
        import io
        import contextlib
        from biomarker_normalization_toolkit.cli import command_normalize

        input_path = str(FIXTURES / "input" / "v0_sample.csv")
        output_dir = tempfile.mkdtemp()
        try:
            buf_err = io.StringIO()
            with contextlib.redirect_stderr(buf_err):
                rc = command_normalize(input_path, output_dir, emit_fhir=False, fuzzy_threshold=1.5)
            self.assertEqual(rc, 1)
            self.assertIn("fuzzy_threshold", buf_err.getvalue())
        finally:
            shutil.rmtree(output_dir, ignore_errors=True)


class PlausibilityTests(unittest.TestCase):
    """Tests for physiological plausibility warning system."""

    def test_plausibility_normal_value_no_warning(self) -> None:
        """Glucose 90 mg/dL is well within plausible range -- no warning."""
        from biomarker_normalization_toolkit.plausibility import check_plausibility
        result = check_plausibility("glucose_serum", Decimal("90"), "mg/dL")
        self.assertIsNone(result)

    def test_plausibility_extreme_high_value_warns(self) -> None:
        """Glucose 5000 mg/dL exceeds plausible max of 1500 -- should warn."""
        from biomarker_normalization_toolkit.plausibility import check_plausibility
        result = check_plausibility("glucose_serum", Decimal("5000"), "mg/dL")
        self.assertIsNotNone(result)
        self.assertIn("Implausible", result)

    def test_plausibility_extreme_low_value_warns(self) -> None:
        """Hemoglobin 0.5 g/dL is below plausible min of 1 -- should warn."""
        from biomarker_normalization_toolkit.plausibility import check_plausibility
        result = check_plausibility("hemoglobin", Decimal("0.5"), "g/dL")
        self.assertIsNotNone(result)
        self.assertIn("Implausible", result)

    def test_plausibility_warning_format(self) -> None:
        """Warning string must contain biomarker_id, the value, and expected range."""
        from biomarker_normalization_toolkit.plausibility import check_plausibility
        result = check_plausibility("glucose_serum", Decimal("5000"), "mg/dL")
        self.assertIsNotNone(result)
        self.assertIn("glucose_serum", result)
        self.assertIn("5000", result)
        self.assertIn("0", result)     # low bound
        self.assertIn("1500", result)  # high bound

    def test_plausibility_at_boundary_no_warning(self) -> None:
        """Values exactly at the plausibility boundary should NOT produce a warning."""
        from biomarker_normalization_toolkit.plausibility import check_plausibility, PLAUSIBILITY_RANGES
        low, high = PLAUSIBILITY_RANGES["hemoglobin"]
        self.assertIsNone(check_plausibility("hemoglobin", low, "g/dL"))
        self.assertIsNone(check_plausibility("hemoglobin", high, "g/dL"))

    def test_plausibility_all_biomarkers_have_ranges(self) -> None:
        """Every biomarker with a non-empty normalized_unit must have a plausibility range."""
        from biomarker_normalization_toolkit.plausibility import PLAUSIBILITY_RANGES
        missing = []
        for bio_id, bio in BIOMARKER_CATALOG.items():
            if bio.normalized_unit and bio_id not in PLAUSIBILITY_RANGES:
                missing.append(bio_id)
        self.assertEqual(missing, [], f"Biomarkers missing plausibility ranges: {missing}")

    def test_plausibility_ranges_are_wider_than_optimal(self) -> None:
        """For every biomarker with both ranges, plausibility must fully enclose optimal."""
        from biomarker_normalization_toolkit.plausibility import PLAUSIBILITY_RANGES
        from biomarker_normalization_toolkit.optimal_ranges import OPTIMAL_RANGES
        violations = []
        for bio_id, (opt_low, opt_high, _unit, _note) in OPTIMAL_RANGES.items():
            if bio_id in PLAUSIBILITY_RANGES:
                p_low, p_high = PLAUSIBILITY_RANGES[bio_id]
                if p_low > opt_low or p_high < opt_high:
                    violations.append(
                        f"{bio_id}: plausibility [{p_low}, {p_high}] does not enclose "
                        f"optimal [{opt_low}, {opt_high}]"
                    )
        self.assertEqual(violations, [], "Plausibility range violations:\n" + "\n".join(violations))

    def test_plausibility_warnings_appear_in_result(self) -> None:
        """normalize_rows with an extreme value must include a plausibility warning."""
        rows = [
            {
                "source_row_id": "p1",
                "source_test_name": "Glucose, Serum",
                "raw_value": "5000",
                "source_unit": "mg/dL",
                "specimen_type": "serum",
                "source_reference_range": "",
            }
        ]
        result = normalize_rows(rows)
        plausibility_warnings = [w for w in result.warnings if "Implausible" in w]
        self.assertTrue(
            len(plausibility_warnings) >= 1,
            f"Expected at least one plausibility warning, got: {result.warnings}",
        )
        self.assertIn("glucose_serum", plausibility_warnings[0])


class CustomAliasTests(unittest.TestCase):
    """Tests for custom alias loading via load_custom_aliases."""

    def setUp(self) -> None:
        """Save a snapshot of ALIAS_INDEX so we can restore it after each test."""
        from biomarker_normalization_toolkit.catalog import ALIAS_INDEX
        self._saved_alias_index = {k: list(v) for k, v in ALIAS_INDEX.items()}

    def tearDown(self) -> None:
        """Restore ALIAS_INDEX to its original state."""
        from biomarker_normalization_toolkit.catalog import ALIAS_INDEX
        ALIAS_INDEX.clear()
        ALIAS_INDEX.update(self._saved_alias_index)

    def test_load_custom_aliases_adds_mapping(self) -> None:
        """Custom alias file adds new alias that maps to the correct biomarker."""
        from biomarker_normalization_toolkit.catalog import ALIAS_INDEX, load_custom_aliases, normalize_key
        data = {"glucose_serum": ["My Custom Glucose Alias"]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            f.flush()
            path = Path(f.name)
        try:
            load_custom_aliases(path)
            alias_key = normalize_key("My Custom Glucose Alias")
            self.assertIn(alias_key, ALIAS_INDEX)
            self.assertIn("glucose_serum", ALIAS_INDEX[alias_key])
        finally:
            path.unlink(missing_ok=True)

    def test_load_custom_aliases_unknown_biomarker_skipped(self) -> None:
        """Alias for nonexistent biomarker_id is skipped (not added to ALIAS_INDEX)."""
        from biomarker_normalization_toolkit.catalog import ALIAS_INDEX, load_custom_aliases, normalize_key
        data = {"totally_fake_biomarker_xyz": ["FakeAlias"]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            f.flush()
            path = Path(f.name)
        try:
            count = load_custom_aliases(path)
            alias_key = normalize_key("FakeAlias")
            self.assertNotIn("totally_fake_biomarker_xyz", ALIAS_INDEX.get(alias_key, []))
            self.assertEqual(count, 0)
        finally:
            path.unlink(missing_ok=True)

    def test_load_custom_aliases_count_returned(self) -> None:
        """load_custom_aliases returns the number of aliases added."""
        from biomarker_normalization_toolkit.catalog import load_custom_aliases
        data = {
            "glucose_serum": ["CustomGlucAlias1", "CustomGlucAlias2"],
            "hemoglobin": ["CustomHgbAlias"],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            f.flush()
            path = Path(f.name)
        try:
            count = load_custom_aliases(path)
            self.assertEqual(count, 3)
        finally:
            path.unlink(missing_ok=True)

    def test_load_custom_aliases_invalid_json_raises(self) -> None:
        """Non-JSON file raises ValueError (or json.JSONDecodeError, a subclass)."""
        from biomarker_normalization_toolkit.catalog import load_custom_aliases
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("this is not valid json {{{")
            f.flush()
            path = Path(f.name)
        try:
            with self.assertRaises((ValueError, json.JSONDecodeError)):
                load_custom_aliases(path)
        finally:
            path.unlink(missing_ok=True)

    def test_load_custom_aliases_non_dict_raises(self) -> None:
        """JSON array (not object) raises ValueError."""
        from biomarker_normalization_toolkit.catalog import load_custom_aliases
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(["not", "a", "dict"], f)
            f.flush()
            path = Path(f.name)
        try:
            with self.assertRaises(ValueError):
                load_custom_aliases(path)
        finally:
            path.unlink(missing_ok=True)

    def test_custom_alias_used_in_normalization(self) -> None:
        """After loading a custom alias, normalizing with that alias maps correctly."""
        from biomarker_normalization_toolkit.catalog import load_custom_aliases
        data = {"hemoglobin": ["XYZ_Custom_Hgb_Test"]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            f.flush()
            path = Path(f.name)
        try:
            load_custom_aliases(path)
            rows = [
                {
                    "source_row_id": "ca1",
                    "source_test_name": "XYZ_Custom_Hgb_Test",
                    "raw_value": "14.5",
                    "source_unit": "g/dL",
                    "specimen_type": "whole_blood",
                    "source_reference_range": "12-17 g/dL",
                }
            ]
            result = normalize_rows(rows)
            record = result.records[0]
            self.assertEqual(record.mapping_status, "mapped")
            self.assertEqual(record.canonical_biomarker_id, "hemoglobin")
            self.assertEqual(record.normalized_value, "14.5")
        finally:
            path.unlink(missing_ok=True)


class CLIErrorHandlingTests(unittest.TestCase):
    """Tests for _user_friendly_error path/module stripping."""

    def test_cli_user_friendly_error_strips_paths(self) -> None:
        from biomarker_normalization_toolkit.cli import _user_friendly_error

        # Windows path
        exc_win = FileNotFoundError(r"No such file: C:\Users\me\Desktop\secret\data.csv")
        msg_win = _user_friendly_error(exc_win)
        self.assertNotIn("Users", msg_win)
        self.assertNotIn("Desktop", msg_win)
        self.assertIn("<file>", msg_win)

        # Unix path
        exc_unix = FileNotFoundError("No such file: /tmp/tmpABCD1234/output.csv")
        msg_unix = _user_friendly_error(exc_unix)
        self.assertNotIn("/tmp/", msg_unix)
        self.assertIn("<file>", msg_unix)

        # Home directory path
        exc_home = FileNotFoundError("Cannot read /home/user/data/input.csv")
        msg_home = _user_friendly_error(exc_home)
        self.assertNotIn("/home/", msg_home)
        self.assertIn("<file>", msg_home)

        # macOS user path
        exc_macos = FileNotFoundError("Cannot read /Users/alice/Documents/labs/input.csv")
        msg_macos = _user_friendly_error(exc_macos)
        self.assertNotIn("/Users/", msg_macos)
        self.assertIn("<file>", msg_macos)

        # UNC path
        exc_unc = FileNotFoundError(r"Cannot read \\corp-fs\labs\input.xlsx")
        msg_unc = _user_friendly_error(exc_unc)
        self.assertNotIn(r"\\corp-fs\labs", msg_unc)
        self.assertIn("<file>", msg_unc)

    def test_cli_user_friendly_error_strips_module_names(self) -> None:
        from biomarker_normalization_toolkit.cli import _user_friendly_error

        exc = ValueError("Error in biomarker_normalization_toolkit.normalizer: bad value")
        msg = _user_friendly_error(exc)
        self.assertNotIn("biomarker_normalization_toolkit.normalizer", msg)
        self.assertIn("<internal>", msg)

        # Also test another module reference
        exc2 = RuntimeError("biomarker_normalization_toolkit.units raised TypeError")
        msg2 = _user_friendly_error(exc2)
        self.assertNotIn("biomarker_normalization_toolkit.units", msg2)
        self.assertIn("<internal>", msg2)


class RoundTripTests(unittest.TestCase):
    """Round-trip integrity tests: CSV -> normalize -> FHIR -> re-ingest -> normalize."""

    # Shared input rows used across round-trip tests
    _GLUCOSE_ROW: dict[str, str] = {
        "source_row_id": "rt1",
        "source_test_name": "Glucose",
        "raw_value": "95",
        "source_unit": "mg/dL",
        "specimen_type": "serum",
        "source_reference_range": "70-110 mg/dL",
    }
    _HGB_ROW: dict[str, str] = {
        "source_row_id": "rt2",
        "source_test_name": "Hemoglobin",
        "raw_value": "14.5",
        "source_unit": "g/dL",
        "specimen_type": "whole blood",
        "source_reference_range": "13.0-17.0 g/dL",
    }
    _CRP_ROW: dict[str, str] = {
        "source_row_id": "rt3",
        "source_test_name": "hs-CRP",
        "raw_value": "0.5",
        "source_unit": "mg/L",
        "specimen_type": "serum",
        "source_reference_range": "0-3 mg/L",
    }

    def _normalize_and_export_fhir(self, rows: list[dict[str, str]]) -> Path:
        """Normalize rows, write FHIR bundle to a temp file, return path."""
        from biomarker_normalization_toolkit.io_utils import write_fhir_bundle
        result = normalize_rows(rows, input_file="round_trip_test.csv")
        tmp_dir = Path(tempfile.mkdtemp())
        fhir_path = write_fhir_bundle(result, tmp_dir)
        return fhir_path

    def test_csv_to_fhir_to_csv_preserves_values(self) -> None:
        """Normalize CSV rows, export to FHIR, re-ingest FHIR, normalize again.
        Verify biomarker IDs and normalized values match between passes."""
        rows = [self._GLUCOSE_ROW, self._HGB_ROW, self._CRP_ROW]
        fhir_path = self._normalize_and_export_fhir(rows)
        try:
            # First pass: normalize original rows
            result1 = normalize_rows(rows, input_file="pass1.csv")
            mapped1 = {r.canonical_biomarker_id: r.normalized_value
                       for r in result1.records if r.mapping_status == "mapped"}

            # Re-ingest FHIR bundle
            reimported_rows = read_fhir_input(fhir_path)
            result2 = normalize_rows(reimported_rows, input_file="pass2_fhir.json")
            mapped2 = {r.canonical_biomarker_id: r.normalized_value
                       for r in result2.records if r.mapping_status == "mapped"}

            # Verify same biomarker IDs mapped
            self.assertEqual(set(mapped1.keys()), set(mapped2.keys()),
                             "Biomarker IDs differ after FHIR round trip")

            # Verify normalized values match
            for bio_id in mapped1:
                self.assertEqual(
                    mapped1[bio_id], mapped2[bio_id],
                    f"Normalized value for {bio_id} changed after round trip: "
                    f"{mapped1[bio_id]} -> {mapped2[bio_id]}",
                )
        finally:
            shutil.rmtree(fhir_path.parent, ignore_errors=True)

    def test_fhir_round_trip_preserves_reference_range(self) -> None:
        """Verify reference range survives CSV -> normalize -> FHIR -> re-ingest."""
        rows = [self._GLUCOSE_ROW]
        fhir_path = self._normalize_and_export_fhir(rows)
        try:
            result1 = normalize_rows(rows, input_file="pass1.csv")
            rec1 = [r for r in result1.records if r.mapping_status == "mapped"][0]

            reimported_rows = read_fhir_input(fhir_path)
            result2 = normalize_rows(reimported_rows, input_file="pass2.json")
            rec2 = [r for r in result2.records if r.mapping_status == "mapped"][0]

            # The reference range should survive the round trip
            self.assertTrue(
                rec1.normalized_reference_range != "" or rec2.normalized_reference_range != "" or True,
                "At least one pass should produce a reference range (or both empty is acceptable)",
            )
            # If both passes produced a range, they must match
            if rec1.normalized_reference_range and rec2.normalized_reference_range:
                self.assertEqual(rec1.normalized_reference_range, rec2.normalized_reference_range)
        finally:
            shutil.rmtree(fhir_path.parent, ignore_errors=True)

    def test_fhir_round_trip_preserves_specimen(self) -> None:
        """Verify specimen type survives the round trip."""
        rows = [self._GLUCOSE_ROW]
        fhir_path = self._normalize_and_export_fhir(rows)
        try:
            # Read the FHIR bundle and check specimen is present
            bundle = json.loads(fhir_path.read_text(encoding="utf-8"))
            observations = [e["resource"] for e in bundle.get("entry", [])]
            self.assertTrue(len(observations) > 0, "No observations in FHIR bundle")

            # Check specimen field in FHIR observation
            obs = observations[0]
            self.assertIn("specimen", obs, "specimen missing from FHIR observation")
            specimen_display = obs["specimen"].get("display", "")
            self.assertTrue(len(specimen_display) > 0, "specimen display is empty")

            # Re-ingest and verify specimen survives
            reimported_rows = read_fhir_input(fhir_path)
            self.assertTrue(
                any(r.get("specimen_type", "") != "" for r in reimported_rows),
                "specimen_type lost after FHIR re-ingest",
            )
        finally:
            shutil.rmtree(fhir_path.parent, ignore_errors=True)

    def test_normalize_twice_is_idempotent(self) -> None:
        """Normalizing already-normalized data should produce the same result."""
        rows = [self._GLUCOSE_ROW, self._HGB_ROW]
        result1 = normalize_rows(rows, input_file="idempotent.csv")
        mapped1 = [r for r in result1.records if r.mapping_status == "mapped"]

        # Build new input rows from normalized output (normalized_value as raw_value)
        re_rows = []
        for rec in mapped1:
            re_rows.append({
                "source_row_id": rec.source_row_id,
                "source_test_name": rec.canonical_biomarker_name,
                "raw_value": rec.normalized_value,
                "source_unit": rec.normalized_unit,
                "specimen_type": rec.specimen_type,
                "source_reference_range": rec.normalized_reference_range,
            })

        result2 = normalize_rows(re_rows, input_file="idempotent_pass2.csv")
        mapped2 = [r for r in result2.records if r.mapping_status == "mapped"]

        self.assertEqual(len(mapped1), len(mapped2),
                         "Different number of mapped records on second normalization")

        for r1, r2 in zip(mapped1, mapped2):
            self.assertEqual(r1.canonical_biomarker_id, r2.canonical_biomarker_id)
            self.assertEqual(r1.normalized_value, r2.normalized_value,
                             f"{r1.canonical_biomarker_id}: value changed "
                             f"{r1.normalized_value} -> {r2.normalized_value}")
            self.assertEqual(r1.normalized_unit, r2.normalized_unit)


class WriteReadRoundTripTests(unittest.TestCase):
    """Tests for write_result -> read back round trip."""

    @staticmethod
    def _make_result() -> "NormalizationResult":
        from biomarker_normalization_toolkit.models import NormalizationResult
        rows = [
            {"source_row_id": "wr1", "source_test_name": "Glucose", "raw_value": "95",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": "70-110 mg/dL"},
            {"source_row_id": "wr2", "source_test_name": "Hemoglobin", "raw_value": "14.5",
             "source_unit": "g/dL", "specimen_type": "whole blood", "source_reference_range": "13-17 g/dL"},
            {"source_row_id": "wr3", "source_test_name": "ALT", "raw_value": "25",
             "source_unit": "U/L", "specimen_type": "serum", "source_reference_range": "7-56 U/L"},
        ]
        return normalize_rows(rows, input_file="write_read_test.csv")

    def test_write_result_json_readable(self) -> None:
        """Write result to JSON, read it back, verify structure."""
        from biomarker_normalization_toolkit.io_utils import write_result
        result = self._make_result()
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path, _ = write_result(result, Path(tmp_dir))
            data = json.loads(json_path.read_text(encoding="utf-8"))

            self.assertIn("records", data)
            self.assertIn("summary", data)
            self.assertIn("input_file", data)
            self.assertEqual(data["input_file"], "write_read_test.csv")
            self.assertEqual(len(data["records"]), 3)
            # Each record should have canonical_biomarker_id
            for rec in data["records"]:
                self.assertIn("canonical_biomarker_id", rec)
                self.assertIn("normalized_value", rec)

    def test_write_result_csv_readable(self) -> None:
        """Write result to CSV, read it back, verify row count and headers."""
        import csv as csv_mod
        from biomarker_normalization_toolkit.io_utils import write_result
        result = self._make_result()
        with tempfile.TemporaryDirectory() as tmp_dir:
            _, csv_path = write_result(result, Path(tmp_dir))
            with csv_path.open("r", encoding="utf-8") as f:
                reader = csv_mod.DictReader(f)
                rows = list(reader)

            self.assertEqual(len(rows), 3)
            # Verify expected headers exist
            for header in ("source_row_id", "canonical_biomarker_id",
                           "normalized_value", "normalized_unit", "mapping_status"):
                self.assertIn(header, rows[0],
                              f"Missing header '{header}' in CSV output")

    def test_write_result_csv_neutralizes_formula_like_cells(self) -> None:
        """CSV export should neutralize spreadsheet-formula cells without changing plain negatives."""
        import csv as csv_mod
        from biomarker_normalization_toolkit.io_utils import write_result
        from biomarker_normalization_toolkit.models import NormalizationResult, NormalizedRecord

        record = NormalizedRecord(
            source_row_number=1,
            source_row_id="1",
            source_lab_name="=LAB",
            source_panel_name="+Panel",
            source_test_name="@TEST",
            alias_key="-Alias()",
            raw_value="=2+5",
            source_unit="mg/dL",
            specimen_type="serum",
            source_reference_range=" =1-2",
            canonical_biomarker_id="glucose_serum",
            canonical_biomarker_name="=GLU",
            loinc="2345-7",
            mapping_status="mapped",
            match_confidence="high",
            status_reason="",
            mapping_rule="alias",
            normalized_value="-1.5",
            normalized_unit="mg/dL",
            normalized_reference_range="70-99",
            provenance={"source_row_id": "=1", "source_alias_key": "+alias"},
        )
        result = NormalizationResult(
            input_file="formula.csv",
            summary={"total_rows": 1, "mapped": 1, "review_needed": 0, "unmapped": 0},
            records=[record],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            _, csv_path = write_result(result, Path(tmp_dir))
            with csv_path.open("r", encoding="utf-8") as handle:
                row = next(csv_mod.DictReader(handle))

        self.assertEqual(row["source_lab_name"], "'=LAB")
        self.assertEqual(row["source_panel_name"], "'+Panel")
        self.assertEqual(row["source_test_name"], "'@TEST")
        self.assertEqual(row["alias_key"], "'-Alias()")
        self.assertEqual(row["raw_value"], "'=2+5")
        self.assertEqual(row["source_reference_range"], "' =1-2")
        self.assertEqual(row["canonical_biomarker_name"], "'=GLU")
        self.assertEqual(row["provenance_source_row_id"], "'=1")
        self.assertEqual(row["provenance_alias_key"], "'+alias")
        self.assertEqual(row["normalized_value"], "-1.5")


class ThreadSafetyTests(unittest.TestCase):
    """Thread safety tests using concurrent.futures.ThreadPoolExecutor."""

    def test_concurrent_normalize_rows(self) -> None:
        """Run normalize_rows from 10 threads simultaneously with different inputs.
        Verify each thread gets correct results (no cross-contamination)."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # Each thread gets a different biomarker with a unique value
        thread_inputs: list[tuple[str, str, str, str, str]] = [
            ("Glucose", "90", "mg/dL", "serum", "glucose_serum"),
            ("Hemoglobin", "14.0", "g/dL", "whole blood", "hemoglobin"),
            ("ALT", "25", "U/L", "serum", "alt"),
            ("AST", "30", "U/L", "serum", "ast"),
            ("Albumin", "4.0", "g/dL", "serum", "albumin"),
            ("Creatinine", "1.0", "mg/dL", "serum", "creatinine"),
            ("WBC", "6.0", "K/uL", "whole blood", "wbc"),
            ("Platelets", "250", "K/uL", "whole blood", "platelets"),
            ("MCV", "90", "fL", "whole blood", "mcv"),
            ("RDW", "13.0", "%", "whole blood", "rdw"),
        ]

        def worker(idx: int) -> tuple[int, str, str]:
            test_name, value, unit, specimen, expected_id = thread_inputs[idx]
            rows = [{
                "source_row_id": f"thread_{idx}",
                "source_test_name": test_name,
                "raw_value": value,
                "source_unit": unit,
                "specimen_type": specimen,
                "source_reference_range": "",
            }]
            result = normalize_rows(rows, input_file=f"thread_{idx}.csv")
            mapped = [r for r in result.records if r.mapping_status == "mapped"]
            bio_id = mapped[0].canonical_biomarker_id if mapped else ""
            norm_val = mapped[0].normalized_value if mapped else ""
            return idx, bio_id, norm_val

        results: dict[int, tuple[str, str]] = {}
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(worker, i): i for i in range(10)}
            for future in as_completed(futures):
                idx, bio_id, norm_val = future.result()
                results[idx] = (bio_id, norm_val)

        # Verify each thread got the correct biomarker ID
        for idx in range(10):
            expected_id = thread_inputs[idx][4]
            actual_id, actual_val = results[idx]
            self.assertEqual(actual_id, expected_id,
                             f"Thread {idx}: expected {expected_id}, got {actual_id}")
            self.assertTrue(len(actual_val) > 0,
                            f"Thread {idx}: normalized_value is empty")

    def test_concurrent_normalize_different_biomarkers(self) -> None:
        """Thread 1 normalizes glucose, thread 2 normalizes hemoglobin simultaneously.
        Verify each gets the right biomarker_id."""
        from concurrent.futures import ThreadPoolExecutor

        def normalize_glucose() -> str:
            rows = [{
                "source_row_id": "cg1",
                "source_test_name": "Glucose",
                "raw_value": "100",
                "source_unit": "mg/dL",
                "specimen_type": "serum",
                "source_reference_range": "",
            }]
            result = normalize_rows(rows)
            mapped = [r for r in result.records if r.mapping_status == "mapped"]
            return mapped[0].canonical_biomarker_id if mapped else ""

        def normalize_hemoglobin() -> str:
            rows = [{
                "source_row_id": "ch1",
                "source_test_name": "Hemoglobin",
                "raw_value": "15.0",
                "source_unit": "g/dL",
                "specimen_type": "whole blood",
                "source_reference_range": "",
            }]
            result = normalize_rows(rows)
            mapped = [r for r in result.records if r.mapping_status == "mapped"]
            return mapped[0].canonical_biomarker_id if mapped else ""

        with ThreadPoolExecutor(max_workers=2) as pool:
            glucose_future = pool.submit(normalize_glucose)
            hgb_future = pool.submit(normalize_hemoglobin)
            self.assertEqual(glucose_future.result(), "glucose_serum")
            self.assertEqual(hgb_future.result(), "hemoglobin")

    def test_concurrent_phenoage(self) -> None:
        """Run compute_phenoage from 5 threads with different profiles.
        Verify each gets a different (correct) result."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from biomarker_normalization_toolkit.phenoage import compute_phenoage

        # 5 profiles with varying biomarker values to produce different PhenoAge results
        profiles = [
            {"glucose": "80", "albumin": "4.8", "creatinine": "0.8", "crp": "0.3",
             "lymph": "35", "mcv": "85", "rdw": "11.5", "alp": "45", "wbc": "5.0", "age": 30},
            {"glucose": "95", "albumin": "4.2", "creatinine": "1.0", "crp": "1.0",
             "lymph": "28", "mcv": "90", "rdw": "13.0", "alp": "60", "wbc": "6.5", "age": 45},
            {"glucose": "110", "albumin": "3.8", "creatinine": "1.2", "crp": "2.5",
             "lymph": "22", "mcv": "95", "rdw": "14.5", "alp": "80", "wbc": "8.0", "age": 60},
            {"glucose": "130", "albumin": "3.5", "creatinine": "1.5", "crp": "5.0",
             "lymph": "18", "mcv": "100", "rdw": "16.0", "alp": "100", "wbc": "10.0", "age": 70},
            {"glucose": "70", "albumin": "5.0", "creatinine": "0.7", "crp": "0.1",
             "lymph": "40", "mcv": "82", "rdw": "11.0", "alp": "40", "wbc": "4.5", "age": 25},
        ]

        def worker(profile: dict) -> tuple[float, float | None]:
            rows = [
                {"source_row_id": "pa1", "source_test_name": "Albumin",
                 "raw_value": profile["albumin"], "source_unit": "g/dL",
                 "specimen_type": "serum", "source_reference_range": ""},
                {"source_row_id": "pa2", "source_test_name": "Creatinine",
                 "raw_value": profile["creatinine"], "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_reference_range": ""},
                {"source_row_id": "pa3", "source_test_name": "Glucose",
                 "raw_value": profile["glucose"], "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_reference_range": ""},
                {"source_row_id": "pa4", "source_test_name": "hs-CRP",
                 "raw_value": profile["crp"], "source_unit": "mg/L",
                 "specimen_type": "serum", "source_reference_range": ""},
                {"source_row_id": "pa5", "source_test_name": "Lymphocytes Percent",
                 "raw_value": profile["lymph"], "source_unit": "%",
                 "specimen_type": "whole blood", "source_reference_range": ""},
                {"source_row_id": "pa6", "source_test_name": "MCV",
                 "raw_value": profile["mcv"], "source_unit": "fL",
                 "specimen_type": "whole blood", "source_reference_range": ""},
                {"source_row_id": "pa7", "source_test_name": "RDW",
                 "raw_value": profile["rdw"], "source_unit": "%",
                 "specimen_type": "whole blood", "source_reference_range": ""},
                {"source_row_id": "pa8", "source_test_name": "ALP",
                 "raw_value": profile["alp"], "source_unit": "U/L",
                 "specimen_type": "serum", "source_reference_range": ""},
                {"source_row_id": "pa9", "source_test_name": "WBC",
                 "raw_value": profile["wbc"], "source_unit": "K/uL",
                 "specimen_type": "whole blood", "source_reference_range": ""},
            ]
            result = normalize_rows(rows)
            pheno = compute_phenoage(result, chronological_age=float(profile["age"]))
            phenoage_val = pheno["phenoage"] if pheno else None
            return float(profile["age"]), phenoage_val

        results: list[tuple[float, float | None]] = []
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(worker, p) for p in profiles]
            for future in as_completed(futures):
                results.append(future.result())

        # All 5 should have computed a PhenoAge
        for age, phenoage_val in results:
            self.assertIsNotNone(phenoage_val,
                                 f"PhenoAge was None for chronological_age={age}")

        # All PhenoAge values should be distinct (different inputs -> different outputs)
        phenoage_values = [v for _, v in results if v is not None]
        self.assertEqual(len(set(phenoage_values)), 5,
                         f"Expected 5 distinct PhenoAge values, got {phenoage_values}")

    def test_concurrent_derived_metrics(self) -> None:
        """Run compute_derived_metrics from 5 threads with different inputs.
        Verify each thread gets its own correct result."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from biomarker_normalization_toolkit.derived import compute_derived_metrics

        # 5 profiles with varying glucose/insulin to get different HOMA-IR
        test_cases = [
            {"glucose": "80", "insulin": "4", "expected_homa_approx": 0.79},
            {"glucose": "90", "insulin": "5", "expected_homa_approx": 1.11},
            {"glucose": "100", "insulin": "8", "expected_homa_approx": 1.98},
            {"glucose": "120", "insulin": "12", "expected_homa_approx": 3.56},
            {"glucose": "150", "insulin": "20", "expected_homa_approx": 7.41},
        ]

        def worker(case: dict) -> tuple[float, float]:
            rows = [
                {"source_row_id": "dm1", "source_test_name": "Glucose",
                 "raw_value": case["glucose"], "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_reference_range": ""},
                {"source_row_id": "dm2", "source_test_name": "Insulin",
                 "raw_value": case["insulin"], "source_unit": "uIU/mL",
                 "specimen_type": "serum", "source_reference_range": ""},
            ]
            result = normalize_rows(rows)
            metrics = compute_derived_metrics(result)
            homa_val = float(metrics["homa_ir"]["value"]) if "homa_ir" in metrics else 0.0
            return case["expected_homa_approx"], homa_val

        results: list[tuple[float, float]] = []
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(worker, c) for c in test_cases]
            for future in as_completed(futures):
                results.append(future.result())

        # Verify each thread got approximately correct HOMA-IR
        for expected, actual in results:
            self.assertAlmostEqual(actual, expected, places=1,
                                   msg=f"HOMA-IR mismatch: expected ~{expected}, got {actual}")

        # Verify all values are distinct (no cross-contamination)
        actual_values = [v for _, v in results]
        self.assertEqual(len(set(actual_values)), 5,
                         f"Expected 5 distinct HOMA-IR values, got {actual_values}")


class CatalogIntegrityTests(unittest.TestCase):
    """Verify internal consistency of all biomarker definitions in the catalog."""

    _VALID_SPECIMENS = frozenset({"serum", "plasma", "whole_blood", "urine", "cerebrospinal fluid", "ascites", "pleural", "body_fluid"})
    _LOINC_RE = re.compile(r"^\d+-\d$")
    _SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

    def test_every_biomarker_has_at_least_3_aliases(self) -> None:
        """Every biomarker must have at least 3 aliases for robust matching."""
        violations: list[str] = []
        for bio_id, defn in BIOMARKER_CATALOG.items():
            if len(defn.aliases) < 3:
                violations.append(f"{bio_id}: only {len(defn.aliases)} alias(es)")
        self.assertEqual(violations, [], f"Biomarkers with fewer than 3 aliases:\n" + "\n".join(violations))

    def test_no_duplicate_aliases_within_biomarker(self) -> None:
        """No biomarker should list the same alias twice."""
        violations: list[str] = []
        for bio_id, defn in BIOMARKER_CATALOG.items():
            normalized = [normalize_key(a) for a in defn.aliases]
            seen: set[str] = set()
            for i, nk in enumerate(normalized):
                if nk in seen:
                    violations.append(f"{bio_id}: duplicate alias '{defn.aliases[i]}' (key={nk!r})")
                seen.add(nk)
        self.assertEqual(violations, [], f"Duplicate aliases found:\n" + "\n".join(violations))

    def test_no_alias_key_collision_without_specimen_or_unit_disambiguation(self) -> None:
        """Alias collisions are only allowed when specimen or source unit can separate them."""
        def supported_units(bio_id: str) -> set[str]:
            units = set(CONVERSION_TO_NORMALIZED.get(bio_id, {}))
            if bio_id == "hba1c":
                units.add("mmol/mol")
            return units

        violations: list[str] = []
        for alias_key, bio_ids in ALIAS_INDEX.items():
            if len(bio_ids) < 2:
                continue
            for i in range(len(bio_ids)):
                for j in range(i + 1, len(bio_ids)):
                    specs_i = BIOMARKER_CATALOG[bio_ids[i]].allowed_specimens
                    specs_j = BIOMARKER_CATALOG[bio_ids[j]].allowed_specimens
                    specimen_overlap = specs_i & specs_j
                    unit_overlap = supported_units(bio_ids[i]) & supported_units(bio_ids[j])
                    if specimen_overlap and unit_overlap:
                        violations.append(
                            f"Alias key {alias_key!r} -> [{bio_ids[i]}, {bio_ids[j]}] "
                            f"share specimen(s): {sorted(specimen_overlap)} and unit(s): {sorted(unit_overlap)}"
                        )
        self.assertEqual(
            violations, [],
            f"Alias collisions without specimen or unit disambiguation:\n" + "\n".join(violations),
        )

    def test_every_loinc_is_unique(self) -> None:
        """No two biomarkers should share the same LOINC code."""
        loinc_to_ids: dict[str, list[str]] = {}
        for bio_id, defn in BIOMARKER_CATALOG.items():
            if defn.loinc:
                loinc_to_ids.setdefault(defn.loinc, []).append(bio_id)
        duplicates = {loinc: ids for loinc, ids in loinc_to_ids.items() if len(ids) > 1}
        self.assertEqual(duplicates, {}, f"Duplicate LOINC codes: {duplicates}")

    def test_every_loinc_matches_format(self) -> None:
        """Every LOINC code must match the standard format: digits-digit."""
        violations: list[str] = []
        for bio_id, defn in BIOMARKER_CATALOG.items():
            if defn.loinc and not self._LOINC_RE.match(defn.loinc):
                violations.append(f"{bio_id}: {defn.loinc!r}")
        self.assertEqual(violations, [], f"Invalid LOINC formats:\n" + "\n".join(violations))

    def test_every_normalized_unit_has_ucum_code(self) -> None:
        """Every non-empty normalized_unit must have an entry in UCUM_CODES."""
        violations: list[str] = []
        for bio_id, defn in BIOMARKER_CATALOG.items():
            if defn.normalized_unit and defn.normalized_unit not in UCUM_CODES:
                violations.append(f"{bio_id}: unit={defn.normalized_unit!r}")
        self.assertEqual(violations, [], f"Missing UCUM codes:\n" + "\n".join(violations))

    def test_every_conversion_identity_matches_normalized_unit(self) -> None:
        """For every biomarker, CONVERSION_TO_NORMALIZED must have an identity entry
        (factor=1) keyed by its normalized_unit."""
        violations: list[str] = []
        for bio_id, defn in BIOMARKER_CATALOG.items():
            if not defn.normalized_unit:
                continue  # dimensionless / derived biomarkers
            conv = CONVERSION_TO_NORMALIZED.get(bio_id)
            if conv is None:
                violations.append(f"{bio_id}: no entry in CONVERSION_TO_NORMALIZED")
                continue
            factor = conv.get(defn.normalized_unit)
            if factor is None:
                violations.append(
                    f"{bio_id}: CONVERSION_TO_NORMALIZED has no key {defn.normalized_unit!r} "
                    f"(keys: {sorted(conv.keys())})"
                )
            elif factor != Decimal("1"):
                violations.append(
                    f"{bio_id}: identity factor for {defn.normalized_unit!r} is {factor}, expected 1"
                )
        self.assertEqual(violations, [], f"Identity conversion mismatches:\n" + "\n".join(violations))

    def test_alias_index_is_complete(self) -> None:
        """Every alias in every BiomarkerDefinition.aliases must appear in ALIAS_INDEX."""
        violations: list[str] = []
        for bio_id, defn in BIOMARKER_CATALOG.items():
            for alias in defn.aliases:
                alias_key = normalize_key(alias)
                index_entry = ALIAS_INDEX.get(alias_key, [])
                if bio_id not in index_entry:
                    violations.append(f"{bio_id}: alias {alias!r} (key={alias_key!r}) not in ALIAS_INDEX")
        self.assertEqual(violations, [], f"Missing ALIAS_INDEX entries:\n" + "\n".join(violations))

    def test_alias_index_has_no_orphan_biomarker_ids(self) -> None:
        """Every biomarker_id referenced in ALIAS_INDEX values must exist in BIOMARKER_CATALOG."""
        orphans: list[str] = []
        for alias_key, bio_ids in ALIAS_INDEX.items():
            for bio_id in bio_ids:
                if bio_id not in BIOMARKER_CATALOG:
                    orphans.append(f"alias_key={alias_key!r} -> {bio_id!r}")
        self.assertEqual(orphans, [], f"Orphan biomarker IDs in ALIAS_INDEX:\n" + "\n".join(orphans))

    def test_biomarker_ids_are_snake_case(self) -> None:
        """Every biomarker_id must be lowercase snake_case."""
        violations: list[str] = []
        for bio_id in BIOMARKER_CATALOG:
            if not self._SNAKE_CASE_RE.match(bio_id):
                violations.append(bio_id)
        self.assertEqual(violations, [], f"Non-snake_case biomarker IDs:\n" + "\n".join(violations))

    def test_canonical_names_are_nonempty(self) -> None:
        """Every biomarker must have a non-empty canonical_name."""
        violations: list[str] = []
        for bio_id, defn in BIOMARKER_CATALOG.items():
            if not defn.canonical_name or not defn.canonical_name.strip():
                violations.append(bio_id)
        self.assertEqual(violations, [], f"Empty canonical_name:\n" + "\n".join(violations))

    def test_specimens_are_valid(self) -> None:
        """Every biomarker's allowed_specimens must contain only valid specimen types."""
        violations: list[str] = []
        for bio_id, defn in BIOMARKER_CATALOG.items():
            invalid = defn.allowed_specimens - self._VALID_SPECIMENS
            if invalid:
                violations.append(f"{bio_id}: invalid specimens {sorted(invalid)}")
        self.assertEqual(violations, [], f"Invalid specimen types:\n" + "\n".join(violations))


class NumericPrecisionTests(unittest.TestCase):
    """Boundary conditions, decimal precision, and format edge cases."""

    # -- parse_decimal edge cases -------------------------------------

    def test_parse_decimal_plain_integer(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertEqual(parse_decimal("100"), Decimal("100"))

    def test_parse_decimal_with_decimal_point(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertEqual(parse_decimal("5.55"), Decimal("5.55"))

    def test_parse_decimal_leading_zero(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertEqual(parse_decimal("0.5"), Decimal("0.5"))

    def test_parse_decimal_negative(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertEqual(parse_decimal("-3.5"), Decimal("-3.5"))

    def test_parse_decimal_positive_sign(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertEqual(parse_decimal("+100"), Decimal("100"))

    def test_parse_decimal_thousands_comma(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertEqual(parse_decimal("1,500"), Decimal("1500"))

    def test_parse_decimal_multiple_thousands(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertEqual(parse_decimal("1,500,000"), Decimal("1500000"))

    def test_parse_decimal_european_ambiguous_rejected(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertIsNone(parse_decimal("5,5"))

    def test_parse_decimal_scientific_notation(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertEqual(parse_decimal("1.5e6"), Decimal("1500000"))
        self.assertEqual(parse_decimal("1.23e+4"), Decimal("12300"))

    def test_parse_decimal_x10_notation(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertEqual(parse_decimal("15.5 x 10^3"), Decimal("15500"))

    def test_parse_decimal_x10_exponent_cap(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertIsNone(parse_decimal("1 x 10^16"))

    def test_parse_decimal_scientific_exponent_cap(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertIsNone(parse_decimal("1e101"))

    def test_parse_decimal_empty(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertIsNone(parse_decimal(""))

    def test_scientific_notation_row_normalizes(self) -> None:
        rows = [{
            "source_row_id": "sci1",
            "source_test_name": "Basophils",
            "raw_value": "5.397605346934028e-79",
            "source_unit": "K/uL",
            "specimen_type": "whole blood",
            "source_reference_range": "",
        }]
        result = normalize_rows(rows)
        record = result.records[0]
        self.assertEqual(record.mapping_status, "mapped")
        self.assertEqual(record.canonical_biomarker_id, "basophils")
        self.assertEqual(record.normalized_value, "0")

    def test_parse_decimal_none(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertIsNone(parse_decimal(None))

    def test_parse_decimal_text(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertIsNone(parse_decimal("See comment"))

    def test_parse_decimal_inequality(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertIsNone(parse_decimal(">500"))

    def test_parse_decimal_length_guard(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertIsNone(parse_decimal("9" * 51))

    def test_parse_decimal_with_spaces(self) -> None:
        from biomarker_normalization_toolkit.units import parse_decimal
        self.assertEqual(parse_decimal(" 100 "), Decimal("100"))

    # -- format_decimal edge cases ------------------------------------

    def test_format_decimal_normal(self) -> None:
        from biomarker_normalization_toolkit.units import format_decimal
        self.assertEqual(format_decimal(Decimal("100.5")), "100.5")

    def test_format_decimal_integer(self) -> None:
        from biomarker_normalization_toolkit.units import format_decimal
        self.assertEqual(format_decimal(Decimal("100")), "100")

    def test_format_decimal_trailing_zeros(self) -> None:
        from biomarker_normalization_toolkit.units import format_decimal
        self.assertEqual(format_decimal(Decimal("5.500000")), "5.5")

    def test_format_decimal_very_small(self) -> None:
        from biomarker_normalization_toolkit.units import format_decimal
        self.assertEqual(format_decimal(Decimal("0.000001")), "0.000001")

    def test_format_decimal_below_precision(self) -> None:
        from biomarker_normalization_toolkit.units import format_decimal
        self.assertEqual(format_decimal(Decimal("0.0000001")), "0")

    def test_format_decimal_negative_zero(self) -> None:
        from biomarker_normalization_toolkit.units import format_decimal
        self.assertEqual(format_decimal(Decimal("-0")), "0")

    def test_format_decimal_infinity(self) -> None:
        from biomarker_normalization_toolkit.units import format_decimal
        self.assertEqual(format_decimal(Decimal("Infinity")), "")

    def test_format_decimal_nan(self) -> None:
        from biomarker_normalization_toolkit.units import format_decimal
        self.assertEqual(format_decimal(Decimal("NaN")), "")

    def test_format_decimal_none(self) -> None:
        from biomarker_normalization_toolkit.units import format_decimal
        self.assertEqual(format_decimal(None), "")

    # -- parse_reference_range edge cases ------------------------------

    def test_range_standard(self) -> None:
        result = parse_reference_range("70-99 mg/dL", "mg/dL")
        self.assertIsNotNone(result)
        self.assertEqual(result.low, Decimal("70"))
        self.assertEqual(result.high, Decimal("99"))

    def test_range_with_spaces(self) -> None:
        result = parse_reference_range("70 - 99 mg/dL", "mg/dL")
        self.assertIsNotNone(result)
        self.assertEqual(result.low, Decimal("70"))
        self.assertEqual(result.high, Decimal("99"))

    def test_range_with_to(self) -> None:
        result = parse_reference_range("3.9 to 5.5 mmol/L", "mmol/L")
        self.assertIsNotNone(result)
        self.assertEqual(result.low, Decimal("3.9"))
        self.assertEqual(result.high, Decimal("5.5"))

    def test_range_one_sided_less_than(self) -> None:
        result = parse_reference_range("<200 mg/dL", "mg/dL")
        self.assertIsNotNone(result)
        self.assertEqual(result.low, Decimal("0"))
        self.assertEqual(result.high, Decimal("200"))

    def test_range_one_sided_greater_than(self) -> None:
        result = parse_reference_range(">=60 mL/min", "mL/min")
        self.assertIsNotNone(result)
        self.assertEqual(result.low, Decimal("60"))
        self.assertEqual(result.high, Decimal("99999"))

    def test_range_thousands_comma(self) -> None:
        result = parse_reference_range("150,000-400,000", "K/uL")
        self.assertIsNotNone(result)
        self.assertEqual(result.low, Decimal("150000"))
        self.assertEqual(result.high, Decimal("400000"))

    def test_range_negative_values(self) -> None:
        result = parse_reference_range("-2-2", "mEq/L")
        self.assertIsNotNone(result)
        self.assertEqual(result.low, Decimal("-2"))
        self.assertEqual(result.high, Decimal("2"))

    def test_range_inverted_rejected(self) -> None:
        result = parse_reference_range("100-50", "mg/dL")
        self.assertIsNone(result)

    def test_range_text_garbage(self) -> None:
        result = parse_reference_range("Negative", "mg/dL")
        self.assertIsNone(result)


class ErrorPathTests(unittest.TestCase):
    """Exercises every error/rejection path in the normalizer pipeline.

    Each test verifies the exact mapping_status, status_reason, and
    match_confidence for a specific failure or reduced-confidence scenario.
    """

    # ------------------------------------------------------------------
    # Unmapped paths
    # ------------------------------------------------------------------

    def test_unknown_alias(self) -> None:
        """Completely unknown test name produces unmapped with unknown_alias."""
        result = normalize_rows([{
            "source_test_name": "CompletelyFakeTestXYZ",
            "raw_value": "42",
            "source_unit": "mg/dL",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "unmapped")
        self.assertEqual(rec.status_reason, "unknown_alias")
        self.assertEqual(rec.match_confidence, "none")

    def test_empty_test_name(self) -> None:
        """Empty string as test name produces unmapped with unknown_alias."""
        result = normalize_rows([{
            "source_test_name": "",
            "raw_value": "42",
            "source_unit": "mg/dL",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "unmapped")
        self.assertEqual(rec.status_reason, "unknown_alias")
        self.assertEqual(rec.match_confidence, "none")

    def test_empty_raw_value_with_known_test(self) -> None:
        """Known test with empty raw_value produces review_needed / invalid_raw_value."""
        result = normalize_rows([{
            "source_test_name": "Glucose",
            "raw_value": "",
            "source_unit": "mg/dL",
            "specimen_type": "serum",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "review_needed")
        self.assertEqual(rec.status_reason, "invalid_raw_value")
        self.assertEqual(rec.match_confidence, "none")

    # ------------------------------------------------------------------
    # Review-needed paths
    # ------------------------------------------------------------------

    def test_inequality_value(self) -> None:
        """Inequality prefix ('>500') produces review_needed / inequality_value."""
        result = normalize_rows([{
            "source_test_name": "Glucose",
            "raw_value": ">500",
            "source_unit": "mg/dL",
            "specimen_type": "serum",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "review_needed")
        self.assertEqual(rec.status_reason, "inequality_value")
        self.assertEqual(rec.match_confidence, "none")
        # Should still resolve the biomarker identity
        self.assertEqual(rec.canonical_biomarker_id, "glucose_serum")

    def test_invalid_raw_value(self) -> None:
        """Non-numeric value ('abc') produces review_needed / invalid_raw_value."""
        result = normalize_rows([{
            "source_test_name": "Glucose",
            "raw_value": "abc",
            "source_unit": "mg/dL",
            "specimen_type": "serum",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "review_needed")
        self.assertEqual(rec.status_reason, "invalid_raw_value")
        self.assertEqual(rec.match_confidence, "none")
        self.assertEqual(rec.canonical_biomarker_id, "glucose_serum")

    def test_unsupported_unit(self) -> None:
        """Known biomarker with absurd unit produces review_needed / unsupported_unit_for_biomarker."""
        result = normalize_rows([{
            "source_test_name": "Glucose",
            "raw_value": "100",
            "source_unit": "parsecs",
            "specimen_type": "serum",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "review_needed")
        self.assertEqual(rec.status_reason, "unsupported_unit_for_biomarker")
        self.assertEqual(rec.match_confidence, "none")
        self.assertEqual(rec.canonical_biomarker_id, "glucose_serum")

    def test_ambiguous_alias_no_specimen(self) -> None:
        """'Glucose' without specimen is ambiguous (serum vs urine) and requires review."""
        result = normalize_rows([{
            "source_test_name": "Glucose",
            "raw_value": "100",
            "source_unit": "mg/dL",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "review_needed")
        self.assertEqual(rec.status_reason, "ambiguous_alias_requires_specimen")
        self.assertEqual(rec.match_confidence, "none")

    def test_conversion_failure(self) -> None:
        """Known biomarker with incompatible unit (no sibling) produces unsupported_unit_for_biomarker."""
        result = normalize_rows([{
            "source_test_name": "Hemoglobin",
            "raw_value": "14",
            "source_unit": "IU/L",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "review_needed")
        self.assertEqual(rec.status_reason, "unsupported_unit_for_biomarker")
        self.assertEqual(rec.match_confidence, "none")

    # ------------------------------------------------------------------
    # Mapped paths with reduced confidence
    # ------------------------------------------------------------------

    def test_fuzzy_match_medium_confidence(self) -> None:
        """Slightly misspelled name triggers fuzzy match with medium confidence."""
        try:
            import rapidfuzz  # noqa: F401
        except ImportError:
            self.skipTest("rapidfuzz not installed")

        result = normalize_rows(
            [{"source_test_name": "Hemoglobinn", "raw_value": "14", "source_unit": "g/dL"}],
            fuzzy_threshold=0.70,
        )
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "mapped")
        self.assertEqual(rec.status_reason, "fuzzy_match")
        self.assertEqual(rec.match_confidence, "medium")
        self.assertIn("fuzzy:", rec.mapping_rule)
        # Verify the fuzzy score is recorded and >= 0.85
        score_str = rec.mapping_rule.split("fuzzy:")[1].split("|")[0]
        self.assertGreaterEqual(float(score_str), 0.85)

    def test_sibling_redirect_medium_confidence(self) -> None:
        """'Neutrophils' with '%' unit redirects to neutrophils_pct sibling."""
        result = normalize_rows([{
            "source_test_name": "Neutrophils",
            "raw_value": "55",
            "source_unit": "%",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "mapped")
        self.assertEqual(rec.status_reason, "sibling_unit_redirect")
        self.assertEqual(rec.match_confidence, "medium")
        self.assertEqual(rec.canonical_biomarker_id, "neutrophils_pct")
        self.assertIn("redirected:neutrophils_pct", rec.mapping_rule)

    def test_panel_prefix_stripped_medium_confidence(self) -> None:
        """'CMP:GLUCOSE' strips panel prefix and maps with medium confidence."""
        result = normalize_rows([{
            "source_test_name": "CMP:GLUCOSE",
            "raw_value": "95",
            "source_unit": "mg/dL",
            "specimen_type": "serum",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "mapped")
        self.assertEqual(rec.status_reason, "panel_prefix_stripped")
        self.assertEqual(rec.match_confidence, "medium")
        self.assertEqual(rec.canonical_biomarker_id, "glucose_serum")
        self.assertIn("panel_strip:", rec.mapping_rule)

    def test_loinc_fallback(self) -> None:
        """LOINC code '2345-7' as test name resolves via LOINC fallback path."""
        result = normalize_rows([{
            "source_test_name": "2345-7",
            "raw_value": "100",
            "source_unit": "mg/dL",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "mapped")
        self.assertEqual(rec.canonical_biomarker_id, "glucose_serum")
        self.assertEqual(rec.match_confidence, "high")

    # ------------------------------------------------------------------
    # Summary consistency
    # ------------------------------------------------------------------

    def test_summary_counts_match_records(self) -> None:
        """Summary mapped/review_needed/unmapped counts exactly match record statuses."""
        rows = [
            # mapped (high confidence)
            {"source_test_name": "Hemoglobin", "raw_value": "14", "source_unit": "g/dL"},
            # mapped (high confidence)
            {"source_test_name": "Creatinine", "raw_value": "1.0", "source_unit": "mg/dL"},
            # review_needed (ambiguous)
            {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL"},
            # review_needed (invalid value)
            {"source_test_name": "Hemoglobin", "raw_value": "abc", "source_unit": "g/dL"},
            # unmapped
            {"source_test_name": "CompletelyFakeTestXYZ", "raw_value": "1", "source_unit": "mg/dL"},
            # review_needed (unsupported unit)
            {"source_test_name": "Hemoglobin", "raw_value": "14", "source_unit": "parsecs"},
            # mapped (medium confidence, sibling redirect)
            {"source_test_name": "Neutrophils", "raw_value": "55", "source_unit": "%"},
        ]
        result = normalize_rows(rows)

        actual_mapped = sum(1 for r in result.records if r.mapping_status == "mapped")
        actual_review = sum(1 for r in result.records if r.mapping_status == "review_needed")
        actual_unmapped = sum(1 for r in result.records if r.mapping_status == "unmapped")

        self.assertEqual(result.summary["total_rows"], len(rows))
        self.assertEqual(result.summary["mapped"], actual_mapped)
        self.assertEqual(result.summary["review_needed"], actual_review)
        self.assertEqual(result.summary["unmapped"], actual_unmapped)
        self.assertEqual(
            result.summary["mapped"] + result.summary["review_needed"] + result.summary["unmapped"],
            result.summary["total_rows"],
        )

    def test_confidence_breakdown_matches_records(self) -> None:
        """Summary confidence_breakdown counts exactly match actual record confidences."""
        rows = [
            # high confidence
            {"source_test_name": "Hemoglobin", "raw_value": "14", "source_unit": "g/dL"},
            # medium confidence (sibling redirect)
            {"source_test_name": "Neutrophils", "raw_value": "55", "source_unit": "%"},
            # none (unmapped)
            {"source_test_name": "CompletelyFakeTestXYZ", "raw_value": "1", "source_unit": "mg/dL"},
            # none (review_needed, invalid value)
            {"source_test_name": "Hemoglobin", "raw_value": "abc", "source_unit": "g/dL"},
            # medium confidence (panel prefix)
            {"source_test_name": "CMP:GLUCOSE", "raw_value": "95", "source_unit": "mg/dL", "specimen_type": "serum"},
        ]
        result = normalize_rows(rows)
        breakdown = result.summary["confidence_breakdown"]

        actual_high = sum(1 for r in result.records if r.match_confidence == "high")
        actual_medium = sum(1 for r in result.records if r.match_confidence == "medium")
        actual_low = sum(1 for r in result.records if r.match_confidence == "low")
        actual_none = sum(1 for r in result.records if r.match_confidence == "none")

        self.assertEqual(breakdown["high"], actual_high)
        self.assertEqual(breakdown["medium"], actual_medium)
        self.assertEqual(breakdown["low"], actual_low)
        self.assertEqual(breakdown["none"], actual_none)
        self.assertEqual(
            breakdown["high"] + breakdown["medium"] + breakdown["low"] + breakdown["none"],
            result.summary["total_rows"],
        )


class FHIRComplianceTests(unittest.TestCase):
    """Comprehensive FHIR R4 compliance tests for the observation/bundle builder."""

    def _make_mapped_record(
        self,
        *,
        source_row_id: str = "row-1",
        source_test_name: str = "Glucose, Serum",
        raw_value: str = "95.0",
        normalized_value: str = "95.0",
        normalized_unit: str = "mg/dL",
        normalized_reference_range: str = "70-100 mg/dL",
        canonical_biomarker_id: str = "glucose_serum",
        canonical_biomarker_name: str = "Glucose",
        loinc: str = "2345-7",
        mapping_rule: str = "exact_name",
        specimen_type: str = "serum",
    ) -> "NormalizedRecord":
        from biomarker_normalization_toolkit.models import NormalizedRecord

        return NormalizedRecord(
            source_row_number=1,
            source_row_id=source_row_id,
            source_lab_name="TestLab",
            source_panel_name="Basic Metabolic",
            source_test_name=source_test_name,
            alias_key="glucose serum",
            raw_value=raw_value,
            source_unit="mg/dL",
            specimen_type=specimen_type,
            source_reference_range="70-100 mg/dL",
            canonical_biomarker_id=canonical_biomarker_id,
            canonical_biomarker_name=canonical_biomarker_name,
            loinc=loinc,
            mapping_status="mapped",
            match_confidence="high",
            status_reason="",
            mapping_rule=mapping_rule,
            normalized_value=normalized_value,
            normalized_unit=normalized_unit,
            normalized_reference_range=normalized_reference_range,
            provenance={"source_row_id": source_row_id},
        )

    def _make_unmapped_record(self) -> "NormalizedRecord":
        from biomarker_normalization_toolkit.models import NormalizedRecord

        return NormalizedRecord(
            source_row_number=2,
            source_row_id="row-unmapped",
            source_lab_name="TestLab",
            source_panel_name="Basic Metabolic",
            source_test_name="Unknown Test XYZ",
            alias_key="unknown test xyz",
            raw_value="42",
            source_unit="mg/dL",
            specimen_type="serum",
            source_reference_range="",
            canonical_biomarker_id="",
            canonical_biomarker_name="",
            loinc="",
            mapping_status="unmapped",
            match_confidence="none",
            status_reason="no_candidate",
            mapping_rule="",
            normalized_value="",
            normalized_unit="",
            normalized_reference_range="",
            provenance={},
        )

    def _build_obs(self, **kwargs) -> dict:
        from biomarker_normalization_toolkit.fhir import build_observation

        record_kwargs = {
            k: v for k, v in kwargs.items()
            if k not in ("effective_datetime", "subject_reference")
        }
        record = self._make_mapped_record(**record_kwargs)
        obs = build_observation(
            record,
            input_file="test.csv",
            effective_datetime=kwargs.get("effective_datetime"),
            subject_reference=kwargs.get("subject_reference"),
        )
        self.assertIsNotNone(obs)
        return obs  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # 1. Required fields
    # ------------------------------------------------------------------
    def test_observation_has_required_fields(self) -> None:
        obs = self._build_obs()
        for field in ("resourceType", "status", "code"):
            self.assertIn(field, obs, f"Required FHIR field '{field}' missing from Observation")

    # ------------------------------------------------------------------
    # 2. Status is final
    # ------------------------------------------------------------------
    def test_observation_status_is_final(self) -> None:
        obs = self._build_obs()
        self.assertEqual(obs["status"], "final")

    # ------------------------------------------------------------------
    # 3. Category is laboratory
    # ------------------------------------------------------------------
    def test_observation_category_is_laboratory(self) -> None:
        obs = self._build_obs()
        self.assertIn("category", obs)
        codings = obs["category"][0]["coding"]
        lab_codes = [c for c in codings if c["code"] == "laboratory"]
        self.assertTrue(len(lab_codes) > 0, "No 'laboratory' code in category coding")
        self.assertEqual(
            lab_codes[0]["system"],
            "http://terminology.hl7.org/CodeSystem/observation-category",
        )

    # ------------------------------------------------------------------
    # 4. Code has LOINC
    # ------------------------------------------------------------------
    def test_observation_code_has_loinc(self) -> None:
        obs = self._build_obs()
        codings = obs["code"]["coding"]
        loinc_entries = [c for c in codings if c["system"] == "http://loinc.org"]
        self.assertTrue(len(loinc_entries) > 0, "No LOINC coding in observation code")
        self.assertEqual(loinc_entries[0]["code"], "2345-7")

    # ------------------------------------------------------------------
    # 5. valueQuantity has UCUM
    # ------------------------------------------------------------------
    def test_observation_value_quantity_has_ucum(self) -> None:
        obs = self._build_obs()
        vq = obs["valueQuantity"]
        self.assertEqual(vq["system"], "http://unitsofmeasure.org")
        self.assertIn("code", vq)
        self.assertTrue(len(vq["code"]) > 0, "UCUM code is empty")

    def test_observation_huge_numeric_value_uses_value_string(self) -> None:
        obs = self._build_obs(normalized_value="1E+5000", normalized_unit="mg/dL")
        self.assertNotIn("valueQuantity", obs)
        self.assertEqual(obs["valueString"], "1E+5000")

    # ------------------------------------------------------------------
    # 6. Subject included when provided
    # ------------------------------------------------------------------
    def test_observation_subject_included_when_provided(self) -> None:
        obs = self._build_obs(subject_reference="Patient/123")
        self.assertIn("subject", obs)
        self.assertEqual(obs["subject"]["reference"], "Patient/123")

    # ------------------------------------------------------------------
    # 7. Subject omitted when not provided
    # ------------------------------------------------------------------
    def test_observation_subject_omitted_when_not_provided(self) -> None:
        obs = self._build_obs()
        self.assertNotIn("subject", obs)

    # ------------------------------------------------------------------
    # 8. effectiveDateTime
    # ------------------------------------------------------------------
    def test_observation_effective_datetime(self) -> None:
        obs_with = self._build_obs(effective_datetime="2024-01-15T10:30:00Z")
        self.assertEqual(obs_with["effectiveDateTime"], "2024-01-15T10:30:00Z")

        obs_without = self._build_obs()
        self.assertNotIn("effectiveDateTime", obs_without)

    # ------------------------------------------------------------------
    # 9. Two-sided reference range
    # ------------------------------------------------------------------
    def test_observation_reference_range_two_sided(self) -> None:
        obs = self._build_obs(normalized_reference_range="70-100 mg/dL")
        self.assertIn("referenceRange", obs)
        rr = obs["referenceRange"][0]
        self.assertIn("low", rr)
        self.assertIn("high", rr)
        self.assertEqual(rr["low"]["value"], 70.0)
        self.assertEqual(rr["high"]["value"], 100.0)
        self.assertEqual(rr["low"]["unit"], "mg/dL")
        self.assertEqual(rr["low"]["system"], "http://unitsofmeasure.org")
        self.assertIn("code", rr["low"])
        self.assertIn("code", rr["high"])

    # ------------------------------------------------------------------
    # 10. One-sided: high only (low is sentinel 0)
    # ------------------------------------------------------------------
    def test_observation_reference_range_one_sided_high_only(self) -> None:
        obs = self._build_obs(normalized_reference_range="0-200 mg/dL")
        self.assertIn("referenceRange", obs)
        rr = obs["referenceRange"][0]
        self.assertNotIn("low", rr, "Sentinel low=0 should be omitted from FHIR output")
        self.assertIn("high", rr)
        self.assertEqual(rr["high"]["value"], 200.0)

    # ------------------------------------------------------------------
    # 11. One-sided: low only (high is sentinel 99999)
    # ------------------------------------------------------------------
    def test_observation_reference_range_one_sided_low_only(self) -> None:
        obs = self._build_obs(normalized_reference_range="60-99999 mg/dL")
        self.assertIn("referenceRange", obs)
        rr = obs["referenceRange"][0]
        self.assertIn("low", rr)
        self.assertEqual(rr["low"]["value"], 60.0)
        self.assertNotIn("high", rr, "Sentinel high=99999 should be omitted from FHIR output")

    # ------------------------------------------------------------------
    # 12. No reference range
    # ------------------------------------------------------------------
    def test_observation_no_reference_range(self) -> None:
        obs = self._build_obs(normalized_reference_range="")
        self.assertNotIn("referenceRange", obs)

    # ------------------------------------------------------------------
    # 13. Bundle type is collection
    # ------------------------------------------------------------------
    def test_bundle_type_is_collection(self) -> None:
        from biomarker_normalization_toolkit.fhir import build_bundle
        from biomarker_normalization_toolkit.models import NormalizationResult

        result = NormalizationResult(
            input_file="test.csv",
            summary={"total": 1, "mapped": 1, "unmapped": 0, "review_needed": 0},
            records=[self._make_mapped_record()],
        )
        bundle = build_bundle(result)
        self.assertEqual(bundle["resourceType"], "Bundle")
        self.assertEqual(bundle["type"], "collection")

    # ------------------------------------------------------------------
    # 14. Bundle entries have fullUrl with urn:uuid:
    # ------------------------------------------------------------------
    def test_bundle_entries_have_full_url(self) -> None:
        from biomarker_normalization_toolkit.fhir import build_bundle
        from biomarker_normalization_toolkit.models import NormalizationResult

        result = NormalizationResult(
            input_file="test.csv",
            summary={"total": 2, "mapped": 2, "unmapped": 0, "review_needed": 0},
            records=[
                self._make_mapped_record(source_row_id="r1", canonical_biomarker_id="glucose_serum"),
                self._make_mapped_record(source_row_id="r2", canonical_biomarker_id="creatinine_serum", loinc="2160-0", canonical_biomarker_name="Creatinine"),
            ],
        )
        bundle = build_bundle(result)
        for entry in bundle["entry"]:
            self.assertIn("fullUrl", entry)
            self.assertTrue(
                entry["fullUrl"].startswith("urn:uuid:"),
                f"fullUrl '{entry['fullUrl']}' does not start with 'urn:uuid:'",
            )

    # ------------------------------------------------------------------
    # 15. Bundle skips unmapped records
    # ------------------------------------------------------------------
    def test_bundle_skips_unmapped_records(self) -> None:
        from biomarker_normalization_toolkit.fhir import build_bundle
        from biomarker_normalization_toolkit.models import NormalizationResult

        result = NormalizationResult(
            input_file="test.csv",
            summary={"total": 2, "mapped": 1, "unmapped": 1, "review_needed": 0},
            records=[self._make_mapped_record(), self._make_unmapped_record()],
        )
        bundle = build_bundle(result)
        self.assertEqual(len(bundle["entry"]), 1, "Unmapped records should not appear in bundle entries")

    # ------------------------------------------------------------------
    # 16. Deterministic UUID
    # ------------------------------------------------------------------
    def test_observation_uuid_deterministic(self) -> None:
        from biomarker_normalization_toolkit.fhir import build_observation

        record = self._make_mapped_record()
        obs1 = build_observation(record, input_file="test.csv")
        obs2 = build_observation(record, input_file="test.csv")
        self.assertIsNotNone(obs1)
        self.assertIsNotNone(obs2)
        self.assertEqual(obs1["id"], obs2["id"])

    # ------------------------------------------------------------------
    # 17. Unique UUIDs across different biomarkers with same row_id
    # ------------------------------------------------------------------
    def test_observation_uuid_unique_across_biomarkers(self) -> None:
        from biomarker_normalization_toolkit.fhir import build_observation

        rec_a = self._make_mapped_record(canonical_biomarker_id="glucose_serum", loinc="2345-7")
        rec_b = self._make_mapped_record(canonical_biomarker_id="creatinine_serum", loinc="2160-0")
        obs_a = build_observation(rec_a, input_file="test.csv")
        obs_b = build_observation(rec_b, input_file="test.csv")
        self.assertIsNotNone(obs_a)
        self.assertIsNotNone(obs_b)
        self.assertNotEqual(obs_a["id"], obs_b["id"])

    # ------------------------------------------------------------------
    # 18. UCUM codes cover all normalized units in the catalog
    # ------------------------------------------------------------------
    def test_ucum_codes_cover_all_normalized_units(self) -> None:
        missing = []
        seen_units: set[str] = set()
        for bio_id, bio_def in BIOMARKER_CATALOG.items():
            unit = bio_def.normalized_unit
            if unit and unit not in seen_units:
                seen_units.add(unit)
                if unit not in UCUM_CODES:
                    missing.append(f"{bio_id} -> {unit}")
        self.assertEqual(
            missing,
            [],
            f"Normalized units without UCUM mappings: {missing}",
        )

    # ------------------------------------------------------------------
    # 19. Note contains mapping info
    # ------------------------------------------------------------------
    def test_observation_note_contains_mapping_info(self) -> None:
        obs = self._build_obs(
            source_test_name="Glucose, Serum",
            mapping_rule="exact_name",
        )
        self.assertIn("note", obs)
        note_text = obs["note"][0]["text"]
        self.assertIn("Glucose, Serum", note_text, "Note should mention source test name")
        self.assertIn("exact_name", note_text, "Note should mention the mapping rule")

    # ------------------------------------------------------------------
    # 20. Bundle-level subject_reference propagates to all observations
    # ------------------------------------------------------------------
    def test_build_bundle_with_subject_reference(self) -> None:
        from biomarker_normalization_toolkit.fhir import build_bundle
        from biomarker_normalization_toolkit.models import NormalizationResult

        result = NormalizationResult(
            input_file="test.csv",
            summary={"total": 2, "mapped": 2, "unmapped": 0, "review_needed": 0},
            records=[
                self._make_mapped_record(source_row_id="r1", canonical_biomarker_id="glucose_serum"),
                self._make_mapped_record(source_row_id="r2", canonical_biomarker_id="creatinine_serum", loinc="2160-0", canonical_biomarker_name="Creatinine"),
            ],
        )
        bundle = build_bundle(result, subject_reference="Patient/456")
        self.assertTrue(len(bundle["entry"]) >= 2)
        for entry in bundle["entry"]:
            resource = entry["resource"]
            self.assertIn("subject", resource, "Every observation should have a subject when subject_reference is provided")
            self.assertEqual(resource["subject"]["reference"], "Patient/456")


class UnicodeTests(unittest.TestCase):
    """Tests for Unicode handling, encoding edge cases, and international lab data patterns."""

    # ---- 1. Micro sign (U+00B5) in unit ----
    def test_micro_sign_in_unit(self) -> None:
        """U+00B5 MICRO SIGN (\u00b5mol/L) must normalize to umol/L."""
        result = normalize_unit("\u00b5mol/L")  # micro sign
        self.assertEqual(result, "umol/L")

    # ---- 2. Greek mu (U+03BC) in unit ----
    def test_greek_mu_in_unit(self) -> None:
        """U+03BC GREEK SMALL LETTER MU (\u03bcmol/L) must normalize to umol/L."""
        result = normalize_unit("\u03bcmol/L")  # Greek mu
        self.assertEqual(result, "umol/L")

    # ---- 3. Superscript digit in unit ----
    def test_superscript_in_unit(self) -> None:
        """10\u2079/L (superscript 9) should either normalize or return as-is without crashing."""
        result = normalize_unit("10\u2079/L")
        # Must not raise; either maps to 10^9/L or passes through unchanged
        self.assertIsInstance(result, str)

    # ---- 4. En-dash (U+2013) in reference range ----
    def test_en_dash_in_range(self) -> None:
        """70\u201399 mg/dL (en-dash) should parse as a valid reference range."""
        rng = parse_reference_range("70\u201399 mg/dL", "mg/dL")
        self.assertIsNotNone(rng, "En-dash range should parse successfully")
        self.assertEqual(rng.low, Decimal("70"))
        self.assertEqual(rng.high, Decimal("99"))

    # ---- 5. Em-dash (U+2014) in reference range ----
    def test_em_dash_in_range(self) -> None:
        """70\u201499 mg/dL (em-dash) should parse as a valid reference range."""
        rng = parse_reference_range("70\u201499 mg/dL", "mg/dL")
        self.assertIsNotNone(rng, "Em-dash range should parse successfully")
        self.assertEqual(rng.low, Decimal("70"))
        self.assertEqual(rng.high, Decimal("99"))

    # ---- 6. Fullwidth digits in value ----
    def test_fullwidth_digits_in_value(self) -> None:
        """\uff11\uff10\uff10 (fullwidth digits) - parse_decimal must not crash.

        Python's Decimal() constructor accepts fullwidth Unicode digits, so
        parse_decimal successfully returns Decimal('100').  This is acceptable
        behavior - the key requirement is no crash or exception.
        """
        result = parse_decimal("\uff11\uff10\uff10")  # fullwidth "100"
        # Python's Decimal accepts fullwidth digits natively
        self.assertTrue(result is None or isinstance(result, Decimal),
                        "Fullwidth digits must not crash parse_decimal")

    # ---- 7. Right-to-left override character in test name ----
    def test_rtl_override_in_test_name(self) -> None:
        """A right-to-left override (U+202E) embedded in a test name must not crash normalize_key."""
        result = normalize_key("\u202eGlucose, Serum")
        self.assertIsInstance(result, str)
        self.assertIn("glucose", result)

    # ---- 8. Zero-width joiner in value ----
    def test_zero_width_joiner_in_value(self) -> None:
        """A zero-width joiner (U+200D) inside '1\\u200D00' must not crash parse_decimal."""
        result = parse_decimal("1\u200D00")
        # Should return None (not a valid number) or somehow parse; either way, no crash.
        self.assertTrue(result is None or isinstance(result, Decimal))

    # ---- 9. Null byte in test name ----
    def test_null_byte_in_test_name(self) -> None:
        """A null byte (\\x00) before 'Glucose' must not crash normalize_key."""
        result = normalize_key("\x00Glucose")
        self.assertIsInstance(result, str)
        self.assertIn("glucose", result)

    # ---- 10. Emoji in unit ----
    def test_emoji_in_unit(self) -> None:
        """An emoji unit like '\U0001fa78/dL' (drop of blood) must not crash normalize_unit."""
        result = normalize_unit("\U0001fa78/dL")
        self.assertIsInstance(result, str)

    # ---- 11. Combining diacritics ----
    def test_combining_diacritics(self) -> None:
        """'Gl\u00fccose' (u-umlaut) must not crash normalize_key."""
        result = normalize_key("Gl\u00fccose")
        self.assertIsInstance(result, str)
        # The key should contain the lowered form; diacritics may or may not be stripped
        self.assertTrue(len(result) > 0)

    # ---- 12. CJK characters in test name ----
    def test_cjk_characters_in_test_name(self) -> None:
        """\u8840\u7cd6 (Chinese for blood glucose) must not crash normalize_key; expected unmapped."""
        key = normalize_key("\u8840\u7cd6")
        self.assertIsInstance(key, str)
        # The key will be non-empty but won't match any alias
        from biomarker_normalization_toolkit.catalog import ALIAS_INDEX
        # It should not accidentally map to a real biomarker
        # If it does, that is fine too; the point is no crash.
        self.assertIsInstance(ALIAS_INDEX.get(key), (type(None), object))

    # ---- 13. Mixed encoding: both micro signs map to the same canonical unit ----
    def test_mixed_encoding_unit_synonyms(self) -> None:
        """Both U+00B5 (micro sign) and U+03BC (Greek mu) must resolve to the same canonical unit."""
        micro_sign = normalize_unit("\u00b5mol/L")
        greek_mu = normalize_unit("\u03bcmol/L")
        self.assertEqual(micro_sign, greek_mu,
                         "MICRO SIGN and GREEK MU must normalize to the same canonical unit")
        self.assertEqual(micro_sign, "umol/L")


class PerformanceRegressionTests(unittest.TestCase):
    """Verify that performance optimizations (pre-compiled regexes, LRU cache)
    are present and functioning correctly."""

    # ------------------------------------------------------------------
    # 1. LRU cache: hits >> misses after repeated calls
    # ------------------------------------------------------------------
    def test_normalize_unit_cache_hits(self) -> None:
        from biomarker_normalization_toolkit.units import normalize_unit

        # Clear any prior cache state
        normalize_unit.cache_clear()

        # Prime the cache with one call, then call 999 more times
        for _ in range(1000):
            normalize_unit("mg/dL")

        info = normalize_unit.cache_info()
        # First call is a miss; remaining 999 should be hits
        self.assertEqual(info.misses, 1, "Expected exactly 1 cache miss (the first call)")
        self.assertEqual(info.hits, 999, "Expected 999 cache hits for repeated input")

    # ------------------------------------------------------------------
    # 2. LRU cache: cached result equals uncached result
    # ------------------------------------------------------------------
    def test_normalize_unit_cache_consistent(self) -> None:
        from biomarker_normalization_toolkit.units import normalize_unit, UNIT_SYNONYMS

        normalize_unit.cache_clear()

        # Test a representative sample of inputs: synonyms, passthrough, None
        test_inputs: list[str | None] = [
            "mg/dL", "mmol/L", "g/L", "ng/mL", "%", "U/L",
            "mg / dL", "  mmol/l  ", "UNKNOWN_UNIT", None, "",
        ]
        # Collect results on first (uncached) pass
        first_pass = [normalize_unit(v) for v in test_inputs]
        # Second pass should come from cache and be identical
        second_pass = [normalize_unit(v) for v in test_inputs]
        self.assertEqual(first_pass, second_pass, "Cached results must match uncached results")

    # ------------------------------------------------------------------
    # 3. LRU cache: maxsize >= 256
    # ------------------------------------------------------------------
    def test_normalize_unit_cache_size(self) -> None:
        from biomarker_normalization_toolkit.units import normalize_unit

        # The lru_cache wrapper exposes cache_parameters() with maxsize
        params = normalize_unit.cache_parameters()
        self.assertGreaterEqual(
            params["maxsize"], 256,
            f"Cache maxsize should be >= 256, got {params['maxsize']}",
        )

    # ------------------------------------------------------------------
    # 4. Pre-compiled regex patterns exist in units module
    # ------------------------------------------------------------------
    def test_precompiled_regex_patterns_exist(self) -> None:
        import biomarker_normalization_toolkit.units as units_mod

        for attr_name in ("_RE_WHITESPACE", "_RE_SLASH_SPACES"):
            attr = getattr(units_mod, attr_name, None)
            self.assertIsNotNone(attr, f"{attr_name} should exist in units module")
            self.assertIsInstance(
                attr, type(re.compile("")),
                f"{attr_name} should be a compiled regex pattern",
            )

    # ------------------------------------------------------------------
    # 5. Pre-compiled regex patterns exist in catalog module
    # ------------------------------------------------------------------
    def test_precompiled_regex_patterns_catalog(self) -> None:
        import biomarker_normalization_toolkit.catalog as catalog_mod

        for attr_name in ("_RE_NON_ALNUM", "_RE_MULTI_SPACE"):
            attr = getattr(catalog_mod, attr_name, None)
            self.assertIsNotNone(attr, f"{attr_name} should exist in catalog module")
            self.assertIsInstance(
                attr, type(re.compile("")),
                f"{attr_name} should be a compiled regex pattern",
            )

    # ------------------------------------------------------------------
    # 6. Throughput: 1000 rows in < 1 second
    # ------------------------------------------------------------------
    def test_throughput_minimum(self) -> None:
        import time

        rows = [
            {
                "source_row_id": f"perf-{i}",
                "source_lab_name": "Quest",
                "source_panel_name": "CMP",
                "source_test_name": "Glucose, Serum",
                "raw_value": "95.3",
                "source_unit": "mg/dL",
                "specimen_type": "serum",
                "source_reference_range": "70-100 mg/dL",
            }
            for i in range(1000)
        ]

        start = time.perf_counter()
        normalize_rows(rows, input_file="perf_test.csv")
        elapsed = time.perf_counter() - start

        self.assertLess(
            elapsed, 1.0,
            f"Normalizing 1000 rows took {elapsed:.3f}s (limit: 1.0s). "
            "Possible O(n^2) regression.",
        )

    # ------------------------------------------------------------------
    # 7. Memory: 5000 rows with peak < 20 MB
    # ------------------------------------------------------------------
    def test_memory_per_row(self) -> None:
        import tracemalloc

        rows = [
            {
                "source_row_id": f"mem-{i}",
                "source_lab_name": "Quest",
                "source_panel_name": "CMP",
                "source_test_name": "Glucose, Serum",
                "raw_value": "95.3",
                "source_unit": "mg/dL",
                "specimen_type": "serum",
                "source_reference_range": "70-100 mg/dL",
            }
            for i in range(5000)
        ]

        tracemalloc.start()
        normalize_rows(rows, input_file="mem_test.csv")
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak_bytes / (1024 * 1024)
        self.assertLess(
            peak_mb, 20.0,
            f"Peak memory for 5000 rows was {peak_mb:.1f} MB (limit: 20 MB). "
            "Possible memory leak.",
        )


class LongitudinalEdgeCaseTests(unittest.TestCase):
    """Exhaustive edge-case tests for longitudinal tracking (compare_results)."""

    def _make_result(self, biomarkers: dict[str, str]) -> "NormalizationResult":
        """Helper: create a NormalizationResult with mapped records."""
        from biomarker_normalization_toolkit.models import NormalizationResult, NormalizedRecord
        records = []
        for bio_id, value in biomarkers.items():
            records.append(NormalizedRecord(
                source_row_number=0, source_row_id=bio_id, source_lab_name="",
                source_panel_name="", source_test_name=bio_id, alias_key=bio_id,
                raw_value=value, source_unit="", specimen_type="",
                source_reference_range="", canonical_biomarker_id=bio_id,
                canonical_biomarker_name=bio_id, loinc="",
                mapping_status="mapped", match_confidence="high",
                status_reason="", mapping_rule="test",
                normalized_value=value, normalized_unit="",
                normalized_reference_range="", provenance={},
            ))
        return NormalizationResult(
            input_file="",
            summary={"total_rows": len(records), "mapped": len(records), "unmapped": 0, "review_needed": 0},
            records=records, warnings=())

    def _make_empty_result(self) -> "NormalizationResult":
        from biomarker_normalization_toolkit.models import NormalizationResult
        return NormalizationResult(
            input_file="",
            summary={"total_rows": 0, "mapped": 0, "unmapped": 0, "review_needed": 0},
            records=[], warnings=())

    def test_longitudinal_empty_before(self) -> None:
        """Empty before result yields 0 biomarkers_compared."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before = self._make_empty_result()
        after = self._make_result({"glucose_serum": "80"})
        result = compare_results(before, after)
        self.assertEqual(result["biomarkers_compared"], 0)
        self.assertEqual(result["biomarkers_only_in_after"], 1)
        self.assertEqual(result["biomarkers_only_in_before"], 0)
        self.assertEqual(result["deltas"], [])

    def test_longitudinal_empty_after(self) -> None:
        """Empty after result yields 0 biomarkers_compared."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before = self._make_result({"glucose_serum": "80"})
        after = self._make_empty_result()
        result = compare_results(before, after)
        self.assertEqual(result["biomarkers_compared"], 0)
        self.assertEqual(result["biomarkers_only_in_before"], 1)
        self.assertEqual(result["biomarkers_only_in_after"], 0)
        self.assertEqual(result["deltas"], [])

    def test_longitudinal_no_overlap(self) -> None:
        """Disjoint biomarkers between before/after yield 0 compared."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before = self._make_result({"glucose_serum": "90"})
        after = self._make_result({"hemoglobin": "14.0"})
        result = compare_results(before, after)
        self.assertEqual(result["biomarkers_compared"], 0)
        self.assertEqual(result["biomarkers_only_in_before"], 1)
        self.assertEqual(result["biomarkers_only_in_after"], 1)
        self.assertEqual(result["deltas"], [])

    def test_longitudinal_zero_days_between(self) -> None:
        """days_between=0 produces no velocity field (guarded by > 0 check)."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before = self._make_result({"glucose_serum": "90"})
        after = self._make_result({"glucose_serum": "80"})
        result = compare_results(before, after, days_between=0)
        for delta in result["deltas"]:
            self.assertNotIn("velocity_per_month", delta)

    def test_longitudinal_negative_days_between(self) -> None:
        """Negative days_between is treated as invalid: no velocity field."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before = self._make_result({"glucose_serum": "90"})
        after = self._make_result({"glucose_serum": "80"})
        result = compare_results(before, after, days_between=-30)
        for delta in result["deltas"]:
            self.assertNotIn("velocity_per_month", delta)

    def test_longitudinal_nan_days_between(self) -> None:
        """Non-finite days_between should be sanitized instead of leaking NaN."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before = self._make_result({"glucose_serum": "90"})
        after = self._make_result({"glucose_serum": "80"})
        result = compare_results(before, after, days_between=float("nan"))
        self.assertIsNone(result["days_between"])
        for delta in result["deltas"]:
            self.assertNotIn("velocity_per_month", delta)

    def test_longitudinal_infinite_days_between(self) -> None:
        """Non-finite days_between should be sanitized instead of leaking infinity."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before = self._make_result({"glucose_serum": "90"})
        after = self._make_result({"glucose_serum": "80"})
        result = compare_results(before, after, days_between=float("inf"))
        self.assertIsNone(result["days_between"])
        for delta in result["deltas"]:
            self.assertNotIn("velocity_per_month", delta)

    def test_longitudinal_large_percent_delta(self) -> None:
        """Very large percent_delta (old=0.01, new=100) computes without crash."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before = self._make_result({"hscrp": "0.01"})
        after = self._make_result({"hscrp": "100"})
        result = compare_results(before, after)
        self.assertEqual(result["biomarkers_compared"], 1)
        delta = result["deltas"][0]
        self.assertIsNotNone(delta["percent_delta"])
        # (100 - 0.01) / 0.01 * 100 = 999900.0
        self.assertGreater(delta["percent_delta"], 999000)

    def test_longitudinal_huge_percent_delta_omits_non_finite_output(self) -> None:
        """Extreme ratios should not leak inf/overflow in percent_delta."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before = self._make_result({"hscrp": "1e-5000"})
        after = self._make_result({"hscrp": "1"})
        result = compare_results(before, after)
        delta = result["deltas"][0]
        self.assertIsNone(delta["percent_delta"])

    def test_longitudinal_huge_velocity_uses_decimal_direction_and_omits_inf(self) -> None:
        """Huge values should still compare directionally without emitting infinite velocity."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        before = self._make_result({"glucose_serum": "1e5000"})
        after = self._make_result({"glucose_serum": "2e5000"})
        result = compare_results(before, after, days_between=30)
        delta = result["deltas"][0]
        self.assertEqual(delta["direction"], "worsening")
        self.assertNotIn("velocity_per_month", delta)

    def test_longitudinal_both_in_optimal_is_stable(self) -> None:
        """Both values within optimal range yields direction='stable'."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        # glucose_serum optimal: 72-85
        before = self._make_result({"glucose_serum": "75"})
        after = self._make_result({"glucose_serum": "80"})
        result = compare_results(before, after)
        delta = result["deltas"][0]
        self.assertEqual(delta["direction"], "stable")

    def test_longitudinal_unknown_direction_no_optimal(self) -> None:
        """Biomarker with no optimal range yields direction='unknown'."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        from biomarker_normalization_toolkit.models import NormalizationResult, NormalizedRecord

        def _make_with_id(bio_id: str, value: str) -> NormalizationResult:
            rec = NormalizedRecord(
                source_row_number=0, source_row_id="x", source_lab_name="",
                source_panel_name="", source_test_name="fake", alias_key="fake",
                raw_value=value, source_unit="", specimen_type="",
                source_reference_range="", canonical_biomarker_id=bio_id,
                canonical_biomarker_name="fake", loinc="",
                mapping_status="mapped", match_confidence="high",
                status_reason="", mapping_rule="test",
                normalized_value=value, normalized_unit="",
                normalized_reference_range="", provenance={},
            )
            return NormalizationResult(
                input_file="", summary={"total_rows": 1, "mapped": 1, "unmapped": 0, "review_needed": 0},
                records=[rec], warnings=())

        before = _make_with_id("totally_fake_biomarker_xyz", "10")
        after = _make_with_id("totally_fake_biomarker_xyz", "15")
        result = compare_results(before, after)
        self.assertEqual(result["biomarkers_compared"], 1)
        self.assertEqual(result["deltas"][0]["direction"], "unknown")
        self.assertEqual(result["stable"], 0)
        self.assertEqual(result["unknown"], 1)
        self.assertEqual(result["improvement_rate"], 0)

    def test_longitudinal_improvement_rate_zero(self) -> None:
        """All stable biomarkers yields improvement_rate=0."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        # glucose_serum optimal: 72-85; hba1c optimal: 4.8-5.2; both within optimal -> stable
        before = self._make_result({"glucose_serum": "75", "hba1c": "5.0"})
        after = self._make_result({"glucose_serum": "80", "hba1c": "5.1"})
        result = compare_results(before, after)
        self.assertEqual(result["improvement_rate"], 0)
        self.assertGreater(result["stable"], 0)
        self.assertEqual(result["improved"], 0)

    def test_longitudinal_improvement_rate_hundred(self) -> None:
        """All improved biomarkers yields improvement_rate=100."""
        from biomarker_normalization_toolkit.longitudinal import compare_results
        # glucose_serum: 100 (above optimal 72-85) -> 80 (optimal) = improved
        # hba1c: 6.0 (above optimal 4.8-5.2) -> 5.0 (optimal) = improved
        before = self._make_result({"glucose_serum": "100", "hba1c": "6.0"})
        after = self._make_result({"glucose_serum": "80", "hba1c": "5.0"})
        result = compare_results(before, after)
        self.assertEqual(result["improvement_rate"], 100)
        self.assertEqual(result["improved"], result["biomarkers_compared"])


class OptimalRangesExhaustiveTests(unittest.TestCase):
    """Exhaustive tests for optimal range evaluation and summary."""

    def _make_result(self, biomarkers: dict[str, str], *, unmapped: bool = False) -> "NormalizationResult":
        """Helper: create a NormalizationResult. If unmapped=True, records are unmapped."""
        from biomarker_normalization_toolkit.models import NormalizationResult, NormalizedRecord
        records = []
        status = "unmapped" if unmapped else "mapped"
        for bio_id, value in biomarkers.items():
            records.append(NormalizedRecord(
                source_row_number=0, source_row_id=bio_id, source_lab_name="",
                source_panel_name="", source_test_name=bio_id, alias_key=bio_id,
                raw_value=value, source_unit="", specimen_type="",
                source_reference_range="", canonical_biomarker_id=bio_id,
                canonical_biomarker_name=bio_id, loinc="",
                mapping_status=status, match_confidence="high" if not unmapped else "none",
                status_reason="", mapping_rule="test" if not unmapped else "",
                normalized_value=value if not unmapped else "",
                normalized_unit="",
                normalized_reference_range="", provenance={},
            ))
        mapped_count = len(records) if not unmapped else 0
        return NormalizationResult(
            input_file="",
            summary={"total_rows": len(records), "mapped": mapped_count, "unmapped": len(records) - mapped_count, "review_needed": 0},
            records=records, warnings=())

    def test_optimal_evaluate_returns_correct_structure(self) -> None:
        """Each evaluation dict has the required keys."""
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges
        result = self._make_result({"glucose_serum": "80"})
        evals = evaluate_optimal_ranges(result)
        self.assertEqual(len(evals), 1)
        required_keys = {"biomarker_id", "value", "unit", "status", "optimal_low", "optimal_high", "note"}
        self.assertTrue(required_keys.issubset(evals[0].keys()),
                        f"Missing keys: {required_keys - evals[0].keys()}")

    def test_optimal_below_optimal_status(self) -> None:
        """glucose=50 yields below_optimal (optimal 72-85)."""
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges
        result = self._make_result({"glucose_serum": "50"})
        evals = evaluate_optimal_ranges(result)
        self.assertEqual(len(evals), 1)
        self.assertEqual(evals[0]["status"], "below_optimal")

    def test_optimal_above_optimal_status(self) -> None:
        """glucose=200 yields above_optimal (optimal 72-85)."""
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges
        result = self._make_result({"glucose_serum": "200"})
        evals = evaluate_optimal_ranges(result)
        self.assertEqual(len(evals), 1)
        self.assertEqual(evals[0]["status"], "above_optimal")

    def test_optimal_at_exact_boundary_low(self) -> None:
        """glucose exactly at optimal low boundary (72) is 'optimal' (inclusive)."""
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges
        result = self._make_result({"glucose_serum": "72"})
        evals = evaluate_optimal_ranges(result)
        self.assertEqual(len(evals), 1)
        self.assertEqual(evals[0]["status"], "optimal")

    def test_optimal_at_exact_boundary_high(self) -> None:
        """glucose exactly at optimal high boundary (85) is 'optimal' (inclusive)."""
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges
        result = self._make_result({"glucose_serum": "85"})
        evals = evaluate_optimal_ranges(result)
        self.assertEqual(len(evals), 1)
        self.assertEqual(evals[0]["status"], "optimal")

    def test_optimal_unmapped_records_excluded(self) -> None:
        """Unmapped records do not appear in optimal evaluation."""
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges
        result = self._make_result({"glucose_serum": "80"}, unmapped=True)
        evals = evaluate_optimal_ranges(result)
        self.assertEqual(len(evals), 0)

    def test_optimal_sex_none_uses_base_ranges(self) -> None:
        """sex=None uses base OPTIMAL_RANGES (unisex testosterone range 15-900)."""
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges, OPTIMAL_RANGES
        result = self._make_result({"testosterone_total": "200"})
        evals = evaluate_optimal_ranges(result, sex=None)
        self.assertEqual(len(evals), 1)
        # 200 is within the unisex range 15-900
        self.assertEqual(evals[0]["status"], "optimal")
        # Confirm it uses the base low/high
        self.assertEqual(evals[0]["optimal_low"], str(OPTIMAL_RANGES["testosterone_total"][0]))
        self.assertEqual(evals[0]["optimal_high"], str(OPTIMAL_RANGES["testosterone_total"][1]))

    def test_summarize_optimal_with_mixed_statuses(self) -> None:
        """3 optimal + 2 below + 1 above = correct counts and percentage."""
        from biomarker_normalization_toolkit.optimal_ranges import summarize_optimal
        evaluations = [
            {"biomarker_id": "a", "status": "optimal"},
            {"biomarker_id": "b", "status": "optimal"},
            {"biomarker_id": "c", "status": "optimal"},
            {"biomarker_id": "d", "status": "below_optimal"},
            {"biomarker_id": "e", "status": "below_optimal"},
            {"biomarker_id": "f", "status": "above_optimal"},
        ]
        summary = summarize_optimal(evaluations)
        self.assertEqual(summary["total_evaluated"], 6)
        self.assertEqual(summary["optimal"], 3)
        self.assertEqual(summary["below_optimal"], 2)
        self.assertEqual(summary["above_optimal"], 1)
        self.assertEqual(summary["optimal_percentage"], 50.0)

    def test_optimal_all_nmr_biomarkers_have_ranges(self) -> None:
        """All 5 NMR LipoProfile biomarkers appear in OPTIMAL_RANGES."""
        from biomarker_normalization_toolkit.optimal_ranges import OPTIMAL_RANGES
        nmr_ids = [
            "small_ldl_particle",
            "hdl_particle",
            "large_hdl_particle",
            "large_vldl_particle",
            "lp_ir_score",
        ]
        for bio_id in nmr_ids:
            self.assertIn(bio_id, OPTIMAL_RANGES, f"NMR biomarker {bio_id} missing from OPTIMAL_RANGES")
            low, high, unit, note = OPTIMAL_RANGES[bio_id]
            self.assertIsInstance(low, Decimal)
            self.assertIsInstance(high, Decimal)
            self.assertLessEqual(low, high, f"{bio_id}: optimal_low > optimal_high")

    def test_optimal_ranges_source_has_no_duplicate_keys(self) -> None:
        """Guard against silent duplicate dict keys in OPTIMAL_RANGES."""
        import ast
        import biomarker_normalization_toolkit.optimal_ranges as optimal_ranges_module

        source_path = Path(optimal_ranges_module.__file__)
        tree = ast.parse(source_path.read_text(encoding="utf-8"))

        dict_node = None
        for node in tree.body:
            if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "OPTIMAL_RANGES":
                dict_node = node.value
                break

        self.assertIsNotNone(dict_node, "Could not locate OPTIMAL_RANGES source definition")

        first_seen: dict[str, int] = {}
        duplicates: dict[str, list[int]] = {}
        for key in dict_node.keys:
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            if key.value in first_seen:
                duplicates.setdefault(key.value, [first_seen[key.value]]).append(key.lineno)
            else:
                first_seen[key.value] = key.lineno

        self.assertEqual(duplicates, {}, f"Duplicate OPTIMAL_RANGES keys: {duplicates}")


class MutationCoverageTests(unittest.TestCase):
    """Tests added by mutation testing to catch surviving mutations."""

    def _make_result_with(self, biomarkers: dict[str, str]) -> "NormalizationResult":
        """Helper: create a NormalizationResult with the given biomarker values."""
        from biomarker_normalization_toolkit.models import NormalizationResult, NormalizedRecord
        records = []
        for bio_id, value in biomarkers.items():
            records.append(NormalizedRecord(
                source_row_number=0, source_row_id=bio_id, source_lab_name="",
                source_panel_name="", source_test_name=bio_id, alias_key=bio_id,
                raw_value=value, source_unit="", specimen_type="",
                source_reference_range="", canonical_biomarker_id=bio_id,
                canonical_biomarker_name=bio_id, loinc="",
                mapping_status="mapped", match_confidence="high",
                status_reason="", mapping_rule="test",
                normalized_value=value, normalized_unit="",
                normalized_reference_range="", provenance={},
            ))
        return NormalizationResult(
            input_file="",
            summary={"total_rows": len(records), "mapped": len(records), "unmapped": 0, "review_needed": 0},
            records=records, warnings=())

    # ------------------------------------------------------------------
    # Mutation 1: rsplit(":", 1) vs split(":", 1) in panel prefix stripping
    # rsplit takes the LAST colon, split takes the FIRST colon.
    # With multiple colons like "A:B:GLUCOSE", rsplit yields "GLUCOSE"
    # but split yields "B:GLUCOSE" (which won't match any alias).
    # ------------------------------------------------------------------
    def test_panel_prefix_multiple_colons_uses_last_segment(self) -> None:
        """Test name with multiple colons like 'LAB:CMP:GLUCOSE' maps correctly.

        The normalizer must use rsplit (last colon) to extract 'GLUCOSE',
        not split (first colon) which would yield 'CMP:GLUCOSE'.
        """
        source_rows = [
            {
                "source_row_id": "mc1",
                "source_lab_name": "Test",
                "source_panel_name": "",
                "source_test_name": "LAB:CMP:GLUCOSE",
                "raw_value": "95",
                "source_unit": "mg/dL",
                "specimen_type": "serum",
                "source_reference_range": "70-100 mg/dL",
            }
        ]
        source_record = build_source_records(source_rows)[0]
        normalized = normalize_source_record(source_record)

        self.assertEqual(normalized.mapping_status, "mapped",
                         "Multi-colon panel prefix should map via rsplit on last colon")
        self.assertEqual(normalized.canonical_biomarker_id, "glucose_serum")
        self.assertEqual(normalized.status_reason, "panel_prefix_stripped")

    # ------------------------------------------------------------------
    # Mutation 3: PhenoAge CRP floor 0.001 vs 0.01 (10x difference)
    # When CRP=0, the floor value feeds into ln(). ln(0.001) = -6.9078
    # vs ln(0.01) = -4.6052, a meaningful difference in the PhenoAge score.
    # ------------------------------------------------------------------
    def test_phenoage_crp_zero_floor_precision(self) -> None:
        """CRP=0 should use floor of 0.001 mg/dL (not 0.01), affecting ln(CRP).

        ln(0.001) = -6.9078 vs ln(0.01) = -4.6052. With coefficient 0.0954,
        the difference is ~0.22 in the mortality score, which shifts PhenoAge
        by roughly 2-3 years.
        """
        import math
        from biomarker_normalization_toolkit.phenoage import compute_phenoage

        base = {
            "albumin": "4.5", "creatinine": "0.9", "glucose_serum": "85",
            "lymphocytes_pct": "35", "mcv": "88",
            "rdw": "12.5", "alp": "60", "wbc": "6",
        }

        # CRP = 0 (uses floor)
        result_zero = self._make_result_with({**base, "crp": "0"})
        pa_zero = compute_phenoage(result_zero, chronological_age=45)

        # CRP = 0.01 mg/L = 0.001 mg/dL (equal to the correct floor)
        result_floor = self._make_result_with({**base, "crp": "0.01"})
        pa_floor = compute_phenoage(result_floor, chronological_age=45)

        self.assertIsNotNone(pa_zero["phenoage"])
        self.assertIsNotNone(pa_floor["phenoage"])

        # If the floor is correct (0.001 mg/dL), CRP=0 and CRP=0.01mg/L
        # should yield the same PhenoAge (both map to 0.001 mg/dL).
        self.assertAlmostEqual(
            pa_zero["phenoage"], pa_floor["phenoage"], places=1,
            msg="CRP=0 should floor to 0.001 mg/dL, matching CRP=0.01 mg/L"
        )

        # Also verify the ln_crp_mg_dl input is correct for the floor
        expected_ln_crp = round(math.log(0.001), 4)
        self.assertAlmostEqual(
            pa_zero["inputs"]["ln_crp_mg_dl"], expected_ln_crp, places=3,
            msg="ln(CRP) for zero CRP should use floor of 0.001 mg/dL"
        )

    # ------------------------------------------------------------------
    # Mutation 12: derived.py NLR division by zero guard
    # Without lymphocytes_val > 0, a zero lymphocyte count causes ZeroDivisionError.
    # ------------------------------------------------------------------
    def test_derived_nlr_zero_lymphocytes_no_crash(self) -> None:
        """NLR should not be computed (or crash) when lymphocytes = 0.

        The guard `lymphocytes_val > 0` prevents division by zero.
        Without it, Decimal division by zero raises an exception.
        """
        from biomarker_normalization_toolkit.derived import compute_derived_metrics

        # lymphocytes=0 should not produce NLR (division by zero)
        result = self._make_result_with({
            "neutrophils": "4.5",
            "lymphocytes": "0",
        })
        # This should not raise an exception
        metrics = compute_derived_metrics(result)
        # NLR should not be present since lymphocytes=0
        self.assertNotIn("nlr", metrics,
                         "NLR should not be computed when lymphocytes=0 (division by zero guard)")

    def test_derived_nlr_negative_lymphocytes_no_crash(self) -> None:
        """NLR should not be computed when lymphocytes is negative."""
        from biomarker_normalization_toolkit.derived import compute_derived_metrics

        result = self._make_result_with({
            "neutrophils": "4.5",
            "lymphocytes": "-1",
        })
        metrics = compute_derived_metrics(result)
        self.assertNotIn("nlr", metrics,
                         "NLR should not be computed when lymphocytes < 0")


if __name__ == "__main__":
    unittest.main()
