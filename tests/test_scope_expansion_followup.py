import unittest

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.normalizer import normalize_rows


class ScopeExpansionFollowupTests(unittest.TestCase):
    def test_new_loinc_assignments(self) -> None:
        self.assertEqual(BIOMARKER_CATALOG["digoxin"].loinc, "10535-3")
        self.assertEqual(BIOMARKER_CATALOG["tacrolimus"].loinc, "11253-2")
        self.assertEqual(BIOMARKER_CATALOG["salicylates"].loinc, "4024-6")
        self.assertEqual(BIOMARKER_CATALOG["myoglobin"].loinc, "2639-3")
        self.assertEqual(BIOMARKER_CATALOG["blasts_pct"].loinc, "26446-5")
        self.assertEqual(BIOMARKER_CATALOG["epithelial_cells_urine"].loinc, "5787-7")
        self.assertEqual(BIOMARKER_CATALOG["hyaline_casts"].loinc, "5796-8")

    def test_followup_scope_gaps_now_map(self) -> None:
        rows = [
            {"source_row_id": "dig", "source_test_name": "Digoxin", "raw_value": "1.2",
             "source_unit": "ng/mL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "tac", "source_test_name": "Tacrolimus-FK506", "raw_value": "7.8",
             "source_unit": "ng/mL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "sal", "source_test_name": "Salicylates", "raw_value": "12",
             "source_unit": "mg/dL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "myo", "source_test_name": "Myoglobin", "raw_value": "48",
             "source_unit": "ng/mL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "blast", "source_test_name": "Blasts", "raw_value": "1",
             "source_unit": "%", "specimen_type": "Blood", "source_reference_range": "0-0 %"},
            {"source_row_id": "epi", "source_test_name": "Epithelial Cells", "raw_value": "3",
             "source_unit": "#/hpf", "specimen_type": "Urine", "source_reference_range": ""},
            {"source_row_id": "cast", "source_test_name": "Hyaline Casts", "raw_value": "1",
             "source_unit": "#/lpf", "specimen_type": "Urine", "source_reference_range": "0-0 #/lpf"},
        ]
        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}
        self.assertEqual(by_id["dig"].canonical_biomarker_id, "digoxin")
        self.assertEqual(by_id["tac"].canonical_biomarker_id, "tacrolimus")
        self.assertEqual(by_id["sal"].canonical_biomarker_id, "salicylates")
        self.assertEqual(by_id["myo"].canonical_biomarker_id, "myoglobin")
        self.assertEqual(by_id["blast"].canonical_biomarker_id, "blasts_pct")
        self.assertEqual(by_id["epi"].canonical_biomarker_id, "epithelial_cells_urine")
        self.assertEqual(by_id["cast"].canonical_biomarker_id, "hyaline_casts")
        self.assertTrue(all(record.mapping_status == "mapped" for record in by_id.values()))

    def test_fhir_style_microscopy_units_map(self) -> None:
        rows = [
            {"source_row_id": "epi-fhir", "source_test_name": "Epithelial Cells", "raw_value": "3",
             "source_unit": "/[HPF]", "specimen_type": "Urine", "source_reference_range": ""},
            {"source_row_id": "cast-fhir", "source_test_name": "Hyaline Casts", "raw_value": "1",
             "source_unit": "/[LPF]", "specimen_type": "Urine", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}
        self.assertEqual(by_id["epi-fhir"].canonical_biomarker_id, "epithelial_cells_urine")
        self.assertEqual(by_id["epi-fhir"].normalized_unit, "#/hpf")
        self.assertEqual(by_id["cast-fhir"].canonical_biomarker_id, "hyaline_casts")
        self.assertEqual(by_id["cast-fhir"].normalized_unit, "#/lpf")
        self.assertTrue(all(record.mapping_status == "mapped" for record in by_id.values()))


if __name__ == "__main__":
    unittest.main()
