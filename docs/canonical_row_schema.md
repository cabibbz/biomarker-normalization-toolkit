# Canonical Row Schema

Date: 2026-04-06

This schema is locked for `v0` of the normalization pipeline.

## Input CSV Columns

Required:

- `source_row_id`
- `source_test_name`
- `raw_value`
- `source_unit`
- `specimen_type`
- `source_reference_range`

Optional:

- `source_lab_name`
- `source_panel_name`

## Normalized Record Fields

Each normalized record must contain:

- `source_row_number`
- `source_row_id`
- `source_lab_name`
- `source_panel_name`
- `source_test_name`
- `alias_key`
- `raw_value`
- `source_unit`
- `specimen_type`
- `source_reference_range`
- `canonical_biomarker_id`
- `canonical_biomarker_name`
- `loinc`
- `mapping_status`
- `match_confidence`
- `status_reason`
- `mapping_rule`
- `normalized_value`
- `normalized_unit`
- `normalized_reference_range`
- `provenance`

## Field Rules

### Mapping fields

- `mapping_status` is one of `mapped`, `review_needed`, `unmapped`
- `match_confidence` is one of `high`, `none`
- `status_reason` explains why the row is mapped, ambiguous, or unmapped
- `mapping_rule` records the deterministic rule used when a row maps

### Provenance

`provenance` must contain:

- `source_row_number`
- `source_row_id`
- `source_alias_key`
- `raw_source`

### Safety rule

If a row is ambiguous or unsupported, the system must:

- keep the original source fields
- return `review_needed` or `unmapped`
- never guess a canonical biomarker

## JSON Output Envelope

The normalized JSON output must contain:

- `schema_version`
- `input_file`
- `summary`
- `records`

## Summary Fields

The output summary must contain:

- `total_rows`
- `mapped`
- `review_needed`
- `unmapped`

