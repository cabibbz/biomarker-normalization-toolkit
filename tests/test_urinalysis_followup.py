import unittest

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.normalizer import normalize_rows


class UrinalysisFollowupTests(unittest.TestCase):
    def test_qualitative_strip_observations_map(self) -> None:
        rows = [
            {
                "source_row_id": "ugluc-pres",
                "source_test_name": "Glucose [Presence] in Urine by Test strip",
                "raw_value": "1.0",
                "source_unit": "{presence}",
                "specimen_type": "",
                "source_reference_range": "",
            },
            {
                "source_row_id": "uprot-pres",
                "source_test_name": "Protein [Presence] in Urine by Test strip",
                "raw_value": "0.0",
                "source_unit": "{presence}",
                "specimen_type": "",
                "source_reference_range": "",
            },
            {
                "source_row_id": "uket-pres",
                "source_test_name": "Ketones [Presence] in Urine by Test strip",
                "raw_value": "1.0",
                "source_unit": "{presence}",
                "specimen_type": "",
                "source_reference_range": "",
            },
            {
                "source_row_id": "ubil-pres",
                "source_test_name": "Bilirubin.total [Presence] in Urine by Test strip",
                "raw_value": "0.0",
                "source_unit": "{presence}",
                "specimen_type": "",
                "source_reference_range": "",
            },
        ]

        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}

        self.assertEqual(by_id["ugluc-pres"].canonical_biomarker_id, "glucose_urine_presence")
        self.assertEqual(by_id["uprot-pres"].canonical_biomarker_id, "urine_protein_presence")
        self.assertEqual(by_id["uket-pres"].canonical_biomarker_id, "urine_ketones_presence")
        self.assertEqual(by_id["ubil-pres"].canonical_biomarker_id, "urine_bilirubin_presence")
        self.assertTrue(all(record.mapping_status == "mapped" for record in by_id.values()))
        self.assertTrue(all(record.normalized_unit == "" for record in by_id.values()))

    def test_24h_urine_protein_maps_and_normalizes_unit(self) -> None:
        rows = [
            {
                "source_row_id": "u24",
                "source_test_name": "24 h urine protein",
                "raw_value": "200",
                "source_unit": "mg/24HR",
                "specimen_type": "",
                "source_reference_range": "0-150 mg/24HR",
            }
        ]

        result = normalize_rows(rows)
        record = result.records[0]

        self.assertEqual(record.mapping_status, "mapped")
        self.assertEqual(record.canonical_biomarker_id, "total_protein_urine_24h")
        self.assertEqual(record.normalized_value, "200")
        self.assertEqual(record.normalized_unit, "mg/24h")
        self.assertEqual(record.normalized_reference_range, "0-150 mg/24h")

    def test_followup_loinc_assignments(self) -> None:
        self.assertEqual(BIOMARKER_CATALOG["glucose_urine_presence"].loinc, "25428-4")
        self.assertEqual(BIOMARKER_CATALOG["urine_protein_presence"].loinc, "20454-5")
        self.assertEqual(BIOMARKER_CATALOG["urine_ketones"].loinc, "5797-6")
        self.assertEqual(BIOMARKER_CATALOG["urine_ketones_presence"].loinc, "2514-8")
        self.assertEqual(BIOMARKER_CATALOG["urine_bilirubin_presence"].loinc, "5770-3")
        self.assertEqual(BIOMARKER_CATALOG["total_protein_urine_24h"].loinc, "2889-4")


if __name__ == "__main__":
    unittest.main()
