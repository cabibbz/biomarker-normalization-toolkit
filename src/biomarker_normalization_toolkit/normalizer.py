from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from biomarker_normalization_toolkit.catalog import ALIAS_INDEX, BIOMARKER_CATALOG, normalize_key, normalize_specimen
from biomarker_normalization_toolkit.models import NormalizationResult, NormalizedRecord, RangeValue, SourceRecord
from biomarker_normalization_toolkit.plausibility import check_plausibility
from biomarker_normalization_toolkit.units import convert_to_normalized, format_decimal, format_range, is_inequality_value, normalize_unit, parse_decimal, parse_reference_range, supports_source_unit

# Explicit sibling map: when unit conversion fails for a biomarker, try these
# related biomarkers. Only curated pairs — no prefix-based guessing.
_SIBLING_MAP: dict[str, list[str]] = {
    "neutrophils": ["neutrophils_pct"],
    "neutrophils_pct": ["neutrophils"],
    "lymphocytes": ["lymphocytes_pct"],
    "lymphocytes_pct": ["lymphocytes"],
    "monocytes": ["monocytes_pct"],
    "monocytes_pct": ["monocytes"],
    "eosinophils": ["eosinophils_pct"],
    "eosinophils_pct": ["eosinophils"],
    "basophils": ["basophils_pct"],
    "basophils_pct": ["basophils"],
    "rdw": ["rdw_sd"],
    "rdw_sd": ["rdw"],
    "reticulocytes": ["reticulocyte_absolute"],
    "reticulocyte_absolute": ["reticulocytes"],
    "immature_granulocytes": ["immature_granulocytes_pct"],
    "immature_granulocytes_pct": ["immature_granulocytes"],
    "bands": ["bands_pct"],
    "bands_pct": ["bands"],
    "nrbc": ["nrbc_pct"],
    "nrbc_pct": ["nrbc"],
    "glucose_serum": ["glucose_urine"],
    "glucose_urine": ["glucose_serum"],
    "creatinine": ["creatinine_urine"],
    "creatinine_urine": ["creatinine"],
}

# Keys from source input that are safe to include in provenance output.
# Prevents arbitrary/sensitive fields from leaking into normalized records.
_SAFE_RAW_SOURCE_KEYS = frozenset({
    "source_row_id", "source_test_name", "raw_value", "source_unit",
    "specimen_type", "source_reference_range", "source_lab_name", "source_panel_name",
    "source_loinc",
})

_CONTEXTUAL_ALIAS_OVERRIDES = (
    {
        "alias_key": "oxygen",
        "panel_key": "blood gas",
        "source_unit": "%",
        "specimens": frozenset({"", "whole_blood"}),
        "biomarker_id": "oxygen_saturation",
    },
)

_IMPLICIT_UNIT_BIOMARKERS = frozenset({
    "esr",
    "pdw",
})


def _str_field(row: dict, key: str) -> str:
    """Safely extract a string field from a row dict, coercing non-string values."""
    val = row.get(key, "")
    if val is None:
        return ""
    return str(val).strip()


def build_source_records(rows: list[dict[str, str]]) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            row = {}
        records.append(
            SourceRecord(
                row_number=index,
                source_row_id=_str_field(row, "source_row_id"),
                source_test_name=_str_field(row, "source_test_name"),
                source_loinc=_str_field(row, "source_loinc"),
                raw_value_text=_str_field(row, "raw_value"),
                raw_value=parse_decimal(_str_field(row, "raw_value")),
                source_unit=normalize_unit(_str_field(row, "source_unit")),
                specimen_type=normalize_specimen(_str_field(row, "specimen_type")) or "",
                source_reference_range=_str_field(row, "source_reference_range"),
                source_lab_name=_str_field(row, "source_lab_name"),
                source_panel_name=_str_field(row, "source_panel_name"),
                alias_key=normalize_key(_str_field(row, "source_test_name")),
                raw_source=row,
            )
        )
    return records


def _build_record(
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


def _filter_candidates_by_unit(candidate_ids: list[str], source_unit: str) -> list[str]:
    if not source_unit:
        return candidate_ids
    filtered = [candidate_id for candidate_id in candidate_ids if supports_source_unit(candidate_id, source_unit)]
    return filtered if len(filtered) == 1 else candidate_ids


def _disambiguate_ambiguous_alias_by_reference_range(
    candidate_ids: list[str], source: SourceRecord
) -> tuple[str, RangeValue] | None:
    if source.specimen_type:
        return None

    source_range = parse_reference_range(source.source_reference_range, source.source_unit)
    if source_range is None:
        return None

    candidate_pair = frozenset(candidate_ids)

    if candidate_pair == frozenset({"glucose_serum", "glucose_urine"}) and source_range.unit == "mg/dL":
        # Serum glucose intervals are decisively higher than urine glucose trace ranges.
        if source_range.low >= Decimal("60") and source_range.high >= Decimal("80"):
            return "glucose_serum", source_range
        if source_range.high <= Decimal("20"):
            return "glucose_urine", source_range

    if candidate_pair == frozenset({"creatinine", "creatinine_urine"}) and source_range.unit == "mg/dL":
        # Blood creatinine stays in low single digits; urine creatinine does not.
        if source_range.high <= Decimal("5"):
            return "creatinine", source_range
        if source_range.low >= Decimal("20"):
            return "creatinine_urine", source_range

    return None


def _default_blank_specimen_candidate(
    candidate_ids: list[str], source: SourceRecord
) -> str | None:
    """Preserve whole-blood differential defaults when specimen is absent.

    Body-fluid differential aliases intentionally reuse common labels such as
    "Lymphocytes" and "Monocytes", but historical behavior maps blank-specimen
    percentage rows for these labels to the whole-blood differential family.
    Keep that fallback narrow to percent-based rows with a single whole-blood
    candidate among the ambiguous set.
    """
    if source.specimen_type or normalize_unit(source.source_unit) != "%":
        return None
    whole_blood_base_candidates: set[str] = set()
    whole_blood_pct_candidates: set[str] = set()
    for candidate_id in candidate_ids:
        candidate = BIOMARKER_CATALOG[candidate_id]
        if candidate.allowed_specimens == frozenset({"whole_blood"}) and candidate.normalized_unit == "%":
            whole_blood_pct_candidates.add(candidate_id)
        for sibling_id in _SIBLING_MAP.get(candidate_id, []):
            sibling = BIOMARKER_CATALOG.get(sibling_id)
            if sibling and sibling.allowed_specimens == frozenset({"whole_blood"}) and sibling.normalized_unit == "%":
                whole_blood_pct_candidates.add(sibling_id)
                if candidate.allowed_specimens == frozenset({"whole_blood"}):
                    whole_blood_base_candidates.add(candidate_id)
    if len(whole_blood_base_candidates) == 1:
        return next(iter(whole_blood_base_candidates))
    if len(whole_blood_pct_candidates) == 1:
        return next(iter(whole_blood_pct_candidates))
    return None


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
_LOINC_INDEX.update({
    # Equivalent source LOINCs that we intentionally collapse into the same
    # canonical biomarker output.
    "2339-0": "glucose_serum",
    "2947-0": "sodium",
    "6298-4": "potassium",
})


def _contextual_alias_override(source: SourceRecord) -> str | None:
    panel_key = normalize_key(source.source_panel_name)
    for rule in _CONTEXTUAL_ALIAS_OVERRIDES:
        if source.alias_key != rule["alias_key"]:
            continue
        if source.source_unit != rule["source_unit"]:
            continue
        if panel_key != rule["panel_key"]:
            continue
        if source.specimen_type not in rule["specimens"]:
            continue
        return str(rule["biomarker_id"])
    return None


def _effective_source_unit(source_unit: str, biomarker_id: str) -> tuple[str, bool]:
    if source_unit:
        return source_unit, False
    if biomarker_id in _IMPLICIT_UNIT_BIOMARKERS:
        return BIOMARKER_CATALOG[biomarker_id].normalized_unit, True
    return source_unit, False


def normalize_source_record(source: SourceRecord, *, fuzzy_threshold: float = 0.0) -> NormalizedRecord:
    source_loinc_matched = False
    source_loinc_candidate = _LOINC_INDEX.get(source.source_loinc.strip()) if source.source_loinc else None
    candidate_ids = [source_loinc_candidate] if source_loinc_candidate else ALIAS_INDEX.get(source.alias_key, [])
    if source_loinc_candidate:
        source_loinc_matched = True
    fuzzy_result: tuple[str, float] | None = None
    contextual_override_biomarker_id: str | None = None
    reference_range_disambiguated = False
    reference_range_signal = ""
    source_range: RangeValue | None = None

    # Fallback: use tightly-scoped context rules for vendor labels that are
    # too generic to add as unconditional aliases.
    if not candidate_ids:
        contextual_override_biomarker_id = _contextual_alias_override(source)
        if contextual_override_biomarker_id:
            candidate_ids = [contextual_override_biomarker_id]

    # Fallback: try LOINC code lookup (source test name may be a LOINC code)
    if not candidate_ids:
        loinc_match = _LOINC_INDEX.get(source.source_test_name.strip())
        if loinc_match:
            candidate_ids = [loinc_match]

    # Fallback: strip panel prefix (e.g. "COMPREHENSIVE METABOLIC PANEL:GLUCOSE" -> "GLUCOSE")
    panel_prefix_stripped = False
    if not candidate_ids and ":" in source.source_test_name:
        suffix = source.source_test_name.rsplit(":", 1)[-1].strip()
        if suffix:
            stripped_key = normalize_key(suffix)
            candidate_ids = ALIAS_INDEX.get(stripped_key, [])
            if candidate_ids:
                panel_prefix_stripped = True

    if not candidate_ids and fuzzy_threshold > 0:
        from biomarker_normalization_toolkit.fuzzy import fuzzy_match
        matches = fuzzy_match(source.alias_key, threshold=max(fuzzy_threshold, 0.70))
        if matches:
            best_alias, best_bio_id, best_score = matches[0]
            candidate_ids = ALIAS_INDEX.get(best_alias, [best_bio_id])
            fuzzy_result = (best_alias, best_score)

    if not candidate_ids:
        return _build_record(source, status="unmapped", reason="unknown_alias")

    specimen_filtered = _filter_candidates_by_specimen(candidate_ids, source.specimen_type)

    if len(specimen_filtered) > 1:
        unit_filtered = _filter_candidates_by_unit(specimen_filtered, source.source_unit)
    else:
        unit_filtered = specimen_filtered

    if len(candidate_ids) > 1 and len(unit_filtered) > 1 and not source.specimen_type:
        reference_range_match = _disambiguate_ambiguous_alias_by_reference_range(unit_filtered, source)
        if reference_range_match is not None:
            unit_filtered = [reference_range_match[0]]
            source_range = reference_range_match[1]
            reference_range_disambiguated = True
            reference_range_signal = format_range(source_range)
        else:
            default_candidate = _default_blank_specimen_candidate(specimen_filtered, source)
            if default_candidate is not None:
                unit_filtered = [default_candidate]
            else:
                reason = "fuzzy_match_ambiguous_requires_specimen" if fuzzy_result else "ambiguous_alias_requires_specimen"
                return _build_record(source, status="review_needed", reason=reason)

    if len(unit_filtered) > 1:
        return _build_record(source, status="review_needed", reason="ambiguous_alias_after_specimen_filter")

    if len(unit_filtered) == 0:
        return _build_record(source, status="review_needed", reason="no_candidate_for_specimen")

    unit_disambiguated = len(specimen_filtered) > 1 and len(unit_filtered) == 1
    candidate = BIOMARKER_CATALOG[unit_filtered[0]]

    if source.raw_value is None:
        reason = "inequality_value" if is_inequality_value(source.raw_value_text) else "invalid_raw_value"
        return _build_record(
            source,
            status="review_needed",
            reason=reason,
            biomarker_id=candidate.biomarker_id,
            biomarker_name=candidate.canonical_name,
            loinc=candidate.loinc,
        )

    original_biomarker_id = candidate.biomarker_id
    sibling_redirected = False
    effective_source_unit, implicit_unit_applied = _effective_source_unit(source.source_unit, candidate.biomarker_id)
    normalized_value = convert_to_normalized(source.raw_value, candidate.biomarker_id, effective_source_unit)
    if normalized_value is None and not source_loinc_matched:
        # Try explicit sibling biomarkers (curated pairs, not prefix matching)
        for sib_id in _SIBLING_MAP.get(candidate.biomarker_id, []):
            if sib_id in BIOMARKER_CATALOG:
                sib_effective_source_unit, sib_implicit_unit_applied = _effective_source_unit(source.source_unit, sib_id)
                sib_value = convert_to_normalized(source.raw_value, sib_id, sib_effective_source_unit)
                if sib_value is not None:
                    candidate = BIOMARKER_CATALOG[sib_id]
                    normalized_value = sib_value
                    effective_source_unit = sib_effective_source_unit
                    implicit_unit_applied = sib_implicit_unit_applied
                    sibling_redirected = True
                    break
    if normalized_value is None:
        return _build_record(
            source,
            status="review_needed",
            reason="unsupported_unit_for_biomarker",
            biomarker_id=candidate.biomarker_id,
            biomarker_name=candidate.canonical_name,
            loinc=candidate.loinc,
        )

    if source_range is None:
        source_range = parse_reference_range(source.source_reference_range, effective_source_unit)
    normalized_range = _convert_range(source_range, candidate.biomarker_id)

    # Determine confidence and reason
    if source_loinc_matched:
        confidence = "high"
        status = "mapped"
        reason = "mapped_by_source_loinc"
        mapping_rule = f"source_loinc:{source.source_loinc}|biomarker:{candidate.biomarker_id}"
    elif fuzzy_result:
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
    elif contextual_override_biomarker_id:
        confidence = "medium"
        status = "mapped"
        reason = "mapped_by_contextual_alias"
        mapping_rule = (
            f"contextual_alias:{source.alias_key}|panel:{normalize_key(source.source_panel_name)}"
            f"|unit:{source.source_unit}|biomarker:{candidate.biomarker_id}"
        )
        if source.specimen_type:
            mapping_rule += f"|specimen:{source.specimen_type}"
    elif panel_prefix_stripped:
        confidence = "medium"
        status = "mapped"
        reason = "panel_prefix_stripped"
        mapping_rule = f"panel_strip:{source.alias_key}|biomarker:{candidate.biomarker_id}"
    elif implicit_unit_applied:
        confidence = "medium"
        status = "mapped"
        reason = "mapped_by_alias_and_implicit_unit"
        mapping_rule = (
            f"alias:{source.alias_key}|biomarker:{candidate.biomarker_id}"
            f"|implicit_unit:{effective_source_unit}"
        )
    elif reference_range_disambiguated:
        confidence = "medium"
        status = "mapped"
        reason = "mapped_by_alias_and_reference_range"
        mapping_rule = (
            f"alias:{source.alias_key}|biomarker:{candidate.biomarker_id}"
            f"|reference_range:{reference_range_signal}"
        )
    elif sibling_redirected:
        # Biomarker identity changed via unit-based sibling redirect
        confidence = "medium"
        status = "mapped"
        reason = "sibling_unit_redirect"
        mapping_rule = f"alias:{source.alias_key}|original:{original_biomarker_id}|redirected:{candidate.biomarker_id}|unit:{source.source_unit}"
    elif unit_disambiguated:
        confidence = "high"
        status = "mapped"
        reason = "mapped_by_alias_and_unit"
        mapping_rule = f"alias:{source.alias_key}|biomarker:{candidate.biomarker_id}|unit:{source.source_unit}"
        if source.specimen_type:
            mapping_rule += f"|specimen:{source.specimen_type}"
    else:
        confidence = "high"
        status = "mapped"
        mapped_by_specimen = len(candidate_ids) > 1
        reason = "mapped_by_alias_and_specimen" if mapped_by_specimen else "mapped_by_unique_alias"
        mapping_rule = f"alias:{source.alias_key}|biomarker:{candidate.biomarker_id}"
        if mapped_by_specimen:
            mapping_rule += f"|specimen:{source.specimen_type}"

    return _build_record(
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
        warnings=tuple(warnings),
    )
