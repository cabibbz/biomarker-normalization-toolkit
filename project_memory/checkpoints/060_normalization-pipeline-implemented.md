# 60% Checkpoint: normalization pipeline implemented

## Summary

Implemented the core normalization pipeline that parses CSV rows into source records, resolves deterministic mappings, applies unit conversion, normalizes reference ranges, and produces per-row statuses with provenance.

## Completed

- Added source-record construction from raw csv rows
- Added row-level normalization logic
- Added mapped, review-needed, and unmapped status handling
- Added normalization summaries

## Decisions Locked

- Unknown aliases return unmapped
- Ambiguous aliases without enough context return review_needed
- Every row carries provenance through to the final normalized output

## Verification Evidence

- Normalization engine implemented in src/biomarker_normalization_toolkit/normalizer.py
- Fixture regression test compares the full JSON output against the gold file

## Files Touched

- src/biomarker_normalization_toolkit/normalizer.py
- src/biomarker_normalization_toolkit/io_utils.py
- tests/test_normalization.py

## Open Questions

- Whether to add richer status-reason taxonomy before v1
- Whether unsupported range text should preserve a separate parse-failure note later

## Next Steps

- Add stable output writing and cli execution flow
- Run the context-derived verification plan against the implemented pipeline

## Resume From

The next step is to validate the engine through the real CLI and output artifacts.
