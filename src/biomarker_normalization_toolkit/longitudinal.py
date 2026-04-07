"""Longitudinal tracking: compare biomarker values across time points.

Computes deltas, trends, and velocity of change between two NormalizationResults
representing the same patient at different time points.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from biomarker_normalization_toolkit.models import NormalizationResult
from biomarker_normalization_toolkit.optimal_ranges import OPTIMAL_RANGES


def _get_mapped_values(result: NormalizationResult) -> dict[str, Decimal]:
    """Extract biomarker_id -> normalized_value for all mapped records."""
    values: dict[str, Decimal] = {}
    for record in result.records:
        if record.mapping_status == "mapped" and record.normalized_value:
            try:
                values[record.canonical_biomarker_id] = Decimal(record.normalized_value)
            except Exception:
                continue
    return values


def compare_results(
    before: NormalizationResult,
    after: NormalizationResult,
    days_between: float | None = None,
) -> dict[str, Any]:
    """Compare two NormalizationResults and compute deltas.

    Args:
        before: Earlier result (baseline).
        after: Later result (follow-up).
        days_between: Days between the two tests (for velocity calculation).

    Returns:
        Dict with per-biomarker deltas and summary.
    """
    before_vals = _get_mapped_values(before)
    after_vals = _get_mapped_values(after)

    common = set(before_vals.keys()) & set(after_vals.keys())
    deltas: list[dict[str, Any]] = []

    improved = 0
    worsened = 0
    stable = 0

    for bio_id in sorted(common):
        old = before_vals[bio_id]
        new = after_vals[bio_id]
        abs_delta = new - old
        pct_delta: float | None = float(abs_delta / old * 100) if old != 0 else None

        # Determine direction relative to optimal ranges
        optimal = OPTIMAL_RANGES.get(bio_id)
        if optimal:
            opt_low, opt_high, unit, _ = optimal
            old_status = "optimal" if opt_low <= old <= opt_high else ("below" if old < opt_low else "above")
            new_status = "optimal" if opt_low <= new <= opt_high else ("below" if new < opt_low else "above")

            if old_status != "optimal" and new_status == "optimal":
                direction = "improved"
                improved += 1
            elif old_status == "optimal" and new_status != "optimal":
                direction = "worsened"
                worsened += 1
            elif old_status == new_status:
                direction = "stable"
                stable += 1
            elif new_status == "optimal":
                direction = "improved"
                improved += 1
            else:
                # Both outside optimal — check if moving toward optimal
                old_dist = min(abs(float(old - opt_low)), abs(float(old - opt_high)))
                new_dist = min(abs(float(new - opt_low)), abs(float(new - opt_high)))
                if new_dist < old_dist:
                    direction = "improving"
                    improved += 1
                elif new_dist > old_dist:
                    direction = "worsening"
                    worsened += 1
                else:
                    direction = "stable"
                    stable += 1
        else:
            direction = "unknown"
            stable += 1

        entry: dict[str, Any] = {
            "biomarker_id": bio_id,
            "before": str(old),
            "after": str(new),
            "absolute_delta": str(abs_delta),
            "percent_delta": round(pct_delta, 1),
            "direction": direction,
        }

        if days_between and days_between > 0:
            velocity_per_month = float(abs_delta) / days_between * 30
            entry["velocity_per_month"] = round(velocity_per_month, 3)

        deltas.append(entry)

    total = improved + worsened + stable
    return {
        "biomarkers_compared": len(common),
        "biomarkers_only_in_before": len(before_vals) - len(common),
        "biomarkers_only_in_after": len(after_vals) - len(common),
        "improved": improved,
        "worsened": worsened,
        "stable": stable,
        "improvement_rate": round(improved / total * 100, 1) if total else 0,
        "days_between": days_between,
        "deltas": deltas,
    }
