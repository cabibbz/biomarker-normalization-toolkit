import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def resolve_with_fallbacks(raw_path: str, *base_dirs: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path

    for base_dir in base_dirs:
        candidate = (base_dir / path).resolve()
        if candidate.exists():
            return candidate
    return (base_dirs[0] / path).resolve()


def ensure(condition: bool, message: str):
    if not condition:
        raise ValueError(message)


def relative_to_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return path.name


def load_task_text(config: dict, workspace: Path, config_dir: Path) -> str:
    task_text = str(config.get("task_text", "")).strip()
    task_file = config.get("task_file")
    if task_file:
        task_path = resolve_with_fallbacks(str(task_file), workspace, config_dir, ROOT)
        file_text = task_path.read_text(encoding="utf-8").strip()
        if task_text:
            return f"{task_text}\n\n{file_text}".strip()
        return file_text
    ensure(bool(task_text), "config must include task_text or task_file")
    return task_text


def snapshot_context_files(config: dict, workspace: Path, config_dir: Path, run_dir: Path) -> list[dict[str, str]]:
    snapshots = []
    context_dir = run_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)

    for index, raw_path in enumerate(config.get("context_files", []), start=1):
        source_path = resolve_with_fallbacks(str(raw_path), workspace, config_dir, ROOT)
        ensure(source_path.exists(), f"context file does not exist: {source_path}")

        rel_name = relative_to_root(source_path)
        snapshot_path = context_dir / rel_name
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, snapshot_path)

        snapshots.append(
            {
                "index": str(index),
                "source": str(source_path),
                "snapshot": str(snapshot_path),
                "relative_source": rel_name,
            }
        )
    return snapshots


def write_context_index(path: Path, snapshots: list[dict[str, str]]):
    lines = [
        "# Shared Context Snapshot",
        "",
        "Both agents must reason from these same frozen files for this run.",
        "",
    ]
    if not snapshots:
        lines.append("No context files were configured.")
    else:
        for item in snapshots:
            lines.append(f"- `{item['relative_source']}`")
            lines.append(f"  source: `{item['source']}`")
            lines.append(f"  snapshot: `{item['snapshot']}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def render_prompt(
    agent_name: str,
    round_number: int,
    task_path: Path,
    context_index_path: Path,
    proposal_path: Path,
    current_proposer: str | None,
) -> str:
    if proposal_path.exists():
        proposal_state = (
            f"A current proposal exists at `{proposal_path}` and was last written by `{current_proposer}`.\n"
            "Review it and choose one action:\n"
            "- `accept`: the current proposal is good enough to ship unchanged\n"
            "- `revise`: replace it with a better full proposal\n"
            "- `block`: stop the run with concrete concerns\n"
        )
    else:
        proposal_state = (
            "No proposal exists yet.\n"
            "Create the initial proposal with action `propose`.\n"
        )

    return "\n".join(
        [
            f"You are `{agent_name}` in a two-agent consensus loop.",
            f"Round: {round_number}",
            "",
            f"Read the shared task from `{task_path}`.",
            f"Read the shared context index from `{context_index_path}`.",
            proposal_state,
            "Rules:",
            "- Be concrete and file-grounded.",
            "- Only accept a proposal you would personally ship.",
            "- If you revise, provide the full replacement proposal, not a diff.",
            "- Keep concerns specific and actionable.",
            "- Output valid JSON only.",
            "",
            "Response schema:",
            "{",
            '  "action": "propose|revise|accept|block",',
            '  "summary": "short summary",',
            '  "concerns": ["optional concern"],',
            '  "proposal_markdown": "required for propose/revise, omit or empty otherwise"',
            "}",
            "",
            "The current proposal file path is:",
            f"`{proposal_path}`",
            "",
            "Do not write anything except the JSON response.",
            "",
        ]
    )


def format_command(template: list[str], values: dict[str, str]) -> list[str]:
    return [part.format(**values) for part in template]


def run_command(command: list[str], cwd: Path, stdout_path: Path, stderr_path: Path) -> int:
    result = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    return result.returncode


def parse_agent_response(response_path: Path, stdout_path: Path) -> dict:
    if response_path.exists():
        payload = response_path.read_text(encoding="utf-8").strip()
    else:
        payload = stdout_path.read_text(encoding="utf-8").strip()
    ensure(bool(payload), "agent returned no response")

    data = json.loads(payload)
    ensure(isinstance(data, dict), "agent response must be a JSON object")
    action = data.get("action")
    ensure(action in {"propose", "revise", "accept", "block"}, "invalid action in agent response")
    summary = str(data.get("summary", "")).strip()
    ensure(bool(summary), "agent response must include summary")
    concerns = data.get("concerns", [])
    ensure(isinstance(concerns, list), "concerns must be a list")
    if action in {"propose", "revise"}:
        proposal = str(data.get("proposal_markdown", "")).strip()
        ensure(bool(proposal), "proposal_markdown is required for propose/revise")
    return data


def normalize_agent_response(response: dict, proposal_exists: bool) -> tuple[dict, str | None]:
    action = str(response["action"])
    proposal_text = str(response.get("proposal_markdown", "")).strip()

    if not proposal_exists and action in {"accept", "revise"} and proposal_text:
        normalized = dict(response)
        normalized["action"] = "propose"
        return normalized, f"normalized `{action}` to `propose` because no proposal existed yet"

    if proposal_exists and action == "propose" and proposal_text:
        normalized = dict(response)
        normalized["action"] = "revise"
        return normalized, "normalized `propose` to `revise` because a proposal already existed"

    return response, None


def append_transcript(path: Path, lines: list[str]):
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    text = existing + "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")


def run_hook(name: str, command_template: list[str], values: dict[str, str], cwd: Path, hooks_dir: Path) -> dict:
    stdout_path = hooks_dir / f"{name}.stdout.txt"
    stderr_path = hooks_dir / f"{name}.stderr.txt"
    command = format_command(command_template, values)
    exit_code = run_command(command, cwd, stdout_path, stderr_path)
    return {
        "name": name,
        "command": command,
        "exit_code": exit_code,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: python dual_agent_consensus.py <config.json>")
        sys.exit(2)

    config_path = Path(sys.argv[1]).resolve()
    config_dir = config_path.parent
    config = load_json(config_path)

    agents = config.get("agents", [])
    ensure(isinstance(agents, list) and len(agents) == 2, "config must include exactly two agents")
    for agent in agents:
        ensure(agent.get("name"), "each agent must have a name")
        ensure(isinstance(agent.get("command"), list) and agent["command"], "each agent must have a command list")

    workspace = resolve_path(ROOT, str(config.get("workspace", ".")))
    run_dir_raw = config.get("run_dir")
    if run_dir_raw:
        run_dir = resolve_with_fallbacks(str(run_dir_raw), workspace, config_dir, ROOT)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = (ROOT / ".agent_consensus" / stamp).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    task_text = load_task_text(config, workspace, config_dir)
    task_path = run_dir / "task.md"
    task_path.write_text(task_text + "\n", encoding="utf-8")

    snapshots = snapshot_context_files(config, workspace, config_dir, run_dir)
    context_index_path = run_dir / "context_index.md"
    write_context_index(context_index_path, snapshots)

    proposal_path = run_dir / "proposal.md"
    responses_dir = run_dir / "responses"
    prompts_dir = run_dir / "prompts"
    logs_dir = run_dir / "logs"
    hooks_dir = run_dir / "hooks"
    responses_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    hooks_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "config": str(config_path),
        "workspace": str(workspace),
        "task_file": str(task_path),
        "context_index_file": str(context_index_path),
        "proposal_file": str(proposal_path),
        "agents": [agent["name"] for agent in agents],
        "max_rounds": int(config.get("max_rounds", 6)),
    }
    write_json(run_dir / "run_manifest.json", manifest)

    transcript_path = run_dir / "transcript.md"
    append_transcript(
        transcript_path,
        [
            "# Dual Agent Consensus Run",
            "",
            f"- workspace: `{workspace}`",
            f"- task file: `{task_path}`",
            f"- context index: `{context_index_path}`",
            "",
        ],
    )

    current_proposer = None
    max_rounds = int(config.get("max_rounds", 6))
    values_base = {
        "workspace": str(workspace),
        "run_dir": str(run_dir),
        "task_file": str(task_path),
        "context_index_file": str(context_index_path),
        "proposal_file": str(proposal_path),
    }

    adopted = None
    for round_number in range(1, max_rounds + 1):
        agent = agents[(round_number - 1) % 2]
        prompt_path = prompts_dir / f"round_{round_number:02d}_{agent['name']}.md"
        response_path = responses_dir / f"round_{round_number:02d}_{agent['name']}.json"
        stdout_path = logs_dir / f"round_{round_number:02d}_{agent['name']}.stdout.txt"
        stderr_path = logs_dir / f"round_{round_number:02d}_{agent['name']}.stderr.txt"

        prompt_path.write_text(
            render_prompt(
                agent_name=str(agent["name"]),
                round_number=round_number,
                task_path=task_path,
                context_index_path=context_index_path,
                proposal_path=proposal_path,
                current_proposer=current_proposer,
            ),
            encoding="utf-8",
        )

        values = dict(values_base)
        values.update(
            {
                "prompt_file": str(prompt_path),
                "response_file": str(response_path),
                "agent_name": str(agent["name"]),
                "round": str(round_number),
            }
        )
        command = format_command(agent["command"], values)
        exit_code = run_command(command, workspace, stdout_path, stderr_path)
        ensure(exit_code == 0, f"agent command failed for {agent['name']} in round {round_number}")

        response = parse_agent_response(response_path, stdout_path)
        response, normalization_note = normalize_agent_response(response, proposal_path.exists())
        action = response["action"]
        summary = str(response["summary"]).strip()
        concerns = [str(item) for item in response.get("concerns", [])]

        append_transcript(
            transcript_path,
            [
                f"## Round {round_number}: {agent['name']}",
                "",
                f"- action: `{action}`",
                f"- summary: {summary}",
                *([f"- normalization: {normalization_note}"] if normalization_note else []),
                *[f"- concern: {item}" for item in concerns],
                "",
            ],
        )

        if action in {"propose", "revise"}:
            proposal_path.write_text(str(response["proposal_markdown"]).strip() + "\n", encoding="utf-8")
            current_proposer = str(agent["name"])
            continue

        if action == "accept":
            ensure(proposal_path.exists(), "agent accepted but no proposal exists")
            adopted = {
                "status": "consensus_reached",
                "round": round_number,
                "accepted_by": str(agent["name"]),
                "proposed_by": current_proposer,
                "proposal_file": str(proposal_path),
                "summary": summary,
                "concerns": concerns,
            }
            break

        if action == "block":
            result = {
                "status": "blocked",
                "round": round_number,
                "blocked_by": str(agent["name"]),
                "summary": summary,
                "concerns": concerns,
            }
            write_json(run_dir / "result.json", result)
            print(f"Consensus blocked in round {round_number} by {agent['name']}")
            sys.exit(1)

    if adopted is None:
        result = {
            "status": "no_consensus",
            "max_rounds": max_rounds,
            "proposal_file": str(proposal_path) if proposal_path.exists() else "",
        }
        write_json(run_dir / "result.json", result)
        print(f"No consensus after {max_rounds} rounds")
        sys.exit(1)

    execution = config.get("execution", {})
    hook_results = []
    for hook_name in ("implementation_command", "verification_command", "deploy_command"):
        command_template = execution.get(hook_name)
        if not command_template:
            continue
        ensure(isinstance(command_template, list), f"{hook_name} must be a command list")
        hook_result = run_hook(hook_name, command_template, values_base, workspace, hooks_dir)
        hook_results.append(hook_result)
        if hook_result["exit_code"] != 0:
            adopted["status"] = "hook_failed"
            adopted["failed_hook"] = hook_name
            adopted["hooks"] = hook_results
            write_json(run_dir / "result.json", adopted)
            print(f"Consensus reached, but {hook_name} failed")
            sys.exit(1)

    adopted["hooks"] = hook_results
    write_json(run_dir / "result.json", adopted)
    print(f"Consensus reached in {adopted['round']} rounds")
    print(f"Proposal: {proposal_path}")
    if hook_results:
        print("Hooks executed:")
        for item in hook_results:
            print(f"- {item['name']}: exit {item['exit_code']}")


if __name__ == "__main__":
    main()
