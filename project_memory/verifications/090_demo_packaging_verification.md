# Verification Record

Change: demo flow and console-script packaging proof

Date: 2026-04-06

## Why These Tests

- This slice changed the public CLI surface and the human-facing demo/report flow.
- The highest-risk issue was proving the installed `bnt` command still works end to end after the CLI changes.
- Regression against the existing normalization and FHIR behavior also had to remain green.

## Derived Verification Scope

- backend regression validation
- installed console-script validation
- demo output generation validation
- human-readable report output validation

## Commands Run

```text
python .\operating_system\tools\derive_verification_plan.py .\project_memory\entries\demo_packaging_change.json
python -m unittest discover -s tests -v
bnt demo --output-dir .\tmp_verify_demo
Get-Content -LiteralPath .\tmp_verify_demo\normalization_summary.md -TotalCount 120
Get-Content -LiteralPath .\tmp_verify_demo\fhir_observations.json -TotalCount 60
```

## Flows Exercised

- Ran the installed `bnt demo` command rather than only `python -m`.
- Verified the demo command writes normalized JSON, CSV, summary markdown, and FHIR output.
- Verified the markdown summary reflects the expected mapped, review-needed, and unmapped counts.
- Verified the existing FHIR output still appears in the demo path.

## Results

- Derived verification plan matched the changed surfaces: backend, CLI, and normalization.
- Automated test suite passed: 7 tests, 0 failures.
- The installed `bnt demo` command executed successfully.
- Direct inspection confirmed the generated summary markdown is readable and the FHIR bundle still exists and is structured correctly.
- No relevant verification mode for the slice was skipped.

## Residual Risk

- Packaging has only been proven for editable local installation so far.
- A built wheel/sdist install path is not verified yet.
- The demo uses the repo fixture dataset rather than a packaged sample asset.
