import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = ROOT / "operating_system" / "tools" / "dual_agent_consensus.py"


def orchestrator_command(config_path: Path) -> list[str]:
    override = os.environ.get("LIVE_CONSENSUS_ORCHESTRATOR", "").strip()
    if not override:
        return [sys.executable, str(ORCHESTRATOR), str(config_path)]
    parts = [part for part in override.split("|") if part]
    if any("{config_path}" in part for part in parts):
        return [part.replace("{config_path}", str(config_path)) for part in parts]
    return [*parts, str(config_path)]


def parse_args():
    parser = argparse.ArgumentParser(description="Run a low-context live smoke test through the dual-agent consensus wrappers.")
    parser.add_argument("--workspace", default=".", help="Workspace root relative to the repo root.")
    parser.add_argument("--run-dir", default="", help="Optional run directory. Defaults under .agent_consensus/.")
    parser.add_argument("--attempts", type=int, default=3, help="Maximum live attempts before failing.")
    parser.add_argument("--codex-model", default="gpt-5.4-mini", help="Codex model for the smoke test.")
    parser.add_argument("--claude-model", default="sonnet", help="Claude model for the smoke test.")
    parser.add_argument("--claude-effort", default="low", help="Claude effort level for the smoke test.")
    parser.add_argument("--claude-max-budget-usd", default="0.25", help="Claude budget cap for the smoke test.")
    parser.add_argument("--max-rounds", type=int, default=4, help="Maximum consensus rounds.")
    return parser.parse_args()


def build_config(args, workspace: Path, run_dir: Path) -> dict:
    task_text = (
        "This is a live wrapper smoke test, not real product work. "
        "If you are the first agent and no proposal exists yet, return action='propose', summary='Smoke proposal', concerns=[], "
        "and proposal_markdown exactly equal to '# Smoke Test\\n\\n- The live dual-agent consensus wrapper path is functioning.'. "
        "If a proposal already exists and it is materially equivalent to that statement, return action='accept', summary='Smoke proposal accepted', "
        "concerns=[], and proposal_markdown=''. "
        "If the current proposal is missing or malformed, return action='revise' with the exact corrected smoke proposal."
    )

    codex_command = [
        sys.executable,
        str(ROOT / "operating_system" / "tools" / "codex_consensus_wrapper.py"),
        "--workspace",
        "{workspace}",
        "--run-dir",
        "{run_dir}",
        "--prompt-file",
        "{prompt_file}",
        "--proposal-file",
        "{proposal_file}",
        "--response-file",
        "{response_file}",
    ]
    if args.codex_model:
        codex_command.extend(["--model", args.codex_model])

    claude_command = [
        sys.executable,
        str(ROOT / "operating_system" / "tools" / "claude_consensus_wrapper.py"),
        "--workspace",
        "{workspace}",
        "--run-dir",
        "{run_dir}",
        "--prompt-file",
        "{prompt_file}",
        "--proposal-file",
        "{proposal_file}",
        "--response-file",
        "{response_file}",
    ]
    if args.claude_model:
        claude_command.extend(["--model", args.claude_model])
    if args.claude_effort:
        claude_command.extend(["--effort", args.claude_effort])
    if args.claude_max_budget_usd:
        claude_command.extend(["--max-budget-usd", args.claude_max_budget_usd])

    return {
        "workspace": str(workspace),
        "run_dir": str(run_dir),
        "task_text": task_text,
        "max_rounds": args.max_rounds,
        "agents": [
            {"name": "codex", "command": codex_command},
            {"name": "claude", "command": claude_command},
        ],
    }


def main():
    args = parse_args()
    workspace = (ROOT / args.workspace).resolve()
    if args.run_dir:
        base_run_dir = (ROOT / args.run_dir).resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_run_dir = (workspace / ".agent_consensus" / f"live_smoke_{stamp}").resolve()
    base_run_dir.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, args.attempts + 1):
        run_dir = base_run_dir / f"attempt_{attempt:02d}"
        run_dir.mkdir(parents=True, exist_ok=True)

        config = build_config(args, workspace, run_dir)
        config_path = run_dir / "live_smoke_config.json"
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

        result = subprocess.run(
            orchestrator_command(config_path),
            cwd=str(workspace),
            capture_output=True,
            text=True,
            check=False,
        )

        print(f"Attempt {attempt}/{args.attempts}")
        sys.stdout.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
        if result.returncode == 0:
            raise SystemExit(0)

    raise SystemExit(1)


if __name__ == "__main__":
    main()
