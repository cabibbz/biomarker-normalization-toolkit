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
    result = normalize_file("labs.csv")
"""

from biomarker_normalization_toolkit.io_utils import read_input
from biomarker_normalization_toolkit.normalizer import normalize_rows
from biomarker_normalization_toolkit.models import NormalizationResult, NormalizedRecord

__all__ = [
    "__version__",
    "normalize",
    "normalize_file",
    "normalize_rows",
    "NormalizationResult",
    "NormalizedRecord",
]
from importlib.metadata import version as _pkg_version, PackageNotFoundError
try:
    __version__ = _pkg_version("biomarker-normalization-toolkit")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"


def normalize(rows: list[dict[str, str]], input_file: str = "", fuzzy_threshold: float = 0.0) -> NormalizationResult:
    """Normalize a list of row dicts into canonical output.

    Each dict should have keys: source_test_name, raw_value, source_unit,
    specimen_type, source_row_id, source_reference_range.
    Optional: source_lab_name, source_panel_name.
    Set fuzzy_threshold > 0 (e.g. 0.85) to enable fuzzy alias matching.
    """
    return normalize_rows(rows, input_file=input_file, fuzzy_threshold=fuzzy_threshold)


def normalize_file(path: str, input_file: str = "", fuzzy_threshold: float = 0.0) -> NormalizationResult:
    """Read and normalize a file. Auto-detects CSV, FHIR JSON, HL7, C-CDA, Excel."""
    from pathlib import Path
    p = Path(path)
    rows = read_input(p)
    return normalize_rows(rows, input_file=input_file or p.name, fuzzy_threshold=fuzzy_threshold)
