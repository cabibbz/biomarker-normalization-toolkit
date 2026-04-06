# 130% Checkpoint: external fhir validation integrated

## Summary

Integrated external FHIR bundle validation into the repo workflow and verified emitted bundles across the original sample, coverage wave 1, and vendor-alias wave fixtures.

## Completed

- Added a verification requirements file for build and external FHIR validation
- Added a repo-owned FHIR bundle validation tool
- Updated workflow docs to require external validation when FHIR output is affected
- Validated emitted bundles across three fixture families through the external validator
- Updated release-readiness docs to reflect current-fixture FHIR validation coverage

## Decisions Locked

- FHIR output changes now require external validation, not just internal structural checks
- Current-fixture FHIR validation is now part of the ready-now baseline
- Broader beta readiness still requires wider fixture and coverage validation, not just one validator pass

## Verification Evidence

- python -m pip install -r .\requirements-verification.txt
- python -m unittest discover -s tests -v
- bnt normalize --input .\fixtures\input\v0_sample.csv --output-dir .\tmp_verify_130_sample --emit-fhir
- bnt normalize --input .\fixtures\input\coverage_wave_1.csv --output-dir .\tmp_verify_130_wave1 --emit-fhir
- bnt normalize --input .\fixtures\input\vendor_alias_edge_cases.csv --output-dir .\tmp_verify_130_vendor --emit-fhir
- python .\operating_system\tools\validate_fhir_bundle.py .\tmp_verify_130_sample\fhir_observations.json
- python .\operating_system\tools\validate_fhir_bundle.py .\tmp_verify_130_wave1\fhir_observations.json
- python .\operating_system\tools\validate_fhir_bundle.py .\tmp_verify_130_vendor\fhir_observations.json
- project_memory/verifications/130_external_fhir_validation_verification.md

## Files Touched

- requirements-verification.txt
- operating_system/tools/validate_fhir_bundle.py
- docs/build_workflow.md
- operating_system/README.md
- docs/release_readiness.md
- README.md

## Open Questions

- Which next biomarker group should be expanded and externally validated next
- Whether future FHIR validation should add stricter domain assertions beyond Bundle and Observation structure
- Whether beta readiness should require automated validation in CI rather than manual slice execution

## Next Steps

- Choose the next biomarker group for expansion
- Carry the same external validation path into the next coverage wave
- Consider automating the validation tool inside a CI-style workflow later

## Resume From

Start from project_memory/current_context.md and docs/release_readiness.md, then choose the next coverage wave with external FHIR validation included from the start.
