import argparse
import json
import subprocess
import sys
from pathlib import Path

from consensus_wrapper_common import RESPONSE_SCHEMA, build_prompt, resolve_executable, validate_response, write_response


def parse_args():
    parser = argparse.ArgumentParser(description="Run Claude as a dual-agent consensus worker.")
    parser.add_argument("--workspace", required=True, help="Workspace root for the Claude run.")
    parser.add_argument("--run-dir", required=True, help="Consensus run directory.")
    parser.add_argument("--prompt-file", required=True, help="Prompt file written by the orchestrator.")
    parser.add_argument("--proposal-file", required=True, help="Current proposal file path.")
    parser.add_argument("--response-file", required=True, help="Where to write the validated response JSON.")
    parser.add_argument("--binary", default="claude", help="Claude CLI binary.")
    parser.add_argument("--binary-arg", action="append", default=[], help="Extra argument to insert after the binary.")
    parser.add_argument("--model", default="", help="Optional Claude model override.")
    parser.add_argument("--effort", default="", help="Optional Claude effort override.")
    parser.add_argument("--max-budget-usd", default="", help="Optional Claude budget cap.")
    parser.add_argument("--bare", action="store_true", help="Run Claude in bare mode.")
    return parser.parse_args()


def main():
    args = parse_args()
    _workspace = Path(args.workspace).resolve()
    run_dir = Path(args.run_dir).resolve()
    prompt_file = Path(args.prompt_file).resolve()
    proposal_file = Path(args.proposal_file).resolve()
    response_file = Path(args.response_file).resolve()

    prompt = build_prompt(run_dir, prompt_file, proposal_file)

    command = [
        resolve_executable(args.binary),
        *args.binary_arg,
        "--no-session-persistence",
        "-p",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(RESPONSE_SCHEMA),
        "--tools",
        "",
    ]
    if args.bare:
        command.append("--bare")
    if args.model:
        command.extend(["--model", args.model])
    if args.effort:
        command.extend(["--effort", args.effort])
    if args.max_budget_usd:
        command.extend(["--max-budget-usd", args.max_budget_usd])
    command.append(prompt)

    result = subprocess.run(
        command,
        cwd=str(run_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
        raise SystemExit(result.returncode)

    envelope = json.loads(result.stdout.strip())
    if isinstance(envelope, dict) and isinstance(envelope.get("structured_output"), dict):
        payload = envelope["structured_output"]
    elif isinstance(envelope, dict) and isinstance(envelope.get("result"), str):
        payload = json.loads(envelope["result"])
    else:
        payload = envelope
    write_response(response_file, validate_response(payload))


if __name__ == "__main__":
    main()
