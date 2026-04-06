from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shutil

from decimal import Decimal

from biomarker_normalization_toolkit.fhir import build_bundle
from biomarker_normalization_toolkit.io_utils import read_fhir_input, read_input, read_input_csv
from biomarker_normalization_toolkit.normalizer import build_source_records, normalize_rows, normalize_source_record
from biomarker_normalization_toolkit.units import convert_to_normalized, is_inequality_value, parse_reference_range


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


class NormalizationTests(unittest.TestCase):
    def test_sample_fixture_matches_expected_json(self) -> None:
        input_path = FIXTURES / "input" / "v0_sample.csv"
        expected_path = FIXTURES / "expected" / "v0_sample_expected.json"

        rows = read_input_csv(input_path)
        result = normalize_rows(rows, input_file=input_path.name)

        actual = result.to_json_dict()
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
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
            self.assertEqual(payload["summary"]["mapped"], 4)
            self.assertEqual(payload["summary"]["review_needed"], 1)
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
        self.assertEqual(len(bundle["entry"]), 4)

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
            self.assertEqual(len(bundle["entry"]), 4)

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
            self.assertIn("Mapped: 4", summary_text)


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

    def test_gt_lt_range_rejected(self) -> None:
        self.assertIsNone(parse_reference_range(">60 mg/dL", "mg/dL"))
        self.assertIsNone(parse_reference_range("<200 mg/dL", "mg/dL"))

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
        self.assertAlmostEqual(float(result), 0.19866, places=4)

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
        self.assertAlmostEqual(float(result), 30.0, places=4)

    def test_vitamin_b12_pmol_to_pgml(self) -> None:
        result = convert_to_normalized(Decimal("369"), "vitamin_b12", "pmol/L")
        self.assertAlmostEqual(float(result), 499.995, places=2)

    def test_folate_nmol_to_ngml(self) -> None:
        result = convert_to_normalized(Decimal("22.7"), "folate", "nmol/L")
        self.assertAlmostEqual(float(result), 5.1438, places=3)

    def test_iron_umol_to_ugdl(self) -> None:
        result = convert_to_normalized(Decimal("14.3"), "iron", "umol/L")
        self.assertAlmostEqual(float(result), 79.8655, places=2)

    def test_magnesium_mmol_to_mgdl(self) -> None:
        result = convert_to_normalized(Decimal("0.83"), "magnesium", "mmol/L")
        self.assertAlmostEqual(float(result), 1.992, places=3)


    # --- FHIR ingest ---

    def test_fhir_single_observation_ingest(self) -> None:
        fhir_path = ROOT / "sample data" / "fhir-examples" / "observation-example-f001-glucose.json"
        if not fhir_path.exists():
            self.skipTest("FHIR example file not available")
        rows = read_fhir_input(fhir_path)
        self.assertEqual(len(rows), 1)
        self.assertIn("Glucose", rows[0]["source_test_name"])
        self.assertEqual(rows[0]["raw_value"], "6.3")

    def test_fhir_bundle_ingest(self) -> None:
        fhir_path = ROOT / "sample data" / "fhir-examples" / "hapi_lab_observations.json"
        if not fhir_path.exists():
            self.skipTest("HAPI FHIR bundle not available")
        rows = read_fhir_input(fhir_path)
        self.assertGreater(len(rows), 0)
        result = normalize_rows(rows)
        self.assertGreater(result.summary["mapped"], 0)

    def test_read_input_auto_detects_csv(self) -> None:
        csv_path = FIXTURES / "input" / "v0_sample.csv"
        rows = read_input(csv_path)
        self.assertEqual(len(rows), 6)

    def test_read_input_auto_detects_json(self) -> None:
        fhir_path = ROOT / "sample data" / "fhir-examples" / "observation-example-f001-glucose.json"
        if not fhir_path.exists():
            self.skipTest("FHIR example file not available")
        rows = read_input(fhir_path)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
