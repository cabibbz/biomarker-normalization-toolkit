# Platform Scope

Date: 2026-04-06

## Product Boundary

The platform starts as a customer-run biomarker normalization toolkit.

It is responsible for:

- canonical biomarker naming
- alias normalization
- unit conversion
- reference-range normalization
- LOINC assignment where supported
- machine-readable export

It is not responsible for:

- diagnosis
- treatment advice
- patient-specific clinical recommendations
- consumer engagement product behavior
- hosted PHI workflows
- clinic operations
- lab ordering

## Product Shapes In Scope

- CLI
- Docker image
- embeddable SDK
- productized mapping service around the toolkit

## Customers In Scope

- digital health startups
- longevity platforms
- remote care companies
- biomarker-driven applications
- teams with messy lab data but no desire to build a full normalization layer

## Outputs In Scope

- normalized CSV
- machine-readable JSON
- optional FHIR Observation JSON

