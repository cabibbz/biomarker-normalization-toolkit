from biomarker_normalization_toolkit import normalize


rows = [
    {
        "source_row_id": "1",
        "source_test_name": "Glucose",
        "raw_value": "100",
        "source_unit": "mg/dL",
        "specimen_type": "serum",
        "source_reference_range": "70-99 mg/dL",
    },
    {
        "source_row_id": "2",
        "source_test_name": "HbA1c",
        "raw_value": "5.4",
        "source_unit": "%",
        "specimen_type": "whole blood",
        "source_reference_range": "4.0-5.6 %",
    },
]

result = normalize(rows)

print("Summary:", result.summary)
for record in result.records:
    print(record.canonical_biomarker_id, record.normalized_value, record.normalized_unit)
