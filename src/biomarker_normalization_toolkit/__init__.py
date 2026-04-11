"""Biomarker normalization toolkit package.

Quick start::

    from biomarker_normalization_toolkit import normalize, normalize_file

    # Normalize raw rows
    result = normalize([
        {"source_test_name": "Glucose", "raw_value": "100", "source_unit": "mg/dL",
         "specimen_type": "serum", "source_row_id": "1", "source_reference_range": "70-99 mg/dL"},
    ])
    for record in result.records:
        print(record.canonical_biomarker_name, record.normalized_value, record.normalized_unit)

    # Normalize a file (CSV, FHIR, HL7, C-CDA, or Excel)
    result = normalize_file("path/to/input.csv")
"""

from typing import Sequence

from biomarker_normalization_toolkit.catalog import (
    build_alias_index,
    list_catalog,
    lookup,
    read_custom_aliases,
    validate_custom_aliases,
)
from biomarker_normalization_toolkit.catalog_metadata import list_catalog_metadata, load_catalog_metadata
from biomarker_normalization_toolkit.io_utils import read_input
from biomarker_normalization_toolkit.normalizer import normalize_rows
from biomarker_normalization_toolkit.models import NormalizationResult, NormalizedRecord

__all__ = [
    "__version__",
    "normalize",
    "normalize_file",
    "normalize_rows",
    "compute_derived_metrics",
    "compute_phenoage",
    "evaluate_optimal_ranges",
    "list_catalog",
    "list_catalog_metadata",
    "load_catalog_metadata",
    "lookup",
    "read_custom_aliases",
    "validate_custom_aliases",
    "NormalizationResult",
    "NormalizedRecord",
]
from importlib.metadata import version as _pkg_version, PackageNotFoundError
try:
    __version__ = _pkg_version("biomarker-normalization-toolkit")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"


def normalize(
    rows: list[dict[str, str]],
    input_file: str = "",
    fuzzy_threshold: float = 0.0,
    custom_aliases: dict[str, Sequence[str]] | None = None,
) -> NormalizationResult:
    """Normalize a list of row dicts into canonical output.

    Each dict should have keys: source_test_name, raw_value, source_unit,
    specimen_type, source_row_id, source_reference_range.
    Optional: source_lab_name, source_panel_name.
    Set fuzzy_threshold > 0 (e.g. 0.85) to enable fuzzy alias matching.
    Pass custom_aliases to apply vendor-specific aliases for this call only.
    """
    alias_index = build_alias_index(custom_aliases) if custom_aliases is not None else None
    return normalize_rows(rows, input_file=input_file, fuzzy_threshold=fuzzy_threshold, alias_index=alias_index)


def normalize_file(
    path: str,
    input_file: str = "",
    fuzzy_threshold: float = 0.0,
    custom_aliases: dict[str, Sequence[str]] | None = None,
) -> NormalizationResult:
    """Read and normalize a file. Auto-detects CSV, FHIR JSON, HL7, C-CDA, Excel."""
    from pathlib import Path
    p = Path(path)
    rows = read_input(p)
    alias_index = build_alias_index(custom_aliases) if custom_aliases is not None else None
    return normalize_rows(rows, input_file=input_file or p.name, fuzzy_threshold=fuzzy_threshold, alias_index=alias_index)


def compute_derived_metrics(result: NormalizationResult) -> dict:
    """Compute HOMA-IR, TG/HDL, ApoB/ApoA1, and other derived metrics."""
    from biomarker_normalization_toolkit.derived import compute_derived_metrics as _compute
    return _compute(result)


def compute_phenoage(result: NormalizationResult, chronological_age: float) -> dict | None:
    """Compute PhenoAge biological age (Levine 2018) from 9 standard biomarkers."""
    from biomarker_normalization_toolkit.phenoage import compute_phenoage as _compute
    return _compute(result, chronological_age=chronological_age)


def evaluate_optimal_ranges(result: NormalizationResult) -> list[dict]:
    """Evaluate biomarkers against the toolkit's curated optimal-range layer."""
    from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges as _evaluate
    return _evaluate(result)
