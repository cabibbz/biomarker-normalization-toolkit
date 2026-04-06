# Initial Build Decisions

Date: 2026-04-06

This file captures the informed decisions needed before real implementation begins.

## Decisions Already Locked

1. Start with a customer-run toolkit, not a hosted PHI platform.
2. Start B2B, not DTC.
3. Focus on normalization and canonicalization, not interpretation.
4. Make provenance and ambiguity handling first-class from day one.
5. Build from de-identified samples, compendia, and local test dictionaries whenever possible.

## Decisions To Make Immediately

### 1. Input format for v0

Recommendation:

- start with structured CSV as the first supported format

Reason:

- fastest to implement
- easiest to fixture-test
- easiest to use with de-identified examples

Do not start with:

- PDFs
- native HL7 parsing

until the core normalization engine is stable.

### 2. Canonical row schema

Need:

- raw test name
- canonical biomarker name
- source unit
- normalized unit
- raw value
- normalized value
- specimen type
- source reference range
- normalized reference range
- LOINC
- mapping status
- confidence or review-needed flag
- provenance metadata

Recommendation:

- lock the canonical row schema before implementing mappings

Status:

- locked in [canonical_row_schema.md](/C:/Users/me/Desktop/longevb2b/docs/canonical_row_schema.md)

### 3. Matching strategy for v0

Recommendation:

- deterministic rule-based mapping first
- alias table + specimen/unit constraints
- no fuzzy guessing in v0

Reason:

- lower risk
- easier to verify
- better auditability

### 4. Ambiguity handling

Recommendation:

- ambiguous rows must return `review_needed`
- unmapped rows must return `unmapped`

Never:

- silently guess

### 5. Unit conversion scope

Recommendation:

- start with a small set of supported deterministic conversions for common biomarkers
- explicit conversion registry, not ad hoc formulas spread across the codebase

### 6. Output scope

Recommendation:

- normalized CSV
- JSON
- FHIR Observation export only after canonical schema is stable

Status:

- normalized CSV and JSON are implemented
- optional FHIR Observation bundle export is now in scope for the next verified slice

### 7. Packaging

Recommendation:

- Python package + CLI first
- Docker packaging second

Reason:

- fastest local iteration
- easiest test fixture flow

### 8. Gold dataset

Need before meaningful release:

- common biomarkers
- common aliases
- unit variants
- ambiguous cases
- unmapped cases
- expected outputs

Status:

- first-pass plan locked in [gold_dataset_plan.md](/C:/Users/me/Desktop/longevb2b/docs/gold_dataset_plan.md)

### 9. Verification baseline

Need before each implemented milestone:

- context-derived verification plan
- actual execution evidence
- residual risk note if anything remains unverified

## Recommended Build Order

1. lock canonical schema
2. create gold dataset fixtures
3. implement deterministic mapping registry
4. implement unit conversion registry
5. implement normalization pipeline
6. emit normalized CSV and JSON
7. add FHIR export
8. package CLI
9. package Docker image
