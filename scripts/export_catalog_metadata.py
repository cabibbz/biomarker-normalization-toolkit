#!/usr/bin/env python3
"""Export machine-readable catalog metadata to package data.

Usage:
    python scripts/export_catalog_metadata.py
    # or from project root:
    python -m scripts.export_catalog_metadata
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    src_dir = project_root / "src"
    if src_dir.exists():
        sys.path.insert(0, str(src_dir))

    from biomarker_normalization_toolkit.catalog_metadata import build_catalog_metadata

    metadata = build_catalog_metadata()
    output_dir = project_root / "src" / "biomarker_normalization_toolkit" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "catalog_metadata.json"

    output_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Catalog metadata written to {output_path} "
        f"({metadata['biomarker_count']} biomarkers)"
    )


if __name__ == "__main__":
    main()
