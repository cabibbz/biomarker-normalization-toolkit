# Verification Record

Change: core normalization engine and cli flow

Date: 2026-04-06

## Why These Tests

- The slice changed backend normalization logic, file parsing, output generation, and the CLI surface.
- No frontend changed, so browser click-throughs were not relevant.
- The highest-risk issues were incorrect alias mapping, silent ambiguity guessing, incorrect unit conversion, broken output files, and weak malformed-input handling.

## Derived Verification Scope

- backend behavior validation
- cli end-to-end execution
- malformed-input error-path validation
- normalization regression against a gold fixture
- ambiguity and unsupported-unit safety validation

## Commands Run

```text
python .\operating_system\tools\derive_verification_plan.py .\project_memory\entries\core_normalization_change.json
python -m unittest discover -s tests -v
python -m biomarker_normalization_toolkit.cli normalize --input .\fixtures\input\v0_sample.csv --output-dir .\tmp_verify_valid
python -m biomarker_normalization_toolkit.cli normalize --input .\fixtures\input\v0_invalid_missing_headers.csv --output-dir .\tmp_verify_invalid
```

## Flows Exercised

- Parsed the sample CSV into source records and normalized six rows.
- Verified mapped, review-needed, and unmapped outcomes against the expected JSON fixture.
- Verified the CLI writes both JSON and CSV outputs on a valid sample.
- Verified malformed input with missing required headers fails cleanly.
- Verified unsupported units return `review_needed` instead of silently converting or guessing.

## Results

- Derived verification plan matched the changed surfaces: backend, normalization, file handling, and CLI.
- Automated test suite passed: 4 tests, 0 failures.
- Valid CLI flow passed and produced normalized JSON and CSV outputs.
- Invalid CLI flow failed as expected with an explicit missing-column error.
- No relevant verification mode for the slice was skipped.

## Residual Risk

- FHIR export is not implemented yet.
- Packaging beyond editable local installation is not verified yet.
- Dataset coverage is intentionally narrow and still needs expansion for broader biomarker support.
