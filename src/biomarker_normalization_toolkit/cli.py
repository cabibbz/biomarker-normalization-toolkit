from __future__ import annotations

import argparse
from importlib import resources
from pathlib import Path
import sys

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.io_utils import read_input, write_fhir_bundle, write_result, write_summary_report
from biomarker_normalization_toolkit.normalizer import normalize_rows


def build_parser() -> argparse.ArgumentParser:
    from biomarker_normalization_toolkit import __version__
    parser = argparse.ArgumentParser(
        prog="bnt",
        description="Biomarker Normalization Toolkit — normalize lab data into canonical output.",
    )
    parser.add_argument("--version", action="version", version=f"bnt {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show current project direction and repo status.")

    checkpoint = subparsers.add_parser(
        "where-left-off",
        help="Show the latest saved context checkpoint.",
    )
    checkpoint.add_argument(
        "--path",
        default="project_memory/current_context.md",
        help="Path to the current context file.",
    )

    normalize = subparsers.add_parser(
        "normalize",
        help="Normalize a CSV or FHIR JSON file into canonical output.",
    )
    normalize.add_argument(
        "--input",
        required=True,
        help="Path to input file (CSV or FHIR JSON, auto-detected).",
    )
    normalize.add_argument(
        "--output-dir",
        required=True,
        help="Directory where normalized outputs should be written.",
    )
    normalize.add_argument(
        "--emit-fhir",
        action="store_true",
        help="Also write mapped rows as a FHIR Observation bundle.",
    )

    demo = subparsers.add_parser(
        "demo",
        help="Run the bundled sample fixture through the toolkit and write demo outputs.",
    )
    demo.add_argument(
        "--output-dir",
        required=True,
        help="Directory where demo outputs should be written.",
    )

    catalog = subparsers.add_parser(
        "catalog",
        help="Show all supported biomarkers.",
    )
    catalog.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table).",
    )

    analyze = subparsers.add_parser(
        "analyze",
        help="Analyze a file and report coverage gaps.",
    )
    analyze.add_argument(
        "--input",
        required=True,
        help="Path to input file (CSV or FHIR JSON).",
    )

    return parser


def command_status() -> int:
    from biomarker_normalization_toolkit import __version__
    print(f"Biomarker Normalization Toolkit v{__version__}")
    print(f"Biomarkers: {len(BIOMARKER_CATALOG)}")
    print(f"Input formats: CSV, FHIR R4 JSON, HL7 v2.x, C-CDA XML, Excel")
    print(f"Output formats: JSON, CSV, FHIR Bundle, Markdown summary")
    print(f"Deployment: customer-run (CLI, Docker, pip)")
    print("Scope: normalization only - no diagnosis, no hosted PHI")
    return 0


def command_where_left_off(path: str) -> int:
    context_path = Path(path)
    if not context_path.exists():
        print(f"No context file found at: {context_path}")
        return 1

    print(context_path.read_text(encoding="utf-8"))
    return 0


def command_normalize(input_path: str, output_dir: str, emit_fhir: bool) -> int:
    source_path = Path(input_path)
    if not source_path.exists():
        print(f"Input file does not exist: {source_path}", file=sys.stderr)
        return 1

    try:
        rows = read_input(source_path)
        result = normalize_rows(rows, input_file=source_path.name)
        json_path, csv_path = write_result(result, Path(output_dir))
        fhir_path = write_fhir_bundle(result, Path(output_dir)) if emit_fhir else None
        summary_path = write_summary_report(result, Path(output_dir))
    except Exception as exc:
        print(f"Normalization failed: {exc}", file=sys.stderr)
        return 1

    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    print(f"Normalized {result.summary['total_rows']} rows.")
    print(
        f"Mapped={result.summary['mapped']} "
        f"ReviewNeeded={result.summary['review_needed']} "
        f"Unmapped={result.summary['unmapped']}"
    )
    print(f"JSON output: {json_path}")
    print(f"CSV output: {csv_path}")
    print(f"Summary output: {summary_path}")
    if fhir_path is not None:
        print(f"FHIR output: {fhir_path}")
    return 0


def command_catalog(fmt: str) -> int:
    if fmt == "json":
        import json
        entries = []
        for bio_id, bio in sorted(BIOMARKER_CATALOG.items()):
            entries.append({
                "biomarker_id": bio.biomarker_id,
                "canonical_name": bio.canonical_name,
                "loinc": bio.loinc,
                "normalized_unit": bio.normalized_unit,
                "allowed_specimens": sorted(bio.allowed_specimens),
                "aliases": list(bio.aliases),
            })
        print(json.dumps(entries, indent=2))
        return 0

    print(f"{'Biomarker ID':<25s} {'Name':<30s} {'LOINC':<12s} {'Unit':<15s} {'Specimens'}")
    print("-" * 110)
    for bio_id, bio in sorted(BIOMARKER_CATALOG.items()):
        specimens = ", ".join(sorted(bio.allowed_specimens))
        print(f"{bio.biomarker_id:<25s} {bio.canonical_name:<30s} {bio.loinc:<12s} {bio.normalized_unit:<15s} {specimens}")
    print(f"\nTotal: {len(BIOMARKER_CATALOG)} biomarkers")
    return 0


def command_analyze(input_path: str) -> int:
    source_path = Path(input_path)
    if not source_path.exists():
        print(f"Input file does not exist: {source_path}", file=sys.stderr)
        return 1

    try:
        rows = read_input(source_path)
        result = normalize_rows(rows, input_file=source_path.name)
    except Exception as exc:
        print(f"Analysis failed: {exc}", file=sys.stderr)
        return 1

    total = result.summary["total_rows"]
    mapped = result.summary["mapped"]
    review = result.summary["review_needed"]
    unmapped = result.summary["unmapped"]
    mapped_pct = mapped / total * 100 if total else 0

    print(f"Coverage Analysis: {source_path.name}")
    print(f"{'=' * 60}")
    print(f"Total rows:     {total}")
    print(f"Mapped:         {mapped} ({mapped_pct:.1f}%)")
    print(f"Review needed:  {review}")
    print(f"Unmapped:       {unmapped}")

    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    # Mapped biomarker breakdown
    mapped_by_biomarker: dict[str, int] = {}
    for r in result.records:
        if r.mapping_status == "mapped":
            mapped_by_biomarker[r.canonical_biomarker_name] = mapped_by_biomarker.get(r.canonical_biomarker_name, 0) + 1

    if mapped_by_biomarker:
        print(f"\n{'Mapped Biomarkers':}")
        print(f"{'-' * 40}")
        for name, count in sorted(mapped_by_biomarker.items(), key=lambda x: -x[1]):
            print(f"  {count:>5d}  {name}")

    # Unmapped test names
    unmapped_tests: dict[str, int] = {}
    for r in result.records:
        if r.mapping_status == "unmapped":
            unmapped_tests[r.source_test_name] = unmapped_tests.get(r.source_test_name, 0) + 1

    if unmapped_tests:
        print(f"\n{'Unmapped Test Names (top 20)':}")
        print(f"{'-' * 40}")
        for name, count in sorted(unmapped_tests.items(), key=lambda x: -x[1])[:20]:
            print(f"  {count:>5d}  {name}")
        if len(unmapped_tests) > 20:
            print(f"  ... and {len(unmapped_tests) - 20} more unique test names")

    # Review needed breakdown
    review_reasons: dict[str, int] = {}
    for r in result.records:
        if r.mapping_status == "review_needed":
            key = f"{r.source_test_name} ({r.status_reason})"
            review_reasons[key] = review_reasons.get(key, 0) + 1

    if review_reasons:
        print(f"\n{'Review Needed (top 10)':}")
        print(f"{'-' * 40}")
        for key, count in sorted(review_reasons.items(), key=lambda x: -x[1])[:10]:
            print(f"  {count:>5d}  {key}")

    # Unit coverage
    unsupported_units: dict[str, int] = {}
    for r in result.records:
        if r.status_reason == "unsupported_unit_for_biomarker":
            key = f"{r.source_test_name}: {r.source_unit}"
            unsupported_units[key] = unsupported_units.get(key, 0) + 1

    if unsupported_units:
        print(f"\n{'Unsupported Units':}")
        print(f"{'-' * 40}")
        for key, count in sorted(unsupported_units.items(), key=lambda x: -x[1]):
            print(f"  {count:>5d}  {key}")

    return 0


def command_demo(output_dir: str) -> int:
    demo_input = resources.files("biomarker_normalization_toolkit").joinpath("data/v0_sample.csv")
    return command_normalize(str(demo_input), output_dir, emit_fhir=True)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "status":
        return command_status()
    if args.command == "where-left-off":
        return command_where_left_off(args.path)
    if args.command == "normalize":
        return command_normalize(args.input, args.output_dir, args.emit_fhir)
    if args.command == "demo":
        return command_demo(args.output_dir)
    if args.command == "catalog":
        return command_catalog(args.format)
    if args.command == "analyze":
        return command_analyze(args.input)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
