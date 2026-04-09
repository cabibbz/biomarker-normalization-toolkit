from __future__ import annotations

import argparse
import logging
from importlib import resources
from pathlib import Path
import sys

from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG, load_custom_aliases
from biomarker_normalization_toolkit.io_utils import read_input, write_fhir_bundle, write_result, write_summary_report
from biomarker_normalization_toolkit.normalizer import normalize_rows

logger = logging.getLogger("bnt.cli")


def _user_friendly_error(exc: Exception) -> str:
    """Strip filesystem paths and module names from exception messages."""
    msg = str(exc)
    # Detect messages that contain filesystem paths (common leak pattern)
    # e.g. "No such file: /tmp/tmpABCD.csv" or "Error in C:\\Users\\..."
    import re
    # Remove absolute filesystem paths (Unix and Windows)
    msg = re.sub(r'[A-Za-z]:\\[\w\\.\-_ ]+', '<file>', msg)
    msg = re.sub(r'/(?:tmp|home|usr|var|etc|opt|private)[\w/.\-_ ]*', '<file>', msg)
    # Remove Python module references like "biomarker_normalization_toolkit.foo"
    msg = re.sub(r'biomarker_normalization_toolkit\.\w+', '<internal>', msg)
    return msg


def build_parser() -> argparse.ArgumentParser:
    from biomarker_normalization_toolkit import __version__
    parser = argparse.ArgumentParser(
        prog="bnt",
        description="Biomarker Normalization Toolkit - normalize lab data into canonical output.",
    )
    parser.add_argument("--version", action="version", version=f"bnt {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show current project direction and repo status.")

    normalize = subparsers.add_parser(
        "normalize",
        help="Normalize a supported lab file into canonical output.",
    )
    normalize.add_argument(
        "--input",
        required=True,
        help="Path to input file (CSV, FHIR JSON, HL7, C-CDA XML, or Excel; auto-detected).",
    )
    normalize.add_argument(
        "--output-dir",
        required=True,
        help="Directory where normalized outputs should be written.",
    )
    normalize.add_argument(
        "--aliases",
        default=None,
        help="Path to custom alias JSON file to merge before normalizing.",
    )
    normalize.add_argument(
        "--emit-fhir",
        action="store_true",
        help="Also write mapped rows as a FHIR Observation bundle.",
    )
    normalize.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=0.0,
        help="Enable fuzzy alias matching (0.0=disabled, 0.85=recommended). Requires rapidfuzz.",
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

    batch = subparsers.add_parser(
        "batch",
        help="Normalize all supported files in a directory.",
    )
    batch.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing input files.",
    )
    batch.add_argument(
        "--output-dir",
        required=True,
        help="Directory where per-file output subdirectories will be created.",
    )
    batch.add_argument(
        "--aliases",
        default=None,
        help="Path to custom alias JSON file.",
    )
    batch.add_argument(
        "--emit-fhir",
        action="store_true",
        help="Also write FHIR bundles for each file.",
    )
    batch.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=0.0,
        help="Enable fuzzy alias matching (0.0=disabled, 0.85=recommended).",
    )

    serve = subparsers.add_parser(
        "serve",
        help="Start the REST API server.",
    )
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1). Use 0.0.0.0 for all interfaces.",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000).",
    )

    analyze = subparsers.add_parser(
        "analyze",
        help="Analyze a file and report coverage gaps.",
    )
    analyze.add_argument(
        "--input",
        required=True,
        help="Path to input file (CSV, FHIR JSON, HL7, C-CDA XML, or Excel).",
    )
    analyze.add_argument(
        "--aliases",
        default=None,
        help="Path to custom alias JSON file to merge before analyzing.",
    )
    analyze.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=0.0,
        help="Enable fuzzy alias matching (0.0=disabled, 0.85=recommended).",
    )

    return parser


def command_status() -> int:
    from biomarker_normalization_toolkit import __version__
    print(f"Biomarker Normalization Toolkit v{__version__}")
    print(f"Biomarkers: {len(BIOMARKER_CATALOG)}")
    print(f"Input formats: CSV, FHIR R4 JSON, HL7 v2.x, C-CDA XML, Excel")
    print(f"Output formats: JSON, CSV, FHIR Bundle, Markdown summary")
    print("Deployment: self-hosted, open-source (CLI, Docker, pip)")
    print("Scope: normalization only - no diagnosis, no hosted PHI")
    return 0


def _load_aliases(aliases_path: str | None) -> bool:
    """Load custom aliases. Returns False if file was specified but missing."""
    if not aliases_path:
        return True
    alias_path = Path(aliases_path)
    if not alias_path.exists():
        print(f"Alias file does not exist: {alias_path}", file=sys.stderr)
        return False
    added = load_custom_aliases(alias_path)
    print(f"Loaded {added} custom aliases from {alias_path}")
    return True


def command_normalize(input_path: str, output_dir: str, emit_fhir: bool, aliases_path: str | None = None, fuzzy_threshold: float = 0.0) -> int:
    if not _load_aliases(aliases_path):
        return 1

    source_path = Path(input_path)
    if not source_path.exists():
        print(f"Input file does not exist: {source_path}", file=sys.stderr)
        return 1

    try:
        rows = read_input(source_path)
        result = normalize_rows(rows, input_file=source_path.name, fuzzy_threshold=fuzzy_threshold)
        json_path, csv_path = write_result(result, Path(output_dir))
        fhir_path = write_fhir_bundle(result, Path(output_dir)) if emit_fhir else None
        summary_path = write_summary_report(result, Path(output_dir))
        # Derived metrics and optimal ranges
        from biomarker_normalization_toolkit.derived import compute_derived_metrics
        from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges, summarize_optimal
        derived = compute_derived_metrics(result)
        optimal_evals = evaluate_optimal_ranges(result)
        optimal_summary = summarize_optimal(optimal_evals)
    except Exception as exc:
        logger.debug("Normalization failed", exc_info=True)
        print(f"Normalization failed: {_user_friendly_error(exc)}", file=sys.stderr)
        return 1

    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    print(f"Normalized {result.summary['total_rows']} rows.")
    print(
        f"Mapped={result.summary['mapped']} "
        f"ReviewNeeded={result.summary['review_needed']} "
        f"Unmapped={result.summary['unmapped']}"
    )
    if derived:
        print(f"Derived metrics: {len(derived)}")
    if optimal_evals:
        print(f"Optimal range: {optimal_summary['optimal']}/{optimal_summary['total_evaluated']} biomarkers in optimal range ({optimal_summary['optimal_percentage']}%)")
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


def command_analyze(input_path: str, aliases_path: str | None = None, fuzzy_threshold: float = 0.0) -> int:
    if not _load_aliases(aliases_path):
        return 1

    source_path = Path(input_path)
    if not source_path.exists():
        print(f"Input file does not exist: {source_path}", file=sys.stderr)
        return 1

    try:
        rows = read_input(source_path)
        result = normalize_rows(rows, input_file=source_path.name, fuzzy_threshold=fuzzy_threshold)
    except Exception as exc:
        logger.debug("Analysis failed", exc_info=True)
        print(f"Analysis failed: {_user_friendly_error(exc)}", file=sys.stderr)
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


SUPPORTED_EXTENSIONS = {".csv", ".json", ".hl7", ".oru", ".xml", ".xlsx", ".xls"}


def command_batch(input_dir: str, output_dir: str, emit_fhir: bool, aliases_path: str | None = None, fuzzy_threshold: float = 0.0) -> int:
    if not _load_aliases(aliases_path):
        return 1

    input_path = Path(input_dir)
    if not input_path.is_dir():
        print(f"Input directory does not exist: {input_path}", file=sys.stderr)
        return 1

    files = sorted(
        f for f in input_path.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not files:
        print(f"No supported files found in {input_path}", file=sys.stderr)
        return 1

    out_base = Path(output_dir)
    total_mapped = 0
    total_rows = 0
    errors: list[str] = []

    for source_file in files:
        file_out = out_base / source_file.stem
        try:
            rows = read_input(source_file)
            result = normalize_rows(rows, input_file=source_file.name, fuzzy_threshold=fuzzy_threshold)
            write_result(result, file_out)
            if emit_fhir:
                write_fhir_bundle(result, file_out)
            write_summary_report(result, file_out)
            total_mapped += result.summary["mapped"]
            total_rows += result.summary["total_rows"]
            pct = result.summary["mapped"] / result.summary["total_rows"] * 100 if result.summary["total_rows"] else 0
            print(f"  {source_file.name}: {result.summary['mapped']}/{result.summary['total_rows']} mapped ({pct:.0f}%)")
        except Exception as exc:
            safe_msg = _user_friendly_error(exc)
            logger.debug("Batch error for %s", source_file.name, exc_info=True)
            errors.append(f"{source_file.name}: {safe_msg}")
            print(f"  {source_file.name}: ERROR - {safe_msg}", file=sys.stderr)

    overall_pct = total_mapped / total_rows * 100 if total_rows else 0
    print(f"\nBatch complete: {len(files)} files, {total_rows} total rows, {total_mapped} mapped ({overall_pct:.1f}%)")
    if errors:
        print(f"{len(errors)} files had errors.", file=sys.stderr)

    return 1 if errors else 0


def command_serve(host: str, port: int) -> int:
    try:
        import uvicorn
        from biomarker_normalization_toolkit.api import app
    except ImportError:
        print(
            "REST API dependencies not installed.\n"
            "Install with: pip install biomarker-normalization-toolkit[rest]",
            file=sys.stderr,
        )
        return 1

    print(f"Starting BNT API server on {host}:{port}")
    print(f"Docs: http://{host}:{port}/docs")
    uvicorn.run(app, host=host, port=port)
    return 0


def command_demo(output_dir: str) -> int:
    demo_input = resources.files("biomarker_normalization_toolkit").joinpath("data/v0_sample.csv")
    return command_normalize(str(demo_input), output_dir, emit_fhir=True)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "status":
        return command_status()
    if args.command == "normalize":
        return command_normalize(args.input, args.output_dir, args.emit_fhir, args.aliases, args.fuzzy_threshold)
    if args.command == "demo":
        return command_demo(args.output_dir)
    if args.command == "batch":
        return command_batch(args.input_dir, args.output_dir, args.emit_fhir, args.aliases, args.fuzzy_threshold)
    if args.command == "serve":
        return command_serve(args.host, args.port)
    if args.command == "catalog":
        return command_catalog(args.format)
    if args.command == "analyze":
        return command_analyze(args.input, args.aliases, args.fuzzy_threshold)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
