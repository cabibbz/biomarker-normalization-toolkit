# Changelog

## 0.3.0 (Unreleased)

### Added
- **183 biomarkers** (from 75): longevity panel, hormones, heavy metals, advanced lipids, cytokines, aging markers
- **PhenoAge biological age** (Levine 2018) from 9 standard biomarkers
- **Optimal longevity ranges** for 68 biomarkers (Attia/Function Health evidence-based)
- **12 derived metrics**: HOMA-IR, TG/HDL, ApoB/ApoA1, NLR, AIP, De Ritis, FIB-4, TyG, UIBC
- **Longitudinal tracking**: before/after comparison with deltas, trends, velocity
- **Fuzzy matching** with medical safety blocklist (opt-in `--fuzzy-threshold`)
- **Smart sibling unit redirect**: "Neutrophils" with "%" auto-routes to neutrophils_pct
- **Plausibility checks** calibrated on 4.65M real rows (zero false positives)
- **API licensing**: free/pro/enterprise tiers with biomarker and feature gating
- **10 API endpoints** with /v1/ versioning, rate limiting, Prometheus /metrics
- **LOINC code lookup**: test names that are LOINC codes resolve directly
- **BSL 1.1 license**, medical disclaimer, release automation
- **Docker**: multi-stage build, non-root user, healthcheck
- JSON output includes `bnt_version`, `generated_at`, `schema_version: 0.2.0`

### Fixed
- PhenoAge glucose formula (was /18, now ln(glucose) per Levine 2018)
- Upload endpoint bypassed licensing tier gate
- API key timing attack (hmac.compare_digest)
- HL7 specimen leak, UCUM round-trip, European decimals, FHIR effectiveDateTime
- Sibling redirect now marked (confidence=medium, reason=sibling_unit_redirect)
- Content-length crash, CORS wildcard default, rate limiter memory

### Validated
- 4.65M rows across 20+ datasets (NHANES 11 cycles, MIMIC-IV, eICU, Synthea, HAPI FHIR, Cerner)
- Lab-only mapping rate: 99.9%
- Quality audit: 10/10, API rating: 9.7/10

## 0.2.1

### Critical Bug Fixes
- **Free T4 conversion was 6x too low** — normal thyroid values appeared as severe hypothyroidism. Factor corrected from 0.0129 to 1/12.87.
- **Folate conversion was 2x too low** — normal folate appeared deficient. Factor corrected from 0.2266 to 1/2.266.
- **All 5 WBC differential LOINCs were percentage codes** but unit is K/uL — FHIR output had semantically wrong LOINC/unit pairing. Corrected to absolute count LOINCs.
- **ALT LOINC was body fluid code** (1744-1) instead of serum/plasma (1742-6).
- **`#/uL` mapped to `K/uL`** with no division — 1000x magnitude error. Removed.
- **NaN/Infinity in raw values crashed the normalizer**. Added `is_finite()` check.

### Serious Bug Fixes
- **C-CDA parser ignored namespaced documents** — zero results from real clinical systems. Added HL7v3 namespace support.
- **C-CDA Element truthiness bug** — `find("x") or find("ns:x")` silently failed because empty XML Elements are falsy in Python.
- **HL7 parser never extracted specimen type** — Glucose/Creatinine/pH always flagged as ambiguous. Now parses OBR-15 and SPM-4.
- **HL7 batch mode leaked panel names** across message boundaries. Now resets on MSH.
- **Excel workbook resource leak** on parse errors. Added try/finally.
- **FHIR profile URL was non-standard**. Corrected to StructureDefinition/Bundle.
- **Custom alias loader accepted malformed input** — could corrupt the alias index. Added type validation.
- **`--aliases` flag silently continued** when file was missing. Now exits with error.
- **Reference range regex rejected numeric-prefix units** like `10^9/L`. Fixed.
- **MCHC accepted `%` as identity** — medically wrong. Removed.

### Precision Improvements
- Magnesium: 2.4 → 2.431 (MW 24.305, was -1.25% error)
- Vitamin D: 0.4 → 1/2.496 (MW 400.6, fixed clinical cutoff at 30 ng/mL)

### New Features
- `bnt batch` command for multi-file processing
- `--aliases` flag for custom alias JSON files
- GitHub Actions CI (3 OS x 3 Python versions)
- Blood pH, Fibrinogen, eAG biomarkers (74 total)
- HL7 specimen extraction from OBR-15/SPM-4
- `"seconds"` unit synonym for PT/PTT

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
