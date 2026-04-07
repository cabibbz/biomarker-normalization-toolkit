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

## What It Does NOT Do

- No diagnosis, treatment advice, or clinical recommendations
- No hosted PHI — runs entirely in the customer's environment
- No consumer-facing product

## Coverage

71 biomarkers across major preventive health, inpatient, and urinalysis panels:

| Panel | Biomarkers |
|-------|-----------|
| Metabolic | Glucose, HbA1c, BUN, Calcium, Ionized Calcium, Phosphate, Uric Acid |
| Lipid | Total Cholesterol, LDL, HDL, Triglycerides |
| Renal | Creatinine (serum + urine), eGFR |
| Liver | ALT, AST, ALP, Bilirubin, Albumin, LDH, Globulin |
| Thyroid | TSH, Free T4 |
| Inflammation | hs-CRP |
| CBC | WBC, RBC, Hemoglobin, Hematocrit, Platelets, MCV, MCH, MCHC, RDW, RDW-SD, MPV, PDW |
| WBC Differential | Neutrophils, Lymphocytes, Monocytes, Eosinophils, Basophils |
| Coagulation | PT, INR, PTT |
| Electrolytes | Sodium, Potassium, Chloride, Bicarbonate |
| Vitamins | D, B12, Folate |
| Minerals | Iron, Ferritin, Magnesium |
| Cardiac | Troponin T, CK, CK-MB |
| Blood Gas | pO2, pCO2, Base Excess, Oxygen Saturation |
| Urinalysis | Specific Gravity, pH, Protein, Ketones, Bilirubin |
| Other | Anion Gap, Lactate, Lipase, Total Protein |

84.7% combined mapping rate tested against 128K real-world lab events from MIMIC-IV and Synthea.

## Input Formats

- **CSV** with columns: `source_row_id`, `source_test_name`, `raw_value`, `source_unit`, `specimen_type`, `source_reference_range`
- **FHIR R4 JSON** — Bundle or individual Observation resources (auto-detected)
- **HL7 v2.x** — ORU^R01 messages with OBX segments (auto-detected by `.hl7` extension)
- **C-CDA XML** — Clinical Document Architecture lab results sections (auto-detected by `.xml` extension)

## Output Formats

- Normalized **JSON** with full provenance
- Normalized **CSV**
- Optional **FHIR R4 Observation Bundle**
- Human-readable **Markdown summary**

## Quick Start

```bash
pip install -e .
bnt status
bnt catalog
bnt demo --output-dir demo_out
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

# Normalize with FHIR output
bnt normalize --input labs.csv --output-dir out --emit-fhir

# Show all supported biomarkers
bnt catalog
bnt catalog --format json

# Analyze coverage gaps in a file
bnt analyze --input labs.csv

# Run bundled demo
bnt demo --output-dir demo_out
```

## Docker

```bash
docker build -t bnt .
docker run -v /path/to/data:/data bnt normalize --input /data/labs.csv --output-dir /data/out
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
| `status_reason` | Why the row was mapped/flagged |
| `raw_value` | Original value |
| `normalized_value` | Converted value in canonical unit |
| `normalized_unit` | Canonical unit |
| `provenance` | Full source traceability |
