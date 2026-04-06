# 40% Checkpoint: mapping registry implemented

## Summary

Implemented the first deterministic mapping catalog with canonical biomarker definitions, alias normalization, specimen normalization, and alias-to-candidate indexing.

## Completed

- Added biomarker definitions for glucose serum, urine glucose, hemoglobin A1c, and total cholesterol
- Added deterministic alias normalization
- Added specimen normalization
- Built the alias index used by the normalization engine

## Decisions Locked

- v0 mapping is deterministic and rule-based only
- Ambiguity is handled by review_needed, not fuzzy guessing
- Specimen type is allowed to disambiguate aliases

## Verification Evidence

- Mapping registry implemented in src/biomarker_normalization_toolkit/catalog.py
- Fixture and test coverage now target mapped, ambiguous, and unknown alias paths

## Files Touched

- src/biomarker_normalization_toolkit/catalog.py
- src/biomarker_normalization_toolkit/models.py

## Open Questions

- Whether panel context should be allowed to disambiguate future aliases
- Whether alias priorities should become explicit metadata in the registry

## Next Steps

- Implement the unit conversion registry
- Connect the catalog to the normalization pipeline

## Resume From

Extend the mapping catalog only through explicit deterministic rules.
