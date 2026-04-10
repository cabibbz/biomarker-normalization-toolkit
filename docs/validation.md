# Validation

This document explains what the public repository validates directly, and what remains outside the reproducible OSS contract.

## Repository-Verified Validation

The public repository validates behavior in several ways:

- targeted unit tests for alias resolution, specimen handling, unit conversion, and parser behavior
- tracked interop fixtures for CSV, FHIR, HL7, and C-CDA ingest
- Excel ingest tests that generate a workbook at runtime instead of committing a binary spreadsheet fixture
- API tests for the public HTTP contract and checked-in OpenAPI output
- property-based tests for normalization invariants
- CLI smoke checks for the packaged command-line interface
- wheel-install smoke checks to verify the built distribution works outside editable mode
- source-distribution install smoke checks to verify the sdist is usable on its own
- packaged REST-server smoke checks to verify `bnt serve` works from built artifacts

The repository also includes `scripts/scrutinize.py`, which runs a public-fixture sanity check against tracked fixtures and catalog metadata.

## Public Fixture Boundary

The supported public fixture surface is:

- `fixtures/input/`
- `fixtures/expected/`
- `src/biomarker_normalization_toolkit/data/`

Those files are the reproducible test inputs for the open-source project.

Excel is the one exception to the text-fixture rule: the test suite generates a minimal workbook at runtime so the repository does not need to ship a tracked binary `.xlsx` file.

## External Validation Context

During development, the toolkit was also exercised against larger local corpora and public/demo sources that are not part of the package distribution.

That work can be useful maintainer context, but it is not the same thing as a public, reproducible repository guarantee.

See [external-datasets.md](external-datasets.md) for the boundary between tracked fixtures and local-only datasets.

## What To Re-Validate When Behavior Changes

Re-run at least:

```bash
pytest -q
python scripts/scrutinize.py
python scripts/export_openapi.py
python -m build
python -m twine check dist/*
```

For packaging or CLI changes, also verify:

```bash
bnt status
bnt analyze --input src/biomarker_normalization_toolkit/data/v0_sample.csv
# Run this in a clean base-install environment without the [rest] extra.
python scripts/smoke_installed_package.py --check-cli --expect-rest-missing
# Run this in a clean environment with the [rest] extra installed.
python scripts/smoke_installed_package.py --serve --port 8010
```

For distribution-grade validation, prefer clean-environment installs instead of relying only on editable mode.

The repository includes `scripts/check_distribution_contents.py` to verify that the wheel and sdist carry the expected public files.

If you ship the Docker path as part of a release, validate it separately in an environment where Docker is available:

```bash
docker build -t bnt .
docker run --rm -p 8000:8000 bnt
```
