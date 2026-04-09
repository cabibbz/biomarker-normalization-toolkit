# Evidence Posture

This document explains the evidence level behind the toolkit's public features.

## Reproducible In This Repository

These behaviors are directly testable from the public repository:

- deterministic normalization behavior
- alias and specimen disambiguation
- unit conversion and reference-range normalization
- CSV, FHIR, HL7, C-CDA, and Excel ingest behavior
- REST API contract and packaged CLI behavior
- PhenoAge computation as implemented in code
- derived metric formulas as implemented in code

Those claims are backed by tracked fixtures, automated tests, and distribution smoke checks.

## Curated Or Opinionated Layers

Some features are intentionally more opinionated than the core normalization engine:

- optimal-range evaluation in `src/biomarker_normalization_toolkit/optimal_ranges.py`
- longevity-oriented summaries derived from those ranges

Those ranges are curated from mixed sources and maintainer judgment. They should be treated as an experimental decision-support layer, not as a clinical standard.

If you use that layer in production or research, review the ranges explicitly and override them where needed for your context.

## External Literature

The repository references external literature for some formulas and concepts:

- PhenoAge follows the Levine 2018 formulation implemented in `src/biomarker_normalization_toolkit/phenoage.py`
- derived metrics are standard deterministic formulas implemented in `src/biomarker_normalization_toolkit/derived.py`
- some optimal-range notes reference public clinical or longevity discussions, but the repository does not claim those notes are exhaustive or consensus guidance

## Development-Only Validation Context

During development, the toolkit was also exercised against larger local corpora and public/demo sources that are not part of the package distribution.

Those inputs are useful maintainer context, but they are not part of the reproducible contract of the open-source repository.

See [external-datasets.md](external-datasets.md) and [validation.md](validation.md) for the distinction between public-repo guarantees and local maintainer validation.
