import unittest

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.normalizer import normalize_rows


class NextWaveSpecialtyFollowupTests(unittest.TestCase):
    def test_new_aliases_and_specialty_markers_map(self) -> None:
        rows = [
            {
                "source_row_id": "ldl-es",
                "source_test_name": "Colesterol LDL",
                "raw_value": "96",
                "source_unit": "mg/dL",
            },
            {
                "source_row_id": "trig-es",
                "source_test_name": "Triglic\u00e9ridos",
                "raw_value": "165",
                "source_unit": "mg/dL",
            },
            {
                "source_row_id": "trig-fast",
                "source_test_name": "Triglyceride [Mass/volume] in Serum or Plasma --fasting",
                "raw_value": "123",
                "source_unit": "mg/dL",
            },
            {
                "source_row_id": "acr-es",
                "source_test_name": "Microalbuminuria (orina)",
                "raw_value": "45",
                "source_unit": "mg/g creatinina",
            },
            {
                "source_row_id": "pcr-ratio",
                "source_test_name": "Protein/Creatinine Ratio",
                "raw_value": "0.3",
                "source_unit": "Ratio",
                "specimen_type": "Urine",
            },
            {
                "source_row_id": "pcr-mgmg",
                "source_test_name": "Protein/Creatinine Ratio",
                "raw_value": "0.5",
                "source_unit": "mg/mg",
                "specimen_type": "Urine",
                "source_reference_range": "0-0.2 mg/mg",
            },
            {
                "source_row_id": "cd3pct",
                "source_test_name": "CD3 Cells, Percent",
                "raw_value": "71",
                "source_unit": "%",
                "specimen_type": "Blood",
            },
            {
                "source_row_id": "crp-hs",
                "source_test_name": "CRP-hs",
                "raw_value": "6.4",
                "source_unit": "mg/L",
            },
            {
                "source_row_id": "creat-wb",
                "source_test_name": "Creatinine, Whole Blood",
                "raw_value": "1.1",
                "source_unit": "mg/dL",
                "specimen_type": "Blood",
            },
            {
                "source_row_id": "alt-tgp",
                "source_test_name": "ALT (TGP)",
                "raw_value": "35",
                "source_unit": "U/L",
            },
            {
                "source_row_id": "ast-tgo",
                "source_test_name": "AST (TGO)",
                "raw_value": "28",
                "source_unit": "U/L",
            },
            {
                "source_row_id": "egfr-es",
                "source_test_name": "TFG / eGFR",
                "raw_value": "87",
                "source_unit": "mL/min/1.73m2",
            },
            {
                "source_row_id": "esr-long",
                "source_test_name": "ESR (Erythrocyte Sed Rate)",
                "raw_value": "12",
                "source_unit": "mm/hr",
                "specimen_type": "Blood",
            },
            {
                "source_row_id": "alb-ser",
                "source_test_name": "Albumin [Mass/volume] in Serum",
                "raw_value": "4.2",
                "source_unit": "g/dL",
            },
            {
                "source_row_id": "prot-csf",
                "source_test_name": "Total Protein, CSF",
                "raw_value": "31",
                "source_unit": "mg/dL",
                "specimen_type": "Cerebrospinal Fluid",
                "source_reference_range": "15-45 mg/dL",
            },
            {
                "source_row_id": "lith",
                "source_test_name": "Lithium",
                "raw_value": "1.0",
                "source_unit": "mmol/L",
            },
            {
                "source_row_id": "genta",
                "source_test_name": "Gentamicin - random",
                "raw_value": "1.8",
                "source_unit": "mcg/mL",
            },
            {
                "source_row_id": "carb",
                "source_test_name": "Carbamazepine",
                "raw_value": "8.3",
                "source_unit": "ug/mL",
                "specimen_type": "Blood",
                "source_reference_range": "4-12 ug/mL",
            },
            {
                "source_row_id": "theo",
                "source_test_name": "Theophylline",
                "raw_value": "14.0",
                "source_unit": "mcg/mL",
            },
            {
                "source_row_id": "rbc-asc",
                "source_test_name": "RBC, Ascites",
                "raw_value": "45",
                "source_unit": "#/uL",
                "specimen_type": "Ascites",
                "source_reference_range": "0-0 #/uL",
            },
            {
                "source_row_id": "alb-asc",
                "source_test_name": "Albumin, Ascites",
                "raw_value": "1.2",
                "source_unit": "g/dL",
                "specimen_type": "Ascites",
            },
            {
                "source_row_id": "glu-asc",
                "source_test_name": "Glucose, Ascites",
                "raw_value": "108",
                "source_unit": "mg/dL",
                "specimen_type": "Ascites",
            },
            {
                "source_row_id": "tp-asc",
                "source_test_name": "Total Protein, Ascites",
                "raw_value": "2.3",
                "source_unit": "g/dL",
                "specimen_type": "Ascites",
            },
            {
                "source_row_id": "rbc-csf",
                "source_test_name": "RBC, CSF",
                "raw_value": "14",
                "source_unit": "#/uL",
                "specimen_type": "Cerebrospinal Fluid",
                "source_reference_range": "0-0 #/uL",
            },
            {
                "source_row_id": "rbc-plr",
                "source_test_name": "RBC, Pleural",
                "raw_value": "2225",
                "source_unit": "#/uL",
                "specimen_type": "Pleural",
                "source_reference_range": "0-0 #/uL",
            },
            {
                "source_row_id": "alb-plr",
                "source_test_name": "Albumin, Pleural",
                "raw_value": "1.6",
                "source_unit": "g/dL",
                "specimen_type": "Pleural Fluid",
            },
            {
                "source_row_id": "glu-plr",
                "source_test_name": "Glucose, Pleural",
                "raw_value": "131",
                "source_unit": "mg/dL",
                "specimen_type": "Pleural",
            },
            {
                "source_row_id": "tp-plr",
                "source_test_name": "Total Protein, Pleural",
                "raw_value": "4.0",
                "source_unit": "g/dL",
                "specimen_type": "Thoracentesis Fluid",
            },
        ]

        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}

        self.assertEqual(by_id["ldl-es"].canonical_biomarker_id, "ldl_cholesterol")
        self.assertEqual(by_id["trig-es"].canonical_biomarker_id, "triglycerides")
        self.assertEqual(by_id["trig-fast"].canonical_biomarker_id, "triglycerides")
        self.assertEqual(by_id["acr-es"].canonical_biomarker_id, "albumin_creatinine_ratio")
        self.assertEqual(by_id["acr-es"].normalized_value, "45")
        self.assertEqual(by_id["acr-es"].normalized_unit, "mg/g")

        self.assertEqual(by_id["pcr-ratio"].canonical_biomarker_id, "protein_creatinine_ratio")
        self.assertEqual(by_id["pcr-ratio"].normalized_value, "0.3")
        self.assertEqual(by_id["pcr-ratio"].normalized_unit, "ratio")
        self.assertEqual(by_id["pcr-mgmg"].canonical_biomarker_id, "protein_creatinine_ratio")
        self.assertEqual(by_id["pcr-mgmg"].normalized_reference_range, "0-0.2 ratio")

        self.assertEqual(by_id["cd3pct"].canonical_biomarker_id, "cd3_pct")
        self.assertEqual(by_id["cd3pct"].normalized_unit, "%")
        self.assertEqual(by_id["crp-hs"].canonical_biomarker_id, "hscrp")
        self.assertEqual(by_id["creat-wb"].canonical_biomarker_id, "creatinine")
        self.assertEqual(by_id["alt-tgp"].canonical_biomarker_id, "alt")
        self.assertEqual(by_id["ast-tgo"].canonical_biomarker_id, "ast")
        self.assertEqual(by_id["egfr-es"].canonical_biomarker_id, "egfr")
        self.assertEqual(by_id["esr-long"].canonical_biomarker_id, "esr")
        self.assertEqual(by_id["alb-ser"].canonical_biomarker_id, "albumin")
        self.assertEqual(by_id["prot-csf"].canonical_biomarker_id, "protein_csf")
        self.assertEqual(by_id["prot-csf"].normalized_reference_range, "15-45 mg/dL")

        self.assertEqual(by_id["lith"].canonical_biomarker_id, "lithium")
        self.assertEqual(by_id["lith"].normalized_unit, "mmol/L")
        self.assertEqual(by_id["genta"].canonical_biomarker_id, "gentamicin")
        self.assertEqual(by_id["genta"].normalized_unit, "ug/mL")
        self.assertEqual(by_id["carb"].canonical_biomarker_id, "carbamazepine")
        self.assertEqual(by_id["carb"].normalized_reference_range, "4-12 ug/mL")
        self.assertEqual(by_id["theo"].canonical_biomarker_id, "theophylline")

        self.assertEqual(by_id["rbc-asc"].canonical_biomarker_id, "rbc_ascites")
        self.assertEqual(by_id["rbc-asc"].normalized_reference_range, "0-0 #/uL")
        self.assertEqual(by_id["alb-asc"].canonical_biomarker_id, "albumin_ascites")
        self.assertEqual(by_id["glu-asc"].canonical_biomarker_id, "glucose_ascites")
        self.assertEqual(by_id["tp-asc"].canonical_biomarker_id, "total_protein_ascites")
        self.assertEqual(by_id["rbc-csf"].canonical_biomarker_id, "rbc_csf")
        self.assertEqual(by_id["rbc-plr"].canonical_biomarker_id, "rbc_pleural")
        self.assertEqual(by_id["alb-plr"].canonical_biomarker_id, "albumin_pleural")
        self.assertEqual(by_id["glu-plr"].canonical_biomarker_id, "glucose_pleural")
        self.assertEqual(by_id["tp-plr"].canonical_biomarker_id, "total_protein_pleural")

        self.assertTrue(all(record.mapping_status == "mapped" for record in by_id.values()))

    def test_new_loincs_are_expected(self) -> None:
        self.assertEqual(BIOMARKER_CATALOG["cd3_pct"].loinc, "8124-0")
        self.assertEqual(BIOMARKER_CATALOG["lithium"].loinc, "14334-7")
        self.assertEqual(BIOMARKER_CATALOG["gentamicin"].loinc, "35668-3")
        self.assertEqual(BIOMARKER_CATALOG["carbamazepine"].loinc, "3432-2")
        self.assertEqual(BIOMARKER_CATALOG["theophylline"].loinc, "4049-3")
        self.assertEqual(BIOMARKER_CATALOG["protein_creatinine_ratio"].loinc, "2890-2")
        self.assertEqual(BIOMARKER_CATALOG["rbc_ascites"].loinc, "26457-2")
        self.assertEqual(BIOMARKER_CATALOG["albumin_ascites"].loinc, "1749-1")
        self.assertEqual(BIOMARKER_CATALOG["glucose_ascites"].loinc, "2347-3")
        self.assertEqual(BIOMARKER_CATALOG["total_protein_ascites"].loinc, "2883-7")
        self.assertEqual(BIOMARKER_CATALOG["rbc_csf"].loinc, "26454-9")
        self.assertEqual(BIOMARKER_CATALOG["rbc_pleural"].loinc, "26456-4")
        self.assertEqual(BIOMARKER_CATALOG["albumin_pleural"].loinc, "1748-3")
        self.assertEqual(BIOMARKER_CATALOG["glucose_pleural"].loinc, "2346-5")
        self.assertEqual(BIOMARKER_CATALOG["total_protein_pleural"].loinc, "2882-9")


if __name__ == "__main__":
    unittest.main()
