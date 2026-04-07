# 170% Checkpoint: live CLI wrappers for dual-agent consensus

## Summary

Added real local wrapper scripts for the installed Codex and Claude CLIs so the dual-agent consensus workflow can use actual model clients while preserving the frozen-context contract. The wrappers build prompts from the run snapshot, isolate model execution to the run directory, and validate structured responses before handing them back to the orchestrator.

## Completed

- Added repo-owned Codex and Claude wrapper scripts for consensus runs
- Added shared wrapper utilities for prompt construction and response validation
- Updated the example config to use the real wrappers and removed placeholder hook paths that would fail out of the box
- Fixed `run_dir` resolution so generated consensus runs land under the workspace instead of `operating_system/examples`
- Added wrapper-specific tests that verify prompt construction and response parsing with fake CLI shims

## Decisions Locked

- Consensus wrappers must reason from the frozen run snapshot, not the live workspace
- Claude wrapper runs in bare, no-session-persistence mode with tools disabled for deterministic review-only behavior
- Codex wrapper runs from the snapshot directory with `--skip-git-repo-check` and read-only sandboxing

## Verification Evidence

- `where.exe codex`
- `where.exe claude`
- `codex exec --help`
- `claude --help`
- `python -m unittest tests.test_consensus_wrappers -v`
- `python -m unittest tests.test_dual_agent_consensus -v`
- `pytest -q` -> `51 passed in 1.30s`

## Files Touched

- operating_system/tools/dual_agent_consensus.py
- operating_system/tools/consensus_wrapper_common.py
- operating_system/tools/codex_consensus_wrapper.py
- operating_system/tools/claude_consensus_wrapper.py
- operating_system/examples/dual_agent_consensus_config.json
- operating_system/multi_agent_consensus.md
- operating_system/README.md
- tests/test_consensus_wrappers.py

## Open Questions

- Whether to add a low-cost live smoke test that exercises both real CLIs against a trivial task
- Whether wrapper model and effort settings should be standardized in config or left entirely to the operator
- Whether deploy hooks should stay fully automatic after consensus or require a human confirmation layer

## Next Steps

- Re-run large-sample validation after the 71-biomarker hardening pass
- Decide whether to add live provider smoke tests or keep verification provider-free
- Continue customer-driven coverage and alias expansion

## Resume From

Start from project_memory/current_context.md. The repo now has real Codex and Claude wrappers for the consensus loop, but live-provider smoke testing and broader validation policy are still open decisions.
