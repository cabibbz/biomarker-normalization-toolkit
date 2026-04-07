# 170% Verification: live CLI wrappers for dual-agent consensus

## Scope

Verify that the repo-owned Codex and Claude wrappers:

- build prompts from frozen run artifacts
- validate structured responses before returning them to the orchestrator
- preserve the existing orchestrator success and failure paths
- do not regress the biomarker toolkit baseline

## Commands

```bash
where.exe codex
where.exe claude
codex exec --help
claude --help
python -m unittest tests.test_consensus_wrappers -v
python -m unittest tests.test_dual_agent_consensus -v
pytest -q
```

## Observed Results

- Both CLIs are installed locally and expose non-interactive interfaces suitable for wrapper use
- Wrapper-specific tests passed for Codex and Claude shimmed executions
- Orchestrator tests still passed for consensus success and no-consensus failure
- Full suite passed with `51 passed in 1.30s`
- The example config no longer points at nonexistent local hook scripts

## Residual Risk

- No full live-provider end-to-end consensus run was executed in this slice to avoid unnecessary model spend
- Wrapper defaults for model selection and reasoning effort are still operator decisions, not hard policy
