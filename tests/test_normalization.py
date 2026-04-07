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
from biomarker_normalization_toolkit.io_utils import read_ccda_input, read_fhir_input, read_hl7_input, read_input, read_input_csv
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


if __name__ == "__main__":
    unittest.main()
