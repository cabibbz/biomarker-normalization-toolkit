import unittest

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.normalizer import normalize_rows


class AllergenIgeFollowupTests(unittest.TestCase):
    def test_specific_allergen_ige_panel_maps(self) -> None:
        cases = [
            ("peanut", "Peanut IgE Ab [Units/volume] in Serum", "ige_peanut"),
            ("walnut", "Walnut IgE Ab [Units/volume] in Serum", "ige_walnut"),
            ("codfish", "Codfish IgE Ab [Units/volume] in Serum", "ige_codfish"),
            ("shrimp", "Shrimp IgE Ab [Units/volume] in Serum", "ige_shrimp"),
            ("wheat", "Wheat IgE Ab [Units/volume] in Serum", "ige_wheat"),
            ("egg", "Egg white IgE Ab [Units/volume] in Serum", "ige_egg_white"),
            ("soy", "Soybean IgE Ab [Units/volume] in Serum", "ige_soybean"),
            ("milk", "Cow milk IgE Ab [Units/volume] in Serum", "ige_cow_milk"),
            ("oak", "White oak IgE Ab [Units/volume] in Serum", "ige_white_oak"),
            ("ragweed", "Common Ragweed IgE Ab [Units/volume] in Serum", "ige_common_ragweed"),
            ("cat", "Cat dander IgE Ab [Units/volume] in Serum", "ige_cat_dander"),
            (
                "dust",
                "American house dust mite IgE Ab [Units/volume] in Serum",
                "ige_american_house_dust_mite",
            ),
            (
                "clado",
                "Cladosporium herbarum IgE Ab [Units/volume] in Serum",
                "ige_cladosporium_herbarum",
            ),
            ("bee", "Honey bee IgE Ab [Units/volume] in Serum", "ige_honey_bee"),
            ("latex", "Latex IgE Ab [Units/volume] in Serum", "ige_latex"),
        ]
        rows = [
            {
                "source_row_id": row_id,
                "source_test_name": source_test_name,
                "raw_value": "0.2",
                "source_unit": "kU/L",
            }
            for row_id, source_test_name, _ in cases
        ]
        rows.append(
            {
                "source_row_id": "total-ige",
                "source_test_name": "IgE",
                "raw_value": "120",
                "source_unit": "k[IU]/L",
            }
        )
        rows.append(
            {
                "source_row_id": "hdl-es",
                "source_test_name": "Colesterol HDL",
                "raw_value": "42",
                "source_unit": "mg/dL",
            }
        )

        result = normalize_rows(rows)
        by_id = {record.source_row_id: record for record in result.records}

        for row_id, _, biomarker_id in cases:
            record = by_id[row_id]
            self.assertEqual(record.mapping_status, "mapped")
            self.assertEqual(record.canonical_biomarker_id, biomarker_id)
            self.assertEqual(record.normalized_value, "0.2")
            self.assertEqual(record.normalized_unit, "IU/mL")

        self.assertEqual(by_id["total-ige"].canonical_biomarker_id, "ige_total")
        self.assertEqual(by_id["total-ige"].normalized_value, "120")
        self.assertEqual(by_id["total-ige"].normalized_unit, "IU/mL")

        self.assertEqual(by_id["hdl-es"].canonical_biomarker_id, "hdl_cholesterol")
        self.assertEqual(by_id["hdl-es"].normalized_unit, "mg/dL")

    def test_new_allergen_ige_loincs_are_expected(self) -> None:
        expected = {
            "ige_peanut": "6206-7",
            "ige_walnut": "6273-7",
            "ige_codfish": "6082-2",
            "ige_shrimp": "6246-3",
            "ige_wheat": "6276-0",
            "ige_egg_white": "6106-9",
            "ige_soybean": "6248-9",
            "ige_cow_milk": "7258-7",
            "ige_white_oak": "6189-5",
            "ige_common_ragweed": "6085-5",
            "ige_cat_dander": "6833-8",
            "ige_american_house_dust_mite": "6095-4",
            "ige_cladosporium_herbarum": "6075-6",
            "ige_honey_bee": "6844-5",
            "ige_latex": "6158-0",
        }
        for biomarker_id, loinc in expected.items():
            self.assertEqual(BIOMARKER_CATALOG[biomarker_id].loinc, loinc)


if __name__ == "__main__":
    unittest.main()
