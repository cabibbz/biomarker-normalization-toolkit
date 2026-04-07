# 180% Checkpoint: live smoke test and consensus hardening

## Summary

Added a retry-aware live smoke runner for the installed Codex and Claude CLIs, hardened the consensus engine against recoverable action-shape mistakes from live providers, and verified that the real wrapper path can reach a completed consensus state through the actual local CLIs.

## Completed

- Added `operating_system/tools/run_live_consensus_smoke_test.py`
- Added tests for smoke-test config generation and retry behavior
- Hardened the orchestrator to normalize first-proposal edge cases such as `accept` with proposal text and `propose` after a proposal already exists
- Updated the Claude wrapper to consume `structured_output` and accept a budget cap
- Verified a real live smoke run through the installed Codex and Claude CLIs with retry support

## Decisions Locked

- Live provider smoke tests are transport-level checks, not semantic guarantees
- Retry support is appropriate for live smoke tests because provider behavior is nondeterministic across runs
- The orchestrator may normalize recoverable response-shape mistakes when proposal text is still usable

## Verification Evidence

- `python -m unittest tests.test_live_consensus_smoke_test -v`
- `python -m unittest tests.test_dual_agent_consensus -v`
- `pytest -q` -> `54 passed in 1.77s`
- `python .\operating_system\tools\run_live_consensus_smoke_test.py --run-dir .agent_consensus\live_smoke_retry --attempts 2`
- Live smoke run result: consensus reached on attempt 1 in 4 rounds at `.agent_consensus/live_smoke_retry/attempt_01/result.json`

## Files Touched

- operating_system/tools/dual_agent_consensus.py
- operating_system/tools/consensus_wrapper_common.py
- operating_system/tools/claude_consensus_wrapper.py
- operating_system/tools/run_live_consensus_smoke_test.py
- operating_system/README.md
- operating_system/multi_agent_consensus.md
- tests/test_dual_agent_consensus.py
- tests/test_live_consensus_smoke_test.py

## Open Questions

- Whether semantic adherence should be checked by a separate evaluator instead of expecting it from a transport smoke test
- Whether live smoke retries should cap by budget as well as attempt count
- Whether the consensus transcript should record the original and normalized actions separately in machine-readable form

## Next Steps

- Re-run large-sample validation after the 71-biomarker hardening pass
- Decide whether to add semantic evaluation on top of the live transport smoke test
- Continue customer-driven coverage and alias expansion

## Resume From

Start from project_memory/current_context.md. The repo now has a retry-aware live smoke test and hardened consensus response handling, but semantic evaluation remains a separate open problem.
