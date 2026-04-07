# Current Context

Latest checkpoint: `180_live-smoke-test-and-consensus-hardening.md`
Progress: `180%`

## Compressed State

Expanded the consensus workflow with a retry-aware live smoke test and hardened the orchestrator against sloppy provider responses such as first-round accept-with-proposal and repeated propose-when-revise would be more correct. The repo now has real Codex and Claude wrappers plus 54 passing tests.

## Locked Decisions

- Serum/plasma biomarkers also accept whole_blood specimen (generic Blood reporting)
- LOINC long-form aliases added for Synthea/EHR compatibility
- FHIR ingest auto-detected by .json extension
- Sample data excluded from git via .gitignore
- Blank-unit reference ranges are valid for unitless biomarkers and should be preserved
- Catalog LOINC edits require regression checks, not just spot inspection
- Dual-agent consensus runs from frozen context snapshots, not live mutable files
- Deploy hooks only run after one agent accepts the other agent's current proposal
- Repo-owned Codex and Claude wrappers should preserve the frozen-context guarantee, not silently reintroduce live workspace context
- Live smoke tests are transport checks, not semantic guarantees about provider behavior
- The orchestrator may normalize recoverable action mistakes when providers return structurally useful output

## Immediate Next Steps

- Re-run large-sample validation after the 71-biomarker hardening pass
- Consider HL7v2 ingest for enterprise customers
- Add broader metadata sanity checks for future catalog expansion waves
- Decide whether to smoke-test live provider calls in CI-like environments or keep wrapper verification provider-free
- Decide whether semantic task adherence needs a separate evaluator beyond transport-level smoke testing

## Resume From

Start from project_memory/current_context.md. The repo now includes real local wrappers, a retry-aware live smoke test, and hardened consensus normalization. Next focus should be broader validation and deciding whether to add semantic evaluation on top of the transport smoke check.
