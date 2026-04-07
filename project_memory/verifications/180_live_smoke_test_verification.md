# 180% Verification: live smoke test and consensus hardening

## Scope

Verify that:

- the live smoke runner can generate configs and retry bounded live attempts
- the orchestrator can normalize recoverable response-shape mistakes
- the real local Codex and Claude wrapper path can reach a completed state
- the rest of the repo remains regression-free

## Commands

```bash
python -m unittest tests.test_live_consensus_smoke_test -v
python -m unittest tests.test_dual_agent_consensus -v
pytest -q
python .\operating_system\tools\run_live_consensus_smoke_test.py --run-dir .agent_consensus\live_smoke_retry --attempts 2
```

## Observed Results

- Smoke-test unit coverage passed for config generation and retry behavior
- Consensus unit coverage passed for normalization of malformed live-provider actions
- Full suite passed with `54 passed in 1.77s`
- A real live smoke run reached `consensus_reached` on attempt 1 in 4 rounds

## Residual Risk

- Live provider outputs were not semantically stable across all attempted runs
- The smoke test currently proves wrapper/orchestrator interoperability, not reliable task adherence by both providers
