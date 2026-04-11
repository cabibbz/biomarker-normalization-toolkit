from __future__ import annotations

import argparse
import json
import logging
from importlib import resources
from pathlib import Path
import sys

from biomarker_normalization_toolkit import (
    list_catalog,
    list_catalog_metadata,
    load_catalog_metadata,
    lookup as lookup_biomarker,
    validate_custom_aliases,
)
from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG, build_alias_index, read_custom_aliases
from biomarker_normalization_toolkit.io_utils import read_input, write_fhir_bundle, write_result, write_summary_report
from biomarker_normalization_toolkit.normalizer import normalize_rows, validate_fuzzy_threshold

logger = logging.getLogger("bnt.cli")


def _module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
    except ImportError:
        return False
    return True


def _rest_dependencies_available() -> bool:
    return all(
        _module_available(module_name)
        for module_name in ("fastapi", "uvicorn", "pydantic", "python_multipart")
    )


def _load_rest_components() -> tuple[object | None, object | None, Exception | None]:
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover - exercised via command wrappers
        return None, None, exc

    try:
        from biomarker_normalization_toolkit.api import app
    except Exception as exc:  # pragma: no cover - exercised via command wrappers
        return None, None, exc

    return uvicorn, app, None


def _user_friendly_error(exc: Exception) -> str:
    """Strip filesystem paths and module names from exception messages."""
    msg = str(exc)
    # Detect messages that contain filesystem paths (common leak pattern)
    # e.g. "No such file: /tmp/tmpABCD.csv" or "Error in C:\\Users\\..."
    import re
    # Remove absolute filesystem paths (Unix and Windows)
    msg = re.sub(r'\\\\[^\s\\]+\\[^\s]+', '<file>', msg)
    msg = re.sub(r'[A-Za-z]:\\[\w\\.\-_ ]+', '<file>', msg)
    msg = re.sub(r'/(?:Users|tmp|home|usr|var|etc|opt|private|Volumes)[\w/.\-_ ]*', '<file>', msg)
    # Remove Python module references like "biomarker_normalization_toolkit.foo"
    msg = re.sub(r'biomarker_normalization_toolkit\.\w+', '<internal>', msg)
    return msg


def _display_text(value: object) -> str:
    text = " ".join(str(value).split())
    return "".join(ch if ch.isprintable() else "?" for ch in text)


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
        help="Path to input file (CSV, FHIR JSON, HL7, C-CDA XML, or Excel with openpyxl installed; auto-detected).",
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
        choices=["table", "json", "metadata-json"],
        default="table",
        help="Output format (default: table).",
    )
    catalog.add_argument(
        "--search",
        default=None,
        help="Filter catalog entries by biomarker ID, canonical name, LOINC, or alias.",
    )
    catalog.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of catalog entries to show.",
    )
    catalog.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip the first N catalog entries after filtering.",
    )

    aliases = subparsers.add_parser(
        "aliases",
        help="Validate a custom alias JSON file without loading it into global state.",
    )
    aliases.add_argument(
        "--input",
        required=True,
        help="Path to custom alias JSON file.",
    )
    aliases.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table).",
    )

    lookup = subparsers.add_parser(
        "lookup",
        help="Look up candidate biomarkers for a test name.",
    )
    lookup.add_argument(
        "--test-name",
        required=True,
        help="Source test name or alias to look up.",
    )
    lookup.add_argument(
        "--specimen",
        default="",
        help="Specimen type to use when filtering ambiguous aliases.",
    )
    lookup.add_argument(
        "--aliases",
        default=None,
        help="Path to custom alias JSON file to apply only to this lookup call.",
    )
    lookup.add_argument(
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
        help="Path to input file (CSV, FHIR JSON, HL7, C-CDA XML, or Excel with openpyxl installed).",
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
    excel_status = "available" if _module_available("openpyxl") else "optional via [excel]"
    fuzzy_status = "available" if _module_available("rapidfuzz") else "optional via [fuzzy]"
    rest_status = "available" if _rest_dependencies_available() else "optional via [rest]"
    print(f"Biomarker Normalization Toolkit v{__version__}")
    print(f"Biomarkers: {len(BIOMARKER_CATALOG)}")
    print(f"Input formats: CSV, FHIR R4 JSON, HL7 v2.x, C-CDA XML, Excel ({excel_status})")
    print(f"Output formats: JSON, CSV, FHIR Bundle, Markdown summary")
    print(f"Optional extras: fuzzy matching ({fuzzy_status}), REST server ({rest_status})")
    print("Deployment: self-hosted, open-source (CLI, Docker, pip)")
    print("Scope: normalization only - no diagnosis, no hosted PHI")
    return 0


def _load_aliases(aliases_path: str | None, announce: bool = True) -> dict[str, list[str]] | None:
    """Read custom aliases without mutating global process state."""
    if not aliases_path:
        return None
    alias_path = Path(aliases_path)
    if not alias_path.exists():
        print(f"Alias file does not exist: {_display_text(alias_path)}", file=sys.stderr)
        return None
    custom_aliases = read_custom_aliases(alias_path)
    added = sum(len(aliases) for aliases in custom_aliases.values())
    if announce:
        print(f"Loaded {added} custom aliases from {_display_text(alias_path)}")
    return custom_aliases


def command_normalize(input_path: str, output_dir: str, emit_fhir: bool, aliases_path: str | None = None, fuzzy_threshold: float = 0.0) -> int:
    custom_aliases = _load_aliases(aliases_path)
    if aliases_path and custom_aliases is None:
        return 1

    source_path = Path(input_path)
    if not source_path.exists():
        print(f"Input file does not exist: {_display_text(source_path)}", file=sys.stderr)
        return 1

    try:
        validate_fuzzy_threshold(fuzzy_threshold)
        rows = read_input(source_path)
        alias_index = build_alias_index(custom_aliases) if custom_aliases is not None else None
        result = normalize_rows(rows, input_file=source_path.name, fuzzy_threshold=fuzzy_threshold, alias_index=alias_index)
        json_path, csv_path = write_result(result, Path(output_dir))
        fhir_path = write_fhir_bundle(result, Path(output_dir)) if emit_fhir else None
        summary_path = write_summary_report(result, Path(output_dir))
        # Derived metrics and the curated optimal-range review layer
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
        print(f"WARNING: {_display_text(warning)}", file=sys.stderr)

    print(f"Normalized {result.summary['total_rows']} rows.")
    print(
        f"Mapped={result.summary['mapped']} "
        f"ReviewNeeded={result.summary['review_needed']} "
        f"Unmapped={result.summary['unmapped']}"
    )
    if derived:
        print(f"Derived metrics: {len(derived)}")
    if optimal_evals:
        print(
            "Curated optimal-range review: "
            f"{optimal_summary['optimal']}/{optimal_summary['total_evaluated']} "
            f"biomarkers in range ({optimal_summary['optimal_percentage']}%)"
        )
    print(f"JSON output: {_display_text(json_path)}")
    print(f"CSV output: {_display_text(csv_path)}")
    print(f"Summary output: {_display_text(summary_path)}")
    if fhir_path is not None:
        print(f"FHIR output: {_display_text(fhir_path)}")
    return 0


def command_catalog(fmt: str, search: str | None = None, limit: int | None = None, offset: int = 0) -> int:
    if fmt == "metadata-json":
        if search or limit is not None or offset:
            print(json.dumps(list_catalog_metadata(search=search, limit=limit, offset=offset), indent=2))
        else:
            print(json.dumps(load_catalog_metadata(), indent=2))
        return 0

    try:
        page = list_catalog(search=search, limit=limit, offset=offset)
    except Exception as exc:
        logger.debug("Catalog failed", exc_info=True)
        print(f"Catalog failed: {_user_friendly_error(exc)}", file=sys.stderr)
        return 1

    if fmt == "json":
        print(json.dumps(page["biomarkers"], indent=2))
        return 0

    print(f"{'Biomarker ID':<25s} {'Name':<30s} {'LOINC':<12s} {'Unit':<15s} {'Specimens'}")
    print("-" * 110)
    for bio in page["biomarkers"]:
        specimens = ", ".join(bio["allowed_specimens"])
        print(
            f"{bio['biomarker_id']:<25s} {bio['canonical_name']:<30s} "
            f"{bio['loinc']:<12s} {bio['normalized_unit']:<15s} {specimens}"
        )
    if page["count"] != page["total"] or page["offset"]:
        print(f"\nShowing: {page['count']} biomarkers (offset {page['offset']})")
    print(f"\nTotal: {page['total']} biomarkers")
    return 0


def command_aliases(input_path: str, fmt: str = "table") -> int:
    alias_path = Path(input_path)
    if not alias_path.exists():
        print(f"Alias file does not exist: {_display_text(alias_path)}", file=sys.stderr)
        return 1

    try:
        report = validate_custom_aliases(alias_path)
    except Exception as exc:
        logger.debug("Alias validation failed", exc_info=True)
        print(f"Alias validation failed: {_user_friendly_error(exc)}", file=sys.stderr)
        return 1

    if fmt == "json":
        print(json.dumps(report, indent=2))
        return 0 if report["clean"] else 1

    print(f"Alias file: {_display_text(alias_path)}")
    print(f"Status: {'clean' if report['clean'] else 'issues found'}")
    print(f"Biomarker entries: {report['biomarker_entries']}")
    print(f"String aliases: {report['string_alias_count']}")
    print(
        f"Accepted aliases: {report['accepted_alias_count']} "
        f"({report['net_new_alias_count']} new, {report['existing_alias_count']} existing)"
    )
    if report["redundant_alias_count"]:
        print(f"Redundant aliases in file: {report['redundant_alias_count']}")

    if report["clean"]:
        print("No structural issues or alias conflicts detected.")
        return 0

    if report["unknown_biomarker_ids"]:
        print(f"Unknown biomarker IDs: {', '.join(report['unknown_biomarker_ids'])}")
    if report["non_list_entries"]:
        print(f"Entries with non-list values: {', '.join(report['non_list_entries'])}")
    if report["non_string_alias_count"]:
        print(f"Non-string aliases: {report['non_string_alias_count']}")
    if report["empty_alias_count"]:
        print(f"Empty aliases after normalization: {report['empty_alias_count']}")
    if report["custom_conflicts"]:
        print("Conflicts within custom aliases:")
        for conflict in report["custom_conflicts"]:
            print(
                f"  {_display_text(conflict['alias'])} -> "
                f"{', '.join(conflict['biomarker_ids'])}"
            )
    if report["catalog_conflicts"]:
        print("Conflicts with built-in catalog:")
        for conflict in report["catalog_conflicts"]:
            print(
                f"  {_display_text(conflict['alias'])} -> requested "
                f"{', '.join(conflict['requested_biomarker_ids'])}; existing "
                f"{', '.join(conflict['existing_biomarker_ids'])}"
            )
    return 1


def command_lookup(test_name: str, specimen: str = "", aliases_path: str | None = None, fmt: str = "table") -> int:
    custom_aliases = _load_aliases(aliases_path, announce=fmt != "json")
    if aliases_path and custom_aliases is None:
        return 1

    try:
        result = lookup_biomarker(test_name, specimen=specimen, custom_aliases=custom_aliases)
    except Exception as exc:
        logger.debug("Lookup failed", exc_info=True)
        print(f"Lookup failed: {_user_friendly_error(exc)}", file=sys.stderr)
        return 1

    if fmt == "json":
        print(json.dumps(result, indent=2))
        return 0

    print(f"Lookup: {_display_text(test_name)}")
    if specimen:
        print(f"Specimen: {_display_text(specimen)}")
    print(f"Alias key: {_display_text(result['alias_key'])}")
    print(f"Matched: {'yes' if result['matched'] else 'no'}")

    candidates = result["candidates"]
    if not candidates:
        print("Candidates: none")
        return 0

    print(f"{'Biomarker ID':<25s} {'Name':<30s} {'LOINC':<12s} {'Unit'}")
    print("-" * 84)
    for candidate in candidates:
        print(
            f"{candidate['biomarker_id']:<25s} "
            f"{candidate['canonical_name']:<30s} "
            f"{candidate['loinc']:<12s} "
            f"{candidate['normalized_unit']}"
        )
    return 0


def command_analyze(input_path: str, aliases_path: str | None = None, fuzzy_threshold: float = 0.0) -> int:
    custom_aliases = _load_aliases(aliases_path)
    if aliases_path and custom_aliases is None:
        return 1

    source_path = Path(input_path)
    if not source_path.exists():
        print(f"Input file does not exist: {_display_text(source_path)}", file=sys.stderr)
        return 1

    try:
        validate_fuzzy_threshold(fuzzy_threshold)
        rows = read_input(source_path)
        alias_index = build_alias_index(custom_aliases) if custom_aliases is not None else None
        result = normalize_rows(rows, input_file=source_path.name, fuzzy_threshold=fuzzy_threshold, alias_index=alias_index)
    except Exception as exc:
        logger.debug("Analysis failed", exc_info=True)
        print(f"Analysis failed: {_user_friendly_error(exc)}", file=sys.stderr)
        return 1

    total = result.summary["total_rows"]
    mapped = result.summary["mapped"]
    review = result.summary["review_needed"]
    unmapped = result.summary["unmapped"]
    mapped_pct = mapped / total * 100 if total else 0

    print(f"Coverage Analysis: {_display_text(source_path.name)}")
    print(f"{'=' * 60}")
    print(f"Total rows:     {total}")
    print(f"Mapped:         {mapped} ({mapped_pct:.1f}%)")
    print(f"Review needed:  {review}")
    print(f"Unmapped:       {unmapped}")

    for warning in result.warnings:
        print(f"WARNING: {_display_text(warning)}", file=sys.stderr)

    # Mapped biomarker breakdown
    mapped_by_biomarker: dict[str, int] = {}
    for r in result.records:
        if r.mapping_status == "mapped":
            mapped_by_biomarker[r.canonical_biomarker_name] = mapped_by_biomarker.get(r.canonical_biomarker_name, 0) + 1

    if mapped_by_biomarker:
        print(f"\n{'Mapped Biomarkers':}")
        print(f"{'-' * 40}")
        for name, count in sorted(mapped_by_biomarker.items(), key=lambda x: -x[1]):
            print(f"  {count:>5d}  {_display_text(name)}")

    # Unmapped test names
    unmapped_tests: dict[str, int] = {}
    for r in result.records:
        if r.mapping_status == "unmapped":
            unmapped_tests[r.source_test_name] = unmapped_tests.get(r.source_test_name, 0) + 1

    if unmapped_tests:
        print(f"\n{'Unmapped Test Names (top 20)':}")
        print(f"{'-' * 40}")
        for name, count in sorted(unmapped_tests.items(), key=lambda x: -x[1])[:20]:
            print(f"  {count:>5d}  {_display_text(name)}")
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
            print(f"  {count:>5d}  {_display_text(key)}")

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
            print(f"  {count:>5d}  {_display_text(key)}")

    return 0


SUPPORTED_EXTENSIONS = {".csv", ".json", ".hl7", ".oru", ".xml", ".xlsx", ".xls"}


def command_batch(input_dir: str, output_dir: str, emit_fhir: bool, aliases_path: str | None = None, fuzzy_threshold: float = 0.0) -> int:
    custom_aliases = _load_aliases(aliases_path)
    if aliases_path and custom_aliases is None:
        return 1
    try:
        validate_fuzzy_threshold(fuzzy_threshold)
    except Exception as exc:
        print(f"Batch failed: {_user_friendly_error(exc)}", file=sys.stderr)
        return 1

    input_path = Path(input_dir)
    if not input_path.is_dir():
        print(f"Input directory does not exist: {_display_text(input_path)}", file=sys.stderr)
        return 1

    files = sorted(
        f for f in input_path.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not files:
        print(f"No supported files found in {_display_text(input_path)}", file=sys.stderr)
        return 1

    out_base = Path(output_dir)
    alias_index = build_alias_index(custom_aliases) if custom_aliases is not None else None
    total_mapped = 0
    total_rows = 0
    errors: list[str] = []

    for source_file in files:
        file_out = out_base / source_file.stem
        try:
            rows = read_input(source_file)
            result = normalize_rows(rows, input_file=source_file.name, fuzzy_threshold=fuzzy_threshold, alias_index=alias_index)
            write_result(result, file_out)
            if emit_fhir:
                write_fhir_bundle(result, file_out)
            write_summary_report(result, file_out)
            total_mapped += result.summary["mapped"]
            total_rows += result.summary["total_rows"]
            pct = result.summary["mapped"] / result.summary["total_rows"] * 100 if result.summary["total_rows"] else 0
            print(
                f"  {_display_text(source_file.name)}: "
                f"{result.summary['mapped']}/{result.summary['total_rows']} mapped ({pct:.0f}%)"
            )
        except Exception as exc:
            safe_msg = _user_friendly_error(exc)
            logger.debug("Batch error for %s", source_file.name, exc_info=True)
            errors.append(f"{source_file.name}: {safe_msg}")
            print(
                f"  {_display_text(source_file.name)}: ERROR - {_display_text(safe_msg)}",
                file=sys.stderr,
            )

    overall_pct = total_mapped / total_rows * 100 if total_rows else 0
    print(f"\nBatch complete: {len(files)} files, {total_rows} total rows, {total_mapped} mapped ({overall_pct:.1f}%)")
    if errors:
        print(f"{len(errors)} files had errors.", file=sys.stderr)

    return 1 if errors else 0


def command_serve(host: str, port: int) -> int:
    if not _rest_dependencies_available():
        print(
            "REST API dependencies not installed or incomplete.\n"
            "Install with: pip install biomarker-normalization-toolkit[rest]",
            file=sys.stderr,
        )
        return 1

    uvicorn, app, exc = _load_rest_components()
    if exc is not None:
        logger.debug(
            "REST API startup failed",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        print(f"REST API startup failed: {_user_friendly_error(exc)}", file=sys.stderr)
        return 1

    if uvicorn is None or app is None:
        print(
            "REST API dependencies not installed or incomplete.\n"
            "Install with: pip install biomarker-normalization-toolkit[rest]",
            file=sys.stderr,
        )
        return 1

    print(f"Starting BNT API server on {_display_text(host)}:{port}")
    print(f"Docs: http://{_display_text(host)}:{port}/docs")
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
        return command_catalog(args.format, args.search, args.limit, args.offset)
    if args.command == "aliases":
        return command_aliases(args.input, args.format)
    if args.command == "lookup":
        return command_lookup(args.test_name, args.specimen, args.aliases, args.format)
    if args.command == "analyze":
        return command_analyze(args.input, args.aliases, args.fuzzy_threshold)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
