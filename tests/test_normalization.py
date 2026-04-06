from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from biomarker_normalization_toolkit.fhir import build_bundle
from biomarker_normalization_toolkit.io_utils import read_input_csv
from biomarker_normalization_toolkit.normalizer import build_source_records, normalize_rows, normalize_source_record


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


if __name__ == "__main__":
    unittest.main()
