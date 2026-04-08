from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import os
from pathlib import Path
import time
import unittest

from fastapi.testclient import TestClient

from biomarker_normalization_toolkit.api import app
from biomarker_normalization_toolkit.licensing import (
    FREE_MAX_ROWS,
    PRO_MAX_ROWS,
    validate_api_key,
)


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
        # Free tier filters some biomarkers; at least 3 should map
        self.assertGreaterEqual(data["summary"]["mapped"], 3)

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


    def test_licensing_rejects_invalid_tier_claim(self) -> None:
        """HMAC key with tier_claim='free' should NOT get PRO access."""
        import hashlib, hmac as _hmac, os, time as _time
        os.environ["BNT_LICENSE_SECRET"] = "test-secret-key"
        try:
            from biomarker_normalization_toolkit.licensing import validate_api_key
            # Create a validly signed key with tier="free"
            expiry = str(int(_time.time()) + 3600)
            sig = _hmac.new(b"test-secret-key", f"free:{expiry}".encode(), hashlib.sha256).hexdigest()[:32]
            api_key = f"free:{expiry}:{sig}"
            info = validate_api_key(api_key)
            # Should NOT get pro features
            self.assertFalse(info["features"].get("phenoage", False),
                             "A 'free' tier HMAC key should not get PhenoAge access")
        finally:
            os.environ.pop("BNT_LICENSE_SECRET", None)


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
        """Lookup with specimen parameter still returns candidates."""
        response = client.get("/lookup", params={"test_name": "Hemoglobin", "specimen": "whole blood"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["matched"])
        self.assertGreater(len(data["candidates"]), 0)

    def test_lookup_missing_test_name(self) -> None:
        """Lookup without required test_name returns 422."""
        response = client.get("/lookup")
        self.assertEqual(response.status_code, 422)

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
        import hashlib, hmac as _hmac, os, time as _time
        os.environ["BNT_PRO_KEY"] = "test-pro-key-compare"
        try:
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
                headers={"X-API-Key": "test-pro-key-compare"},
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
            # Each delta should have velocity_per_month since days_between was provided
            for delta in data["deltas"]:
                self.assertIn("biomarker_id", delta)
                self.assertIn("before", delta)
                self.assertIn("after", delta)
                self.assertIn("absolute_delta", delta)
                self.assertIn("direction", delta)
                self.assertIn("velocity_per_month", delta)
        finally:
            os.environ.pop("BNT_PRO_KEY", None)

    def test_compare_requires_pro_tier(self) -> None:
        """Compare endpoint should reject free-tier requests."""
        response = client.post("/compare", json={
            "before": {"rows": [{"source_test_name": "Glucose", "raw_value": "100",
                                  "source_unit": "mg/dL", "specimen_type": "serum",
                                  "source_row_id": "1", "source_reference_range": ""}]},
            "after": {"rows": [{"source_test_name": "Glucose", "raw_value": "90",
                                 "source_unit": "mg/dL", "specimen_type": "serum",
                                 "source_row_id": "1", "source_reference_range": ""}]},
            "days_between": 30,
        })
        self.assertEqual(response.status_code, 403)
        self.assertIn("Pro tier", response.json()["error"])

    def test_compare_invalid_before(self) -> None:
        """Compare with empty before rows returns 400."""
        import os
        os.environ["BNT_PRO_KEY"] = "test-pro-key-compare2"
        try:
            response = client.post("/compare", json={
                "before": {"rows": []},
                "after": {"rows": [{"source_test_name": "Glucose", "raw_value": "90",
                                     "source_unit": "mg/dL", "specimen_type": "serum",
                                     "source_row_id": "1", "source_reference_range": ""}]},
            }, headers={"X-API-Key": "test-pro-key-compare2"})
            self.assertEqual(response.status_code, 400)
            self.assertIn("before", response.json()["error"])
        finally:
            os.environ.pop("BNT_PRO_KEY", None)

    # ─── POST /normalize with fuzzy_threshold ─────────────────

    def test_normalize_with_fuzzy_threshold_free_tier(self) -> None:
        """Free tier: fuzzy_threshold param is accepted but fuzzy matching is disabled."""
        response = client.post("/normalize?fuzzy_threshold=0.8", json={
            "rows": [
                {"source_test_name": "Glucos", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
            ],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["summary"]["total_rows"], 1)

    def test_normalize_with_fuzzy_threshold_pro_tier(self) -> None:
        """Pro tier: fuzzy_threshold enables fuzzy matching."""
        import os
        os.environ["BNT_PRO_KEY"] = "test-pro-key-fuzzy"
        try:
            response = client.post("/normalize?fuzzy_threshold=0.7", json={
                "rows": [
                    {"source_test_name": "Glucos", "raw_value": "100", "source_unit": "mg/dL",
                     "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
                ],
            }, headers={"X-API-Key": "test-pro-key-fuzzy"})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["summary"]["total_rows"], 1)
            self.assertEqual(data["tier"], "pro")
        finally:
            os.environ.pop("BNT_PRO_KEY", None)

    # ─── Rate limiting ────────────────────────────────────────

    def test_rate_limit_header_decreases(self) -> None:
        """X-RateLimit-Remaining header should decrease across requests."""
        # Use a unique API key to get a fresh rate limit bucket
        unique_key = "rate-limit-test-key-unique-12345"
        r1 = client.get("/health", headers={"X-API-Key": unique_key})
        self.assertEqual(r1.status_code, 200)
        remaining1 = int(r1.headers["X-RateLimit-Remaining"])

        r2 = client.get("/health", headers={"X-API-Key": unique_key})
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

    def test_invalid_api_key_returns_401(self) -> None:
        """An invalid API key on normalize should return 401."""
        response = client.post("/normalize", json={
            "rows": [
                {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
                 "specimen_type": "serum", "source_row_id": "1", "source_reference_range": ""},
            ],
        }, headers={"X-API-Key": "bogus-invalid-key"})
        self.assertEqual(response.status_code, 401)
        self.assertIn("Invalid API key", response.json()["error"])

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


class LicensingTests(unittest.TestCase):
    """Tests for biomarker_normalization_toolkit.licensing.validate_api_key."""

    def _clean_env(self, keys: list[str]) -> dict[str, str | None]:
        """Save and remove env vars, return originals for restoration."""
        saved: dict[str, str | None] = {}
        for k in keys:
            saved[k] = os.environ.pop(k, None)
        return saved

    def _restore_env(self, saved: dict[str, str | None]) -> None:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_free_tier_default(self) -> None:
        """No API key returns free tier features."""
        saved = self._clean_env(["BNT_LICENSE_SECRET", "BNT_PRO_KEY", "BNT_ENTERPRISE_KEY"])
        try:
            info = validate_api_key(None)
            self.assertEqual(info["tier"], "free")
            self.assertTrue(info["valid"])
            self.assertEqual(info["max_rows"], FREE_MAX_ROWS)
            self.assertFalse(info["features"]["phenoage"])
            self.assertFalse(info["features"]["optimal_ranges"])
        finally:
            self._restore_env(saved)

    def test_static_pro_key(self) -> None:
        """BNT_PRO_KEY env var grants pro features."""
        saved = self._clean_env(["BNT_LICENSE_SECRET", "BNT_PRO_KEY", "BNT_ENTERPRISE_KEY"])
        try:
            os.environ["BNT_PRO_KEY"] = "my-pro-secret"
            info = validate_api_key("my-pro-secret")
            self.assertEqual(info["tier"], "pro")
            self.assertTrue(info["valid"])
            self.assertEqual(info["max_rows"], PRO_MAX_ROWS)
            self.assertTrue(info["features"]["phenoage"])
            self.assertTrue(info["features"]["optimal_ranges"])
            self.assertIsNone(info["biomarker_ids"])
        finally:
            self._restore_env(saved)

    def test_static_enterprise_key(self) -> None:
        """BNT_ENTERPRISE_KEY grants enterprise features."""
        saved = self._clean_env(["BNT_LICENSE_SECRET", "BNT_PRO_KEY", "BNT_ENTERPRISE_KEY"])
        try:
            os.environ["BNT_ENTERPRISE_KEY"] = "my-enterprise-secret"
            info = validate_api_key("my-enterprise-secret")
            self.assertEqual(info["tier"], "enterprise")
            self.assertTrue(info["valid"])
            self.assertEqual(info["max_rows"], PRO_MAX_ROWS)
            self.assertTrue(info["features"]["phenoage"])
            self.assertIsNone(info["biomarker_ids"])
        finally:
            self._restore_env(saved)

    def test_expired_hmac_key_falls_to_free(self) -> None:
        """Expired HMAC key does not grant pro."""
        saved = self._clean_env(["BNT_LICENSE_SECRET", "BNT_PRO_KEY", "BNT_ENTERPRISE_KEY"])
        try:
            secret = "test-hmac-secret"
            os.environ["BNT_LICENSE_SECRET"] = secret
            # Create a key that expired 1 hour ago
            expiry = str(int(time.time()) - 3600)
            sig = hmac_mod.new(
                secret.encode(), f"pro:{expiry}".encode(), hashlib.sha256
            ).hexdigest()[:32]
            api_key = f"pro:{expiry}:{sig}"
            info = validate_api_key(api_key)
            self.assertEqual(info["tier"], "free")
            self.assertFalse(info["features"]["phenoage"])
        finally:
            self._restore_env(saved)

    def test_hmac_enterprise_key(self) -> None:
        """Valid HMAC with enterprise tier grants enterprise."""
        saved = self._clean_env(["BNT_LICENSE_SECRET", "BNT_PRO_KEY", "BNT_ENTERPRISE_KEY"])
        try:
            secret = "test-hmac-secret"
            os.environ["BNT_LICENSE_SECRET"] = secret
            expiry = str(int(time.time()) + 3600)
            sig = hmac_mod.new(
                secret.encode(), f"enterprise:{expiry}".encode(), hashlib.sha256
            ).hexdigest()[:32]
            api_key = f"enterprise:{expiry}:{sig}"
            info = validate_api_key(api_key)
            self.assertEqual(info["tier"], "enterprise")
            self.assertTrue(info["valid"])
            self.assertTrue(info["features"]["phenoage"])
            self.assertTrue(info["features"]["optimal_ranges"])
            self.assertIsNone(info["biomarker_ids"])
        finally:
            self._restore_env(saved)

    def test_malformed_key_format(self) -> None:
        """Key with wrong number of colons falls to free tier."""
        saved = self._clean_env(["BNT_LICENSE_SECRET", "BNT_PRO_KEY", "BNT_ENTERPRISE_KEY"])
        try:
            os.environ["BNT_LICENSE_SECRET"] = "some-secret"
            info = validate_api_key("only-one-part")
            self.assertEqual(info["tier"], "free")
            self.assertFalse(info.get("valid", True))
        finally:
            self._restore_env(saved)

    def test_empty_api_key_is_free(self) -> None:
        """Empty string key is free tier."""
        saved = self._clean_env(["BNT_LICENSE_SECRET", "BNT_PRO_KEY", "BNT_ENTERPRISE_KEY"])
        try:
            info = validate_api_key("")
            self.assertEqual(info["tier"], "free")
            self.assertTrue(info["valid"])
            self.assertFalse(info["features"]["phenoage"])
        finally:
            self._restore_env(saved)

    def test_whitespace_api_key_is_free(self) -> None:
        """Whitespace-only key is free tier (invalid key, falls through)."""
        saved = self._clean_env(["BNT_LICENSE_SECRET", "BNT_PRO_KEY", "BNT_ENTERPRISE_KEY"])
        try:
            info = validate_api_key("   ")
            self.assertEqual(info["tier"], "free")
            self.assertFalse(info["features"]["phenoage"])
        finally:
            self._restore_env(saved)


if __name__ == "__main__":
    unittest.main()
