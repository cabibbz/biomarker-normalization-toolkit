from __future__ import annotations

import re

from biomarker_normalization_toolkit.models import NormalizationResult


def _markdown_text(value: object) -> str:
    return " ".join(str(value).split())


def _markdown_code(value: object) -> str:
    text = _markdown_text(value)
    if not text:
        return "` `"
    max_backtick_run = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (max_backtick_run + 1)
    if text.startswith("`") or text.endswith("`"):
        text = f" {text} "
    return f"{fence}{text}{fence}"


def build_summary_report(result: NormalizationResult) -> str:
    mapped_examples = [record for record in result.records if record.mapping_status == "mapped"][:5]
    review_examples = [record for record in result.records if record.mapping_status == "review_needed"][:5]
    unmapped_examples = [record for record in result.records if record.mapping_status == "unmapped"][:5]

    lines = [
        "# Normalization Summary",
        "",
        f"Input file: {_markdown_code(result.input_file)}",
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
                f"- {_markdown_code(record.source_test_name)} -> {_markdown_code(record.canonical_biomarker_name)} "
                f"({record.normalized_value} {record.normalized_unit})"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Example Review-Needed Rows", ""])
    if review_examples:
        for record in review_examples:
            lines.append(
                f"- {_markdown_code(record.source_test_name)} -> {_markdown_code(record.status_reason)}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Example Unmapped Rows", ""])
    if unmapped_examples:
        for record in unmapped_examples:
            lines.append(
                f"- {_markdown_code(record.source_test_name)} -> {_markdown_code(record.status_reason)}"
            )
    else:
        lines.append("- None")

    if result.warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in result.warnings[:20]:
            lines.append(f"- {_markdown_text(warning)}")
        if len(result.warnings) > 20:
            lines.append(f"- ... and {len(result.warnings) - 20} more warnings")

    lines.extend([
        "",
        "## Notes",
        "",
        "- This report is derived from deterministic normalization output.",
        "- Review-needed and unmapped rows should be inspected before downstream use.",
        "",
    ])
    return "\n".join(lines)
