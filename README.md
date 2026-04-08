# Biomarker Normalization Toolkit

Customer-run toolkit that normalizes messy lab data from any vendor into clean, canonical, machine-readable output.

Takes test names like `"GLU"`, `"Fasting Glucose"`, `"Glucose [Mass/volume] in Blood"` — all different names for the same test from different labs — and maps them to a single canonical biomarker with a standard LOINC code and normalized unit.

## What It Does

- Maps vendor-specific test names to canonical biomarkers via deterministic alias matching
- Converts units (mmol/L to mg/dL, umol/L to mg/dL, g/L to g/dL, etc.)
- Normalizes reference ranges
- Assigns LOINC codes
- Preserves full provenance (original values always kept alongside normalized output)
- Flags ambiguous or unknown tests as `review_needed` / `unmapped` — never guesses
- Optional fuzzy matching for typos/misspellings (with medical safety guards)
- Physiological plausibility checks (warns on likely data entry errors)
- LOINC code lookup (resolves test names that are LOINC codes)
- Smart unit redirect (e.g., "Neutrophils" with % unit auto-redirects to percentage biomarker)

## What It Does NOT Do

- No diagnosis, treatment advice, or clinical recommendations
- No hosted PHI — runs entirely in the customer's environment
- No consumer-facing product

## Coverage

235 biomarkers across preventive health, inpatient, longevity, and specialty panels:

| Panel | Biomarkers |
|-------|-----------|
| Metabolic | Glucose, HbA1c, BUN, Calcium, Ionized Calcium, Phosphate, Uric Acid, Insulin, Homocysteine, Ammonia |
| Lipid | Total Cholesterol, LDL, HDL, Triglycerides, ApoB, Lp(a), Non-HDL Cholesterol, Chol/HDL Ratio |
| Renal | Creatinine (serum + urine), eGFR, BUN/Creatinine Ratio, Osmolality, Urine Albumin, ACR |
| Liver | ALT, AST, ALP, GGT, Total/Direct/Indirect Bilirubin, Albumin, Prealbumin, A/G Ratio, LDH, Globulin, Amylase, Lipase |
| Thyroid | TSH, Free T4, T3 Total, T4 Total |
| Hormones | DHEA-S, Estradiol, LH, FSH, Testosterone (total/free/bioavailable), SHBG, Cortisol, PTH |
| Inflammation | hs-CRP, CRP, ESR, Procalcitonin |
| CBC | WBC, RBC, Hemoglobin, Hematocrit, Platelets, MCV, MCH, MCHC, RDW, RDW-SD, MPV, PDW, Reticulocytes |
| WBC Differential | Neutrophils, Lymphocytes, Monocytes, Eosinophils, Basophils, Atypical Lymphocytes, Metamyelocytes, Myelocytes, Promyelocytes, Other Cells, Blasts (absolute + percentage where applicable) |
| ICU Hematology | Bands, Immature Granulocytes, Nucleated RBC |
| Coagulation | PT, INR, PTT, PTT Ratio, Fibrinogen, D-Dimer |
| Cardiac | Troponin T, Troponin I, BNP, NT-proBNP, CK, CK-MB, CK-MB Index, Myoglobin |
| Electrolytes | Sodium, Potassium, Chloride, Bicarbonate |
| Vitamins | D (25-OH), B12, Folate |
| Minerals | Iron, Ferritin, TIBC, Transferrin, Transferrin Saturation, Magnesium |
| Immunology | IgA, IgG, IgM, Complement C3, C4, Haptoglobin |
| Blood Gas | pH, pO2, pCO2, Base Excess, Base Deficit, Oxygen Saturation, Oxyhemoglobin, Carboxyhemoglobin, Methemoglobin, Oxygen Content, Alveolar-Arterial Gradient, Lactate |
| Drug Monitoring / Toxicology | Vancomycin, Vancomycin Trough, Digoxin, Tacrolimus, Salicylates, Ethanol, Phenytoin, Acetaminophen |
| Urinalysis | Specific Gravity, pH, Protein, Ketones, Bilirubin, Blood, Nitrite, Leukocyte Esterase, Urobilinogen, RBC, WBC, Epithelial Cells, Hyaline Casts, Glucose/Protein/Ketones/Bilirubin Presence |
| Cancer Screening | PSA |
| Urine Chemistry | Sodium, Potassium, Chloride, BUN, Albumin, Total Protein, 24h Total Protein, Osmolality, Creatinine |

**95.8% combined mapping rate** tested against 124K real-world lab events from MIMIC-IV (94.8%) and Synthea (99.0%). 100% on simulated Quest/LabCorp longevity panel data.

## Input Formats

- **CSV** with columns: `source_row_id`, `source_test_name`, `raw_value`, `source_unit`, `specimen_type`, `source_reference_range`
- **FHIR R4 JSON** — Bundle or individual Observation resources (auto-detected)
- **HL7 v2.x** — ORU^R01 messages with OBX segments (auto-detected by `.hl7` extension)
- **C-CDA XML** — Clinical Document Architecture lab results sections (auto-detected by `.xml` extension)
- **Excel** — `.xlsx` files with flexible header matching (auto-detected)

## Output Formats

- Normalized **JSON** with full provenance
- Normalized **CSV**
- Optional **FHIR R4 Observation Bundle**
- Human-readable **Markdown summary**

## Quick Start

```bash
pip install biomarker-normalization-toolkit
bnt status       # Shows 235 biomarkers, supported formats
bnt catalog      # Lists all biomarkers with LOINC codes
bnt demo --output-dir demo_out  # Run on bundled sample data
```

### Python API

```python
from biomarker_normalization_toolkit import normalize, normalize_file

# Normalize a list of rows
result = normalize([
    {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
     "specimen_type": "serum", "source_row_id": "1", "source_reference_range": "70-99 mg/dL"},
])
for record in result.records:
    print(record.canonical_biomarker_name, record.normalized_value, record.normalized_unit)

# Normalize a file (CSV, FHIR, HL7, C-CDA, or Excel — auto-detected)
result = normalize_file("labs.csv")

# Enable fuzzy matching for typo tolerance
result = normalize_file("labs.csv", fuzzy_threshold=0.85)
```

## Usage

```bash
# Normalize a CSV file
bnt normalize --input labs.csv --output-dir out

# Normalize a FHIR Bundle
bnt normalize --input fhir_bundle.json --output-dir out

# Normalize an HL7 v2.x ORU message
bnt normalize --input lab_results.hl7 --output-dir out

# Normalize a C-CDA XML document
bnt normalize --input lab_results.xml --output-dir out

# Normalize an Excel spreadsheet
bnt normalize --input lab_results.xlsx --output-dir out

# Batch-process a directory of mixed-format files
bnt batch --input-dir /data/labs --output-dir /data/normalized --emit-fhir

# Use custom aliases for vendor-specific test names
bnt normalize --input labs.csv --output-dir out --aliases custom_aliases.json

# Normalize with FHIR output
bnt normalize --input labs.csv --output-dir out --emit-fhir

# Enable fuzzy matching (recommended: 0.85 threshold)
bnt normalize --input labs.csv --output-dir out --fuzzy-threshold 0.85

# Show all supported biomarkers
bnt catalog
bnt catalog --format json

# Analyze coverage gaps in a file
bnt analyze --input labs.csv

# Run bundled demo
bnt demo --output-dir demo_out
```

## REST API

```bash
pip install biomarker-normalization-toolkit[rest]
bnt serve --port 8000
```

### Authentication and Rate Limiting

All endpoints accept an optional `X-API-Key` header. Without a key, requests run in free tier (limited biomarkers, no PhenoAge/optimal ranges). Pro tier keys unlock all features. Invalid keys receive a `401` response.

Rate limiting is enforced per API key (default: 60 requests/minute). Exceeding the limit returns `429` with a `Retry-After` header. Every response includes `X-RateLimit-Remaining` and `X-Request-Duration-Ms` headers.

### Endpoints

```bash
# Health check
curl localhost:8000/health

# Prometheus-compatible metrics (JSON by default, text/plain for Prometheus)
curl localhost:8000/metrics
curl -H "Accept: text/plain" localhost:8000/metrics

# List all biomarkers
curl localhost:8000/catalog
curl "localhost:8000/catalog?search=glucose"

# Look up a test name to find matching biomarkers
curl "localhost:8000/lookup?test_name=GLU&specimen=serum"

# Normalize JSON rows
curl -X POST localhost:8000/normalize \
  -H "Content-Type: application/json" \
  -d '{"rows": [{"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "1", "source_reference_range": "70-99 mg/dL"}]}'

# Normalize with FHIR output
curl -X POST "localhost:8000/normalize?emit_fhir=true" \
  -H "Content-Type: application/json" \
  -d '{"rows": [...]}'

# Upload a file (CSV, FHIR, HL7, C-CDA, Excel)
curl -X POST localhost:8000/normalize/upload -F "file=@labs.csv"

# Coverage analysis from JSON rows
curl -X POST localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"rows": [{"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "1"}]}'

# Coverage analysis from file upload
curl -X POST localhost:8000/analyze/upload -F "file=@labs.csv"

# Compute PhenoAge biological age (Pro tier, requires 9 biomarkers)
curl -X POST localhost:8000/phenoage \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_PRO_KEY" \
  -d '{"chronological_age": 45, "rows": [{"source_test_name": "Albumin", "raw_value": "4.2", "source_unit": "g/dL", "specimen_type": "serum", "source_row_id": "1"}, ...]}'

# Evaluate biomarker values against longevity-optimal ranges (Pro tier)
curl -X POST localhost:8000/optimal-ranges \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_PRO_KEY" \
  -d '{"rows": [{"source_test_name": "Glucose", "raw_value": "88", "source_unit": "mg/dL", "specimen_type": "serum", "source_row_id": "1"}]}'

# Longitudinal before/after comparison (Pro tier)
curl -X POST localhost:8000/compare \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_PRO_KEY" \
  -d '{"before": {"rows": [...]}, "after": {"rows": [...]}, "days_between": 90}'

# Interactive API docs
open http://localhost:8000/docs
```

All endpoints are also available under the `/v1/` prefix (e.g., `/v1/normalize`, `/v1/phenoage`).

## Docker

```bash
docker build -t bnt .

# Run API server
docker run -p 8000:8000 bnt serve --host 0.0.0.0

# Normalize a local file
docker run -v /path/to/data:/data bnt normalize --input /data/labs.csv --output-dir /data/out

# Batch process a directory
docker run -v /path/to/data:/data bnt batch --input-dir /data/labs --output-dir /data/normalized --emit-fhir
```

## Output Schema

Each normalized record contains:

| Field | Description |
|-------|-------------|
| `source_test_name` | Original test name from vendor |
| `canonical_biomarker_id` | Standardized ID (e.g., `glucose_serum`) |
| `canonical_biomarker_name` | Human-readable name (e.g., `Glucose`) |
| `loinc` | LOINC code |
| `mapping_status` | `mapped`, `review_needed`, or `unmapped` |
| `match_confidence` | `high` (exact), `medium` (fuzzy), `low`, or `none` |
| `status_reason` | Why the row was mapped/flagged |
| `raw_value` | Original value |
| `normalized_value` | Converted value in canonical unit |
| `normalized_unit` | Canonical unit |
| `provenance` | Full source traceability |

## Custom Aliases

When your lab uses test names not in the built-in catalog, create a JSON alias file:

```json
{
  "glucose_serum": ["Blood Sugar Level", "Gluc Fasting", "FBG"],
  "hba1c": ["Glycated Hemoglobin A1C", "A1C Panel"],
  "ldl_cholesterol": ["LDL Direct", "LDL-C Direct"]
}
```

Then pass it with `--aliases`:

```bash
bnt normalize --input labs.csv --output-dir out --aliases my_aliases.json
```

Use `bnt analyze --input labs.csv` to find which test names are unmapped and need aliases.

## Performance

- **37,000 rows/sec** on standard hardware (without fuzzy matching)
- **33,000 rows/sec** with fuzzy matching enabled
- Tested on 124K real-world lab events (MIMIC-IV + Synthea)
- Zero false-positive plausibility warnings across 124K rows
