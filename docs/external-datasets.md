# External Datasets

The public repository is intentionally small. Large upstream datasets and local conversion scratch space are not part of the tracked source tree or package distribution.

## What Stays Outside The Public Repo

Examples of data that may exist in maintainer-local environments:

- MIMIC-derived local extracts
- NHANES source files
- Synthea bulk exports
- eICU-derived exports
- large FHIR or HL7 sample corpora

Those datasets can be useful for development and regression hunting, but they are not required to build or validate the public repository.

## Why They Are Not Shipped

- size
- license or access constraints
- patient-data handling concerns
- reproducibility boundaries for a normal open-source Python package

## Public Validation Boundary

The repository's supported validation boundary is:

- tracked fixtures under `fixtures/`
- bundled package data under `src/biomarker_normalization_toolkit/data/`
- automated tests and packaging smoke checks

Anything beyond that should be treated as maintainer-local validation context unless it is separately documented and made redistributable.

## If You Add New Datasets

- keep non-redistributable inputs outside the tracked repository
- document the dataset license and access constraints
- extract only the smallest redistributable fixture needed for a public regression test
- avoid making the main test suite depend on local-only data
