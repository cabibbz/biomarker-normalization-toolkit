# REST API Examples

Start the server:

```bash
pip install biomarker-normalization-toolkit[rest]
bnt serve --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

Normalize rows:

```bash
curl -X POST http://localhost:8000/normalize \
  -H "Content-Type: application/json" \
  -d '{"rows": [{"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "1"}]}'
```

Upload a tracked CSV fixture:

```bash
curl -X POST http://localhost:8000/normalize/upload -F "file=@fixtures/input/v0_sample.csv"
```
