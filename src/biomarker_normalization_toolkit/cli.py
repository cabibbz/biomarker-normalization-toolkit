from __future__ import annotations

import argparse
from pathlib import Path
import sys

from biomarker_normalization_toolkit.io_utils import read_input_csv, write_result
from biomarker_normalization_toolkit.normalizer import normalize_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bnt",
        description="Biomarker Normalization Toolkit scaffold CLI.",
    )
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
        help="Normalize a CSV file into canonical output.",
    )
    normalize.add_argument(
        "--input",
        required=True,
        help="Path to the input CSV file.",
    )
    normalize.add_argument(
        "--output-dir",
        required=True,
        help="Directory where normalized outputs should be written.",
    )

    return parser


def command_status() -> int:
    print("Biomarker Normalization Toolkit")
    print("Route: customer-run B2B normalization toolkit")
    print("Scope: lab aliases, units, ranges, LOINC, canonical output")
    print("Hosted PHI: off by default")
    print("Consumer app: excluded")
    print("Next step: lock initial build decisions and begin core normalization fixtures")
    return 0


def command_where_left_off(path: str) -> int:
    context_path = Path(path)
    if not context_path.exists():
        print(f"No context file found at: {context_path}")
        return 1

    print(context_path.read_text(encoding="utf-8"))
    return 0


def command_normalize(input_path: str, output_dir: str) -> int:
    source_path = Path(input_path)
    if not source_path.exists():
        print(f"Input file does not exist: {source_path}", file=sys.stderr)
        return 1

    try:
        rows = read_input_csv(source_path)
        result = normalize_rows(rows, input_file=source_path.name)
        json_path, csv_path = write_result(result, Path(output_dir))
    except Exception as exc:
        print(f"Normalization failed: {exc}", file=sys.stderr)
        return 1

    print(f"Normalized {result.summary['total_rows']} rows.")
    print(
        f"Mapped={result.summary['mapped']} "
        f"ReviewNeeded={result.summary['review_needed']} "
        f"Unmapped={result.summary['unmapped']}"
    )
    print(f"JSON output: {json_path}")
    print(f"CSV output: {csv_path}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "status":
        return command_status()
    if args.command == "where-left-off":
        return command_where_left_off(args.path)
    if args.command == "normalize":
        return command_normalize(args.input, args.output_dir)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
