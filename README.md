# Biomarker Normalization Toolkit

[![CI](https://github.com/cabibbz/biomarker-normalization-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/cabibbz/biomarker-normalization-toolkit/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

Open-source toolkit for normalizing messy lab data into canonical, machine-readable output.

It takes test names like `GLU`, `Fasting Glucose`, and `Glucose [Mass/volume] in Blood` and maps them to a single canonical biomarker with a standard LOINC code, normalized unit, and preserved provenance.

## Why It Exists

Lab data is inconsistent across vendors, EHR exports, FHIR feeds, HL7 messages, spreadsheets, and ad hoc CSVs. This toolkit gives application teams a deterministic normalization layer they can run inside their own environment.

## What It Does

- Deterministic alias-based biomarker mapping
- Unit normalization across common SI and conventional units
- Reference-range normalization
- LOINC assignment where supported
- Full provenance preservation
- Safe ambiguity handling with `review_needed` and `unmapped`
- Optional fuzzy matching for typo-tolerant lookup
- Structured-code fallback for embedded LOINC values
- FHIR R4 Observation bundle export
- Coverage analysis for onboarding new data sources
- Derived metrics, PhenoAge, longitudinal comparison, and an optional experimental optimal-range layer

## What It Does Not Do

- Diagnosis
- Treatment recommendations
- Patient-specific clinical decision support
- Hosted PHI workflows

## Coverage

- 297 biomarkers across metabolic, lipid, renal, liver, thyroid, CBC, coagulation, electrolytes, vitamins, minerals, cardiac, urinalysis, body fluid, drug monitoring, immunology, neuro/CSF, blood gas, and specialty panels
- Multi-format ingest: CSV, FHIR R4 JSON, HL7 v2.x, C-CDA XML, and Excel
- Output formats: JSON, CSV, Markdown summary, optional FHIR bundle

The repo currently validates a 600+ test suite locally and in CI across Windows, macOS, and Linux.

## Quick Start

```bash
pip install biomarker-normalization-toolkit
bnt status
bnt demo --output-dir demo_out
```

### Python API

```python
from biomarker_normalization_toolkit import normalize, normalize_file

result = normalize([
    {
        "source_test_name": "Glucose",
        "raw_value": "100",
        "source_unit": "mg/dL",
        "specimen_type": "serum",
        "source_row_id": "1",
        "source_reference_range": "70-99 mg/dL",
    }
])

for record in result.records:
    print(record.canonical_biomarker_name, record.normalized_value, record.normalized_unit)

result = normalize_file("fixtures/input/v0_sample.csv", fuzzy_threshold=0.85)
```

### CLI

```bash
# Normalize a single file
bnt normalize --input fixtures/input/v0_sample.csv --output-dir out

# Emit FHIR
bnt normalize --input fixtures/input/v0_sample.csv --output-dir out --emit-fhir

# Analyze coverage gaps
bnt analyze --input fixtures/input/v0_sample.csv

# Batch-process a directory of supported files
bnt batch --input-dir /data/labs --output-dir /data/normalized --emit-fhir

# Load custom aliases
bnt normalize --input fixtures/input/v0_sample.csv --output-dir out --aliases examples/custom_aliases/custom_aliases.json

# Explore the built-in catalog
bnt catalog
bnt catalog --format json
```

### REST API

```bash
pip install biomarker-normalization-toolkit[rest]
bnt serve --port 8000
```

The built-in API is full-access. There is no feature gating in the open-source distribution.

```bash
# Health
curl http://localhost:8000/health

# Catalog
curl http://localhost:8000/catalog
curl "http://localhost:8000/catalog?search=glucose"

# Lookup
curl "http://localhost:8000/lookup?test_name=GLU&specimen=serum"

# Normalize JSON rows
curl -X POST http://localhost:8000/normalize \
  -H "Content-Type: application/json" \
  -d '{"rows": [{"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "1", "source_reference_range": "70-99 mg/dL"}]}'

# Normalize with FHIR output
curl -X POST "http://localhost:8000/normalize?emit_fhir=true" \
  -H "Content-Type: application/json" \
  -d '{"rows": [{"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "1"}]}'

# Upload a source file
curl -X POST http://localhost:8000/normalize/upload -F "file=@fixtures/input/v0_sample.csv"

# Analyze coverage from JSON rows
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"rows": [{"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "1"}]}'

# Compute PhenoAge
curl -X POST http://localhost:8000/phenoage \
  -H "Content-Type: application/json" \
  -d '{"chronological_age": 45, "rows": [{"source_test_name": "Albumin", "raw_value": "4.5", "source_unit": "g/dL", "specimen_type": "serum", "source_row_id": "pa1"}, {"source_test_name": "Creatinine", "raw_value": "0.9", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "pa2"}, {"source_test_name": "Glucose", "raw_value": "90", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "pa3"}, {"source_test_name": "hs-CRP", "raw_value": "0.5", "source_unit": "mg/L", "specimen_type": "serum", "source_row_id": "pa4"}, {"source_test_name": "Lymphocytes Percent", "raw_value": "30", "source_unit": "%", "specimen_type": "whole blood", "source_row_id": "pa5"}, {"source_test_name": "MCV", "raw_value": "88", "source_unit": "fL", "specimen_type": "whole blood", "source_row_id": "pa6"}, {"source_test_name": "RDW", "raw_value": "12.5", "source_unit": "%", "specimen_type": "whole blood", "source_row_id": "pa7"}, {"source_test_name": "ALP", "raw_value": "55", "source_unit": "U/L", "specimen_type": "serum", "source_row_id": "pa8"}, {"source_test_name": "WBC", "raw_value": "5.5", "source_unit": "K/uL", "specimen_type": "whole blood", "source_row_id": "pa9"}]}'

# Evaluate optimal ranges
curl -X POST http://localhost:8000/optimal-ranges \
  -H "Content-Type: application/json" \
  -d '{"rows": [{"source_test_name": "Glucose", "raw_value": "88", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "1"}]}'

# Compare two result sets
curl -X POST http://localhost:8000/compare \
  -H "Content-Type: application/json" \
  -d '{"before": {"rows": [{"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "b1"}]}, "after": {"rows": [{"source_test_name": "Glucose", "raw_value": "92", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "a1"}]}, "days_between": 90}'
```

All endpoints are also available under `/v1/`.

## Input Schema

The core row format is:

```json
{
  "source_row_id": "1",
  "source_test_name": "Glucose",
  "raw_value": "100",
  "source_unit": "mg/dL",
  "specimen_type": "serum",
  "source_reference_range": "70-99 mg/dL"
}
```

Optional fields such as `source_lab_name` and `source_panel_name` are preserved when present.

## Output Schema

Each normalized record contains fields including:

- `canonical_biomarker_id`
- `canonical_biomarker_name`
- `loinc`
- `mapping_status`
- `match_confidence`
- `normalized_value`
- `normalized_unit`
- `provenance`

The toolkit never overwrites the original source values.

## Docker

```bash
docker build -t bnt .
docker run --rm -p 8000:8000 bnt
```

## Examples

Runnable examples live under `examples/`:

- `examples/python_sdk/basic_normalize.py`
- `examples/fhir_ingest/normalize_bundle.py`
- `examples/rest_api/curl_examples.md`
- `examples/custom_aliases/use_custom_aliases.py`

## Custom Aliases

When your source system uses vendor-specific naming, create a JSON alias file:

```json
{
  "glucose_serum": ["Blood Sugar Level", "Gluc Fasting", "FBG"],
  "hba1c": ["Glycated Hemoglobin A1C", "A1C Panel"],
  "ldl_cholesterol": ["LDL Direct", "LDL-C Direct"]
}
```

Then pass it with `--aliases`.

## Safety Notes

- This is a normalization and data-quality tool, not a medical device.
- Ambiguous mappings are surfaced explicitly instead of guessed.
- Optimal-range output is curated and opinionated; treat it as experimental until reviewed for your use case.
- Review [DISCLAIMER.md](DISCLAIMER.md) before clinical or research use.
- Review [docs/compliance-guide.md](docs/compliance-guide.md) for deployment guidance in regulated environments.
- Review [docs/evidence.md](docs/evidence.md) and [docs/validation.md](docs/validation.md) before relying on research-oriented outputs.

## Project Docs

- [docs/architecture.md](docs/architecture.md)
- [docs/platform_scope.md](docs/platform_scope.md)
- [docs/compliance-guide.md](docs/compliance-guide.md)
- [docs/evidence.md](docs/evidence.md)
- [docs/external-datasets.md](docs/external-datasets.md)
- [docs/canonical_row_schema.md](docs/canonical_row_schema.md)
- [docs/gold_dataset_plan.md](docs/gold_dataset_plan.md)
- [docs/oss-cutover.md](docs/oss-cutover.md)
- [docs/releasing.md](docs/releasing.md)
- [docs/validation.md](docs/validation.md)
- [docs/roadmap.md](docs/roadmap.md)
- [examples/README.md](examples/README.md)

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md), and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

Good first contributions:

- new aliases for real-world vendor names
- additional unit synonyms
- new biomarker mappings with tests
- parser edge cases across FHIR, HL7, C-CDA, and Excel
- documentation improvements and integration examples

For support routing and vulnerability reporting, see [SUPPORT.md](SUPPORT.md) and [SECURITY.md](SECURITY.md).

## License

Apache-2.0. See [LICENSE](LICENSE).

## Citation

If you use this project in research or developer infrastructure, see [CITATION.cff](CITATION.cff).
