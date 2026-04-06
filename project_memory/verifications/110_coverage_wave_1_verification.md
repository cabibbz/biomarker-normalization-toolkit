# Verification Record

Change: coverage expansion wave 1

Date: 2026-04-06

## Why These Tests

- This slice changed deterministic alias mapping, conversion factors, and specimen filtering for a new biomarker group.
- The highest-risk failures were wrong unit conversions, wrong canonical mappings, and silent acceptance of unsupported specimen contexts.
- The primary verification artifact for this slice was created on the spot for the new fixture and expected outcomes.

## Derived Verification Scope

- backend regression validation
- CLI success-path validation on the new coverage fixture
- slice-specific output verification for new biomarkers
- safety validation for unsupported specimen and unknown alias handling

## Commands Run

```text
python .\operating_system\tools\derive_verification_plan.py .\project_memory\entries\coverage_wave_1_change.json
python -m unittest discover -s tests -v
bnt normalize --input .\fixtures\input\coverage_wave_1.csv --output-dir .\tmp_verify_110
python .\project_memory\verifications\110_coverage_wave_1_verify.py .\tmp_verify_110\normalized_records.json
Get-Content -LiteralPath .\tmp_verify_110\normalized_records.json -TotalCount 120
```

## Flows Exercised

- Ran the public CLI on the new coverage fixture.
- Verified LDL, HDL, triglycerides, and creatinine map correctly.
- Verified mmol/L and umol/L conversions normalize into mg/dL as expected.
- Verified urine creatinine does not map silently and returns `review_needed`.
- Verified an unknown lipid alias still returns `unmapped`.

## Results

- Existing regression suite passed: 7 tests, 0 failures.
- CLI normalization on the coverage-wave fixture succeeded.
- The dedicated slice-specific verifier passed.
- Direct output inspection confirmed the new rows carry the expected canonical ids, LOINC codes, normalized values, and range conversions.

## Residual Risk

- Coverage is broader than before but still limited relative to real vendor catalogs.
- No new FHIR-specific assertions were added for the new biomarkers in this slice.
- More alias breadth and real-world reference-range variants are still needed before broader beta confidence.
