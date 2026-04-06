# 20% Checkpoint: canonical schema locked

## Summary

Locked the v0 canonical row schema for the normalization engine, including required input columns, normalized record fields, output envelope, mapping status rules, and provenance requirements.

## Completed

- Defined the required v0 input CSV columns
- Defined the normalized record field list
- Locked mapping status and confidence semantics
- Locked provenance expectations and summary fields

## Decisions Locked

- v0 uses structured CSV as the first input format
- Every normalized record must preserve provenance
- Ambiguous and unsupported rows must never be guessed

## Verification Evidence

- Canonical schema documented in docs/canonical_row_schema.md
- Initial build decisions doc now links to the locked schema

## Files Touched

- docs/canonical_row_schema.md
- docs/initial_build_decisions.md

## Open Questions

- Whether any additional input metadata fields should become required before v1
- Whether FHIR-specific fields should stay out of the core schema until export is added

## Next Steps

- Create the first gold dataset fixtures
- Implement deterministic mapping against the locked schema

## Resume From

Use docs/canonical_row_schema.md as the schema contract for all engine work.
