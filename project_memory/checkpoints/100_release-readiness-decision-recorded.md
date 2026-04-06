# 100% Checkpoint: release readiness decision recorded

## Summary

Verified a real build-and-install path with the packaged demo asset and recorded the current release decision: alpha-ready for constrained use, not ready for broad external release.

## Completed

- Packaged the sample demo asset inside the distribution
- Verified sdist and wheel builds succeed
- Verified wheel install in an isolated virtual environment
- Verified installed bnt status and bnt demo work outside the editable repo install
- Recorded the current release-readiness decision in docs/release_readiness.md

## Decisions Locked

- The toolkit is currently ready for constrained alpha use only
- Broad external release is blocked on coverage and validation expansion
- Release readiness now includes a built-distribution verification path

## Verification Evidence

- python -m unittest discover -s tests -v
- python -m build
- .\.tmp_dist_verify_venv\Scripts\bnt status
- .\.tmp_dist_verify_venv\Scripts\bnt demo --output-dir .\tmp_dist_demo
- project_memory/verifications/100_release_readiness_verification.md

## Files Touched

- pyproject.toml
- src/biomarker_normalization_toolkit/cli.py
- src/biomarker_normalization_toolkit/data/v0_sample.csv
- docs/release_readiness.md

## Open Questions

- Which biomarkers and vendor patterns belong in the next coverage expansion wave
- Whether broader beta readiness should require external FHIR validation as a hard gate
- Whether a formal release automation path should be built before external beta

## Next Steps

- Expand biomarker and fixture coverage
- Add external FHIR validation to the verification workflow
- Define the beta release bar separately from the alpha bar

## Resume From

Start from docs/release_readiness.md and project_memory/current_context.md, then expand coverage against the new release bar.
