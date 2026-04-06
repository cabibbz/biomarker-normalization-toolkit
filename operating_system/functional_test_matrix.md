# Functional Test Matrix

This matrix defines when the biomarker normalization toolkit is good enough to ship.

## Release Gate

A release passes only if:

- the verification scope was derived from the actual implementation context
- every critical test passes
- no safety test fails
- unknowns are surfaced explicitly instead of guessed

## Context Rule

Do not treat this file as a static substitute for real verification planning.

Use [verification_gate.md](/C:/Users/me/Desktop/longevb2b/operating_system/verification_gate.md) first to decide which verification modes apply to the current implementation.

This file is only a safety baseline. The actual tests for a slice must be created from the slice's own context.

## Critical Product Behaviors

### 1. Input handling

The toolkit must:

- accept at least one structured source format in `v1`
- read a local test name, unit, result value, specimen type, and reference range when present
- preserve the raw source fields exactly
- reject malformed rows with explicit errors

Critical tests:

- install and run locally in under 10 minutes
- process a valid sample file without manual edits
- fail cleanly on malformed headers or missing required fields

### 2. Normalization correctness

The toolkit must:

- map known aliases to a canonical biomarker name
- assign the correct LOINC when confidence is sufficient
- convert supported units deterministically
- normalize reference ranges without losing provenance

Critical tests:

- alias set maps to the same canonical biomarker
- unit conversion outputs exact expected values for supported conversions
- ambiguous aliases are flagged for review, not silently guessed
- unmapped tests are returned as unmapped with reason codes

### 3. Safety and traceability

The toolkit must:

- never invent a biomarker mapping
- emit confidence or match status for every row
- preserve source-to-output lineage
- distinguish between raw value, normalized value, and converted value

Critical tests:

- every output row contains source identifiers or row references
- every mapped row includes a rule or lookup basis
- every unmapped row includes a reason
- every ambiguous row includes a review-needed status

### 4. Canonical output

The toolkit must:

- emit normalized CSV
- emit machine-readable JSON
- optionally emit FHIR `Observation` JSON for supported fields

Critical tests:

- output schema is stable across repeated runs
- same input produces byte-for-byte equivalent normalized output except timestamps
- FHIR output validates structurally against the expected field layout

### 5. Performance

The toolkit must:

- complete a small implementation dataset quickly on a normal laptop
- avoid network dependency for core mapping logic

Critical tests:

- process `10,000` rows in under `60` seconds on a normal laptop baseline
- run fully offline once installed

### 6. Packaging

The toolkit must:

- install from a documented local path
- run from one command
- include sample inputs and expected outputs

Critical tests:

- fresh install on a clean machine using only the docs
- sample command completes successfully
- expected-output fixture matches actual output

## Gold Dataset Standard

Before launch, maintain a gold dataset with:

- common biomarkers
- common aliases
- common unit variants
- known edge cases
- intentionally ambiguous cases
- intentionally unmapped cases

Minimum rule:

- do not claim broad coverage without a gold dataset proving it.

## Ship Blockers

Do not ship if any of these happen:

- the tool guesses on ambiguous aliases
- provenance is missing
- unmapped rows disappear silently
- unit conversion changes values incorrectly
- output schema changes without notice
- the implementation skipped a relevant verification mode for the surfaces it changed
