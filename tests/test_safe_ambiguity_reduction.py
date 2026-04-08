import unittest

from biomarker_normalization_toolkit.normalizer import normalize_rows


class SafeAmbiguityReductionTests(unittest.TestCase):
    def test_glucose_reference_range_disambiguates_to_serum(self) -> None:
        result = normalize_rows([{
            "source_test_name": "Glucose",
            "raw_value": "95",
            "source_unit": "mg/dL",
            "specimen_type": "",
            "source_reference_range": "70-99 mg/dL",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "mapped")
        self.assertEqual(rec.canonical_biomarker_id, "glucose_serum")
        self.assertEqual(rec.status_reason, "mapped_by_alias_and_reference_range")
        self.assertEqual(rec.match_confidence, "medium")

    def test_glucose_reference_range_disambiguates_to_urine(self) -> None:
        result = normalize_rows([{
            "source_test_name": "Glucose",
            "raw_value": "5",
            "source_unit": "mg/dL",
            "specimen_type": "",
            "source_reference_range": "0-15 mg/dL",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "mapped")
        self.assertEqual(rec.canonical_biomarker_id, "glucose_urine")
        self.assertEqual(rec.status_reason, "mapped_by_alias_and_reference_range")
        self.assertEqual(rec.match_confidence, "medium")

    def test_creatinine_reference_range_disambiguates_to_blood(self) -> None:
        result = normalize_rows([{
            "source_test_name": "Creatinine",
            "raw_value": "1.0",
            "source_unit": "mg/dL",
            "specimen_type": "",
            "source_reference_range": "0.6-1.2 mg/dL",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "mapped")
        self.assertEqual(rec.canonical_biomarker_id, "creatinine")
        self.assertEqual(rec.status_reason, "mapped_by_alias_and_reference_range")
        self.assertEqual(rec.match_confidence, "medium")

    def test_creatinine_reference_range_disambiguates_to_urine(self) -> None:
        result = normalize_rows([{
            "source_test_name": "Creatinine",
            "raw_value": "88",
            "source_unit": "mg/dL",
            "specimen_type": "",
            "source_reference_range": "20-300 mg/dL",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "mapped")
        self.assertEqual(rec.canonical_biomarker_id, "creatinine_urine")
        self.assertEqual(rec.status_reason, "mapped_by_alias_and_reference_range")
        self.assertEqual(rec.match_confidence, "medium")

    def test_ph_without_strong_signal_remains_ambiguous(self) -> None:
        result = normalize_rows([{
            "source_test_name": "pH",
            "raw_value": "7.0",
            "source_unit": "",
            "specimen_type": "",
            "source_reference_range": "",
        }])
        rec = result.records[0]
        self.assertEqual(rec.mapping_status, "review_needed")
        self.assertEqual(rec.status_reason, "ambiguous_alias_requires_specimen")


if __name__ == "__main__":
    unittest.main()
