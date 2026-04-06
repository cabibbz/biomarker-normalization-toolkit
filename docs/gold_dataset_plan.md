# Gold Dataset Plan

Date: 2026-04-06

## Goal

The first gold dataset should prove that the normalization engine can safely handle:

- direct alias matches
- specimen-disambiguated matches
- deterministic unit conversion
- direct no-conversion matches
- ambiguous aliases
- unknown aliases

## v0 Biomarker Set

Start with:

- serum/plasma glucose
- urine glucose
- hemoglobin A1c
- total cholesterol

## v0 Alias Coverage

Examples that should be covered in early fixtures:

- `Glucose`
- `Glucose, Serum`
- `GLU`
- `Hemoglobin A1c`
- `A1C`
- `Total Cholesterol`
- `Cholesterol, Total`

## Required Fixture Types

### Happy path

- unique alias maps directly
- alias + specimen resolves ambiguity
- supported unit conversion succeeds

### Safety path

- ambiguous alias returns `review_needed`
- unknown alias returns `unmapped`
- unsupported unit returns `review_needed`

### Regression path

- repeated runs produce the same output structure
- provenance remains intact
- summary counts stay stable

## First Fixture Files

- `fixtures/input/v0_sample.csv`
- `fixtures/input/v0_invalid_missing_headers.csv`
- `fixtures/expected/v0_sample_expected.json`

