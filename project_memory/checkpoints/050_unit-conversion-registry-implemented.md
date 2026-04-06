# 50% Checkpoint: unit conversion registry implemented

## Summary

Implemented the first explicit conversion registry, unit normalization helpers, decimal formatting, and range parsing support for the initial biomarker set.

## Completed

- Added unit normalization
- Added explicit conversion factors for v0 biomarkers
- Added decimal formatting helpers
- Added structured reference range parsing and formatting

## Decisions Locked

- v0 conversion logic lives in an explicit registry
- Unsupported units force review_needed rather than silent fallback
- Reference range normalization follows the same deterministic conversion path as values

## Verification Evidence

- Unit conversion helpers implemented in src/biomarker_normalization_toolkit/units.py
- Unsupported-unit behavior is directly tested

## Files Touched

- src/biomarker_normalization_toolkit/units.py
- tests/test_normalization.py

## Open Questions

- Whether conversion precision should be configurable later
- Which biomarkers need immediate next-wave conversion support

## Next Steps

- Implement the row normalization pipeline
- Wire conversion and mapping into an end-to-end command

## Resume From

Use the explicit conversion registry as the only source of truth for supported unit changes.
