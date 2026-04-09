#!/usr/bin/env python3
"""Smoke-test an installed biomarker_normalization_toolkit distribution.

This script is intended to run after installing a built wheel or source
distribution into a clean environment. It validates the installed package,
not the editable checkout.
"""

from __future__ import annotations

import argparse
import importlib.resources as resources
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def _read_expected_version() -> str | None:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover
        return None
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return data.get("project", {}).get("version")


def _assert_basic_import(expected_version: str | None) -> None:
    from biomarker_normalization_toolkit import __version__, normalize

    result = normalize([
        {
            "source_test_name": "Glucose",
            "raw_value": "100",
            "source_unit": "mg/dL",
            "specimen_type": "serum",
            "source_row_id": "1",
            "source_reference_range": "70-99 mg/dL",
        }
    ])
    if expected_version is not None:
        assert __version__ == expected_version, (__version__, expected_version)
    assert result.summary["mapped"] == 1, result.summary
    assert result.records[0].canonical_biomarker_id == "glucose_serum"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "biomarker_normalization_toolkit.cli", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _assert_basic_cli(expected_version: str | None) -> None:
    status = _run_cli("status")
    assert status.returncode == 0, status.stderr or status.stdout
    assert "Biomarker Normalization Toolkit" in status.stdout, status.stdout
    if expected_version is not None:
        assert f"v{expected_version}" in status.stdout, status.stdout

    with resources.as_file(
        resources.files("biomarker_normalization_toolkit.data").joinpath("v0_sample.csv")
    ) as sample_path, tempfile.TemporaryDirectory(prefix="bnt-installed-cli-") as tmpdir:
        demo_dir = Path(tmpdir) / "demo"
        demo = _run_cli("demo", "--output-dir", str(demo_dir))
        assert demo.returncode == 0, demo.stderr or demo.stdout
        assert (demo_dir / "normalized_records.json").exists(), demo.stdout
        assert (demo_dir / "fhir_observations.json").exists(), demo.stdout

        normalize_dir = Path(tmpdir) / "normalize"
        normalize = _run_cli(
            "normalize",
            "--input",
            str(sample_path),
            "--output-dir",
            str(normalize_dir),
        )
        assert normalize.returncode == 0, normalize.stderr or normalize.stdout
        assert (normalize_dir / "normalized_records.json").exists(), normalize.stdout

        analyze = _run_cli("analyze", "--input", str(sample_path))
        assert analyze.returncode == 0, analyze.stderr or analyze.stdout
        assert "Coverage Analysis" in analyze.stdout, analyze.stdout


def _assert_rest_missing_guidance() -> None:
    serve = _run_cli("serve", "--port", "8010")
    combined = f"{serve.stdout}\n{serve.stderr}"
    assert serve.returncode != 0, combined
    assert "biomarker-normalization-toolkit[rest]" in combined, combined


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _assert_served_api(port: int) -> None:
    host = "127.0.0.1"
    health_url = f"http://{host}:{port}/health"
    lookup_url = (
        f"http://{host}:{port}/lookup?"
        + urllib.parse.urlencode({"test_name": "GLU", "specimen": "serum"})
    )

    with tempfile.TemporaryDirectory(prefix="bnt-serve-logs-") as tmpdir:
        stdout_path = Path(tmpdir) / "stdout.log"
        stderr_path = Path(tmpdir) / "stderr.log"
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "biomarker_normalization_toolkit.cli",
                    "serve",
                    "--host",
                    host,
                    "--port",
                    str(port),
                ],
                stdout=stdout,
                stderr=stderr,
                text=True,
            )
            try:
                ready = False
                last_error: Exception | None = None
                for _ in range(30):
                    time.sleep(0.5)
                    if proc.poll() is not None:
                        break
                    try:
                        health = _fetch_json(health_url)
                        ready = True
                        break
                    except (urllib.error.URLError, TimeoutError) as exc:
                        last_error = exc

                if not ready:
                    stderr_text = stderr_path.read_text(encoding="utf-8")
                    stdout_text = stdout_path.read_text(encoding="utf-8")
                    raise RuntimeError(
                        "Packaged server did not become ready.\n"
                        f"stdout:\n{stdout_text}\n"
                        f"stderr:\n{stderr_text}\n"
                        f"last_error: {last_error!r}"
                    )

                assert health["status"] == "ok", health
                lookup = _fetch_json(lookup_url)
                assert lookup["matched"] is True, lookup
                assert lookup["candidates"][0]["biomarker_id"] == "glucose_serum", lookup
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test an installed BNT package.")
    parser.add_argument(
        "--expected-version",
        default=None,
        help="Expected installed package version. Defaults to pyproject.toml when available.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Also start the packaged REST server and validate HTTP endpoints.",
    )
    parser.add_argument(
        "--check-cli",
        action="store_true",
        help="Also run installed CLI status/demo/normalize/analyze smoke checks.",
    )
    parser.add_argument(
        "--expect-rest-missing",
        action="store_true",
        help="Assert that `bnt serve` fails with guidance to install the [rest] extra.",
    )
    parser.add_argument("--port", type=int, default=8010, help="Port for --serve mode.")
    args = parser.parse_args()

    expected_version = args.expected_version or _read_expected_version()
    _assert_basic_import(expected_version)
    print("installed package smoke: ok")

    if args.check_cli:
        _assert_basic_cli(expected_version)
        print("installed CLI smoke: ok")

    if args.expect_rest_missing:
        _assert_rest_missing_guidance()
        print("missing-rest guidance smoke: ok")

    if args.serve:
        _assert_served_api(args.port)
        print("packaged serve smoke: ok")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
