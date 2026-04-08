"""Property-based tests using Hypothesis.

These tests generate random inputs and verify invariants that must ALWAYS hold,
regardless of input data. Unlike deterministic tests that check specific values,
property tests find edge cases automatically.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from biomarker_normalization_toolkit.normalizer import normalize_rows, normalize_source_record, build_source_records
from biomarker_normalization_toolkit.units import (
    CONVERSION_TO_NORMALIZED,
    UNIT_SYNONYMS,
    convert_to_normalized,
    format_decimal,
    normalize_unit,
    parse_decimal,
    parse_reference_range,
)
from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG, normalize_key, normalize_specimen
from biomarker_normalization_toolkit.fhir import build_bundle


class PropertyTests(unittest.TestCase):

    # --- parse_decimal properties ---

    @given(st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False))
    @settings(max_examples=200)
    def test_parse_decimal_roundtrips_floats(self, f: float) -> None:
        """Any finite float formatted as string should parse back."""
        s = f"{f:.6f}"
        result = parse_decimal(s)
        if result is not None:
            self.assertAlmostEqual(float(result), f, places=4)

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=200)
    def test_parse_decimal_never_crashes(self, s: str) -> None:
        """parse_decimal should never raise on any string input."""
        result = parse_decimal(s)
        # Result is either None or a finite Decimal
        if result is not None:
            self.assertTrue(result.is_finite())

    @given(st.integers(min_value=-999999, max_value=999999))
    @settings(max_examples=100)
    def test_parse_decimal_integers(self, n: int) -> None:
        """Integers should always parse correctly."""
        result = parse_decimal(str(n))
        self.assertIsNotNone(result)
        self.assertEqual(int(result), n)

    # --- normalize_unit properties ---

    @given(st.text(min_size=0, max_size=50))
    @settings(max_examples=200)
    def test_normalize_unit_never_crashes(self, s: str) -> None:
        """normalize_unit should never raise on any string."""
        result = normalize_unit(s)
        self.assertIsInstance(result, str)

    @given(st.sampled_from(["mg/dL", "mmol/L", "g/dL", "U/L", "%", "mEq/L", "ng/mL"]))
    def test_normalize_unit_idempotent(self, unit: str) -> None:
        """Normalizing a normalized unit should return the same value."""
        result = normalize_unit(unit)
        result2 = normalize_unit(result)
        self.assertEqual(result, result2)

    # --- normalize_key properties ---

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=200)
    def test_normalize_key_never_crashes(self, s: str) -> None:
        """normalize_key should never raise."""
        result = normalize_key(s)
        self.assertIsInstance(result, str)
        # Result should be lowercase with no leading/trailing whitespace
        self.assertEqual(result, result.strip())
        self.assertEqual(result, result.lower())

    # --- normalize_rows properties ---

    @given(st.lists(
        st.fixed_dictionaries({
            "source_row_id": st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnop0123456789"),
            "source_test_name": st.sampled_from(["Glucose", "HbA1c", "WBC", "Hemoglobin", "UNKNOWN_TEST_XYZ"]),
            "raw_value": st.sampled_from(["100", "5.5", "7.0", "14", "", "abc", ">500"]),
            "source_unit": st.sampled_from(["mg/dL", "%", "K/uL", "g/dL", "", "mmol/L"]),
            "specimen_type": st.sampled_from(["serum", "whole blood", "urine", ""]),
            "source_reference_range": st.sampled_from(["", "70-99 mg/dL", "4.5-11.0"]),
        }),
        min_size=0, max_size=20,
    ))
    @settings(max_examples=100)
    def test_normalize_rows_invariants(self, rows: list[dict]) -> None:
        """normalize_rows must satisfy these invariants for ANY input:
        1. Output has same number of records as input rows
        2. Every record has a valid mapping_status
        3. mapped + review_needed + unmapped = total_rows
        4. No exception is raised
        """
        result = normalize_rows(rows)

        # Invariant 1: record count matches
        self.assertEqual(len(result.records), len(rows))
        self.assertEqual(result.summary["total_rows"], len(rows))

        # Invariant 2: valid statuses
        for r in result.records:
            self.assertIn(r.mapping_status, ("mapped", "review_needed", "unmapped"))
            self.assertIn(r.match_confidence, ("high", "medium", "low", "none"))

        # Invariant 3: counts add up
        total = result.summary["mapped"] + result.summary["review_needed"] + result.summary["unmapped"]
        self.assertEqual(total, result.summary["total_rows"])

    # --- Conversion factor properties ---

    @given(
        st.sampled_from(list(BIOMARKER_CATALOG.keys())),
        st.decimals(min_value=Decimal("0.001"), max_value=Decimal("100000"), allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_conversion_produces_finite_results(self, bio_id: str, value: Decimal) -> None:
        """Converting any finite value should produce a finite result or None."""
        bio = BIOMARKER_CATALOG[bio_id]
        result = convert_to_normalized(value, bio_id, bio.normalized_unit)
        if result is not None:
            self.assertTrue(result.is_finite())

    # --- Reference range properties ---

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=200)
    def test_parse_reference_range_never_crashes(self, text: str) -> None:
        """parse_reference_range should never raise."""
        result = parse_reference_range(text, "mg/dL")
        if result is not None:
            self.assertLessEqual(result.low, result.high)


    # ===================================================================
    # NEW PROPERTY TESTS (10 additional invariants)
    # ===================================================================

    # --- 1. normalize_unit idempotent on ALL known canonical units ---

    @given(st.sampled_from(sorted(set(UNIT_SYNONYMS.values()))))
    @settings(max_examples=200)
    def test_normalize_unit_idempotent_on_all_known_units(self, unit: str) -> None:
        """For every canonical unit in UNIT_SYNONYMS values, normalizing it
        should return itself (fixed point property)."""
        result = normalize_unit(unit)
        self.assertEqual(
            result, unit,
            f"normalize_unit({unit!r}) returned {result!r}, expected {unit!r}"
        )

    # --- 2. format_decimal never produces NaN or Infinity ---

    @given(st.decimals(allow_nan=False, allow_infinity=False))
    @settings(max_examples=200)
    def test_format_decimal_never_produces_nan_or_inf(self, d: Decimal) -> None:
        """For any finite Decimal, format_decimal never returns 'NaN',
        'Infinity', '-Infinity', or 'inf'."""
        result = format_decimal(d)
        forbidden = {"NaN", "nan", "Infinity", "-Infinity", "inf", "-inf", "sNaN"}
        self.assertNotIn(
            result, forbidden,
            f"format_decimal({d!r}) returned forbidden value {result!r}"
        )

    # --- 3. format_decimal roundtrips ---

    @given(st.decimals(
        min_value=Decimal("-1e12"), max_value=Decimal("1e12"),
        allow_nan=False, allow_infinity=False,
    ))
    @settings(max_examples=200)
    def test_format_decimal_roundtrips(self, d: Decimal) -> None:
        """For any Decimal in [-1e12, 1e12], format_decimal then parse_decimal
        should return approximately the same value."""
        formatted = format_decimal(d)
        assume(formatted != "")  # skip if format_decimal returns empty
        parsed = parse_decimal(formatted)
        self.assertIsNotNone(
            parsed,
            f"parse_decimal({formatted!r}) returned None for format_decimal({d!r})"
        )
        # Compare as Decimals to avoid float precision loss for very large values.
        self.assertLessEqual(
            abs(parsed - d), Decimal("0.000001"),
            f"Roundtrip mismatch: {d!r} -> {formatted!r} -> {parsed!r}"
        )

    # --- 4. normalize_rows never drops records ---

    @given(st.lists(
        st.fixed_dictionaries({
            "source_row_id": st.text(min_size=1, max_size=8, alphabet="abcdef0123456789"),
            "source_test_name": st.sampled_from(["Glucose", "ALT", "TSH", "UNKNOWN_ZZZ", "Hemoglobin", ""]),
            "raw_value": st.sampled_from(["50", "0", "-1", "999999", "", "abc", "3.14", ">100"]),
            "source_unit": st.sampled_from(["mg/dL", "U/L", "mIU/L", "%", "", "g/dL", "mmol/L"]),
            "specimen_type": st.sampled_from(["serum", "plasma", "urine", "whole blood", ""]),
            "source_reference_range": st.sampled_from(["", "10-50", "0-100 mg/dL"]),
        }),
        min_size=0, max_size=15,
    ))
    @settings(max_examples=200)
    def test_normalize_rows_never_drops_records(self, rows: list[dict]) -> None:
        """For any list of row dicts, the output record count always equals
        the input row count. No record is silently dropped."""
        result = normalize_rows(rows)
        self.assertEqual(
            len(result.records), len(rows),
            f"Expected {len(rows)} records, got {len(result.records)}"
        )

    # --- 5. normalize_rows summary is consistent ---

    @given(st.lists(
        st.fixed_dictionaries({
            "source_row_id": st.text(min_size=1, max_size=8, alphabet="abcdef0123456789"),
            "source_test_name": st.sampled_from(["Glucose", "WBC", "Creatinine", "FAKE_BIOMARKER", ""]),
            "raw_value": st.sampled_from(["100", "5.5", "", "xyz", "0.001"]),
            "source_unit": st.sampled_from(["mg/dL", "K/uL", "%", ""]),
            "specimen_type": st.sampled_from(["serum", ""]),
            "source_reference_range": st.sampled_from(["", "70-99"]),
        }),
        min_size=0, max_size=15,
    ))
    @settings(max_examples=200)
    def test_normalize_rows_summary_is_consistent(self, rows: list[dict]) -> None:
        """For any input, mapped + review_needed + unmapped = total_rows."""
        result = normalize_rows(rows)
        s = result.summary
        self.assertEqual(
            s["mapped"] + s["review_needed"] + s["unmapped"],
            s["total_rows"],
            f"Summary counts do not add up: {s}"
        )

    # --- 6. confidence breakdown is consistent ---

    @given(st.lists(
        st.fixed_dictionaries({
            "source_row_id": st.text(min_size=1, max_size=8, alphabet="abcdef0123456789"),
            "source_test_name": st.sampled_from(["Glucose", "HbA1c", "ALT", "NONEXISTENT"]),
            "raw_value": st.sampled_from(["100", "5.5", "", "bad"]),
            "source_unit": st.sampled_from(["mg/dL", "%", "U/L", ""]),
            "specimen_type": st.sampled_from(["serum", ""]),
            "source_reference_range": st.sampled_from(["", "70-99"]),
        }),
        min_size=0, max_size=15,
    ))
    @settings(max_examples=200)
    def test_normalize_rows_confidence_breakdown_is_consistent(self, rows: list[dict]) -> None:
        """For any input, high + medium + low + none = total_rows in
        the confidence_breakdown."""
        result = normalize_rows(rows)
        cb = result.summary["confidence_breakdown"]
        total = cb["high"] + cb["medium"] + cb["low"] + cb["none"]
        self.assertEqual(
            total, result.summary["total_rows"],
            f"Confidence breakdown {cb} does not sum to {result.summary['total_rows']}"
        )

    # --- 7. build_bundle entry count <= mapped count ---

    @given(st.lists(
        st.fixed_dictionaries({
            "source_row_id": st.text(min_size=1, max_size=8, alphabet="abcdef0123456789"),
            "source_test_name": st.sampled_from(["Glucose", "HbA1c", "WBC", "UNKNOWN_XYZ"]),
            "raw_value": st.sampled_from(["100", "5.5", "7.0", "", "abc"]),
            "source_unit": st.sampled_from(["mg/dL", "%", "K/uL", ""]),
            "specimen_type": st.sampled_from(["serum", ""]),
            "source_reference_range": st.sampled_from(["", "70-99 mg/dL"]),
        }),
        min_size=0, max_size=15,
    ))
    @settings(max_examples=200)
    def test_build_bundle_entry_count_lte_mapped(self, rows: list[dict]) -> None:
        """For any NormalizationResult, the FHIR bundle entry count should be
        <= the mapped count (unmapped/review_needed records are excluded)."""
        result = normalize_rows(rows)
        bundle = build_bundle(result)
        mapped_count = result.summary["mapped"]
        entry_count = len(bundle["entry"])
        self.assertLessEqual(
            entry_count, mapped_count,
            f"Bundle has {entry_count} entries but only {mapped_count} mapped records"
        )

    # --- 8. convert_to_normalized identity for factor=1 ---

    @given(
        st.sampled_from(list(BIOMARKER_CATALOG.keys())),
        st.decimals(
            min_value=Decimal("0.001"), max_value=Decimal("100000"),
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=200)
    def test_convert_to_normalized_identity(self, bio_id: str, value: Decimal) -> None:
        """For any biomarker, converting a value that is already in the
        normalized unit (factor=1) should return the same value."""
        bio = BIOMARKER_CATALOG[bio_id]
        norm_unit = bio.normalized_unit
        factors = CONVERSION_TO_NORMALIZED.get(bio_id, {})
        # Only test if the normalized unit has factor 1
        if norm_unit in factors and factors[norm_unit] == Decimal("1"):
            result = convert_to_normalized(value, bio_id, norm_unit)
            self.assertIsNotNone(result, f"Identity conversion returned None for {bio_id}")
            # The multiplication runs inside a localcontext(prec=28), so very
            # high-precision Decimals may be rounded. Use approximate comparison.
            self.assertAlmostEqual(
                float(result), float(value), places=6,
                msg=f"Identity conversion changed value: {value!r} -> {result!r} for {bio_id}"
            )

    # --- 9. parse_decimal never returns non-finite ---

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=200)
    def test_parse_decimal_never_returns_non_finite(self, s: str) -> None:
        """For any string input, if parse_decimal returns a Decimal it must
        be finite (not NaN, not Infinity)."""
        result = parse_decimal(s)
        if result is not None:
            self.assertIsInstance(result, Decimal)
            self.assertTrue(
                result.is_finite(),
                f"parse_decimal({s!r}) returned non-finite Decimal: {result!r}"
            )

    # --- 10. normalize_specimen is lowercase with no whitespace padding ---

    @given(st.text(min_size=0, max_size=80))
    @settings(max_examples=200)
    def test_normalize_specimen_is_lowercase(self, s: str) -> None:
        """For any string input, normalize_specimen returns either None or a
        lowercase string with no leading/trailing whitespace."""
        result = normalize_specimen(s)
        if result is not None:
            self.assertIsInstance(result, str)
            self.assertEqual(
                result, result.lower(),
                f"normalize_specimen({s!r}) returned non-lowercase: {result!r}"
            )
            self.assertEqual(
                result, result.strip(),
                f"normalize_specimen({s!r}) has leading/trailing whitespace: {result!r}"
            )


if __name__ == "__main__":
    unittest.main()
