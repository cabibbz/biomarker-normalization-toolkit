from __future__ import annotations

import json
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from biomarker_normalization_toolkit.api import app


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"

client = TestClient(app)


class APITests(unittest.TestCase):

    def test_health(self) -> None:
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("version", data)
        self.assertGreater(data["biomarkers"], 0)

    def test_catalog(self) -> None:
        response = client.get("/catalog")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["count"], 70)
        self.assertEqual(len(data["biomarkers"]), data["count"])

    def test_catalog_search(self) -> None:
        response = client.get("/catalog?search=glucose")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["count"], 0)
        for bio in data["biomarkers"]:
            searchable = f"{bio['biomarker_id']} {bio['canonical_name']} {' '.join(bio['aliases'])}".lower()
            self.assertIn("glucose", searchable)

    def test_normalize_json(self) -> None:
        response = client.post("/normalize", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": "70-99 mg/dL"},
                {"source_test_name": "HbA1c", "raw_value": "5.4", "source_unit": "%",
                 "specimen_type": "whole blood", "source_row_id": "2", "source_reference_range": ""},
            ],
            "input_file": "test.csv",
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["summary"]["total_rows"], 2)
        self.assertEqual(data["summary"]["mapped"], 2)
        self.assertEqual(len(data["records"]), 2)

    def test_normalize_with_fhir(self) -> None:
        response = client.post("/normalize?emit_fhir=true", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("fhir_bundle", data)
        self.assertEqual(data["fhir_bundle"]["resourceType"], "Bundle")

    def test_normalize_empty_rows(self) -> None:
        response = client.post("/normalize", json={"rows": []})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("error", data)

    def test_normalize_upload_csv(self) -> None:
        csv_path = FIXTURES / "input" / "v0_sample.csv"
        with csv_path.open("rb") as f:
            response = client.post(
                "/normalize/upload",
                files={"file": ("v0_sample.csv", f, "text/csv")},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["summary"]["total_rows"], 6)
        self.assertEqual(data["summary"]["mapped"], 4)

    def test_normalize_upload_hl7(self) -> None:
        hl7_path = ROOT / "sample data" / "hl7-examples" / "sample_oru_cmp.hl7"
        if not hl7_path.exists():
            self.skipTest("HL7 sample not available")
        with hl7_path.open("rb") as f:
            response = client.post(
                "/normalize/upload",
                files={"file": ("sample.hl7", f, "application/octet-stream")},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["summary"]["mapped"], 0)

    def test_analyze_json(self) -> None:
        response = client.post("/analyze", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
                {"source_test_name": "Unknown Test", "raw_value": "42", "source_unit": "U/L",
                 "specimen_type": "serum", "source_row_id": "2", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["summary"]["mapped"], 1)
        self.assertEqual(data["summary"]["unmapped"], 1)
        self.assertIn("Glucose", data["mapped_biomarkers"])
        self.assertIn("Unknown Test", data["unmapped_tests"])
        self.assertIn("mapping_rate", data)

    def test_analyze_upload(self) -> None:
        csv_path = FIXTURES / "input" / "coverage_wave_2.csv"
        with csv_path.open("rb") as f:
            response = client.post(
                "/analyze/upload",
                files={"file": ("wave2.csv", f, "text/csv")},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["mapping_rate"], 90)

    def test_openapi_docs_available(self) -> None:
        response = client.get("/docs")
        self.assertEqual(response.status_code, 200)

    def test_openapi_schema_available(self) -> None:
        response = client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertIn("/health", schema["paths"])
        self.assertIn("/normalize", schema["paths"])
        self.assertIn("/catalog", schema["paths"])


if __name__ == "__main__":
    unittest.main()
