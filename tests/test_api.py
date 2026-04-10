from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from biomarker_normalization_toolkit.api import _metrics, _rate_limiter, app


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
INTEROP_FIXTURES = FIXTURES / "input" / "interop"

client = TestClient(app)


def _reset_api_test_state() -> None:
    _rate_limiter.reset()
    _metrics.reset()


class APITests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_api_test_state()

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

    def test_optimal_ranges_endpoint_applies_sex_specific_ranges(self) -> None:
        payload = {
            "sex": "female",
            "rows": [
                {"source_test_name": "Testosterone Total", "raw_value": "100", "source_unit": "ng/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
            ],
        }
        response = client.post("/optimal-ranges", json=payload)
        self.assertEqual(response.status_code, 200)
        evaluation = response.json()["evaluations"][0]
        self.assertEqual(evaluation["biomarker_id"], "testosterone_total")
        self.assertEqual(evaluation["status"], "above_optimal")

    def test_normalize_empty_rows(self) -> None:
        response = client.post("/normalize", json={"rows": []})
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)

    def test_normalize_non_string_values_coerced(self) -> None:
        response = client.post("/normalize", json={
            "rows": [{"source_test_name": 123, "raw_value": 100, "source_unit": "mg/dL",
                      "specimen_type": "serum", "source_row_id": 1, "source_reference_range": ""}],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["summary"]["total_rows"], 1)

    def test_upload_rejects_unsupported_extension(self) -> None:
        response = client.post(
            "/normalize/upload",
            files={"file": ("malware.exe", b"not a lab file", "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file type", response.json()["error"])

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
        self.assertGreaterEqual(data["summary"]["mapped"], 5)

    def test_normalize_upload_hl7(self) -> None:
        hl7_path = INTEROP_FIXTURES / "hl7_oru_cmp.hl7"
        with hl7_path.open("rb") as f:
            response = client.post(
                "/normalize/upload",
                files={"file": ("sample.hl7", f, "application/octet-stream")},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["summary"]["mapped"], 0)

    def test_normalize_upload_sanitizes_windows_style_filename(self) -> None:
        csv_path = FIXTURES / "input" / "v0_sample.csv"
        with csv_path.open("rb") as f:
            response = client.post(
                "/normalize/upload",
                files={"file": ("..\\..\\secret\\evil.csv", f, "text/csv")},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["input_file"], "evil.csv")

    def test_normalize_json_sanitizes_windows_style_input_file(self) -> None:
        response = client.post("/normalize", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": "70-99 mg/dL"},
            ],
            "input_file": "..\\..\\secret\\evil.csv",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["input_file"], "evil.csv")

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
        schema_text = str(schema)
        self.assertNotIn("X-API-Key", schema_text)


    # ─── GET /metrics ────────────────────────────────────────

    def test_metrics_json(self) -> None:
        """GET /metrics with Accept: application/json returns a JSON dict."""
        response = client.get("/metrics", headers={"Accept": "application/json"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("uptime_seconds", data)
        self.assertIn("total_requests", data)
        self.assertIn("total_errors", data)
        self.assertIn("error_rate", data)
        self.assertIn("total_rows_processed", data)
        self.assertIn("avg_latency_ms", data)
        self.assertIn("requests_per_endpoint", data)
        self.assertIn("status_code_counts", data)
        self.assertIsInstance(data["total_requests"], int)

    def test_metrics_prometheus(self) -> None:
        """GET /metrics with Accept: text/plain returns Prometheus exposition format."""
        response = client.get("/metrics", headers={"Accept": "text/plain"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.headers["content-type"])
        text = response.text
        self.assertIn("# HELP bnt_requests_total", text)
        self.assertIn("# TYPE bnt_requests_total counter", text)
        self.assertIn("bnt_requests_total", text)
        self.assertIn("bnt_errors_total", text)
        self.assertIn("bnt_rows_processed_total", text)
        self.assertIn("bnt_avg_latency_ms", text)

    def test_metrics_track_processed_rows(self) -> None:
        before = client.get("/metrics", headers={"Accept": "application/json"}).json()["total_rows_processed"]
        response = client.post("/normalize", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "m1", "source_reference_range": ""},
                {"source_test_name": "HbA1c", "raw_value": "5.2", "source_unit": "%",
                 "specimen_type": "whole blood", "source_row_id": "m2", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("X-BNT-Rows-Processed", response.headers)
        after = client.get("/metrics", headers={"Accept": "application/json"}).json()["total_rows_processed"]
        self.assertEqual(after - before, 2)

    # ─── GET /lookup ──────────────────────────────────────────

    def test_lookup_known_biomarker(self) -> None:
        """Lookup a known test name and verify we get a match."""
        response = client.get("/lookup", params={"test_name": "Glucose"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["matched"])
        self.assertEqual(data["test_name"], "Glucose")
        self.assertIn("alias_key", data)
        self.assertGreater(len(data["candidates"]), 0)
        candidate = data["candidates"][0]
        self.assertIn("biomarker_id", candidate)
        self.assertIn("canonical_name", candidate)
        self.assertIn("loinc", candidate)
        self.assertIn("normalized_unit", candidate)

    def test_lookup_unknown_biomarker(self) -> None:
        """Lookup an unknown test name returns matched=False."""
        response = client.get("/lookup", params={"test_name": "CompletelyFakeTest9999"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["matched"])
        self.assertEqual(data["candidates"], [])

    def test_lookup_with_specimen(self) -> None:
        """Lookup with specimen parameter returns specimen-compatible candidates."""
        response = client.get("/lookup", params={"test_name": "Hemoglobin", "specimen": "whole blood"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["matched"])
        self.assertGreater(len(data["candidates"]), 0)

    def test_lookup_filters_ambiguous_alias_by_specimen(self) -> None:
        response = client.get("/lookup", params={"test_name": "GLU", "specimen": "urine"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["matched"])
        self.assertEqual(len(data["candidates"]), 1)
        self.assertEqual(data["candidates"][0]["biomarker_id"], "glucose_urine")

    def test_lookup_missing_test_name(self) -> None:
        """Lookup without required test_name returns 422."""
        response = client.get("/lookup")
        self.assertEqual(response.status_code, 422)

    def test_phenoage_rejects_negative_age(self) -> None:
        response = client.post("/phenoage", json={"rows": [], "chronological_age": -1})
        self.assertEqual(response.status_code, 422)

    def test_phenoage_rejects_infinite_age(self) -> None:
        response = client.post("/phenoage", json={
            "chronological_age": "inf",
            "rows": [
                {"source_test_name": "Albumin", "raw_value": "4.5", "source_unit": "g/dL",
                 "specimen_type": "serum", "source_row_id": "pa1"},
            ],
        })
        self.assertEqual(response.status_code, 422)

    def test_phenoage_computes_with_complete_payload(self) -> None:
        response = client.post("/phenoage", json={
            "chronological_age": 45,
            "rows": [
                {"source_test_name": "Albumin", "raw_value": "4.5", "source_unit": "g/dL",
                 "specimen_type": "serum", "source_row_id": "pa1"},
                {"source_test_name": "Creatinine", "raw_value": "0.9", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "pa2"},
                {"source_test_name": "Glucose", "raw_value": "90", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "pa3"},
                {"source_test_name": "hs-CRP", "raw_value": "0.5", "source_unit": "mg/L",
                 "specimen_type": "serum", "source_row_id": "pa4"},
                {"source_test_name": "Lymphocytes Percent", "raw_value": "30", "source_unit": "%",
                 "specimen_type": "whole blood", "source_row_id": "pa5"},
                {"source_test_name": "MCV", "raw_value": "88", "source_unit": "fL",
                 "specimen_type": "whole blood", "source_row_id": "pa6"},
                {"source_test_name": "RDW", "raw_value": "12.5", "source_unit": "%",
                 "specimen_type": "whole blood", "source_row_id": "pa7"},
                {"source_test_name": "ALP", "raw_value": "55", "source_unit": "U/L",
                 "specimen_type": "serum", "source_row_id": "pa8"},
                {"source_test_name": "WBC", "raw_value": "5.5", "source_unit": "K/uL",
                 "specimen_type": "whole blood", "source_row_id": "pa9"},
            ],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["chronological_age"], 45.0)
        self.assertAlmostEqual(data["phenoage"], 39.3, places=1)
        self.assertLess(data["age_acceleration"], 0)
        self.assertIn("interpretation", data)

    def test_v1_get_endpoints_available(self) -> None:
        self.assertEqual(client.get("/v1/health").status_code, 200)
        self.assertEqual(client.get("/v1/metrics").status_code, 200)
        self.assertEqual(client.get("/v1/catalog", params={"limit": 1}).status_code, 200)
        self.assertEqual(client.get("/v1/lookup", params={"test_name": "Glucose"}).status_code, 200)

    # ─── POST /analyze (JSON body) ────────────────────────────

    def test_analyze_mapping_rate_field(self) -> None:
        """Verify mapping_rate is a numeric percentage."""
        response = client.post("/analyze", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "90", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
                {"source_test_name": "Hemoglobin", "raw_value": "14", "source_unit": "g/dL",
                 "specimen_type": "whole blood", "source_row_id": "2", "source_reference_range": ""},
                {"source_test_name": "Bogus Marker", "raw_value": "1", "source_unit": "U/L",
                 "specimen_type": "serum", "source_row_id": "3", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data["mapping_rate"], (int, float))
        self.assertGreater(data["mapping_rate"], 0)
        self.assertLessEqual(data["mapping_rate"], 100)
        # mapped_biomarkers should have real biomarkers
        self.assertIsInstance(data["mapped_biomarkers"], dict)
        self.assertGreater(len(data["mapped_biomarkers"]), 0)
        # unmapped_tests should contain the bogus one
        self.assertIsInstance(data["unmapped_tests"], dict)
        self.assertIn("Bogus Marker", data["unmapped_tests"])

    def test_analyze_all_mapped(self) -> None:
        """When all rows map, mapping_rate should be 100."""
        response = client.post("/analyze", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "90", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["mapping_rate"], 100.0)
        self.assertEqual(data["unmapped_tests"], {})

    # ─── POST /compare ────────────────────────────────────────

    def test_compare_longitudinal(self) -> None:
        """Compare before/after results with days_between."""
        before_rows = [
            {"source_test_name": "Glucose", "raw_value": "110", "source_unit": "mg/dL",
             "specimen_type": "serum", "source_row_id": "b1", "source_reference_range": ""},
            {"source_test_name": "HbA1c", "raw_value": "6.0", "source_unit": "%",
             "specimen_type": "whole blood", "source_row_id": "b2", "source_reference_range": ""},
        ]
        after_rows = [
            {"source_test_name": "Glucose", "raw_value": "95", "source_unit": "mg/dL",
             "specimen_type": "serum", "source_row_id": "a1", "source_reference_range": ""},
            {"source_test_name": "HbA1c", "raw_value": "5.5", "source_unit": "%",
             "specimen_type": "whole blood", "source_row_id": "a2", "source_reference_range": ""},
        ]
        response = client.post(
            "/compare",
            json={
                "before": {"rows": before_rows},
                "after": {"rows": after_rows},
                "days_between": 90,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("biomarkers_compared", data)
        self.assertGreater(data["biomarkers_compared"], 0)
        self.assertIn("deltas", data)
        self.assertIsInstance(data["deltas"], list)
        self.assertEqual(data["days_between"], 90)
        self.assertIn("improved", data)
        self.assertIn("worsened", data)
        self.assertIn("stable", data)
        self.assertIn("improvement_rate", data)
        for delta in data["deltas"]:
            self.assertIn("biomarker_id", delta)
            self.assertIn("before", delta)
            self.assertIn("after", delta)
            self.assertIn("absolute_delta", delta)
            self.assertIn("direction", delta)
            self.assertIn("velocity_per_month", delta)

    def test_compare_rejects_negative_days_between(self) -> None:
        response = client.post("/compare", json={
            "before": {"rows": [{
                "source_test_name": "Glucose", "raw_value": "100",
                "source_unit": "mg/dL", "specimen_type": "serum",
                "source_row_id": "b1", "source_reference_range": "",
            }]},
            "after": {"rows": [{
                "source_test_name": "Glucose", "raw_value": "90",
                "source_unit": "mg/dL", "specimen_type": "serum",
                "source_row_id": "a1", "source_reference_range": "",
            }]},
            "days_between": -1,
        })
        self.assertEqual(response.status_code, 422)

    def test_compare_rejects_infinite_days_between(self) -> None:
        response = client.post("/compare", json={
            "before": {"rows": [{
                "source_test_name": "Glucose", "raw_value": "100",
                "source_unit": "mg/dL", "specimen_type": "serum",
                "source_row_id": "b1", "source_reference_range": "",
            }]},
            "after": {"rows": [{
                "source_test_name": "Glucose", "raw_value": "90",
                "source_unit": "mg/dL", "specimen_type": "serum",
                "source_row_id": "a1", "source_reference_range": "",
            }]},
            "days_between": "inf",
        })
        self.assertEqual(response.status_code, 422)

    def test_compare_invalid_before(self) -> None:
        """Compare with empty before rows returns 400."""
        response = client.post("/compare", json={
            "before": {"rows": []},
            "after": {"rows": [{"source_test_name": "Glucose", "raw_value": "90",
                                 "source_unit": "mg/dL", "specimen_type": "serum",
                                 "source_row_id": "1", "source_reference_range": ""}]},
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("before", response.json()["error"])

    # ─── POST /normalize with fuzzy_threshold ─────────────────

    def test_normalize_with_fuzzy_threshold(self) -> None:
        """Fuzzy threshold enables typo-tolerant matching without auth."""
        response = client.post("/normalize?fuzzy_threshold=0.7", json={
            "rows": [
                {"source_test_name": "Glucos", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["summary"]["total_rows"], 1)
        self.assertEqual(data["summary"]["mapped"], 1)
        self.assertEqual(data["records"][0]["canonical_biomarker_id"], "glucose_serum")

    def test_normalize_rejects_invalid_fuzzy_threshold(self) -> None:
        response = client.post("/normalize?fuzzy_threshold=1.5", json={
            "rows": [
                {"source_test_name": "Glucos", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 422)

    def test_normalize_rejects_infinite_chronological_age(self) -> None:
        response = client.post("/normalize", json={
            "chronological_age": "inf",
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 422)

    # ─── Rate limiting ────────────────────────────────────────

    def test_rate_limit_header_decreases(self) -> None:
        """X-RateLimit-Remaining header should decrease across requests."""
        r1 = client.get("/health", headers={"X-Forwarded-For": "203.0.113.9"})
        self.assertEqual(r1.status_code, 200)
        remaining1 = int(r1.headers["X-RateLimit-Remaining"])

        r2 = client.get("/health", headers={"X-Forwarded-For": "203.0.113.9"})
        self.assertEqual(r2.status_code, 200)
        remaining2 = int(r2.headers["X-RateLimit-Remaining"])

        self.assertLess(remaining2, remaining1)

    def test_rate_limit_header_present(self) -> None:
        """All responses should include X-RateLimit-Remaining."""
        response = client.get("/health")
        self.assertIn("X-RateLimit-Remaining", response.headers)
        remaining = int(response.headers["X-RateLimit-Remaining"])
        self.assertGreaterEqual(remaining, 0)

    # ─── Body size limit ──────────────────────────────────────

    def test_body_size_limit_returns_413(self) -> None:
        """Sending a body larger than MAX_JSON_BODY_BYTES returns 413."""
        from biomarker_normalization_toolkit.api import MAX_JSON_BODY_BYTES
        # Build a payload slightly over the limit
        oversized = "x" * (MAX_JSON_BODY_BYTES + 1)
        response = client.post(
            "/normalize",
            content=oversized,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 413)
        data = response.json()
        self.assertIn("too large", data["error"])

    # ─── Invalid rows ─────────────────────────────────────────

    def test_normalize_non_dict_rows(self) -> None:
        """Rows containing non-dict items should be rejected (422 from Pydantic validation)."""
        response = client.post("/normalize", json={
            "rows": ["not a dict", 42, None],
        })
        # Pydantic rejects non-dict items in rows before _validate_rows runs
        self.assertIn(response.status_code, (400, 422))

    def test_normalize_mixed_valid_and_invalid_rows(self) -> None:
        """A mix of dict and non-dict items should still be rejected."""
        response = client.post("/normalize", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
                "invalid_string_row",
            ],
        })
        # Pydantic rejects non-dict items in rows before _validate_rows runs
        self.assertIn(response.status_code, (400, 422))

    # ─── Empty rows ───────────────────────────────────────────

    def test_normalize_empty_rows_error_message(self) -> None:
        """Empty rows array returns a descriptive error."""
        response = client.post("/normalize", json={"rows": []})
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("No rows provided", data["error"])

    def test_analyze_empty_rows(self) -> None:
        """Analyze endpoint with empty rows returns 400."""
        response = client.post("/analyze", json={"rows": []})
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("No rows provided", data["error"])

    def test_normalize_missing_rows_key(self) -> None:
        """Request without rows key returns 422 (Pydantic validation)."""
        response = client.post("/normalize", json={"not_rows": []})
        self.assertEqual(response.status_code, 422)

    # ─── FHIR output ──────────────────────────────────────────

    def test_fhir_bundle_structure(self) -> None:
        """FHIR bundle should be a valid Bundle with proper entries."""
        response = client.post("/normalize?emit_fhir=true", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": "70-99 mg/dL"},
                {"source_test_name": "Hemoglobin", "raw_value": "14.5", "source_unit": "g/dL",
                 "specimen_type": "whole blood", "source_row_id": "2", "source_reference_range": "12-17 g/dL"},
            ],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        bundle = data["fhir_bundle"]
        self.assertEqual(bundle["resourceType"], "Bundle")
        self.assertEqual(bundle["type"], "collection")
        self.assertIn("entry", bundle)
        self.assertIsInstance(bundle["entry"], list)
        self.assertGreater(len(bundle["entry"]), 0)
        # Each entry should have a resource with resourceType Observation
        for entry in bundle["entry"]:
            self.assertIn("resource", entry)
            resource = entry["resource"]
            self.assertEqual(resource["resourceType"], "Observation")
            self.assertIn("code", resource)
            self.assertIn("status", resource)

    def test_fhir_bundle_entry_has_loinc_coding(self) -> None:
        """FHIR Observation entries should include LOINC coding."""
        response = client.post("/normalize?emit_fhir=true", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 200)
        bundle = response.json()["fhir_bundle"]
        entry = bundle["entry"][0]
        resource = entry["resource"]
        codings = resource["code"]["coding"]
        self.assertIsInstance(codings, list)
        self.assertGreater(len(codings), 0)
        # At least one coding should be LOINC
        loinc_codings = [c for c in codings if "loinc" in c.get("system", "").lower()]
        self.assertGreater(len(loinc_codings), 0, "Expected at least one LOINC coding")

    def test_fhir_bundle_unique_fullurls(self) -> None:
        """Each FHIR bundle entry should have a unique fullUrl."""
        response = client.post("/normalize?emit_fhir=true", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
                {"source_test_name": "Hemoglobin", "raw_value": "14", "source_unit": "g/dL",
                 "specimen_type": "whole blood", "source_row_id": "2", "source_reference_range": ""},
                {"source_test_name": "HbA1c", "raw_value": "5.4", "source_unit": "%",
                 "specimen_type": "whole blood", "source_row_id": "3", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 200)
        bundle = response.json()["fhir_bundle"]
        full_urls = [e.get("fullUrl") for e in bundle["entry"]]
        self.assertEqual(len(full_urls), len(set(full_urls)),
                         "FHIR bundle entries must have unique fullUrl values")

    def test_fhir_not_included_by_default(self) -> None:
        """Without emit_fhir=true, response should not contain fhir_bundle."""
        response = client.post("/normalize", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("fhir_bundle", response.json())

    # ─── Additional endpoint coverage ─────────────────────────

    def test_request_duration_header(self) -> None:
        """All responses should include X-Request-Duration-Ms."""
        response = client.get("/health")
        self.assertIn("X-Request-Duration-Ms", response.headers)
        duration = float(response.headers["X-Request-Duration-Ms"])
        self.assertGreater(duration, 0)

    def test_request_id_header(self) -> None:
        """All responses should include X-Request-Id."""
        response = client.get("/health")
        self.assertIn("X-Request-Id", response.headers)
        # Should be a valid UUID
        import uuid
        uuid.UUID(response.headers["X-Request-Id"])

    def test_catalog_pagination(self) -> None:
        """Catalog endpoint supports limit and offset pagination."""
        r1 = client.get("/catalog?limit=5&offset=0")
        self.assertEqual(r1.status_code, 200)
        d1 = r1.json()
        self.assertEqual(d1["count"], 5)
        self.assertEqual(d1["offset"], 0)

        r2 = client.get("/catalog?limit=5&offset=5")
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()
        self.assertEqual(d2["offset"], 5)
        # Pages should be different
        ids1 = {b["biomarker_id"] for b in d1["biomarkers"]}
        ids2 = {b["biomarker_id"] for b in d2["biomarkers"]}
        self.assertEqual(len(ids1 & ids2), 0, "Paginated results should not overlap")

    def test_catalog_total_field(self) -> None:
        """Catalog response includes total count of all matching biomarkers."""
        response = client.get("/catalog?limit=5")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total", data)
        self.assertGreaterEqual(data["total"], data["count"])

    def test_v1_normalize_endpoint(self) -> None:
        """V1-prefixed normalize endpoint works identically."""
        response = client.post("/v1/normalize", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["summary"]["total_rows"], 1)
        self.assertEqual(data["summary"]["mapped"], 1)

    def test_v1_analyze_endpoint(self) -> None:
        """V1-prefixed analyze endpoint works identically."""
        response = client.post("/v1/analyze", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("mapping_rate", data)

    def test_normalize_records_contain_expected_fields(self) -> None:
        """Each normalized record should have the canonical output fields."""
        response = client.post("/normalize", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 200)
        record = response.json()["records"][0]
        expected_fields = [
            "source_test_name", "raw_value", "source_unit",
            "canonical_biomarker_id", "canonical_biomarker_name",
            "mapping_status", "match_confidence",
            "normalized_value", "normalized_unit",
        ]
        for field in expected_fields:
            self.assertIn(field, record, f"Missing field: {field}")


class APISnapshotTests(unittest.TestCase):
    """Snapshot tests that pin the exact JSON structure of every API endpoint.

    These tests catch any field additions, removals, or type changes in the
    API contract. Each test asserts every expected key exists and that value
    types match the documented contract.
    """

    # ─── Shared fixtures ─────────────────────────────────────

    GLUCOSE_ROW = {
        "source_test_name": "Glucose",
        "raw_value": "100",
        "source_unit": "mg/dL",
        "specimen_type": "serum",
        "source_row_id": "snap-1",
        "source_reference_range": "70-99 mg/dL",
    }

    def setUp(self) -> None:
        _reset_api_test_state()

    # ─── 1. GET /health ──────────────────────────────────────

    def test_snapshot_health(self) -> None:
        """Pin all keys and value types of the /health response."""
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        expected_keys = {"status", "version", "biomarkers"}
        self.assertEqual(set(data.keys()), expected_keys,
                         f"Health endpoint keys changed: {set(data.keys())} != {expected_keys}")

        self.assertIsInstance(data["status"], str)
        self.assertIsInstance(data["version"], str)
        self.assertIsInstance(data["biomarkers"], int)

    # ─── 2. GET /catalog?limit=1 ─────────────────────────────

    def test_snapshot_catalog_entry(self) -> None:
        """Pin the biomarker entry structure from /catalog."""
        response = client.get("/catalog?limit=1")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Top-level catalog keys
        catalog_keys = {"biomarkers", "count", "total", "offset"}
        self.assertEqual(set(data.keys()), catalog_keys,
                         f"Catalog top-level keys changed: {set(data.keys())} != {catalog_keys}")
        self.assertIsInstance(data["biomarkers"], list)
        self.assertIsInstance(data["count"], int)
        self.assertIsInstance(data["total"], int)
        self.assertIsInstance(data["offset"], int)

        # Biomarker entry keys
        self.assertGreater(len(data["biomarkers"]), 0)
        entry = data["biomarkers"][0]
        entry_keys = {
            "biomarker_id", "canonical_name", "loinc",
            "normalized_unit", "allowed_specimens", "aliases",
        }
        self.assertEqual(set(entry.keys()), entry_keys,
                         f"Catalog entry keys changed: {set(entry.keys())} != {entry_keys}")
        self.assertIsInstance(entry["biomarker_id"], str)
        self.assertIsInstance(entry["canonical_name"], str)
        self.assertIsInstance(entry["loinc"], str)
        self.assertIsInstance(entry["normalized_unit"], str)
        self.assertIsInstance(entry["allowed_specimens"], list)
        self.assertIsInstance(entry["aliases"], list)

    # ─── 3. GET /lookup matched ──────────────────────────────

    def test_snapshot_lookup_matched(self) -> None:
        """Pin matched=True response structure from /lookup."""
        response = client.get("/lookup", params={
            "test_name": "Glucose", "specimen": "serum",
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()

        lookup_keys = {"matched", "test_name", "alias_key", "candidates"}
        self.assertEqual(set(data.keys()), lookup_keys,
                         f"Lookup keys changed: {set(data.keys())} != {lookup_keys}")
        self.assertIsInstance(data["matched"], bool)
        self.assertTrue(data["matched"])
        self.assertIsInstance(data["test_name"], str)
        self.assertIsInstance(data["alias_key"], str)
        self.assertIsInstance(data["candidates"], list)
        self.assertGreater(len(data["candidates"]), 0)

        # Candidate entry structure
        candidate = data["candidates"][0]
        candidate_keys = {"biomarker_id", "canonical_name", "loinc", "normalized_unit"}
        self.assertEqual(set(candidate.keys()), candidate_keys,
                         f"Lookup candidate keys changed: {set(candidate.keys())} != {candidate_keys}")
        self.assertIsInstance(candidate["biomarker_id"], str)
        self.assertIsInstance(candidate["canonical_name"], str)
        self.assertIsInstance(candidate["loinc"], str)
        self.assertIsInstance(candidate["normalized_unit"], str)

    # ─── 4. GET /lookup unmatched ────────────────────────────

    def test_snapshot_lookup_unmatched(self) -> None:
        """Pin matched=False response structure from /lookup."""
        response = client.get("/lookup", params={"test_name": "Fake"})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        lookup_keys = {"matched", "test_name", "alias_key", "candidates"}
        self.assertEqual(set(data.keys()), lookup_keys,
                         f"Unmatched lookup keys changed: {set(data.keys())} != {lookup_keys}")
        self.assertIsInstance(data["matched"], bool)
        self.assertFalse(data["matched"])
        self.assertIsInstance(data["test_name"], str)
        self.assertEqual(data["test_name"], "Fake")
        self.assertIsInstance(data["alias_key"], str)
        self.assertIsInstance(data["candidates"], list)
        self.assertEqual(len(data["candidates"]), 0)

    # ─── 5. POST /normalize top-level keys ───────────────────

    def test_snapshot_normalize_response(self) -> None:
        """Pin top-level response keys from POST /normalize."""
        response = client.post("/normalize", json={
            "rows": [self.GLUCOSE_ROW],
            "input_file": "snapshot_test.csv",
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()

        required_keys = {
            "schema_version", "bnt_version", "generated_at",
            "input_file", "summary", "records",
        }
        for key in required_keys:
            self.assertIn(key, data, f"Missing top-level normalize key: {key}")

        self.assertIsInstance(data["schema_version"], str)
        self.assertIsInstance(data["bnt_version"], str)
        self.assertIsInstance(data["generated_at"], str)
        self.assertIsInstance(data["input_file"], str)
        self.assertIsInstance(data["summary"], dict)
        self.assertIsInstance(data["records"], list)

        # warnings is optional (only present when non-empty)
        if "warnings" in data:
            self.assertIsInstance(data["warnings"], list)

    # ─── 6. Normalized record fields ─────────────────────────

    def test_snapshot_normalize_record_fields(self) -> None:
        """Pin every field in a normalized record (21 fields)."""
        response = client.post("/normalize", json={
            "rows": [self.GLUCOSE_ROW],
        })
        self.assertEqual(response.status_code, 200)
        records = response.json()["records"]
        self.assertEqual(len(records), 1)
        record = records[0]

        record_keys = {
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
            "provenance",
        }
        self.assertEqual(set(record.keys()), record_keys,
                         f"Record keys changed: {set(record.keys())} != {record_keys}")

        # Assert types for every field
        self.assertIsInstance(record["source_row_number"], int)
        self.assertIsInstance(record["source_row_id"], str)
        self.assertIsInstance(record["source_lab_name"], str)
        self.assertIsInstance(record["source_panel_name"], str)
        self.assertIsInstance(record["source_test_name"], str)
        self.assertIsInstance(record["alias_key"], str)
        self.assertIsInstance(record["raw_value"], str)
        self.assertIsInstance(record["source_unit"], str)
        self.assertIsInstance(record["specimen_type"], str)
        self.assertIsInstance(record["source_reference_range"], str)
        self.assertIsInstance(record["canonical_biomarker_id"], str)
        self.assertIsInstance(record["canonical_biomarker_name"], str)
        self.assertIsInstance(record["loinc"], str)
        self.assertIsInstance(record["mapping_status"], str)
        self.assertIsInstance(record["match_confidence"], str)
        self.assertIsInstance(record["status_reason"], str)
        self.assertIsInstance(record["mapping_rule"], str)
        self.assertIsInstance(record["normalized_value"], str)
        self.assertIsInstance(record["normalized_unit"], str)
        self.assertIsInstance(record["normalized_reference_range"], str)
        self.assertIsInstance(record["provenance"], dict)

        # Verify mapping_status and match_confidence are from allowed enums
        self.assertIn(record["mapping_status"], {"mapped", "review_needed", "unmapped"})
        self.assertIn(record["match_confidence"], {"high", "medium", "low", "none"})

    # ─── 7. Summary fields ───────────────────────────────────

    def test_snapshot_normalize_summary_fields(self) -> None:
        """Pin every key in summary dict including confidence_breakdown."""
        response = client.post("/normalize", json={
            "rows": [self.GLUCOSE_ROW],
        })
        self.assertEqual(response.status_code, 200)
        summary = response.json()["summary"]

        summary_keys = {"total_rows", "mapped", "review_needed", "unmapped", "confidence_breakdown"}
        self.assertEqual(set(summary.keys()), summary_keys,
                         f"Summary keys changed: {set(summary.keys())} != {summary_keys}")

        self.assertIsInstance(summary["total_rows"], int)
        self.assertIsInstance(summary["mapped"], int)
        self.assertIsInstance(summary["review_needed"], int)
        self.assertIsInstance(summary["unmapped"], int)
        self.assertIsInstance(summary["confidence_breakdown"], dict)

        # confidence_breakdown sub-keys
        cb = summary["confidence_breakdown"]
        cb_keys = {"high", "medium", "low", "none"}
        self.assertEqual(set(cb.keys()), cb_keys,
                         f"confidence_breakdown keys changed: {set(cb.keys())} != {cb_keys}")
        for level in cb_keys:
            self.assertIsInstance(cb[level], int,
                                 f"confidence_breakdown['{level}'] should be int")

    # ─── 8. POST /analyze response ───────────────────────────

    def test_snapshot_analyze_response(self) -> None:
        """Pin all top-level keys from POST /analyze."""
        response = client.post("/analyze", json={
            "rows": [
                self.GLUCOSE_ROW,
                {"source_test_name": "FakeTest999", "raw_value": "1",
                 "source_unit": "U/L", "specimen_type": "serum",
                 "source_row_id": "snap-2", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()

        analyze_keys = {
            "input_file", "summary", "mapping_rate",
            "mapped_biomarkers", "unmapped_tests",
            "review_reasons", "unsupported_units",
            "warnings",
        }
        self.assertEqual(set(data.keys()), analyze_keys,
                         f"Analyze keys changed: {set(data.keys())} != {analyze_keys}")

        self.assertIsInstance(data["input_file"], str)
        self.assertIsInstance(data["summary"], dict)
        self.assertIsInstance(data["mapping_rate"], (int, float))
        self.assertIsInstance(data["mapped_biomarkers"], dict)
        self.assertIsInstance(data["unmapped_tests"], dict)
        self.assertIsInstance(data["review_reasons"], dict)
        self.assertIsInstance(data["unsupported_units"], dict)
        self.assertIsInstance(data["warnings"], list)

        # Summary within analyze should have the same structure
        summary = data["summary"]
        for key in ("total_rows", "mapped", "review_needed", "unmapped", "confidence_breakdown"):
            self.assertIn(key, summary, f"Missing analyze summary key: {key}")

    # ─── 9. FHIR bundle top-level keys ──────────────────────

    def test_snapshot_fhir_bundle_top_level(self) -> None:
        """Pin fhir_bundle top-level keys from POST /normalize?emit_fhir=true."""
        response = client.post("/normalize?emit_fhir=true", json={
            "rows": [self.GLUCOSE_ROW],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("fhir_bundle", data)

        bundle = data["fhir_bundle"]
        bundle_keys = {"resourceType", "type", "meta", "identifier", "entry"}
        self.assertEqual(set(bundle.keys()), bundle_keys,
                         f"FHIR bundle keys changed: {set(bundle.keys())} != {bundle_keys}")

        self.assertIsInstance(bundle["resourceType"], str)
        self.assertEqual(bundle["resourceType"], "Bundle")
        self.assertIsInstance(bundle["type"], str)
        self.assertEqual(bundle["type"], "collection")
        self.assertIsInstance(bundle["meta"], dict)
        self.assertIn("profile", bundle["meta"])
        self.assertIsInstance(bundle["meta"]["profile"], list)
        self.assertIsInstance(bundle["identifier"], dict)
        self.assertIn("system", bundle["identifier"])
        self.assertIn("value", bundle["identifier"])
        self.assertIsInstance(bundle["identifier"]["system"], str)
        self.assertIsInstance(bundle["identifier"]["value"], str)
        self.assertIsInstance(bundle["entry"], list)

    # ─── 10. FHIR Observation resource fields ────────────────

    def test_snapshot_fhir_observation_fields(self) -> None:
        """Pin every key in a FHIR Observation resource."""
        response = client.post("/normalize?emit_fhir=true", json={
            "rows": [self.GLUCOSE_ROW],
        })
        self.assertEqual(response.status_code, 200)
        bundle = response.json()["fhir_bundle"]
        self.assertGreater(len(bundle["entry"]), 0)

        entry = bundle["entry"][0]
        # Entry structure
        entry_keys = {"fullUrl", "resource"}
        self.assertEqual(set(entry.keys()), entry_keys,
                         f"FHIR entry keys changed: {set(entry.keys())} != {entry_keys}")
        self.assertIsInstance(entry["fullUrl"], str)
        self.assertTrue(entry["fullUrl"].startswith("urn:uuid:"))

        obs = entry["resource"]

        # Required Observation fields (always present for a mapped glucose with row_id and ref range)
        obs_required_keys = {
            "resourceType", "id", "status", "category", "code",
            "valueQuantity", "note", "identifier", "referenceRange",
            "specimen",
        }
        for key in obs_required_keys:
            self.assertIn(key, obs, f"Missing FHIR Observation key: {key}")

        # resourceType and status
        self.assertEqual(obs["resourceType"], "Observation")
        self.assertIsInstance(obs["id"], str)
        self.assertEqual(obs["status"], "final")

        # category
        self.assertIsInstance(obs["category"], list)
        self.assertGreater(len(obs["category"]), 0)
        cat = obs["category"][0]
        self.assertIn("coding", cat)
        self.assertIsInstance(cat["coding"], list)
        cat_coding = cat["coding"][0]
        self.assertIn("system", cat_coding)
        self.assertIn("code", cat_coding)
        self.assertIn("display", cat_coding)
        self.assertEqual(cat_coding["code"], "laboratory")

        # code
        self.assertIn("coding", obs["code"])
        self.assertIn("text", obs["code"])
        self.assertIsInstance(obs["code"]["coding"], list)
        code_coding = obs["code"]["coding"][0]
        self.assertIn("system", code_coding)
        self.assertIn("code", code_coding)
        self.assertIn("display", code_coding)
        self.assertEqual(code_coding["system"], "http://loinc.org")

        # valueQuantity
        vq = obs["valueQuantity"]
        self.assertIsInstance(vq, dict)
        self.assertIn("value", vq)
        self.assertIsInstance(vq["value"], (int, float))
        self.assertIn("unit", vq)
        self.assertIsInstance(vq["unit"], str)
        self.assertIn("system", vq)
        self.assertEqual(vq["system"], "http://unitsofmeasure.org")
        self.assertIn("code", vq)
        self.assertIsInstance(vq["code"], str)

        # note
        self.assertIsInstance(obs["note"], list)
        self.assertGreater(len(obs["note"]), 0)
        self.assertIn("text", obs["note"][0])
        self.assertIsInstance(obs["note"][0]["text"], str)

        # identifier (present because source_row_id is set)
        self.assertIsInstance(obs["identifier"], list)
        self.assertGreater(len(obs["identifier"]), 0)
        ident = obs["identifier"][0]
        self.assertIn("system", ident)
        self.assertIn("value", ident)
        self.assertEqual(ident["system"], "urn:source-row-id")

        # referenceRange (present because source_reference_range is "70-99 mg/dL")
        self.assertIsInstance(obs["referenceRange"], list)
        self.assertGreater(len(obs["referenceRange"]), 0)
        rr = obs["referenceRange"][0]
        self.assertIn("text", rr)
        self.assertIsInstance(rr["text"], str)
        # Reference range should have low and/or high
        has_low_or_high = "low" in rr or "high" in rr
        self.assertTrue(has_low_or_high,
                        "referenceRange should have 'low' and/or 'high'")
        if "low" in rr:
            self.assertIn("value", rr["low"])
            self.assertIn("unit", rr["low"])
            self.assertIn("system", rr["low"])
            self.assertIn("code", rr["low"])
        if "high" in rr:
            self.assertIn("value", rr["high"])
            self.assertIn("unit", rr["high"])
            self.assertIn("system", rr["high"])
            self.assertIn("code", rr["high"])

        # specimen (present because specimen_type is "serum")
        self.assertIsInstance(obs["specimen"], dict)
        self.assertIn("display", obs["specimen"])
        self.assertIsInstance(obs["specimen"]["display"], str)


if __name__ == "__main__":
    unittest.main()
