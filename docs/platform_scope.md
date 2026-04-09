# Platform Scope

## Project Boundary

The project is an open-source biomarker normalization toolkit.

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

## Project Shapes In Scope

- CLI
- Docker image
- embeddable SDK
- self-hosted API service built from the toolkit

## Users In Scope

- digital health startups
- longevity platforms
- remote care companies
- biomarker-driven applications
- teams with messy lab data that do not want to build a normalization layer from scratch

## Outputs In Scope

- normalized CSV
- machine-readable JSON
- optional FHIR Observation JSON
