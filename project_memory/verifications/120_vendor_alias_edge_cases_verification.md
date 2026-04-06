# Verification Record

Change: vendor alias and edge-case normalization wave

Date: 2026-04-06

## Why These Tests

- This slice changed alias breadth, specimen shorthand handling, and unit spelling normalization.
- The highest-risk failures were false-positive mappings, broken unit normalization, and failure to handle vendor-style shorthand consistently.
- The primary verification artifact for this slice was created on the spot around a dedicated edge-case fixture.

## Derived Verification Scope

- backend regression validation
- CLI normalization on a vendor-style edge-case fixture
- slice-specific verification for alias, specimen, and unit handling
- direct output inspection for representative mapped rows

## Commands Run

```text
python .\operating_system\tools\derive_verification_plan.py .\project_memory\entries\vendor_alias_edge_cases_change.json
python -m unittest discover -s tests -v
bnt normalize --input .\fixtures\input\vendor_alias_edge_cases.csv --output-dir .\tmp_verify_120
python .\project_memory\verifications\120_vendor_alias_edge_cases_verify.py .\tmp_verify_120\normalized_records.json
Get-Content -LiteralPath .\tmp_verify_120\normalized_records.json -TotalCount 120
Get-Content -LiteralPath .\tmp_verify_120\normalization_summary.md -TotalCount 80
```

## Flows Exercised

- Ran the public CLI on the vendor-alias fixture.
- Verified shorthand aliases like `LDL Chol Calc`, `HDL CHOL`, `TRIG`, `CREA`, and `Hgb A1C`.
- Verified specimen shorthand values like `ser/plas` and `bld`.
- Verified unit spelling variants like `mg/dl`, `mg dl`, and `mg per dL`.
- Verified an unsupported derived metric alias remains unmapped.

## Results

- Existing regression suite passed: 7 tests, 0 failures.
- CLI normalization on the vendor-alias fixture succeeded.
- The dedicated slice-specific verifier passed.
- Direct output inspection confirmed the new alias, specimen, and unit forms normalize into the expected canonical outputs.

## Residual Risk

- Real-world vendor catalogs will still include many more alias variants than this wave covers.
- The slice improves compatibility but does not yet provide exhaustive vendor compendia coverage.
- FHIR-specific validation for the vendor-alias fixture remains outside this slice.
