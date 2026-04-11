# REST API Examples

These commands assume you are running them from the repository root so the tracked fixture paths resolve as written.

Start the server:

```bash
pip install biomarker-normalization-toolkit[rest]
bnt serve --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

Read machine-readable catalog metadata:

```bash
curl http://localhost:8000/catalog/metadata
```

Search machine-readable catalog metadata:

```bash
curl "http://localhost:8000/catalog/metadata/search?search=glucose&limit=3"
```

Validate a custom alias payload before using it:

```bash
curl -X POST http://localhost:8000/aliases/validate \
  -H "Content-Type: application/json" \
  -d '{"custom_aliases": {"hemoglobin": ["Vendor Hgb Alias"]}}'
```

Look up a built-in alias:

```bash
curl "http://localhost:8000/lookup?test_name=GLU&specimen=serum"
```

Look up with per-request custom aliases:

```bash
curl -X POST http://localhost:8000/lookup \
  -H "Content-Type: application/json" \
  -d '{"test_name": "Vendor Glucose Alias", "specimen": "serum", "custom_aliases": {"glucose_serum": ["Vendor Glucose Alias"]}}'
```

Normalize rows:

```bash
curl -X POST http://localhost:8000/normalize \
  -H "Content-Type: application/json" \
  -d '{"rows": [{"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "1"}]}'
```

Normalize rows with per-request custom aliases:

```bash
curl -X POST http://localhost:8000/normalize \
  -H "Content-Type: application/json" \
  -d '{"custom_aliases": {"glucose_serum": ["Vendor Glucose Alias"]}, "rows": [{"source_test_name": "Vendor Glucose Alias", "raw_value": "100", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "1"}]}'
```

Upload a tracked CSV fixture:

```bash
curl -X POST http://localhost:8000/normalize/upload -F "file=@fixtures/input/v0_sample.csv"
```

Upload a tracked CSV fixture with per-request custom aliases:

```bash
curl -X POST http://localhost:8000/normalize/upload \
  -F "file=@fixtures/input/v0_sample.csv" \
  -F 'custom_aliases_json={"glucose_serum":["Vendor Glucose Alias"]}'
```

Compute PhenoAge with the full required biomarker set:

```bash
curl -X POST http://localhost:8000/phenoage \
  -H "Content-Type: application/json" \
  -d '{"chronological_age": 45, "rows": [{"source_test_name": "Albumin", "raw_value": "4.5", "source_unit": "g/dL", "specimen_type": "serum", "source_row_id": "pa1"}, {"source_test_name": "Creatinine", "raw_value": "0.9", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "pa2"}, {"source_test_name": "Glucose", "raw_value": "90", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "pa3"}, {"source_test_name": "hs-CRP", "raw_value": "0.5", "source_unit": "mg/L", "specimen_type": "serum", "source_row_id": "pa4"}, {"source_test_name": "Lymphocytes Percent", "raw_value": "30", "source_unit": "%", "specimen_type": "whole blood", "source_row_id": "pa5"}, {"source_test_name": "MCV", "raw_value": "88", "source_unit": "fL", "specimen_type": "whole blood", "source_row_id": "pa6"}, {"source_test_name": "RDW", "raw_value": "12.5", "source_unit": "%", "specimen_type": "whole blood", "source_row_id": "pa7"}, {"source_test_name": "ALP", "raw_value": "55", "source_unit": "U/L", "specimen_type": "serum", "source_row_id": "pa8"}, {"source_test_name": "WBC", "raw_value": "5.5", "source_unit": "K/uL", "specimen_type": "whole blood", "source_row_id": "pa9"}]}'
```
