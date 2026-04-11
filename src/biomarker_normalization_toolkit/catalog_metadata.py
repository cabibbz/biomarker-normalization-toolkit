from __future__ import annotations

import importlib.resources as resources
import json
from decimal import Decimal
from typing import Any

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.units import CONVERSION_TO_NORMALIZED

_METADATA_RESOURCE = "catalog_metadata.json"


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def build_catalog_metadata() -> dict[str, Any]:
    biomarkers: list[dict[str, Any]] = []
    for biomarker_id, biomarker in sorted(BIOMARKER_CATALOG.items()):
        conversions = CONVERSION_TO_NORMALIZED.get(biomarker_id, {})
        biomarkers.append(
            {
                "biomarker_id": biomarker.biomarker_id,
                "canonical_name": biomarker.canonical_name,
                "loinc": biomarker.loinc,
                "normalized_unit": biomarker.normalized_unit,
                "allowed_specimens": sorted(biomarker.allowed_specimens),
                "aliases": list(biomarker.aliases),
                "supported_source_units": sorted(conversions.keys()),
                "conversion_to_normalized": {
                    unit: _decimal_text(conversions[unit])
                    for unit in sorted(conversions.keys())
                },
            }
        )

    return {
        "schema_version": "0.1.0",
        "biomarker_count": len(biomarkers),
        "biomarkers": biomarkers,
    }


def load_catalog_metadata() -> dict[str, Any]:
    text = resources.files("biomarker_normalization_toolkit").joinpath(
        f"data/{_METADATA_RESOURCE}"
    ).read_text(encoding="utf-8")
    return json.loads(text)


def list_catalog_metadata(
    search: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    """List bundled catalog metadata entries with optional search and pagination."""
    if limit is not None and limit < 0:
        raise ValueError("limit must be >= 0")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    metadata = load_catalog_metadata()
    entries = metadata["biomarkers"]
    if search:
        query = search.lower()
        filtered = []
        for biomarker in entries:
            searchable = (
                f"{biomarker['biomarker_id']} {biomarker['canonical_name']} "
                f"{biomarker['loinc']} {biomarker['normalized_unit']} "
                f"{' '.join(biomarker['aliases'])} {' '.join(biomarker['supported_source_units'])}"
            ).lower()
            if query in searchable:
                filtered.append(biomarker)
        entries = filtered

    total = len(entries)
    page = entries[offset:] if limit is None else entries[offset : offset + limit]
    return {
        "schema_version": metadata["schema_version"],
        "biomarker_count": metadata["biomarker_count"],
        "biomarkers": page,
        "count": len(page),
        "total": total,
        "offset": offset,
    }
