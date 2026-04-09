#!/usr/bin/env python3
"""Smoke-test an installed biomarker_normalization_toolkit distribution.

This script is intended to run after installing a built wheel or source
distribution into a clean environment. It validates the installed package,
not the editable checkout.
"""

from __future__ import annotations

import argparse
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
    parser.add_argument("--port", type=int, default=8010, help="Port for --serve mode.")
    args = parser.parse_args()

    expected_version = args.expected_version or _read_expected_version()
    _assert_basic_import(expected_version)
    print("installed package smoke: ok")

    if args.serve:
        _assert_served_api(args.port)
        print("packaged serve smoke: ok")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
