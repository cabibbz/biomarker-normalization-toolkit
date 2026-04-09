import unittest
from pathlib import Path

from biomarker_normalization_toolkit.io_utils import read_ccda_input
from biomarker_normalization_toolkit.normalizer import normalize_rows


ROOT = Path(__file__).resolve().parents[1]


class IngestAndUnitResidueFollowupTests(unittest.TestCase):
    def test_ccda_translation_original_text_units_flow_through(self) -> None:
        ccda_path = ROOT / "sample data" / "ccda-examples" / "Results Unit Non-UCUM(C-CDA2.1).xml"
        if not ccda_path.exists():
            self.skipTest("C-CDA example not available")

        rows = read_ccda_input(ccda_path)

        self.assertEqual(rows[0]["source_test_name"], "Platelets [#/volume] in Blood")
        self.assertEqual(rows[0]["source_unit"], "THOUS/MCL")
        self.assertEqual(rows[0]["source_reference_range"], "150-400 THOUS/MCL")

        record = normalize_rows(rows).records[0]
        self.assertEqual(record.mapping_status, "mapped")
        self.assertEqual(record.canonical_biomarker_id, "platelets")
        self.assertEqual(record.normalized_value, "152")
        self.assertEqual(record.normalized_unit, "K/uL")
        self.assertEqual(record.normalized_reference_range, "150-400 K/uL")

    def test_curated_blank_unit_fallback_stays_narrow(self) -> None:
        rows = [
            {
                "source_row_id": "esr",
                "source_test_name": "ESR Westergren",
                "raw_value": "19",
                "source_unit": "",
            },
            {
                "source_row_id": "pdw-blank",
                "source_test_name": "Platelet distribution width [Entitic volume] in Blood by Automated count",
                "raw_value": "12.4",
                "source_unit": "",
                "specimen_type": "Blood",
            },
            {
                "source_row_id": "pdw-bad",
                "source_test_name": "Platelet distribution width [Entitic volume] in Blood by Automated count",
                "raw_value": "12.4",
                "source_unit": "mm",
                "specimen_type": "Blood",
            },
            {
                "source_row_id": "hgb",
                "source_test_name": "Hgb",
                "raw_value": "8",
                "source_unit": "",
            },
            {
                "source_row_id": "uwbc-blank",
                "source_test_name": "WBC's in urine",
                "raw_value": "12",
                "source_unit": "",
            },
            {
                "source_row_id": "csf-wbc-blank",
                "source_test_name": "WBC's in cerebrospinal fluid",
                "raw_value": "4",
                "source_unit": "",
            },
            {
                "source_row_id": "bf-wbc-blank",
                "source_test_name": "WBC's in body fluid",
                "raw_value": "250",
                "source_unit": "",
            },
            {
                "source_row_id": "wbc-generic",
                "source_test_name": "WBC",
                "raw_value": "7.2",
                "source_unit": "",
            },
        ]

        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}

        self.assertEqual(by_id["esr"].mapping_status, "mapped")
        self.assertEqual(by_id["esr"].canonical_biomarker_id, "esr")
        self.assertEqual(by_id["esr"].normalized_unit, "mm/hr")
        self.assertEqual(by_id["esr"].status_reason, "mapped_by_alias_and_implicit_unit")

        self.assertEqual(by_id["pdw-blank"].mapping_status, "mapped")
        self.assertEqual(by_id["pdw-blank"].canonical_biomarker_id, "pdw")
        self.assertEqual(by_id["pdw-blank"].normalized_unit, "fL")
        self.assertEqual(by_id["pdw-blank"].status_reason, "mapped_by_alias_and_implicit_unit")

        self.assertEqual(by_id["pdw-bad"].mapping_status, "review_needed")
        self.assertEqual(by_id["pdw-bad"].status_reason, "unsupported_unit_for_biomarker")

        self.assertEqual(by_id["hgb"].mapping_status, "review_needed")
        self.assertEqual(by_id["hgb"].canonical_biomarker_id, "hemoglobin")
        self.assertEqual(by_id["hgb"].status_reason, "unsupported_unit_for_biomarker")

        self.assertEqual(by_id["uwbc-blank"].mapping_status, "mapped")
        self.assertEqual(by_id["uwbc-blank"].canonical_biomarker_id, "urine_wbc")
        self.assertEqual(by_id["uwbc-blank"].normalized_unit, "#/uL")
        self.assertEqual(by_id["uwbc-blank"].status_reason, "mapped_by_alias_and_implicit_unit")

        self.assertEqual(by_id["csf-wbc-blank"].mapping_status, "mapped")
        self.assertEqual(by_id["csf-wbc-blank"].canonical_biomarker_id, "wbc_csf")
        self.assertEqual(by_id["csf-wbc-blank"].normalized_unit, "#/uL")
        self.assertEqual(by_id["csf-wbc-blank"].status_reason, "mapped_by_alias_and_implicit_unit")

        self.assertEqual(by_id["bf-wbc-blank"].mapping_status, "mapped")
        self.assertEqual(by_id["bf-wbc-blank"].canonical_biomarker_id, "wbc_body_fluid")
        self.assertEqual(by_id["bf-wbc-blank"].normalized_unit, "#/uL")
        self.assertEqual(by_id["bf-wbc-blank"].status_reason, "mapped_by_alias_and_implicit_unit")

        self.assertEqual(by_id["wbc-generic"].mapping_status, "review_needed")
        self.assertEqual(by_id["wbc-generic"].canonical_biomarker_id, "")
        self.assertEqual(by_id["wbc-generic"].status_reason, "ambiguous_alias_requires_specimen")


if __name__ == "__main__":
    unittest.main()
