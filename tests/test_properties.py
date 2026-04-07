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
from biomarker_normalization_toolkit.units import parse_decimal, normalize_unit, convert_to_normalized, parse_reference_range
from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG, normalize_key


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
            # Identity conversion (factor=1) should preserve value within precision
            if bio.normalized_unit:
                self.assertAlmostEqual(float(result), float(value), places=6)

    # --- Reference range properties ---

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=200)
    def test_parse_reference_range_never_crashes(self, text: str) -> None:
        """parse_reference_range should never raise."""
        result = parse_reference_range(text, "mg/dL")
        if result is not None:
            self.assertLessEqual(result.low, result.high)


if __name__ == "__main__":
    unittest.main()
