import json
from pathlib import Path


RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["propose", "revise", "accept", "block"],
        },
        "summary": {"type": "string"},
        "concerns": {
            "type": "array",
            "items": {"type": "string"},
        },
        "proposal_markdown": {"type": "string"},
    },
    "required": ["action", "summary", "concerns"],
    "additionalProperties": False,
}


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def collect_context_snapshots(run_dir: Path) -> list[tuple[str, str]]:
    context_dir = run_dir / "context"
    if not context_dir.exists():
        return []

    snapshots = []
    for path in sorted(item for item in context_dir.rglob("*") if item.is_file()):
        rel_path = str(path.relative_to(run_dir)).replace("\\", "/")
        snapshots.append((rel_path, path.read_text(encoding="utf-8")))
    return snapshots


def build_prompt(run_dir: Path, prompt_file: Path, proposal_file: Path | None) -> str:
    sections = [
        "You are participating in a dual-agent consensus workflow.",
        "Return one JSON object that matches the required schema exactly.",
        "Do not wrap the JSON in markdown.",
        "",
        "<orchestrator_prompt>",
        prompt_file.read_text(encoding="utf-8").strip(),
        "</orchestrator_prompt>",
        "",
        "<shared_task>",
        load_text(run_dir / "task.md"),
        "</shared_task>",
        "",
        "<context_index>",
        load_text(run_dir / "context_index.md"),
        "</context_index>",
        "",
    ]

    for rel_path, text in collect_context_snapshots(run_dir):
        sections.extend(
            [
                f'<context_file path="{rel_path}">',
                text.rstrip(),
                "</context_file>",
                "",
            ]
        )

    if proposal_file is not None and proposal_file.exists():
        sections.extend(
            [
                "<current_proposal>",
                proposal_file.read_text(encoding="utf-8").strip(),
                "</current_proposal>",
                "",
            ]
        )

    return "\n".join(sections).strip() + "\n"


def validate_response(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("response must be a JSON object")

    action = data.get("action")
    if action not in {"propose", "revise", "accept", "block"}:
        raise ValueError("response action must be propose, revise, accept, or block")

    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("response summary must be a non-empty string")

    concerns = data.get("concerns")
    if not isinstance(concerns, list) or not all(isinstance(item, str) for item in concerns):
        raise ValueError("response concerns must be a list of strings")

    if action in {"propose", "revise"}:
        proposal = data.get("proposal_markdown")
        if not isinstance(proposal, str) or not proposal.strip():
            raise ValueError("proposal_markdown is required for propose/revise")

    normalized = {
        "action": action,
        "summary": summary.strip(),
        "concerns": [item.strip() for item in concerns],
    }
    if "proposal_markdown" in data and isinstance(data["proposal_markdown"], str):
        normalized["proposal_markdown"] = data["proposal_markdown"].strip()
    return normalized


def write_response(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
