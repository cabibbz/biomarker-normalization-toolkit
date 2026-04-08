import unittest

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.normalizer import normalize_rows


class CatalogGapExpansionTests(unittest.TestCase):
    def test_new_drug_and_toxicology_gaps_map(self) -> None:
        rows = [
            {
                "source_row_id": "etoh",
                "source_test_name": "ethanol",
                "raw_value": "145",
                "source_unit": "mg/dL",
                "specimen_type": "",
                "source_reference_range": "",
            },
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
                "source_row_id": "tacrofk",
                "source_test_name": "tacroFK",
                "raw_value": "7.4",
                "source_unit": "ng/mL",
                "specimen_type": "Blood",
                "source_reference_range": "5-20 ng/mL",
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
            {
                "source_row_id": "pheny",
                "source_test_name": "Phenytoin",
                "raw_value": "14.2",
                "source_unit": "ug/mL",
                "specimen_type": "",
                "source_reference_range": "",
            },
            {
                "source_row_id": "apap",
                "source_test_name": "APAP",
                "raw_value": "22",
                "source_unit": "ug/mL",
                "specimen_type": "",
                "source_reference_range": "",
            },
        ]

        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}

        self.assertEqual(by_id["etoh"].mapping_status, "mapped")
        self.assertEqual(by_id["etoh"].canonical_biomarker_id, "ethanol")
        self.assertEqual(by_id["etoh"].normalized_value, "145")
        self.assertEqual(by_id["etoh"].normalized_unit, "mg/dL")

        self.assertEqual(by_id["dig"].mapping_status, "mapped")
        self.assertEqual(by_id["dig"].canonical_biomarker_id, "digoxin")
        self.assertEqual(by_id["dig"].normalized_value, "1")
        self.assertEqual(by_id["dig"].normalized_unit, "ng/mL")

        self.assertEqual(by_id["tac"].mapping_status, "mapped")
        self.assertEqual(by_id["tac"].canonical_biomarker_id, "tacrolimus")
        self.assertEqual(by_id["tac"].normalized_value, "6.9")
        self.assertEqual(by_id["tac"].normalized_unit, "ng/mL")

        self.assertEqual(by_id["tacrofk"].mapping_status, "mapped")
        self.assertEqual(by_id["tacrofk"].canonical_biomarker_id, "tacrolimus")
        self.assertEqual(by_id["tacrofk"].normalized_value, "7.4")
        self.assertEqual(by_id["tacrofk"].normalized_unit, "ng/mL")

        self.assertEqual(by_id["sal"].mapping_status, "mapped")
        self.assertEqual(by_id["sal"].canonical_biomarker_id, "salicylates")
        self.assertEqual(by_id["sal"].normalized_value, "7")
        self.assertEqual(by_id["sal"].normalized_unit, "mg/dL")

        self.assertEqual(by_id["myo"].mapping_status, "mapped")
        self.assertEqual(by_id["myo"].canonical_biomarker_id, "myoglobin")
        self.assertEqual(by_id["myo"].normalized_value, "62.7")
        self.assertEqual(by_id["myo"].normalized_unit, "ng/mL")

        self.assertEqual(by_id["pheny"].mapping_status, "mapped")
        self.assertEqual(by_id["pheny"].canonical_biomarker_id, "phenytoin")
        self.assertEqual(by_id["pheny"].normalized_value, "14.2")
        self.assertEqual(by_id["pheny"].normalized_unit, "ug/mL")

        self.assertEqual(by_id["apap"].mapping_status, "mapped")
        self.assertEqual(by_id["apap"].canonical_biomarker_id, "acetaminophen")
        self.assertEqual(by_id["apap"].normalized_value, "22")
        self.assertEqual(by_id["apap"].normalized_unit, "ug/mL")

    def test_new_gap_loinc_assignments(self) -> None:
        self.assertEqual(BIOMARKER_CATALOG["ethanol"].loinc, "5643-2")
        self.assertEqual(BIOMARKER_CATALOG["digoxin"].loinc, "10535-3")
        self.assertEqual(BIOMARKER_CATALOG["tacrolimus"].loinc, "11253-2")
        self.assertEqual(BIOMARKER_CATALOG["salicylates"].loinc, "4024-6")
        self.assertEqual(BIOMARKER_CATALOG["myoglobin"].loinc, "2639-3")
        self.assertEqual(BIOMARKER_CATALOG["phenytoin"].loinc, "3968-5")
        self.assertEqual(BIOMARKER_CATALOG["acetaminophen"].loinc, "3298-7")


if __name__ == "__main__":
    unittest.main()
