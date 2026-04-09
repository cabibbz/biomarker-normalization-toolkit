# Releasing

This document describes the practical release flow for the open-source repository.

## Before Tagging

Make sure the working tree reflects the intended release:

1. Update `pyproject.toml` version if needed.
2. Move the top changelog section in `CHANGELOG.md` into the correct release state.
3. Update `CITATION.cff` release metadata if you use it for published versions.
4. Regenerate `docs/openapi.json` if the API contract changed.
5. Build from a clean artifact directory so local checks only inspect the intended release:

```bash
python -c "import shutil; [shutil.rmtree(path, ignore_errors=True) for path in ('dist', 'build')]"
```

6. Re-run the full validation set:

```bash
pytest -q
python scripts/scrutinize.py
python scripts/export_openapi.py
python -m build
python scripts/check_distribution_contents.py
python -m twine check dist/*
python scripts/smoke_installed_package.py --check-cli --expect-rest-missing
python scripts/smoke_installed_package.py --serve --port 8010
```

## Artifact Validation

The release workflows also validate:

- editable-install test suite
- public-fixture sanity check
- checked-in OpenAPI drift
- distribution content checks for wheel and sdist artifacts
- wheel install smoke, including installed CLI behavior and missing-`[rest]` guidance
- source-distribution install smoke, including installed CLI behavior and missing-`[rest]` guidance
- packaged REST server startup

Do not cut a release if any of those validations are failing locally or in CI.

If the Docker image is part of the supported release surface, also run a Docker build and basic health check in an environment where Docker is available.

## Tagging

Create a tag that matches `pyproject.toml` exactly:

```bash
git tag v<version>
git push origin v<version>
```

The release workflow checks that the tag name and package version match.

## Publish Strategy

There is one repo-level decision outside the code:

- publish from the existing public history, or
- publish from a clean/squashed public history

Whichever strategy you choose, keep the tag/version history coherent from that point forward.

## After Release

- verify the GitHub Actions release workflow passed
- verify the PyPI page renders the README and metadata correctly
- verify the source distribution and wheel are both available
- update any public announcement or release notes links if needed
