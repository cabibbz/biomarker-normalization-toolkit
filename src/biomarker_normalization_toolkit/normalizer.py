from __future__ import annotations

from pathlib import Path

from biomarker_normalization_toolkit.catalog import ALIAS_INDEX, BIOMARKER_CATALOG, normalize_key, normalize_specimen
from biomarker_normalization_toolkit.models import NormalizationResult, NormalizedRecord, RangeValue, SourceRecord
from biomarker_normalization_toolkit.units import convert_to_normalized, format_decimal, format_range, normalize_unit, parse_decimal, parse_reference_range


def build_source_records(rows: list[dict[str, str]]) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    for index, row in enumerate(rows, start=1):
        records.append(
            SourceRecord(
                row_number=index,
                source_row_id=row.get("source_row_id", "").strip(),
                source_test_name=row.get("source_test_name", "").strip(),
                raw_value_text=row.get("raw_value", "").strip(),
                raw_value=parse_decimal(row.get("raw_value", "")),
                source_unit=normalize_unit(row.get("source_unit", "")),
                specimen_type=normalize_specimen(row.get("specimen_type", "").strip()) or "",
                source_reference_range=row.get("source_reference_range", "").strip(),
                source_lab_name=row.get("source_lab_name", "").strip(),
                source_panel_name=row.get("source_panel_name", "").strip(),
                alias_key=normalize_key(row.get("source_test_name", "")),
                raw_source=row,
            )
        )
    return records


def _empty_record(
    source: SourceRecord,
    *,
    status: str,
    reason: str,
    biomarker_id: str = "",
    biomarker_name: str = "",
    loinc: str = "",
    mapping_rule: str = "",
    normalized_value: str = "",
    normalized_unit: str = "",
    normalized_reference_range: str = "",
    confidence: str = "none",
) -> NormalizedRecord:
    return NormalizedRecord(
        source_row_number=source.row_number,
        source_row_id=source.source_row_id,
        source_lab_name=source.source_lab_name,
        source_panel_name=source.source_panel_name,
        source_test_name=source.source_test_name,
        alias_key=source.alias_key,
        raw_value=source.raw_value_text,
        source_unit=source.source_unit,
        specimen_type=source.specimen_type,
        source_reference_range=source.source_reference_range,
        canonical_biomarker_id=biomarker_id,
        canonical_biomarker_name=biomarker_name,
        loinc=loinc,
        mapping_status=status,
        match_confidence=confidence,
        status_reason=reason,
        mapping_rule=mapping_rule,
        normalized_value=normalized_value,
        normalized_unit=normalized_unit,
        normalized_reference_range=normalized_reference_range,
        provenance={
            "source_row_number": source.row_number,
            "source_row_id": source.source_row_id,
            "source_alias_key": source.alias_key,
            "raw_source": source.raw_source,
        },
    )


def _filter_candidates_by_specimen(candidate_ids: list[str], specimen_type: str) -> list[str]:
    if not specimen_type:
        return candidate_ids
    filtered: list[str] = []
    for candidate_id in candidate_ids:
        candidate = BIOMARKER_CATALOG[candidate_id]
        if not candidate.allowed_specimens or specimen_type in candidate.allowed_specimens:
            filtered.append(candidate_id)
    return filtered


def _convert_range(range_value: RangeValue | None, biomarker_id: str) -> RangeValue | None:
    if range_value is None:
        return None

    low = convert_to_normalized(range_value.low, biomarker_id, range_value.unit)
    high = convert_to_normalized(range_value.high, biomarker_id, range_value.unit)
    target_unit = BIOMARKER_CATALOG[biomarker_id].normalized_unit
    if low is None or high is None:
        return None
    return RangeValue(low=low, high=high, unit=target_unit)


def normalize_source_record(source: SourceRecord) -> NormalizedRecord:
    candidate_ids = ALIAS_INDEX.get(source.alias_key, [])
    if not candidate_ids:
        return _empty_record(source, status="unmapped", reason="unknown_alias")

    specimen_filtered = _filter_candidates_by_specimen(candidate_ids, source.specimen_type)

    if len(candidate_ids) > 1 and not source.specimen_type:
        return _empty_record(source, status="review_needed", reason="ambiguous_alias_requires_specimen")

    if len(specimen_filtered) > 1:
        return _empty_record(source, status="review_needed", reason="ambiguous_alias_after_specimen_filter")

    if len(specimen_filtered) == 0:
        return _empty_record(source, status="review_needed", reason="no_candidate_for_specimen")

    candidate = BIOMARKER_CATALOG[specimen_filtered[0]]

    if source.raw_value is None:
        return _empty_record(
            source,
            status="review_needed",
            reason="invalid_raw_value",
            biomarker_id=candidate.biomarker_id,
            biomarker_name=candidate.canonical_name,
            loinc=candidate.loinc,
        )

    normalized_value = convert_to_normalized(source.raw_value, candidate.biomarker_id, source.source_unit)
    if normalized_value is None:
        return _empty_record(
            source,
            status="review_needed",
            reason="unsupported_unit_for_biomarker",
            biomarker_id=candidate.biomarker_id,
            biomarker_name=candidate.canonical_name,
            loinc=candidate.loinc,
        )

    source_range = parse_reference_range(source.source_reference_range, source.source_unit)
    normalized_range = _convert_range(source_range, candidate.biomarker_id)

    mapped_by_specimen = len(candidate_ids) > 1
    reason = "mapped_by_alias_and_specimen" if mapped_by_specimen else "mapped_by_unique_alias"
    mapping_rule = f"alias:{source.alias_key}|biomarker:{candidate.biomarker_id}"
    if mapped_by_specimen:
        mapping_rule += f"|specimen:{source.specimen_type}"

    return _empty_record(
        source,
        status="mapped",
        reason=reason,
        biomarker_id=candidate.biomarker_id,
        biomarker_name=candidate.canonical_name,
        loinc=candidate.loinc,
        mapping_rule=mapping_rule,
        normalized_value=format_decimal(normalized_value),
        normalized_unit=candidate.normalized_unit,
        normalized_reference_range=format_range(normalized_range),
        confidence="high",
    )


def normalize_rows(rows: list[dict[str, str]], input_file: str = "") -> NormalizationResult:
    source_records = build_source_records(rows)
    normalized_records = [normalize_source_record(record) for record in source_records]

    summary = {
        "total_rows": len(normalized_records),
        "mapped": sum(1 for record in normalized_records if record.mapping_status == "mapped"),
        "review_needed": sum(1 for record in normalized_records if record.mapping_status == "review_needed"),
        "unmapped": sum(1 for record in normalized_records if record.mapping_status == "unmapped"),
    }

    return NormalizationResult(
        input_file=Path(input_file).name if input_file else "",
        summary=summary,
        records=normalized_records,
    )

