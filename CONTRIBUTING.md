# Contributing

Thanks for contributing.

This project values deterministic behavior, explicit ambiguity handling, and conservative clinical-data normalization. Small, well-tested changes are easier to review than broad speculative refactors.

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[all,dev]"
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[all,dev]"
```

That install includes the test stack plus local packaging tools used by the validation and release docs.

## Typical Workflow

1. Create a focused branch.
2. Add or update tests with the change.
3. Run `pytest -q`.
4. If the API contract changes, regenerate `docs/openapi.json` with:

```bash
python scripts/export_openapi.py
```

5. Update documentation when behavior changes.
6. Keep pull requests narrow enough that a reviewer can reason about the behavioral impact.

## Validation Commands

Use the smallest command that proves the change:

```bash
pytest tests/test_normalization.py -q
pytest tests/test_api.py -q
pytest -q
python scripts/export_openapi.py
python -m build
```

CLI changes should also be smoke-tested with `bnt status` and, when relevant, `bnt demo --output-dir <dir>`.

## Contribution Expectations

- Prefer deterministic behavior over guessy heuristics.
- Preserve provenance and explicit review states.
- Do not silently widen mappings that could introduce clinical ambiguity.
- Add tests for new aliases, units, parser behavior, or endpoint changes.

## Good Contribution Areas

- vendor alias additions
- new biomarker mappings with LOINC coverage
- parser improvements across FHIR, HL7, C-CDA, and Excel
- unit synonym and reference-range edge cases
- documentation and example integrations

## Adding Biomarkers Or Aliases

- Add the catalog or alias change in the narrowest place possible.
- Add targeted tests for the exact biomarker, specimen, and unit behavior you changed.
- Prefer explicit specimen handling over broad alias widening when ambiguity is possible.
- Keep safety behavior intact: ambiguous input should still surface `review_needed` instead of silently guessing.

## Pull Requests

- Keep PRs small and scoped.
- Explain the user-visible change.
- Mention any compatibility impact.
- Include before/after examples when changing normalization behavior.
- If you change output shape or endpoint behavior, call that out explicitly in the PR description.

## Safety

This project handles medical data structures. Changes that increase false-positive mappings or hide ambiguity will be reviewed more strictly than changes that only add coverage.

## Communication

- Use [SUPPORT.md](SUPPORT.md) for the correct issue channel.
- Use [SECURITY.md](SECURITY.md) for sensitive vulnerability reporting.
- Review [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before participating in project discussions.
- Maintainers should follow [docs/releasing.md](docs/releasing.md) when preparing a release.
