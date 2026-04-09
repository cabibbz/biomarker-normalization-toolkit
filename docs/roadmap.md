# Roadmap

## Now

- expand tracked interop fixtures across FHIR, HL7, C-CDA, and Excel
- improve real-world alias coverage without widening unsafe matches
- keep the CLI, API, and output schema stable as coverage grows
- tighten evidence and validation documentation around research-oriented features

## Next

- add more public integration examples and embedding guides
- improve specialty biomarker coverage and unit hardening
- add more fixture-driven regressions for body-fluid and qualitative-result edge cases
- validate the Docker path as part of routine release checks

## Later

- broader fixture packs for redistributable public standards examples
- optional benchmark and profiling harnesses built from public inputs
- deeper override/configuration surface for teams that want local policy on ranges or mappings

## Stability Priorities

The project prefers:

- deterministic output over aggressive heuristics
- explicit ambiguity over silent guessing
- narrow, reviewable coverage expansion over broad speculative matching
