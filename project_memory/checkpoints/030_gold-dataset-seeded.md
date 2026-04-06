# 30% Checkpoint: gold dataset seeded

## Summary

Created the first gold dataset plan and seeded the initial fixture set covering mapped, ambiguous, and unmapped biomarker rows plus a malformed-input case.

## Completed

- Locked the initial gold dataset strategy
- Added a sample v0 input CSV fixture
- Added a malformed header fixture for failure-path validation
- Added a golden expected JSON output fixture

## Decisions Locked

- The first dataset covers glucose, urine glucose, hemoglobin A1c, and total cholesterol
- The first fixture set must prove mapped, review-needed, and unmapped behavior
- Golden expected outputs are part of the verification baseline

## Verification Evidence

- Fixture planning documented in docs/gold_dataset_plan.md
- Fixture files added under fixtures/input and fixtures/expected

## Files Touched

- docs/gold_dataset_plan.md
- fixtures/input/v0_sample.csv
- fixtures/input/v0_invalid_missing_headers.csv
- fixtures/expected/v0_sample_expected.json

## Open Questions

- Which additional biomarkers should be added to the second fixture wave
- How broad unit-conversion coverage should be before v0 release

## Next Steps

- Implement the deterministic alias mapping registry
- Implement the first conversion registry

## Resume From

Use the seeded fixtures as the gold baseline before adding more biomarkers.
