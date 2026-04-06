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

## Not Ready Yet

- broad biomarker coverage
- large gold dataset coverage
- richer unit conversion coverage
- production packaging/release pipeline
- real-world vendor catalog breadth

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
