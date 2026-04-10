from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Any, Literal

# Type-safe constants for mapping status and confidence
MappingStatus = Literal["mapped", "review_needed", "unmapped"]
MatchConfidence = Literal["high", "medium", "low", "none"]

_PLAIN_NEGATIVE_NUMBER = re.compile(r"^-(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def _protect_csv_cell(value: object) -> str:
    text = str(value)
    stripped = text.lstrip(" \t\r")
    if not stripped:
        return text
    if stripped[0] in "=+@":
        return "'" + text
    if stripped[0] == "-" and not _PLAIN_NEGATIVE_NUMBER.fullmatch(stripped):
        return "'" + text
    return text


@dataclass(frozen=True)
class RangeValue:
    low: Decimal
    high: Decimal
    unit: str


@dataclass(frozen=True)
class SourceRecord:
    row_number: int
    source_row_id: str
    source_test_name: str
    source_loinc: str
    raw_value_text: str
    raw_value: Decimal | None
    source_unit: str
    specimen_type: str
    source_reference_range: str
    source_lab_name: str
    source_panel_name: str
    alias_key: str
    raw_source: dict[str, str]


@dataclass(frozen=True)
class NormalizedRecord:
    source_row_number: int
    source_row_id: str
    source_lab_name: str
    source_panel_name: str
    source_test_name: str
    alias_key: str
    raw_value: str
    source_unit: str
    specimen_type: str
    source_reference_range: str
    canonical_biomarker_id: str
    canonical_biomarker_name: str
    loinc: str
    mapping_status: MappingStatus
    match_confidence: MatchConfidence
    status_reason: str
    mapping_rule: str
    normalized_value: str
    normalized_unit: str
    normalized_reference_range: str
    provenance: dict[str, Any]  # Frozen via convention — callers must not mutate

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "source_row_number": self.source_row_number,
            "source_row_id": self.source_row_id,
            "source_lab_name": self.source_lab_name,
            "source_panel_name": self.source_panel_name,
            "source_test_name": self.source_test_name,
            "alias_key": self.alias_key,
            "raw_value": self.raw_value,
            "source_unit": self.source_unit,
            "specimen_type": self.specimen_type,
            "source_reference_range": self.source_reference_range,
            "canonical_biomarker_id": self.canonical_biomarker_id,
            "canonical_biomarker_name": self.canonical_biomarker_name,
            "loinc": self.loinc,
            "mapping_status": self.mapping_status,
            "match_confidence": self.match_confidence,
            "status_reason": self.status_reason,
            "mapping_rule": self.mapping_rule,
            "normalized_value": self.normalized_value,
            "normalized_unit": self.normalized_unit,
            "normalized_reference_range": self.normalized_reference_range,
            "provenance": self.provenance,
        }

    def to_csv_row(self) -> dict[str, str]:
        return {
            "source_row_number": str(self.source_row_number),
            "source_row_id": _protect_csv_cell(self.source_row_id),
            "source_lab_name": _protect_csv_cell(self.source_lab_name),
            "source_panel_name": _protect_csv_cell(self.source_panel_name),
            "source_test_name": _protect_csv_cell(self.source_test_name),
            "alias_key": _protect_csv_cell(self.alias_key),
            "raw_value": _protect_csv_cell(self.raw_value),
            "source_unit": _protect_csv_cell(self.source_unit),
            "specimen_type": _protect_csv_cell(self.specimen_type),
            "source_reference_range": _protect_csv_cell(self.source_reference_range),
            "canonical_biomarker_id": _protect_csv_cell(self.canonical_biomarker_id),
            "canonical_biomarker_name": _protect_csv_cell(self.canonical_biomarker_name),
            "loinc": _protect_csv_cell(self.loinc),
            "mapping_status": _protect_csv_cell(self.mapping_status),
            "match_confidence": _protect_csv_cell(self.match_confidence),
            "status_reason": _protect_csv_cell(self.status_reason),
            "mapping_rule": _protect_csv_cell(self.mapping_rule),
            "normalized_value": _protect_csv_cell(self.normalized_value),
            "normalized_unit": _protect_csv_cell(self.normalized_unit),
            "normalized_reference_range": _protect_csv_cell(self.normalized_reference_range),
            "provenance_source_row_id": _protect_csv_cell(self.provenance.get("source_row_id", "")),
            "provenance_alias_key": _protect_csv_cell(self.provenance.get("source_alias_key", "")),
        }


@dataclass(frozen=True)
class NormalizationResult:
    input_file: str
    summary: dict[str, Any]  # Contains int counts + nested confidence_breakdown dict
    records: list[NormalizedRecord]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.warnings, list):
            object.__setattr__(self, "warnings", tuple(self.warnings))

    def to_json_dict(self, *, include_generated_at: bool = False) -> dict[str, Any]:
        from biomarker_normalization_toolkit import __version__
        result: dict[str, Any] = {
            "schema_version": "0.2.0",
            "bnt_version": __version__,
            "input_file": self.input_file,
            "summary": self.summary,
            "records": [record.to_json_dict() for record in self.records],
        }
        if include_generated_at:
            import datetime
            result["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if self.warnings:
            result["warnings"] = list(self.warnings)
        return result
