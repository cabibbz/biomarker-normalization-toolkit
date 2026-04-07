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

Optional for high-risk or ambiguous changes: run the two-agent consensus loop so Codex and Claude work from the same context snapshot and bounce a shared proposal until one agent accepts the other's plan.

```powershell
python .\operating_system\tools\dual_agent_consensus.py .\operating_system\examples\dual_agent_consensus_config.json
```

See [multi_agent_consensus.md](/C:/Users/me/Desktop/longevb2b/operating_system/multi_agent_consensus.md) for the config contract and wrapper expectations.

The repo now includes real local wrappers for both CLIs:

- [codex_consensus_wrapper.py](/C:/Users/me/Desktop/longevb2b/operating_system/tools/codex_consensus_wrapper.py)
- [claude_consensus_wrapper.py](/C:/Users/me/Desktop/longevb2b/operating_system/tools/claude_consensus_wrapper.py)

These wrappers run from the frozen consensus run directory rather than the live workspace so both agents reason from the same snapshot.

For a low-cost end-to-end transport check through the installed CLIs, use the live smoke runner:

```powershell
python .\operating_system\tools\run_live_consensus_smoke_test.py --attempts 2
```

This smoke test verifies wrapper and orchestrator interoperability. It does not guarantee that both providers semantically follow the requested task exactly on every run.

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

If the slice affects FHIR output, include external bundle validation using [validate_fhir_bundle.py](/C:/Users/me/Desktop/longevb2b/operating_system/tools/validate_fhir_bundle.py).
