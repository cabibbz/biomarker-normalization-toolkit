# 80% Checkpoint: fhir export implemented

## Summary

Added optional FHIR Observation bundle export for mapped rows, wired it into the normalize CLI behind --emit-fhir, and verified the new output path without regressing the existing normalization baseline.

## Completed

- Added FHIR Observation bundle generation
- Added optional FHIR bundle writing to the output directory
- Extended the normalize CLI with --emit-fhir
- Added focused tests for FHIR bundle generation and CLI emission
- Recorded a per-slice verification artifact for the change

## Decisions Locked

- FHIR export is optional and explicit, not always-on
- Only mapped rows are emitted as Observation resources
- Per-slice verification records are now mandatory for implementation work

## Verification Evidence

- python .\operating_system\tools\derive_verification_plan.py .\project_memory\entries\fhir_export_change.json
- python -m unittest discover -s tests -v
- python -m biomarker_normalization_toolkit.cli normalize --input .\fixtures\input\v0_sample.csv --output-dir .\tmp_verify_fhir --emit-fhir
- project_memory/verifications/080_fhir_export_verification.md

## Files Touched

- src/biomarker_normalization_toolkit/fhir.py
- src/biomarker_normalization_toolkit/io_utils.py
- src/biomarker_normalization_toolkit/cli.py
- tests/test_normalization.py
- README.md
- project_memory/roadmap.md

## Open Questions

- Whether the next slice should focus on packaging or a stronger demo flow
- Whether to introduce a proper FHIR validation step before release readiness
- Whether mapped-but-partial rows need a second FHIR export policy later

## Next Steps

- Stabilize packaging beyond editable local install
- Add a stronger demo or sample-report flow on top of the CLI
- Expand fixture coverage with more biomarkers and edge cases

## Resume From

Start from project_memory/current_context.md, then choose between packaging stabilization and a stronger demo flow for the 90% milestone.
