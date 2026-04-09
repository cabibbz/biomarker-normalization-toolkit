from pathlib import Path

from biomarker_normalization_toolkit import normalize_file


repo_root = Path(__file__).resolve().parents[2]
fixture_path = repo_root / "fixtures" / "input" / "interop" / "fhir_bundle_minimal.json"

result = normalize_file(str(fixture_path))

print("Summary:", result.summary)
for record in result.records:
    print(record.canonical_biomarker_name, record.normalized_value, record.normalized_unit)
