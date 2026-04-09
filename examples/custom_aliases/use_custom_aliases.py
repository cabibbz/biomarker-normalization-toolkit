from pathlib import Path

from biomarker_normalization_toolkit.catalog import load_custom_aliases
from biomarker_normalization_toolkit.normalizer import normalize_rows


repo_root = Path(__file__).resolve().parents[2]
alias_path = repo_root / "examples" / "custom_aliases" / "custom_aliases.json"

added = load_custom_aliases(alias_path)
print("Aliases loaded:", added)

result = normalize_rows(
    [
        {
            "source_row_id": "1",
            "source_test_name": "Blood Sugar",
            "raw_value": "100",
            "source_unit": "mg/dL",
            "specimen_type": "serum",
            "source_reference_range": "",
        }
    ]
)

for record in result.records:
    print(record.canonical_biomarker_id, record.mapping_status)
