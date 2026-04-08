import unittest

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.normalizer import normalize_rows


class NextWaveScopeExpansionTests(unittest.TestCase):
    def test_corpus_backed_aliases_map(self) -> None:
        rows = [
            {
                "source_row_id": "oxy",
                "source_test_name": "Oxygen",
                "raw_value": "90",
                "source_unit": "%",
                "specimen_type": "Blood",
                "source_panel_name": "Blood Gas",
                "source_reference_range": "",
            },
            {
                "source_row_id": "pttr",
                "source_test_name": "PTT ratio",
                "raw_value": "1.1",
                "source_unit": "ratio",
                "specimen_type": "",
                "source_reference_range": "",
            },
            {
                "source_row_id": "etoh",
                "source_test_name": "ethanol",
                "raw_value": "145",
                "source_unit": "mg/dL",
                "specimen_type": "",
                "source_reference_range": "",
            },
        ]

        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}

        self.assertEqual(by_id["oxy"].mapping_status, "mapped")
        self.assertEqual(by_id["oxy"].canonical_biomarker_id, "oxygen_saturation")
        self.assertEqual(by_id["oxy"].normalized_unit, "%")
        self.assertEqual(by_id["oxy"].status_reason, "mapped_by_contextual_alias")

        self.assertEqual(by_id["pttr"].mapping_status, "mapped")
        self.assertEqual(by_id["pttr"].canonical_biomarker_id, "ptt_ratio")
        self.assertEqual(by_id["pttr"].normalized_unit, "ratio")

        self.assertEqual(by_id["etoh"].mapping_status, "mapped")
        self.assertEqual(by_id["etoh"].canonical_biomarker_id, "ethanol")
        self.assertEqual(by_id["etoh"].normalized_unit, "mg/dL")

    def test_generic_oxygen_alias_stays_unmapped_without_blood_gas_context(self) -> None:
        rows = [
            {
                "source_row_id": "oxy-generic",
                "source_test_name": "Oxygen",
                "raw_value": "90",
                "source_unit": "%",
                "specimen_type": "",
                "source_reference_range": "",
            },
        ]

        result = normalize_rows(rows)
        record = result.records[0]

        self.assertEqual(record.mapping_status, "unmapped")
        self.assertEqual(record.status_reason, "unknown_alias")

    def test_gap_decisions_stay_conservative(self) -> None:
        rows = [
            {
                "source_row_id": "uwbc",
                "source_test_name": "WBC's in urine",
                "raw_value": "5",
                "source_unit": "",
                "specimen_type": "",
                "source_reference_range": "",
            },
            {
                "source_row_id": "kbad",
                "source_test_name": "Potassium Level",
                "raw_value": "0.4",
                "source_unit": "g/dL",
                "specimen_type": "",
                "source_reference_range": "<=0.6 g/dL",
            },
        ]

        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}

        self.assertEqual(by_id["uwbc"].mapping_status, "unmapped")
        self.assertEqual(by_id["uwbc"].status_reason, "unknown_alias")

        self.assertEqual(by_id["kbad"].mapping_status, "review_needed")
        self.assertEqual(by_id["kbad"].status_reason, "unsupported_unit_for_biomarker")
        self.assertEqual(by_id["kbad"].canonical_biomarker_id, "potassium")

    def test_existing_loinc_assignments_used_for_mapped_candidates(self) -> None:
        self.assertEqual(BIOMARKER_CATALOG["oxygen_saturation"].loinc, "2708-6")
        self.assertEqual(BIOMARKER_CATALOG["ptt_ratio"].loinc, "63561-5")
        self.assertEqual(BIOMARKER_CATALOG["ethanol"].loinc, "5643-2")


if __name__ == "__main__":
    unittest.main()
