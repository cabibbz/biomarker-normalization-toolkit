from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shutil

from decimal import Decimal

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.fhir import build_bundle
from biomarker_normalization_toolkit.io_utils import read_ccda_input, read_excel_input, read_fhir_input, read_hl7_input, read_input, read_input_csv
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

    # --- Catalog integrity ---

    def test_corrected_loinc_assignments(self) -> None:
        self.assertEqual(BIOMARKER_CATALOG["bun"].loinc, "3094-0")
        self.assertEqual(BIOMARKER_CATALOG["iron"].loinc, "2498-4")
        self.assertEqual(BIOMARKER_CATALOG["potassium"].loinc, "2823-3")
        self.assertEqual(BIOMARKER_CATALOG["uric_acid"].loinc, "3084-1")

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

    # --- HL7v2 ingest ---

    def test_hl7_cbc_ingest(self) -> None:
        hl7_path = ROOT / "sample data" / "hl7-examples" / "sample_oru_cbc.hl7"
        if not hl7_path.exists():
            self.skipTest("HL7 CBC sample not available")
        rows = read_hl7_input(hl7_path)
        self.assertEqual(len(rows), 14)
        result = normalize_rows(rows)
        self.assertGreater(result.summary["mapped"], 0)

    def test_hl7_cmp_ingest(self) -> None:
        hl7_path = ROOT / "sample data" / "hl7-examples" / "sample_oru_cmp.hl7"
        if not hl7_path.exists():
            self.skipTest("HL7 CMP sample not available")
        rows = read_hl7_input(hl7_path)
        self.assertEqual(len(rows), 16)
        result = normalize_rows(rows)
        self.assertGreaterEqual(result.summary["mapped"], 13)

    def test_hl7_sn_inequality_parsing(self) -> None:
        hl7_path = ROOT / "sample data" / "hl7-examples" / "sample_oru_edge_cases.hl7"
        if not hl7_path.exists():
            self.skipTest("HL7 edge cases sample not available")
        rows = read_hl7_input(hl7_path)
        # Find the glucose row with SN value <^10
        glucose_rows = [r for r in rows if "Glucose" in r["source_test_name"] and r["raw_value"] == "<10"]
        self.assertEqual(len(glucose_rows), 1)
        self.assertEqual(glucose_rows[0]["raw_value"], "<10")

    def test_hl7_qualitative_values_preserved(self) -> None:
        hl7_path = ROOT / "sample data" / "hl7-examples" / "sample_oru_edge_cases.hl7"
        if not hl7_path.exists():
            self.skipTest("HL7 edge cases sample not available")
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
        ccda_path = ROOT / "sample data" / "ccda-examples" / "Result with lab location(C-CDAR2.1).xml"
        if not ccda_path.exists():
            self.skipTest("C-CDA example not available")
        rows = read_ccda_input(ccda_path)
        self.assertGreater(len(rows), 0)
        self.assertEqual(rows[0]["raw_value"], "1.015")

    def test_ccda_non_ucum_units(self) -> None:
        ccda_path = ROOT / "sample data" / "ccda-examples" / "Results Unit Non-UCUM(C-CDA2.1).xml"
        if not ccda_path.exists():
            self.skipTest("C-CDA example not available")
        rows = read_ccda_input(ccda_path)
        self.assertGreater(len(rows), 0)
        self.assertEqual(rows[0]["raw_value"], "152")

    # --- Excel ingest ---

    def test_excel_ingest_with_flexible_headers(self) -> None:
        xlsx_path = ROOT / "sample data" / "test_lab_results.xlsx"
        if not xlsx_path.exists():
            self.skipTest("Excel test file not available")
        rows = read_excel_input(xlsx_path)
        self.assertEqual(len(rows), 10)
        result = normalize_rows(rows)
        self.assertEqual(result.summary["mapped"], 9)
        self.assertEqual(result.summary["unmapped"], 1)

    def test_read_input_auto_detects_xlsx(self) -> None:
        xlsx_path = ROOT / "sample data" / "test_lab_results.xlsx"
        if not xlsx_path.exists():
            self.skipTest("Excel test file not available")
        rows = read_input(xlsx_path)
        self.assertEqual(len(rows), 10)

    def test_read_input_auto_detects_xml(self) -> None:
        ccda_path = ROOT / "sample data" / "ccda-examples" / "Result with lab location(C-CDAR2.1).xml"
        if not ccda_path.exists():
            self.skipTest("C-CDA example not available")
        rows = read_input(ccda_path)
        self.assertGreater(len(rows), 0)

    def test_read_input_auto_detects_hl7(self) -> None:
        hl7_path = ROOT / "sample data" / "hl7-examples" / "sample_oru_cbc.hl7"
        if not hl7_path.exists():
            self.skipTest("HL7 sample not available")
        rows = read_input(hl7_path)
        self.assertEqual(len(rows), 14)

    # --- Custom alias overrides ---

    def test_custom_alias_loading(self) -> None:
        from biomarker_normalization_toolkit.catalog import load_custom_aliases
        alias_path = ROOT / "sample data" / "test_aliases.json"
        if not alias_path.exists():
            self.skipTest("Test aliases file not available")
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
        self.assertEqual(normalize_unit("m[IU]/mL"), "mIU/L")
        self.assertEqual(normalize_unit("[IU]/mL"), "IU/mL")

    def test_fhir_round_trip_tsh(self) -> None:
        """Export to FHIR then re-import should preserve the mapping."""
        from biomarker_normalization_toolkit.fhir import build_bundle
        rows = [{"source_row_id": "rt1", "source_test_name": "TSH", "raw_value": "2.5",
                 "source_unit": "mIU/L", "specimen_type": "", "source_reference_range": "0.4-4.0 mIU/L"}]
        result = normalize_rows(rows, input_file="round_trip.csv")
        bundle = build_bundle(result)
        # The FHIR bundle uses UCUM code m[IU]/L — simulate re-ingest
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

    def test_fhir_bundle_has_total(self) -> None:
        from biomarker_normalization_toolkit.fhir import build_bundle
        rows = [{"source_row_id": "t1", "source_test_name": "Glucose", "raw_value": "100",
                 "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""}]
        result = normalize_rows(rows, input_file="total_test.csv")
        bundle = build_bundle(result)
        self.assertIn("total", bundle)
        self.assertEqual(bundle["total"], len(bundle["entry"]))

    # --- Scrutiny pass: API validates non-dict rows (Fix #7) ---

    def test_api_rejects_non_dict_rows(self) -> None:
        try:
            from fastapi.testclient import TestClient
        except Exception:
            self.skipTest("httpx/fastapi not available")
        from biomarker_normalization_toolkit.api import app
        client = TestClient(app)
        response = client.post("/normalize", json={"rows": ["not a dict", 123]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("not objects", response.json()["error"])

    # --- Deep scrutiny pass 2: Legacy unit synonyms ---

    def test_legacy_unit_synonyms_normalize(self) -> None:
        from biomarker_normalization_toolkit.units import normalize_unit
        self.assertEqual(normalize_unit("gm/dL"), "g/dL")
        self.assertEqual(normalize_unit("gm/L"), "g/L")
        self.assertEqual(normalize_unit("gm%"), "g/dL")
        self.assertEqual(normalize_unit("cells/cumm"), "#/uL")
        self.assertEqual(normalize_unit("thou/cumm"), "K/uL")
        self.assertEqual(normalize_unit("K/cumm"), "K/uL")
        self.assertEqual(normalize_unit("mill/cumm"), "M/uL")
        self.assertEqual(normalize_unit("ug/L"), "ug/L")

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
        except Exception:
            self.skipTest("httpx/fastapi not available")
        from biomarker_normalization_toolkit.api import app
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
        # Filename should be sanitized — no path traversal in output
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

    def test_bare_neutrophils_with_pct_unit_does_not_silently_map(self) -> None:
        """Bare 'Neutrophils' with unit '%' should NOT map to neutrophils_pct."""
        rows = [{"source_row_id": "np1", "source_test_name": "Neutrophils", "raw_value": "65",
                 "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""}]
        result = normalize_rows(rows)
        # Should hit absolute neutrophils (no % conversion) → review_needed
        self.assertEqual(result.records[0].mapping_status, "review_needed")
        self.assertEqual(result.records[0].status_reason, "unsupported_unit_for_biomarker")

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


if __name__ == "__main__":
    unittest.main()
