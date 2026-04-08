#!/usr/bin/env python3
"""Export the FastAPI OpenAPI specification to docs/openapi.json.

Usage:
    python scripts/export_openapi.py
    # or from project root:
    python -m scripts.export_openapi
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

def main() -> None:
    # Ensure the project root is on sys.path so the package can be imported
    project_root = Path(__file__).resolve().parent.parent
    src_dir = project_root / "src"
    if src_dir.exists():
        sys.path.insert(0, str(src_dir))

    from biomarker_normalization_toolkit.api import app

    spec = app.openapi()

    output_dir = project_root / "docs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "openapi.json"

    output_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"OpenAPI spec written to {output_path} ({len(spec.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
