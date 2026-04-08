import unittest

from biomarker_normalization_toolkit.normalizer import normalize_rows


class AliasGapFollowupTests(unittest.TestCase):
    def test_alias_only_gap_fixes_map(self) -> None:
        rows = [
            {
                "source_row_id": "creat",
                "source_test_name": "Creatinina",
                "raw_value": "1.3",
                "source_unit": "mg/dL",
            },
            {
                "source_row_id": "bicarb",
                "source_test_name": "Calculated Bicarbonate, Whole Blood",
                "raw_value": "24",
                "source_unit": "mEq/L",
                "specimen_type": "Blood",
                "source_panel_name": "Blood Gas",
            },
            {
                "source_row_id": "ldl",
                "source_test_name": "Cholesterol, LDL, Measured",
                "raw_value": "92",
                "source_unit": "mg/dL",
                "specimen_type": "Blood",
            },
            {
                "source_row_id": "uwbc",
                "source_test_name": "Leukocytes [#/area] in Urine sediment by Microscopy high power field",
                "raw_value": "12",
                "source_unit": "/[HPF]",
            },
            {
                "source_row_id": "urbc",
                "source_test_name": "Erythrocytes [#/area] in Urine sediment by Microscopy high power field",
                "raw_value": "2",
                "source_unit": "/[HPF]",
            },
        ]

        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}

        self.assertEqual(by_id["creat"].canonical_biomarker_id, "creatinine")
        self.assertEqual(by_id["bicarb"].canonical_biomarker_id, "bicarbonate")
        self.assertEqual(by_id["ldl"].canonical_biomarker_id, "ldl_cholesterol")
        self.assertEqual(by_id["uwbc"].canonical_biomarker_id, "urine_wbc")
        self.assertEqual(by_id["urbc"].canonical_biomarker_id, "urine_rbc")

        self.assertEqual(by_id["uwbc"].normalized_unit, "#/uL")
        self.assertEqual(by_id["urbc"].normalized_unit, "#/uL")
        self.assertTrue(all(record.mapping_status == "mapped" for record in by_id.values()))


if __name__ == "__main__":
    unittest.main()
