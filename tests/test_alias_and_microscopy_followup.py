import unittest

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.normalizer import normalize_rows


class AliasAndMicroscopyFollowupTests(unittest.TestCase):
    def test_spanish_blood_chemistry_aliases_map(self) -> None:
        rows = [
            {
                "source_row_id": "glu-es-blood",
                "source_test_name": "Glucosa en sangre",
                "raw_value": "92",
                "source_unit": "mg/dL",
                "specimen_type": "",
                "source_reference_range": "70-110 mg/dL",
            },
            {
                "source_row_id": "glu-es-plasma",
                "source_test_name": "Glucosa en plasma",
                "raw_value": "148",
                "source_unit": "mg/dL",
                "specimen_type": "",
                "source_reference_range": "",
            },
            {
                "source_row_id": "glu-es-fasting",
                "source_test_name": "Glucosa en plasma (ayuno)",
                "raw_value": "150",
                "source_unit": "mg/dL",
                "specimen_type": "",
                "source_reference_range": "",
            },
            {
                "source_row_id": "cre-es",
                "source_test_name": "Creatinina sérica",
                "raw_value": "1.2",
                "source_unit": "mg/dL",
                "specimen_type": "",
                "source_reference_range": "",
            },
        ]

        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}

        self.assertEqual(by_id["glu-es-blood"].canonical_biomarker_id, "glucose_serum")
        self.assertEqual(by_id["glu-es-plasma"].canonical_biomarker_id, "glucose_serum")
        self.assertEqual(by_id["glu-es-fasting"].canonical_biomarker_id, "glucose_serum")
        self.assertEqual(by_id["cre-es"].canonical_biomarker_id, "creatinine")
        self.assertTrue(all(record.mapping_status == "mapped" for record in by_id.values()))

    def test_granular_casts_maps(self) -> None:
        rows = [
            {
                "source_row_id": "gran-cast",
                "source_test_name": "Granular Casts",
                "raw_value": "3",
                "source_unit": "#/lpf",
                "specimen_type": "urine",
                "source_reference_range": "0-0 #/lpf",
            }
        ]

        result = normalize_rows(rows)
        record = result.records[0]

        self.assertEqual(record.mapping_status, "mapped")
        self.assertEqual(record.canonical_biomarker_id, "granular_casts")
        self.assertEqual(record.normalized_unit, "#/lpf")
        self.assertEqual(record.normalized_reference_range, "0-0 #/lpf")

    def test_followup_loinc_assignments(self) -> None:
        self.assertEqual(BIOMARKER_CATALOG["granular_casts"].loinc, "5793-5")


if __name__ == "__main__":
    unittest.main()
