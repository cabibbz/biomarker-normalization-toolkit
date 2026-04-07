from __future__ import annotations

from pathlib import Path

from biomarker_normalization_toolkit.catalog import ALIAS_INDEX, BIOMARKER_CATALOG, normalize_key, normalize_specimen
from biomarker_normalization_toolkit.models import NormalizationResult, NormalizedRecord, RangeValue, SourceRecord
from biomarker_normalization_toolkit.plausibility import check_plausibility
from biomarker_normalization_toolkit.units import convert_to_normalized, format_decimal, format_range, is_inequality_value, normalize_unit, parse_decimal, parse_reference_range

_SAFE_RAW_SOURCE_KEYS = frozenset({
    "source_row_id", "source_test_name", "raw_value", "source_unit",
    "specimen_type", "source_reference_range", "source_lab_name", "source_panel_name",
})


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
            "raw_source": {k: v for k, v in source.raw_source.items()
                          if k in _SAFE_RAW_SOURCE_KEYS},
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


_LOINC_INDEX: dict[str, str] = {bio.loinc: bio_id for bio_id, bio in BIOMARKER_CATALOG.items()}


def normalize_source_record(source: SourceRecord, *, fuzzy_threshold: float = 0.0) -> NormalizedRecord:
    candidate_ids = ALIAS_INDEX.get(source.alias_key, [])
    fuzzy_result: tuple[str, float] | None = None

    # Fallback: try LOINC code lookup (source test name may be a LOINC code)
    if not candidate_ids:
        loinc_match = _LOINC_INDEX.get(source.source_test_name.strip())
        if loinc_match:
            candidate_ids = [loinc_match]

    if not candidate_ids and fuzzy_threshold > 0:
        from biomarker_normalization_toolkit.fuzzy import fuzzy_match
        matches = fuzzy_match(source.alias_key, threshold=max(fuzzy_threshold, 0.70))
        if matches:
            best_alias, best_bio_id, best_score = matches[0]
            candidate_ids = ALIAS_INDEX.get(best_alias, [best_bio_id])
            fuzzy_result = (best_alias, best_score)

    if not candidate_ids:
        return _empty_record(source, status="unmapped", reason="unknown_alias")

    specimen_filtered = _filter_candidates_by_specimen(candidate_ids, source.specimen_type)

    if len(candidate_ids) > 1 and not source.specimen_type:
        reason = "fuzzy_match_ambiguous_requires_specimen" if fuzzy_result else "ambiguous_alias_requires_specimen"
        return _empty_record(source, status="review_needed", reason=reason)

    if len(specimen_filtered) > 1:
        return _empty_record(source, status="review_needed", reason="ambiguous_alias_after_specimen_filter")

    if len(specimen_filtered) == 0:
        return _empty_record(source, status="review_needed", reason="no_candidate_for_specimen")

    candidate = BIOMARKER_CATALOG[specimen_filtered[0]]

    if source.raw_value is None:
        reason = "inequality_value" if is_inequality_value(source.raw_value_text) else "invalid_raw_value"
        return _empty_record(
            source,
            status="review_needed",
            reason=reason,
            biomarker_id=candidate.biomarker_id,
            biomarker_name=candidate.canonical_name,
            loinc=candidate.loinc,
        )

    normalized_value = convert_to_normalized(source.raw_value, candidate.biomarker_id, source.source_unit)
    if normalized_value is None:
        # Try sibling biomarkers with related suffixes (_pct, _sd, _absolute, _urine, _serum)
        base = candidate.biomarker_id
        # Strip known suffixes to find base, then try all siblings
        for suffix in ("_pct", "_sd", "_absolute", "_urine", "_serum"):
            if base.endswith(suffix):
                base = base.removesuffix(suffix)
                break
        sibling_ids = [
            sid for sid in BIOMARKER_CATALOG
            if (sid.startswith(base + "_") or sid == base) and sid != candidate.biomarker_id
        ]
        for sib_id in sibling_ids:
            sib_value = convert_to_normalized(source.raw_value, sib_id, source.source_unit)
            if sib_value is not None:
                candidate = BIOMARKER_CATALOG[sib_id]
                normalized_value = sib_value
                break
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

    # Determine confidence and reason
    if fuzzy_result:
        best_alias, best_score = fuzzy_result
        if best_score >= 0.85:
            confidence = "medium"
            status = "mapped"
            reason = "fuzzy_match"
        else:
            confidence = "low"
            status = "review_needed"
            reason = "fuzzy_match_low_confidence"
        mapping_rule = f"fuzzy:{best_score:.2f}|source:{source.alias_key}|match:{best_alias}|biomarker:{candidate.biomarker_id}"
    else:
        confidence = "high"
        status = "mapped"
        mapped_by_specimen = len(candidate_ids) > 1
        reason = "mapped_by_alias_and_specimen" if mapped_by_specimen else "mapped_by_unique_alias"
        mapping_rule = f"alias:{source.alias_key}|biomarker:{candidate.biomarker_id}"
        if mapped_by_specimen:
            mapping_rule += f"|specimen:{source.specimen_type}"

    return _empty_record(
        source,
        status=status,
        reason=reason,
        biomarker_id=candidate.biomarker_id,
        biomarker_name=candidate.canonical_name,
        loinc=candidate.loinc,
        mapping_rule=mapping_rule,
        normalized_value=format_decimal(normalized_value),
        normalized_unit=candidate.normalized_unit,
        normalized_reference_range=format_range(normalized_range),
        confidence=confidence,
    )


def _detect_duplicate_row_ids(source_records: list[SourceRecord]) -> list[str]:
    seen: dict[str, list[int]] = {}
    for record in source_records:
        if record.source_row_id:
            seen.setdefault(record.source_row_id, []).append(record.row_number)
    warnings: list[str] = []
    for row_id, row_numbers in seen.items():
        if len(row_numbers) > 1:
            warnings.append(
                f"Duplicate source_row_id '{row_id}' at input rows {row_numbers}"
            )
    return warnings


def normalize_rows(rows: list[dict[str, str]], input_file: str = "", fuzzy_threshold: float = 0.0) -> NormalizationResult:
    source_records = build_source_records(rows)
    normalized_records = [normalize_source_record(record, fuzzy_threshold=fuzzy_threshold) for record in source_records]

    warnings = _detect_duplicate_row_ids(source_records)

    # Plausibility checks on mapped records
    for record in normalized_records:
        if record.mapping_status == "mapped" and record.normalized_value:
            from decimal import Decimal
            try:
                val = Decimal(record.normalized_value)
            except Exception:
                continue
            warning = check_plausibility(record.canonical_biomarker_id, val, record.normalized_unit)
            if warning:
                warnings.append(f"Row {record.source_row_number}: {warning}")

    summary = {
        "total_rows": len(normalized_records),
        "mapped": sum(1 for record in normalized_records if record.mapping_status == "mapped"),
        "review_needed": sum(1 for record in normalized_records if record.mapping_status == "review_needed"),
        "unmapped": sum(1 for record in normalized_records if record.mapping_status == "unmapped"),
        "confidence_breakdown": {
            "high": sum(1 for r in normalized_records if r.match_confidence == "high"),
            "medium": sum(1 for r in normalized_records if r.match_confidence == "medium"),
            "low": sum(1 for r in normalized_records if r.match_confidence == "low"),
            "none": sum(1 for r in normalized_records if r.match_confidence == "none"),
        },
    }

    return NormalizationResult(
        input_file=Path(input_file).name if input_file else "",
        summary=summary,
        records=normalized_records,
        warnings=warnings,
    )

