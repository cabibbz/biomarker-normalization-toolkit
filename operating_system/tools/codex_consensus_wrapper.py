import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from consensus_wrapper_common import RESPONSE_SCHEMA, build_prompt, resolve_executable, validate_response, write_response


def parse_args():
    parser = argparse.ArgumentParser(description="Run Codex as a dual-agent consensus worker.")
    parser.add_argument("--workspace", required=True, help="Workspace root for the Codex run.")
    parser.add_argument("--run-dir", required=True, help="Consensus run directory.")
    parser.add_argument("--prompt-file", required=True, help="Prompt file written by the orchestrator.")
    parser.add_argument("--proposal-file", required=True, help="Current proposal file path.")
    parser.add_argument("--response-file", required=True, help="Where to write the validated response JSON.")
    parser.add_argument("--binary", default="codex", help="Codex CLI binary.")
    parser.add_argument("--binary-arg", action="append", default=[], help="Extra argument to insert after the binary.")
    parser.add_argument("--model", default="", help="Optional Codex model override.")
    return parser.parse_args()


def main():
    args = parse_args()
    _workspace = Path(args.workspace).resolve()
    run_dir = Path(args.run_dir).resolve()
    prompt_file = Path(args.prompt_file).resolve()
    proposal_file = Path(args.proposal_file).resolve()
    response_file = Path(args.response_file).resolve()

    prompt = build_prompt(run_dir, prompt_file, proposal_file)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        schema_path = temp / "schema.json"
        raw_response_path = temp / "codex_response.json"
        schema_path.write_text(json.dumps(RESPONSE_SCHEMA), encoding="utf-8")

        command = [
            resolve_executable(args.binary),
            *args.binary_arg,
            "exec",
            "--skip-git-repo-check",
            "-s",
            "read-only",
        ]
        if args.model:
            command.extend(["-m", args.model])
        command.extend(["--output-schema", str(schema_path), "-o", str(raw_response_path), prompt])

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

        payload = json.loads(raw_response_path.read_text(encoding="utf-8"))
        write_response(response_file, validate_response(payload))


if __name__ == "__main__":
    main()
