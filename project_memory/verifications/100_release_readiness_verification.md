# Verification Record

Change: distribution packaging and release readiness

Date: 2026-04-06

## Why These Tests

- This slice had to prove the toolkit works from a real built distribution, not just from the repo checkout.
- The highest-risk failure was a packaged install missing assets or breaking the public `bnt` command.
- Release readiness also required an explicit decision about what kind of release the current state can actually support.

## Derived Verification Scope

- backend regression validation
- built-distribution packaging validation
- isolated install validation
- installed console-script validation

## Commands Run

```text
python .\operating_system\tools\derive_verification_plan.py .\project_memory\entries\distribution_release_readiness_change.json
python -m pip install build
python -m unittest discover -s tests -v
python -m build
python -m venv .\.tmp_dist_verify_venv
.\.tmp_dist_verify_venv\Scripts\python -m pip install .\dist\biomarker_normalization_toolkit-0.1.0-py3-none-any.whl
.\.tmp_dist_verify_venv\Scripts\bnt status
.\.tmp_dist_verify_venv\Scripts\bnt demo --output-dir .\tmp_dist_demo
```

## Flows Exercised

- Built both sdist and wheel artifacts.
- Installed the wheel into an isolated virtual environment.
- Ran the installed `bnt status` command.
- Ran the installed `bnt demo` command and confirmed it wrote JSON, CSV, summary markdown, and FHIR output from the packaged sample asset.

## Results

- Regression tests passed: 7 tests, 0 failures.
- Distribution build succeeded for both sdist and wheel.
- Wheel install into an isolated environment succeeded.
- Installed `bnt` entry point worked in the isolated environment.
- Packaged demo asset resolved correctly and the installed demo flow completed successfully.

## Residual Risk

- The release-readiness decision is intentionally conservative: alpha-ready, not broad-release ready.
- Biomarker coverage remains narrow.
- External FHIR validation and broader real-world data coverage remain open.
