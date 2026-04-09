# Governance

## Project Model

This repository is maintained as a pragmatic open-source infrastructure project.

Maintainers are responsible for:

- triaging issues and pull requests
- reviewing behavior changes that affect normalization safety
- cutting releases
- keeping the public API, CLI, and schema documentation coherent

## Decision Process

Most changes should land through normal pull request review.

Maintainers will review more strictly when a change:

- widens alias matching in a way that could increase false positives
- changes unit-conversion behavior
- alters API or CLI output contracts
- affects ambiguity handling, provenance, or clinical-data safety

For low-risk documentation, fixture, and example updates, lightweight review is usually enough.

## Compatibility

The project aims for stable machine-readable output and conservative normalization behavior.

When behavior must change:

- the change should be documented
- tests should show the intended new contract
- breaking API or CLI changes should be called out in the changelog

## Release Policy

- Releases are cut from a green test suite.
- API contract changes should regenerate `docs/openapi.json`.
- Packaging changes should pass `python -m build` and `python -m twine check dist/*`.

## Community Expectations

- Technical arguments should be concrete and reproducible.
- Safety concerns take priority over convenience.
- Contributors are expected to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
