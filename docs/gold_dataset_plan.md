# Fixture Coverage Plan

This document describes the public fixture roadmap for expanding parser and normalization coverage. It is intended to help contributors add realistic test data in small, reviewable waves.

## Goal

The first fixture set should prove that the normalization engine can safely handle:

- direct alias matches
- specimen-disambiguated matches
- deterministic unit conversion
- direct no-conversion matches
- ambiguous aliases
- unknown aliases

## Initial Biomarker Set

Start with:

- serum/plasma glucose
- urine glucose
- hemoglobin A1c
- total cholesterol

## Initial Alias Coverage

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

## Coverage Expansion Wave 1

Add the next coverage fixture around common lipid and renal markers:

- LDL cholesterol
- HDL cholesterol
- triglycerides
- creatinine

Wave 1 should prove:

- additional mmol/L to mg/dL conversions
- creatinine `umol/L` to `mg/dL` conversion
- serum/plasma specimen handling for the new biomarkers
- urine creatinine specimen-disambiguated mapping

Wave 1 fixture file:

- `fixtures/input/coverage_wave_1.csv`

Vendor-style alias and edge-case fixture:

- `fixtures/input/vendor_alias_edge_cases.csv`

## Coverage Expansion Wave 2

Liver panel, thyroid, renal expansion, inflammation, and CBC:

- ALT, AST, ALP, total bilirubin, albumin
- TSH, free T4
- BUN
- hs-CRP
- WBC, hemoglobin, hematocrit, platelets

Wave 2 should prove:

- U/L identity and IU/L synonym handling
- umol/L to mg/dL conversion for bilirubin
- g/L to g/dL conversion for albumin and hemoglobin
- pmol/L to ng/dL conversion for free T4
- mmol/L to mg/dL conversion for BUN
- mg/dL to mg/L conversion for CRP
- L/L to % conversion for hematocrit
- 10^9/L to K/uL identity for WBC and platelets

Wave 2 fixture file:

- `fixtures/input/coverage_wave_2.csv`

## Coverage Expansion Wave 3

Vitamins and minerals:

- vitamin D 25-OH, vitamin B12, folate
- iron, ferritin, magnesium

Wave 3 should prove:

- nmol/L to ng/mL conversion for vitamin D
- pmol/L to pg/mL conversion for B12
- nmol/L to ng/mL conversion for folate (different MW)
- umol/L to ug/dL conversion for iron
- mmol/L to mg/dL conversion for magnesium

Wave 3 fixture file:

- `fixtures/input/coverage_wave_3.csv`
