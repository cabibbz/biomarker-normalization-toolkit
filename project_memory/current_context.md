# Current Context

Latest checkpoint: `080_fhir-export-implemented.md`
Progress: `80%`

## Compressed State

Added optional FHIR Observation bundle export for mapped rows, wired it into the normalize CLI behind --emit-fhir, and verified the new output path without regressing the existing normalization baseline.

## Locked Decisions

- FHIR export is optional and explicit, not always-on
- Only mapped rows are emitted as Observation resources
- Per-slice verification records are now mandatory for implementation work

## Immediate Next Steps

- Stabilize packaging beyond editable local install
- Add a stronger demo or sample-report flow on top of the CLI
- Expand fixture coverage with more biomarkers and edge cases

## Resume From

Start from project_memory/current_context.md, then choose between packaging stabilization and a stronger demo flow for the 90% milestone.
