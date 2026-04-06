# Release Readiness

Date: 2026-04-06

## Decision

The current state is:

- **ready for constrained alpha use**
- **not ready for broad external release**

## Ready Now

- deterministic normalization for the initial biomarker set
- explicit mapped / review-needed / unmapped behavior
- JSON and CSV output
- optional FHIR Observation bundle export
- human-readable summary report
- working `bnt` console command
- editable install verification
- built wheel verification
- installed wheel demo verification
- external FHIR bundle validation for current fixtures
- 28 biomarkers across metabolic, lipid, renal, liver, thyroid, inflammation, CBC, vitamin, and mineral panels
- unit conversions for all major SI/conventional unit pairs
- Docker packaging

## Not Ready Yet

- production packaging/release pipeline (CI/CD, versioned releases)
- real-world vendor catalog breadth (more vendor-specific alias coverage)

## Release Bar

### Alpha

Allowed:

- internal use
- design-partner demos
- constrained pilot with clear scope limits

Requirements:

- current verification workflow stays enforced
- customers understand biomarker coverage is narrow
- ambiguous and unmapped output remains visible

### Broader external beta

Not yet met.

Minimum next requirements:

- expanded biomarker and alias coverage
- expanded gold dataset and edge-case set
- explicit packaging/release process
- broader FHIR validation coverage across expanded fixtures

## Current Recommendation

Treat the toolkit as an **alpha-quality partner pilot artifact** with strong process controls, not a broad market-ready release.
