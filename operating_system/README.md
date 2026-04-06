# Operating System

This folder is the decision and release gate for the business.

Use it in this order:

1. Check [constraints.md](/C:/Users/me/Desktop/longevb2b/operating_system/constraints.md)
2. Score the idea with [review_rubric.md](/C:/Users/me/Desktop/longevb2b/operating_system/review_rubric.md)
3. Record the proposal in JSON using [proposal_template.json](/C:/Users/me/Desktop/longevb2b/operating_system/proposal_template.json)
4. Run the evaluator:

```powershell
python .\operating_system\tools\evaluate_proposal.py .\operating_system\examples\customer_run_toolkit.json
```

5. After implementation, derive a context-based verification plan using [verification_gate.md](/C:/Users/me/Desktop/longevb2b/operating_system/verification_gate.md) and [change_record_template.json](/C:/Users/me/Desktop/longevb2b/operating_system/change_record_template.json)

```powershell
python .\operating_system\tools\derive_verification_plan.py .\operating_system\examples\ui_and_api_change.json
```

6. Execute the derived verification plan and validate the changed system against [functional_test_matrix.md](/C:/Users/me/Desktop/longevb2b/operating_system/functional_test_matrix.md)
7. If progress crosses a 10% milestone, record a checkpoint in [project_memory/](/C:/Users/me/Desktop/longevb2b/project_memory)

```powershell
python .\operating_system\tools\record_checkpoint.py .\project_memory\entries\010_repo_setup.json
```

## What This System Optimizes For

- low compliance exposure
- low launch cost
- fast path to first revenue
- reusable biomarker normalization IP
- customer-run deployment by default
- recurring revenue from support and mapping updates

## Operating Rule

Any new feature, product direction, or customer request must pass:

- hard constraints
- score threshold
- context-derived verification planning
- functional release gates

If it fails the hard constraints, do not build it.

If the implementation cannot be verified across the surfaces it changed, do not mark it done.

If a 10% milestone is reached and no checkpoint is written, the work is not operationally ready for handoff.

After verification and checkpointing, commit the slice and push it to `origin/main`.
