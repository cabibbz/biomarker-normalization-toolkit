from pathlib import Path

from biomarker_normalization_toolkit import normalize, read_custom_aliases, validate_custom_aliases


repo_root = Path(__file__).resolve().parents[2]
alias_path = repo_root / "examples" / "custom_aliases" / "custom_aliases.json"

report = validate_custom_aliases(alias_path)
print("Alias file clean:", report["clean"])
print("Net new aliases:", report["net_new_alias_count"])

custom_aliases = read_custom_aliases(alias_path)
print("Aliases available:", sum(len(aliases) for aliases in custom_aliases.values()))

result = normalize(
    [
        {
            "source_row_id": "1",
            "source_test_name": "Blood Sugar",
            "raw_value": "100",
            "source_unit": "mg/dL",
            "specimen_type": "serum",
            "source_reference_range": "",
        }
    ],
    custom_aliases=custom_aliases,
)

for record in result.records:
    print(record.canonical_biomarker_id, record.mapping_status)
