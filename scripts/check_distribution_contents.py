#!/usr/bin/env python3
"""Validate expected files inside built BNT distributions."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path


def _read_version(project_root: Path) -> str:
    import tomllib

    pyproject = project_root / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return data["project"]["version"]


def _check_sdist(dist_dir: Path, version: str) -> None:
    sdist_path = dist_dir / f"biomarker_normalization_toolkit-{version}.tar.gz"
    if not sdist_path.exists():
        raise SystemExit(f"Missing sdist: {sdist_path}")

    root = f"biomarker_normalization_toolkit-{version}"
    required = {
        f"{root}/CHANGELOG.md",
        f"{root}/CITATION.cff",
        f"{root}/CODE_OF_CONDUCT.md",
        f"{root}/CONTRIBUTING.md",
        f"{root}/GOVERNANCE.md",
        f"{root}/README.md",
        f"{root}/SECURITY.md",
        f"{root}/SUPPORT.md",
        f"{root}/docs/evidence.md",
        f"{root}/docs/external-datasets.md",
        f"{root}/docs/openapi.json",
        f"{root}/docs/oss-cutover.md",
        f"{root}/docs/releasing.md",
        f"{root}/docs/validation.md",
        f"{root}/examples/README.md",
        f"{root}/examples/python_sdk/basic_normalize.py",
        f"{root}/fixtures/input/interop/fhir_bundle_minimal.json",
        f"{root}/scripts/export_openapi.py",
        f"{root}/scripts/smoke_installed_package.py",
        f"{root}/scripts/scrutinize.py",
        f"{root}/src/biomarker_normalization_toolkit/api.py",
    }

    with tarfile.open(sdist_path, "r:gz") as tf:
        names = set(tf.getnames())

    missing = sorted(required - names)
    if missing:
        raise SystemExit("sdist is missing required files:\n" + "\n".join(missing))


def _check_wheel(dist_dir: Path, version: str) -> None:
    wheel_path = dist_dir / f"biomarker_normalization_toolkit-{version}-py3-none-any.whl"
    if not wheel_path.exists():
        raise SystemExit(f"Missing wheel: {wheel_path}")

    required = {
        "biomarker_normalization_toolkit/__init__.py",
        "biomarker_normalization_toolkit/api.py",
        "biomarker_normalization_toolkit/cli.py",
        "biomarker_normalization_toolkit/data/v0_sample.csv",
        f"biomarker_normalization_toolkit-{version}.dist-info/METADATA",
        f"biomarker_normalization_toolkit-{version}.dist-info/entry_points.txt",
        f"biomarker_normalization_toolkit-{version}.dist-info/licenses/LICENSE",
    }

    with zipfile.ZipFile(wheel_path) as zf:
        names = set(zf.namelist())

    missing = sorted(required - names)
    if missing:
        raise SystemExit("wheel is missing required files:\n" + "\n".join(missing))


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    version = _read_version(project_root)
    dist_dir = project_root / "dist"

    _check_sdist(dist_dir, version)
    _check_wheel(dist_dir, version)
    print("distribution contents: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
