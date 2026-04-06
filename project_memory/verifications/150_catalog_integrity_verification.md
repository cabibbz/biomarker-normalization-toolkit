# 150% Verification: catalog integrity and 71-biomarker hardening

## Scope

Verify that the post-expansion repair pass corrected the catalog metadata defects, preserved blank-unit urinalysis reference ranges, and kept the CLI-facing baseline aligned with the hardened 71-biomarker catalog.

## Commands

```bash
pytest -q
python -m biomarker_normalization_toolkit.cli status
```

Observed results:

- `47 passed in 0.55s`
- `bnt status` reported 71 biomarkers

## What Was Verified

- Corrected BUN and Iron LOINC assignments are enforced by regression tests
- Catalog LOINC codes are unique across the current 71-biomarker registry
- The newest 10 biomarkers map successfully
- Urine specific gravity and blank-unit urine pH retain normalized reference ranges instead of dropping them
- The CLI status command reports the live catalog count

## Residual Risk

- The claimed 128K-row benchmark has not been re-run from this repaired baseline in this checkpoint
- External terminology validation is still manual rather than enforced in automated checks
