# Biomarker Normalization Toolkit

Customer-run toolkit for normalizing biomarker and lab data into canonical machine-readable output.

## Current Direction

The repo is intentionally starting with the lowest-risk, highest-probability route:

- B2B first
- customer-run deployment
- biomarker normalization and mapping only
- no hosted PHI by default
- no consumer product
- no clinical recommendation engine

## What This Repo Includes

- decision memos in [`docs/`](/C:/Users/me/Desktop/longevb2b/docs)
- the enforcement system in [`operating_system/`](/C:/Users/me/Desktop/longevb2b/operating_system)
- resumable progress checkpoints in [`project_memory/`](/C:/Users/me/Desktop/longevb2b/project_memory)
- the initial Python package scaffold in [`src/biomarker_normalization_toolkit/`](/C:/Users/me/Desktop/longevb2b/src/biomarker_normalization_toolkit)

## Working Rules

Before building:

1. Check hard constraints in [constraints.md](/C:/Users/me/Desktop/longevb2b/operating_system/constraints.md)
2. Score the idea with [review_rubric.md](/C:/Users/me/Desktop/longevb2b/operating_system/review_rubric.md)

During implementation:

1. Derive a context-based verification plan with [derive_verification_plan.py](/C:/Users/me/Desktop/longevb2b/operating_system/tools/derive_verification_plan.py)
2. Create a slice-specific verification record in [project_memory/verifications/](/C:/Users/me/Desktop/longevb2b/project_memory/verifications)
3. Run the relevant functionality verification, including click-through and backend behavior when the change calls for it
4. Do not mark work complete if relevant verification modes were skipped

During delivery:

1. Record a checkpoint at each 10% milestone using [record_checkpoint.py](/C:/Users/me/Desktop/longevb2b/operating_system/tools/record_checkpoint.py)
2. Update the resumable state in [current_context.md](/C:/Users/me/Desktop/longevb2b/project_memory/current_context.md)
3. Commit the verified slice
4. Push `main` to `origin`

## Git Discipline

After every verified implementation slice:

1. derive the context-based verification plan
2. create the phase-specific verification record
3. execute the relevant verification
4. record the checkpoint and update project memory
5. commit the changes
6. push to `origin/main`

Work is not considered operationally complete until the checkpoint, commit, and push all happen.

## Quick Start

```powershell
python -m pip install -e .
python -m biomarker_normalization_toolkit.cli status
python -m biomarker_normalization_toolkit.cli normalize --input .\fixtures\input\v0_sample.csv --output-dir .\out
python -m biomarker_normalization_toolkit.cli normalize --input .\fixtures\input\v0_sample.csv --output-dir .\out --emit-fhir
python .\operating_system\tools\evaluate_proposal.py .\operating_system\examples\customer_run_toolkit.json
python .\operating_system\tools\derive_verification_plan.py .\operating_system\examples\ui_and_api_change.json
```
