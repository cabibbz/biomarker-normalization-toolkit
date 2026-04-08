import unittest

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.normalizer import normalize_rows


class ScopeExpansionFollowupTests(unittest.TestCase):
    def test_new_loinc_assignments(self) -> None:
        self.assertEqual(BIOMARKER_CATALOG["ethanol"].loinc, "5643-2")
        self.assertEqual(BIOMARKER_CATALOG["digoxin"].loinc, "10535-3")
        self.assertEqual(BIOMARKER_CATALOG["tacrolimus"].loinc, "11253-2")
        self.assertEqual(BIOMARKER_CATALOG["salicylates"].loinc, "4024-6")
        self.assertEqual(BIOMARKER_CATALOG["myoglobin"].loinc, "2639-3")
        self.assertEqual(BIOMARKER_CATALOG["phenytoin"].loinc, "3968-5")
        self.assertEqual(BIOMARKER_CATALOG["acetaminophen"].loinc, "3298-7")
        self.assertEqual(BIOMARKER_CATALOG["ptt_ratio"].loinc, "63561-5")
        self.assertEqual(BIOMARKER_CATALOG["alveolar_arterial_gradient"].loinc, "19991-9")
        self.assertEqual(BIOMARKER_CATALOG["promyelocytes_pct"].loinc, "783-1")
        self.assertEqual(BIOMARKER_CATALOG["other_cells_pct"].loinc, "44096-6")
        self.assertEqual(BIOMARKER_CATALOG["blasts_pct"].loinc, "26446-5")
        self.assertEqual(BIOMARKER_CATALOG["epithelial_cells_urine"].loinc, "5787-7")
        self.assertEqual(BIOMARKER_CATALOG["hyaline_casts"].loinc, "5796-8")

    def test_followup_scope_gaps_now_map(self) -> None:
        rows = [
            {"source_row_id": "etoh", "source_test_name": "ethanol", "raw_value": "148",
             "source_unit": "mg/dL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "dig", "source_test_name": "Digoxin", "raw_value": "1.2",
             "source_unit": "ng/mL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "tac", "source_test_name": "Tacrolimus-FK506", "raw_value": "7.8",
             "source_unit": "ng/mL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "sal", "source_test_name": "Salicylates", "raw_value": "12",
             "source_unit": "mg/dL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "myo", "source_test_name": "Myoglobin", "raw_value": "48",
             "source_unit": "ng/mL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "pheny", "source_test_name": "Phenytoin", "raw_value": "14.2",
             "source_unit": "ug/mL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "apap", "source_test_name": "APAP", "raw_value": "20",
             "source_unit": "ug/mL", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "pttr", "source_test_name": "PTT ratio", "raw_value": "1.1",
             "source_unit": "ratio", "specimen_type": "", "source_reference_range": ""},
            {"source_row_id": "aagrad", "source_test_name": "Alveolar-arterial Gradient", "raw_value": "18",
             "source_unit": "mmHg", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "promo", "source_test_name": "Promyelocytes", "raw_value": "1",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": "0-0 %"},
            {"source_row_id": "other", "source_test_name": "Other Cells", "raw_value": "2",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": "0-0 %"},
            {"source_row_id": "blast", "source_test_name": "Blasts", "raw_value": "1",
             "source_unit": "%", "specimen_type": "Blood", "source_reference_range": "0-0 %"},
            {"source_row_id": "epi", "source_test_name": "Epithelial Cells", "raw_value": "3",
             "source_unit": "#/hpf", "specimen_type": "Urine", "source_reference_range": ""},
            {"source_row_id": "cast", "source_test_name": "Hyaline Casts", "raw_value": "1",
             "source_unit": "#/lpf", "specimen_type": "Urine", "source_reference_range": "0-0 #/lpf"},
        ]
        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}
        self.assertEqual(by_id["etoh"].canonical_biomarker_id, "ethanol")
        self.assertEqual(by_id["dig"].canonical_biomarker_id, "digoxin")
        self.assertEqual(by_id["tac"].canonical_biomarker_id, "tacrolimus")
        self.assertEqual(by_id["sal"].canonical_biomarker_id, "salicylates")
        self.assertEqual(by_id["myo"].canonical_biomarker_id, "myoglobin")
        self.assertEqual(by_id["pheny"].canonical_biomarker_id, "phenytoin")
        self.assertEqual(by_id["apap"].canonical_biomarker_id, "acetaminophen")
        self.assertEqual(by_id["pttr"].canonical_biomarker_id, "ptt_ratio")
        self.assertEqual(by_id["aagrad"].canonical_biomarker_id, "alveolar_arterial_gradient")
        self.assertEqual(by_id["promo"].canonical_biomarker_id, "promyelocytes_pct")
        self.assertEqual(by_id["other"].canonical_biomarker_id, "other_cells_pct")
        self.assertEqual(by_id["blast"].canonical_biomarker_id, "blasts_pct")
        self.assertEqual(by_id["epi"].canonical_biomarker_id, "epithelial_cells_urine")
        self.assertEqual(by_id["cast"].canonical_biomarker_id, "hyaline_casts")
        self.assertTrue(all(record.mapping_status == "mapped" for record in by_id.values()))

    def test_multilingual_aliases_map(self) -> None:
        rows = [
            {"source_row_id": "a1c", "source_test_name": "Hemoglobina glicosilada (HbA1c)", "raw_value": "6.0",
             "source_unit": "%", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "creat", "source_test_name": "Creatinina [Volume] no soro ou plasma", "raw_value": "1.1",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "chol", "source_test_name": "Colesterol total", "raw_value": "178",
             "source_unit": "mg/dL", "specimen_type": "serum", "source_reference_range": ""},
            {"source_row_id": "hgb", "source_test_name": "Hemoglobina", "raw_value": "14.2",
             "source_unit": "g/dL", "specimen_type": "whole blood", "source_reference_range": ""},
            {"source_row_id": "plt", "source_test_name": "Plaquetas", "raw_value": "245",
             "source_unit": "K/uL", "specimen_type": "whole blood", "source_reference_range": ""},
        ]
        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}
        self.assertEqual(by_id["a1c"].canonical_biomarker_id, "hba1c")
        self.assertEqual(by_id["creat"].canonical_biomarker_id, "creatinine")
        self.assertEqual(by_id["chol"].canonical_biomarker_id, "total_cholesterol")
        self.assertEqual(by_id["hgb"].canonical_biomarker_id, "hemoglobin")
        self.assertEqual(by_id["plt"].canonical_biomarker_id, "platelets")
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
