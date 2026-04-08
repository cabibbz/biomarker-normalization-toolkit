import unittest

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.normalizer import normalize_rows


class CatalogGapExpansionTests(unittest.TestCase):
    def test_new_drug_and_toxicology_gaps_map(self) -> None:
        rows = [
            {
                "source_row_id": "dig",
                "source_test_name": "Digoxin",
                "raw_value": "1.0",
                "source_unit": "ng/mL",
                "specimen_type": "",
                "source_reference_range": "",
            },
            {
                "source_row_id": "tac",
                "source_test_name": "Tacrolimus-FK506",
                "raw_value": "6.9",
                "source_unit": "ng/mL",
                "specimen_type": "",
                "source_reference_range": "",
            },
            {
                "source_row_id": "sal",
                "source_test_name": "salicylate",
                "raw_value": "7.0",
                "source_unit": "mg/dL",
                "specimen_type": "",
                "source_reference_range": "",
            },
            {
                "source_row_id": "myo",
                "source_test_name": "myoglobin",
                "raw_value": "62.7",
                "source_unit": "ng/mL",
                "specimen_type": "",
                "source_reference_range": "",
            },
        ]

        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}

        self.assertEqual(by_id["dig"].mapping_status, "mapped")
        self.assertEqual(by_id["dig"].canonical_biomarker_id, "digoxin")
        self.assertEqual(by_id["dig"].normalized_value, "1")
        self.assertEqual(by_id["dig"].normalized_unit, "ng/mL")

        self.assertEqual(by_id["tac"].mapping_status, "mapped")
        self.assertEqual(by_id["tac"].canonical_biomarker_id, "tacrolimus")
        self.assertEqual(by_id["tac"].normalized_value, "6.9")
        self.assertEqual(by_id["tac"].normalized_unit, "ng/mL")

        self.assertEqual(by_id["sal"].mapping_status, "mapped")
        self.assertEqual(by_id["sal"].canonical_biomarker_id, "salicylates")
        self.assertEqual(by_id["sal"].normalized_value, "7")
        self.assertEqual(by_id["sal"].normalized_unit, "mg/dL")

        self.assertEqual(by_id["myo"].mapping_status, "mapped")
        self.assertEqual(by_id["myo"].canonical_biomarker_id, "myoglobin")
        self.assertEqual(by_id["myo"].normalized_value, "62.7")
        self.assertEqual(by_id["myo"].normalized_unit, "ng/mL")

    def test_new_gap_loinc_assignments(self) -> None:
        self.assertEqual(BIOMARKER_CATALOG["digoxin"].loinc, "10535-3")
        self.assertEqual(BIOMARKER_CATALOG["tacrolimus"].loinc, "11253-2")
        self.assertEqual(BIOMARKER_CATALOG["salicylates"].loinc, "4024-6")
        self.assertEqual(BIOMARKER_CATALOG["myoglobin"].loinc, "2639-3")


if __name__ == "__main__":
    unittest.main()
