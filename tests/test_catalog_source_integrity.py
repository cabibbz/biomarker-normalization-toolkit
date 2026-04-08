import ast
from pathlib import Path
import unittest


class CatalogSourceIntegrityTests(unittest.TestCase):
    def test_biomarker_catalog_literal_has_no_duplicate_keys(self) -> None:
        catalog_path = Path(__file__).resolve().parents[1] / "src" / "biomarker_normalization_toolkit" / "catalog.py"
        module = ast.parse(catalog_path.read_text(encoding="utf-8"))

        dict_node = None
        for node in module.body:
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
                value = node.value
            else:
                continue

            for target in targets:
                if isinstance(target, ast.Name) and target.id == "BIOMARKER_CATALOG":
                    dict_node = value
                    break
            if dict_node is not None:
                break

        self.assertIsNotNone(dict_node, "BIOMARKER_CATALOG assignment not found")
        self.assertIsInstance(dict_node, ast.Dict, "BIOMARKER_CATALOG is not a dict literal")

        seen: set[str] = set()
        duplicates: list[str] = []
        for key_node in dict_node.keys:
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                continue
            key = key_node.value
            if key in seen:
                duplicates.append(key)
            seen.add(key)

        self.assertEqual(duplicates, [], f"Duplicate biomarker keys in catalog.py: {duplicates}")
