from __future__ import annotations

from biomarker_normalization_toolkit.models import NormalizationResult


def build_summary_report(result: NormalizationResult) -> str:
    mapped_examples = [record for record in result.records if record.mapping_status == "mapped"][:5]
    review_examples = [record for record in result.records if record.mapping_status == "review_needed"][:5]
    unmapped_examples = [record for record in result.records if record.mapping_status == "unmapped"][:5]

    lines = [
        "# Normalization Summary",
        "",
        f"Input file: `{result.input_file}`",
        "",
        "## Counts",
        "",
        f"- Total rows: {result.summary['total_rows']}",
        f"- Mapped: {result.summary['mapped']}",
        f"- Review needed: {result.summary['review_needed']}",
        f"- Unmapped: {result.summary['unmapped']}",
        "",
        "## Example Mapped Rows",
        "",
    ]

    if mapped_examples:
        for record in mapped_examples:
            lines.append(
                f"- `{record.source_test_name}` -> `{record.canonical_biomarker_name}` "
                f"({record.normalized_value} {record.normalized_unit})"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Example Review-Needed Rows", ""])
    if review_examples:
        for record in review_examples:
            lines.append(
                f"- `{record.source_test_name}` -> `{record.status_reason}`"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Example Unmapped Rows", ""])
    if unmapped_examples:
        for record in unmapped_examples:
            lines.append(
                f"- `{record.source_test_name}` -> `{record.status_reason}`"
            )
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Notes",
        "",
        "- This report is derived from deterministic normalization output.",
        "- Review-needed and unmapped rows should be inspected before downstream use.",
        "",
    ])
    return "\n".join(lines)
