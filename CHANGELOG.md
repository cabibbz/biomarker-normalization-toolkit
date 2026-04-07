# Changelog

## 0.2.0

### Biomarker Coverage
- Expanded from 9 to 71 biomarkers across 15 panels
- Metabolic, lipid, renal, liver, thyroid, inflammation, CBC, WBC differential, coagulation, electrolytes, vitamins, minerals, cardiac, blood gas, urinalysis
- 84.8% mapping rate validated against 128K real-world lab events (MIMIC-IV + Synthea)

### Input Formats
- **CSV** — standard tabular input
- **FHIR R4 JSON** — Bundle or individual Observation resources
- **HL7 v2.x** — ORU^R01 messages with OBX segment extraction and SN (structured numeric) parsing
- **C-CDA XML** — Clinical Document Architecture lab results sections
- **Excel** — `.xlsx` files with flexible header matching
- All formats auto-detected by file extension

### New CLI Commands
- `bnt catalog` — show all supported biomarkers with LOINC codes and units
- `bnt catalog --format json` — machine-readable catalog export
- `bnt analyze --input <file>` — coverage gap report for customer onboarding
- `bnt --version` — version flag

### Bug Fixes
- Fixed reference range parser rejecting malformed ranges like "70-99-120 mg/dL"
- Fixed FHIR fullUrl using invalid UUID format (now RFC 4122 deterministic UUIDs)
- Fixed alias index allowing duplicate entries causing false ambiguity
- Fixed blank-unit reference ranges being silently dropped (urinalysis)
- Added inequality value detection (">100" gets specific reason code)
- Added duplicate source_row_id warning in output
- Corrected LOINC codes for BUN and Iron

### Infrastructure
- Dockerfile for customer-run Docker deployment
- UCUM code mapping for all FHIR unit codes
- 57 automated tests
- External FHIR bundle validation
- Sample data pipeline with converters for MIMIC-IV, Synthea, HAPI FHIR

## 0.1.0

Initial release with 9 biomarkers (glucose, HbA1c, lipid panel, creatinine), CSV input, JSON/CSV/FHIR output, and deterministic alias-based mapping.
