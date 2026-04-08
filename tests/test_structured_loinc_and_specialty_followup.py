import json
import tempfile
import unittest
from pathlib import Path

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.io_utils import read_ccda_input, read_fhir_input, read_hl7_input
from biomarker_normalization_toolkit.normalizer import normalize_rows


class StructuredLoincFallbackTests(unittest.TestCase):
    def test_source_loinc_aliases_map_equivalent_structured_codes(self) -> None:
        rows = [
            {"source_row_id": "glu-alt", "source_test_name": "Glucose", "source_loinc": "2339-0", "raw_value": "101", "source_unit": "mg/dL"},
            {"source_row_id": "na-alt", "source_test_name": "Natrium", "source_loinc": "2947-0", "raw_value": "139", "source_unit": "mmol/L"},
            {"source_row_id": "k-alt", "source_test_name": "Kalium", "source_loinc": "6298-4", "raw_value": "4.2", "source_unit": "mmol/L"},
        ]

        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}

        self.assertEqual(by_id["glu-alt"].canonical_biomarker_id, "glucose_serum")
        self.assertEqual(by_id["na-alt"].canonical_biomarker_id, "sodium")
        self.assertEqual(by_id["k-alt"].canonical_biomarker_id, "potassium")
        self.assertTrue(all(record.status_reason == "mapped_by_source_loinc" for record in by_id.values()))

    def test_fhir_source_loinc_maps_ambiguous_and_localized_names(self) -> None:
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {
                    "resourceType": "Observation",
                    "id": "glu1",
                    "code": {
                        "coding": [{"system": "http://loinc.org", "code": "2345-7", "display": "Glucose"}],
                        "text": "Glucose",
                    },
                    "valueQuantity": {"value": 101, "unit": "mg/dL"},
                }},
                {"resource": {
                    "resourceType": "Observation",
                    "id": "cre1",
                    "code": {
                        "coding": [{"system": "http://loinc.org", "code": "2160-0", "display": "Creatinina"}],
                        "text": "Creatinina",
                    },
                    "valueQuantity": {"value": 1.2, "unit": "mg/dL"},
                }},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(bundle, handle)
            tmp = Path(handle.name)
        try:
            rows = read_fhir_input(tmp)
        finally:
            tmp.unlink(missing_ok=True)

        self.assertEqual(rows[0]["source_test_name"], "Glucose")
        self.assertEqual(rows[0]["source_loinc"], "2345-7")
        self.assertEqual(rows[1]["source_test_name"], "Creatinina")
        self.assertEqual(rows[1]["source_loinc"], "2160-0")

        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}

        self.assertEqual(by_id["glu1"].mapping_status, "mapped")
        self.assertEqual(by_id["glu1"].canonical_biomarker_id, "glucose_serum")
        self.assertEqual(by_id["glu1"].status_reason, "mapped_by_source_loinc")

        self.assertEqual(by_id["cre1"].mapping_status, "mapped")
        self.assertEqual(by_id["cre1"].canonical_biomarker_id, "creatinine")
        self.assertEqual(by_id["cre1"].status_reason, "mapped_by_source_loinc")

    def test_hl7_source_loinc_maps_localized_display(self) -> None:
        hl7 = (
            "MSH|^~\\&|LAB|HOSP|BNT|BNT|202604081200||ORU^R01|MSG1|P|2.5\r"
            "OBR|1|||CHEM^Chemistry\r"
            "OBX|1|NM|2160-0^Kreatinin^LN||1.1|mg/dL|||N|||F\r"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".hl7", delete=False, encoding="utf-8") as handle:
            handle.write(hl7)
            tmp = Path(handle.name)
        try:
            rows = read_hl7_input(tmp)
        finally:
            tmp.unlink(missing_ok=True)

        self.assertEqual(rows[0]["source_test_name"], "Kreatinin")
        self.assertEqual(rows[0]["source_loinc"], "2160-0")

        record = normalize_rows(rows).records[0]
        self.assertEqual(record.mapping_status, "mapped")
        self.assertEqual(record.canonical_biomarker_id, "creatinine")
        self.assertEqual(record.status_reason, "mapped_by_source_loinc")

    def test_ccda_source_loinc_maps_localized_display(self) -> None:
        ccda = """<?xml version="1.0" encoding="UTF-8"?>
<ClinicalDocument xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <observation>
    <code code="3016-3" codeSystem="2.16.840.1.113883.6.1" displayName="TSH (Thyroid Stimulating Hormone)"/>
    <value xsi:type="PQ" value="2.4" unit="mIU/L"/>
  </observation>
</ClinicalDocument>
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as handle:
            handle.write(ccda)
            tmp = Path(handle.name)
        try:
            rows = read_ccda_input(tmp)
        finally:
            tmp.unlink(missing_ok=True)

        self.assertEqual(rows[0]["source_test_name"], "TSH (Thyroid Stimulating Hormone)")
        self.assertEqual(rows[0]["source_loinc"], "3016-3")

        record = normalize_rows(rows).records[0]
        self.assertEqual(record.mapping_status, "mapped")
        self.assertEqual(record.canonical_biomarker_id, "tsh")
        self.assertEqual(record.status_reason, "mapped_by_source_loinc")


class SpecialtyFollowupTests(unittest.TestCase):
    def test_specialty_followup_markers_map(self) -> None:
        rows = [
            {"source_row_id": "csfg", "source_test_name": "glucose - CSF", "raw_value": "65", "source_unit": "mg/dL"},
            {"source_row_id": "csfp", "source_test_name": "protein - CSF", "raw_value": "42", "source_unit": "mg/dL"},
            {"source_row_id": "cd3", "source_test_name": "Absolute CD3 Count", "raw_value": "850", "source_unit": "#/uL", "specimen_type": "Blood"},
            {"source_row_id": "cd4", "source_test_name": "Absolute CD4 Count", "raw_value": "540", "source_unit": "#/uL", "specimen_type": "Blood"},
            {"source_row_id": "cd4p", "source_test_name": "CD4 Cells, Percent", "raw_value": "22", "source_unit": "%", "specimen_type": "Blood"},
            {"source_row_id": "cd8", "source_test_name": "Absolute CD8 Count", "raw_value": "620", "source_unit": "#/uL", "specimen_type": "Blood"},
            {"source_row_id": "ratio", "source_test_name": "CD4/CD8 Ratio", "raw_value": "1.1", "source_unit": "ratio", "specimen_type": "Blood"},
            {"source_row_id": "cd8p", "source_test_name": "CD8 Cells, Percent", "raw_value": "31", "source_unit": "%", "specimen_type": "Blood"},
        ]

        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}

        self.assertEqual(by_id["csfg"].canonical_biomarker_id, "glucose_csf")
        self.assertEqual(by_id["csfp"].canonical_biomarker_id, "protein_csf")
        self.assertEqual(by_id["cd3"].canonical_biomarker_id, "cd3_absolute")
        self.assertEqual(by_id["cd4"].canonical_biomarker_id, "cd4_absolute")
        self.assertEqual(by_id["cd4p"].canonical_biomarker_id, "cd4_pct")
        self.assertEqual(by_id["cd8"].canonical_biomarker_id, "cd8_absolute")
        self.assertEqual(by_id["ratio"].canonical_biomarker_id, "cd4_cd8_ratio")
        self.assertEqual(by_id["cd8p"].canonical_biomarker_id, "cd8_pct")

        self.assertEqual(by_id["cd3"].normalized_unit, "#/uL")
        self.assertEqual(by_id["cd4"].normalized_unit, "#/uL")
        self.assertEqual(by_id["cd4p"].normalized_unit, "%")
        self.assertEqual(by_id["ratio"].normalized_unit, "ratio")
        self.assertTrue(all(record.mapping_status == "mapped" for record in by_id.values()))

    def test_specialty_followup_loincs_are_expected(self) -> None:
        self.assertEqual(BIOMARKER_CATALOG["glucose_csf"].loinc, "2342-4")
        self.assertEqual(BIOMARKER_CATALOG["protein_csf"].loinc, "2880-3")
        self.assertEqual(BIOMARKER_CATALOG["cd3_absolute"].loinc, "8122-4")
        self.assertEqual(BIOMARKER_CATALOG["cd4_absolute"].loinc, "24467-3")
        self.assertEqual(BIOMARKER_CATALOG["cd4_pct"].loinc, "8123-2")
        self.assertEqual(BIOMARKER_CATALOG["cd8_absolute"].loinc, "14135-8")
        self.assertEqual(BIOMARKER_CATALOG["cd4_cd8_ratio"].loinc, "54218-3")
        self.assertEqual(BIOMARKER_CATALOG["cd8_pct"].loinc, "8101-8")


if __name__ == "__main__":
    unittest.main()
