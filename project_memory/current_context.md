# Current Context

Latest checkpoint: `170_live-cli-wrappers-for-dual-agent-consensus.md`
Progress: `170%`

## Compressed State

Expanded the repo workflow with real Codex and Claude wrapper scripts for the dual-agent consensus loop. The wrappers now build prompts from frozen run artifacts, isolate agent reasoning to the snapshot run directory instead of the live workspace, and the repo passes 51 tests including wrapper-specific coverage.

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

## Immediate Next Steps

- Re-run large-sample validation after the 71-biomarker hardening pass
- Consider HL7v2 ingest for enterprise customers
- Add broader metadata sanity checks for future catalog expansion waves
- Decide whether to smoke-test live provider calls in CI-like environments or keep wrapper verification provider-free

## Resume From

Start from project_memory/current_context.md. The repo now includes real local wrappers for Codex and Claude plus the hardened 71-biomarker toolkit baseline. Next focus should be broader validation and deciding how much live-provider verification to automate.
