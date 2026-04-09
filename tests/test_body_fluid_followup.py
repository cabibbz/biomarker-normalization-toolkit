import unittest

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.normalizer import normalize_rows


class BodyFluidFollowupTests(unittest.TestCase):
    def test_body_fluid_counts_and_differentials_map(self) -> None:
        rows = [
            {
                "source_row_id": "tnc-asc",
                "source_test_name": "Total Nucleated Cells, Ascites",
                "raw_value": "277",
                "source_unit": "#/uL",
                "specimen_type": "Ascites",
                "source_reference_range": "0-0 #/uL",
            },
            {
                "source_row_id": "poly-asc",
                "source_test_name": "Polys",
                "raw_value": "3",
                "source_unit": "%",
                "specimen_type": "Ascites",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "lym-asc",
                "source_test_name": "Lymphocytes",
                "raw_value": "21",
                "source_unit": "%",
                "specimen_type": "Ascites",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "mono-asc",
                "source_test_name": "Monocytes",
                "raw_value": "24",
                "source_unit": "%",
                "specimen_type": "Ascites",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "eos-asc",
                "source_test_name": "Eosinophils",
                "raw_value": "4",
                "source_unit": "%",
                "specimen_type": "Ascites",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "macro-asc",
                "source_test_name": "Macrophage",
                "raw_value": "62",
                "source_unit": "%",
                "specimen_type": "Ascites",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "meso-asc",
                "source_test_name": "Mesothelial Cell",
                "raw_value": "2",
                "source_unit": "%",
                "specimen_type": "Ascites",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "tnc-plr",
                "source_test_name": "Total Nucleated Cells, Pleural",
                "raw_value": "444",
                "source_unit": "#/uL",
                "specimen_type": "Pleural",
                "source_reference_range": "0-0 #/uL",
            },
            {
                "source_row_id": "poly-plr",
                "source_test_name": "Polys",
                "raw_value": "12",
                "source_unit": "%",
                "specimen_type": "Pleural",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "lym-plr",
                "source_test_name": "Lymphocytes",
                "raw_value": "71",
                "source_unit": "%",
                "specimen_type": "Pleural",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "eos-plr",
                "source_test_name": "Eosinophils",
                "raw_value": "3",
                "source_unit": "%",
                "specimen_type": "Pleural",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "monos-plr",
                "source_test_name": "Monos",
                "raw_value": "14",
                "source_unit": "%",
                "specimen_type": "Thoracentesis Fluid",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "poly-bf",
                "source_test_name": "Polys",
                "raw_value": "7",
                "source_unit": "%",
                "specimen_type": "Other Body Fluid",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "lym-bf",
                "source_test_name": "Lymphocytes",
                "raw_value": "18",
                "source_unit": "%",
                "specimen_type": "Other Body Fluid",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "eos-bf",
                "source_test_name": "Eosinophils",
                "raw_value": "2",
                "source_unit": "%",
                "specimen_type": "Other Body Fluid",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "monos-bf",
                "source_test_name": "Monos",
                "raw_value": "11",
                "source_unit": "%",
                "specimen_type": "Other Body Fluid",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "macro-bf",
                "source_test_name": "Macrophage",
                "raw_value": "65",
                "source_unit": "%",
                "specimen_type": "Other Body Fluid",
                "source_reference_range": "0-0 %",
            },
            {
                "source_row_id": "tnc-csf",
                "source_test_name": "Total Nucleated Cells, CSF",
                "raw_value": "4",
                "source_unit": "#/uL",
                "specimen_type": "Cerebrospinal Fluid",
                "source_reference_range": "0-5 #/uL",
            },
            {
                "source_row_id": "poly-csf",
                "source_test_name": "Polys",
                "raw_value": "1",
                "source_unit": "%",
                "specimen_type": "Cerebrospinal Fluid",
            },
            {
                "source_row_id": "mono-csf",
                "source_test_name": "Monocytes",
                "raw_value": "33",
                "source_unit": "%",
                "specimen_type": "Cerebrospinal Fluid",
            },
            {
                "source_row_id": "macro-csf",
                "source_test_name": "Macrophage",
                "raw_value": "12",
                "source_unit": "%",
                "specimen_type": "Cerebrospinal Fluid",
            },
        ]

        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}

        self.assertEqual(by_id["tnc-asc"].canonical_biomarker_id, "total_nucleated_cells_ascites")
        self.assertEqual(by_id["poly-asc"].canonical_biomarker_id, "neutrophils_ascites_pct")
        self.assertEqual(by_id["lym-asc"].canonical_biomarker_id, "lymphocytes_ascites_pct")
        self.assertEqual(by_id["mono-asc"].canonical_biomarker_id, "monocytes_ascites_pct")
        self.assertEqual(by_id["eos-asc"].canonical_biomarker_id, "eosinophils_ascites_pct")
        self.assertEqual(by_id["macro-asc"].canonical_biomarker_id, "monocytes_macrophages_ascites_pct")
        self.assertEqual(by_id["meso-asc"].canonical_biomarker_id, "mesothelial_cells_ascites_pct")

        self.assertEqual(by_id["tnc-plr"].canonical_biomarker_id, "total_nucleated_cells_pleural")
        self.assertEqual(by_id["poly-plr"].canonical_biomarker_id, "neutrophils_pleural_pct")
        self.assertEqual(by_id["lym-plr"].canonical_biomarker_id, "lymphocytes_pleural_pct")
        self.assertEqual(by_id["eos-plr"].canonical_biomarker_id, "eosinophils_pleural_pct")
        self.assertEqual(by_id["monos-plr"].canonical_biomarker_id, "monocytes_macrophages_pleural_pct")

        self.assertEqual(by_id["poly-bf"].canonical_biomarker_id, "neutrophils_body_fluid_pct")
        self.assertEqual(by_id["lym-bf"].canonical_biomarker_id, "lymphocytes_body_fluid_pct")
        self.assertEqual(by_id["eos-bf"].canonical_biomarker_id, "eosinophils_body_fluid_pct")
        self.assertEqual(by_id["monos-bf"].canonical_biomarker_id, "monocytes_macrophages_body_fluid_pct")
        self.assertEqual(by_id["macro-bf"].canonical_biomarker_id, "macrophages_body_fluid_pct")

        self.assertEqual(by_id["tnc-csf"].canonical_biomarker_id, "total_nucleated_cells_csf")
        self.assertEqual(by_id["tnc-csf"].normalized_reference_range, "0-5 #/uL")
        self.assertEqual(by_id["poly-csf"].canonical_biomarker_id, "neutrophils_csf_pct")
        self.assertEqual(by_id["mono-csf"].canonical_biomarker_id, "monocytes_csf_pct")
        self.assertEqual(by_id["macro-csf"].canonical_biomarker_id, "macrophages_csf_pct")

        self.assertTrue(all(record.mapping_status == "mapped" for record in by_id.values()))

    def test_new_body_fluid_loincs_are_expected(self) -> None:
        self.assertEqual(BIOMARKER_CATALOG["total_nucleated_cells_ascites"].loinc, "51926-4")
        self.assertEqual(BIOMARKER_CATALOG["neutrophils_ascites_pct"].loinc, "26514-0")
        self.assertEqual(BIOMARKER_CATALOG["lymphocytes_ascites_pct"].loinc, "26482-0")
        self.assertEqual(BIOMARKER_CATALOG["monocytes_ascites_pct"].loinc, "26488-7")
        self.assertEqual(BIOMARKER_CATALOG["eosinophils_ascites_pct"].loinc, "30380-0")
        self.assertEqual(BIOMARKER_CATALOG["monocytes_macrophages_ascites_pct"].loinc, "35020-7")
        self.assertEqual(BIOMARKER_CATALOG["mesothelial_cells_ascites_pct"].loinc, "30432-9")

        self.assertEqual(BIOMARKER_CATALOG["total_nucleated_cells_pleural"].loinc, "58904-4")
        self.assertEqual(BIOMARKER_CATALOG["neutrophils_pleural_pct"].loinc, "30455-0")
        self.assertEqual(BIOMARKER_CATALOG["lymphocytes_pleural_pct"].loinc, "26481-2")
        self.assertEqual(BIOMARKER_CATALOG["eosinophils_pleural_pct"].loinc, "30379-2")
        self.assertEqual(BIOMARKER_CATALOG["monocytes_macrophages_pleural_pct"].loinc, "35021-5")

        self.assertEqual(BIOMARKER_CATALOG["neutrophils_body_fluid_pct"].loinc, "26513-2")
        self.assertEqual(BIOMARKER_CATALOG["lymphocytes_body_fluid_pct"].loinc, "11031-2")
        self.assertEqual(BIOMARKER_CATALOG["eosinophils_body_fluid_pct"].loinc, "26452-3")
        self.assertEqual(BIOMARKER_CATALOG["monocytes_macrophages_body_fluid_pct"].loinc, "30437-8")
        self.assertEqual(BIOMARKER_CATALOG["macrophages_body_fluid_pct"].loinc, "30427-9")

        self.assertEqual(BIOMARKER_CATALOG["total_nucleated_cells_csf"].loinc, "58906-9")
        self.assertEqual(BIOMARKER_CATALOG["neutrophils_csf_pct"].loinc, "26512-4")
        self.assertEqual(BIOMARKER_CATALOG["monocytes_csf_pct"].loinc, "26486-1")
        self.assertEqual(BIOMARKER_CATALOG["macrophages_csf_pct"].loinc, "30426-1")


if __name__ == "__main__":
    unittest.main()
