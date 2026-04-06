import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MEMORY_DIR = ROOT / "project_memory"
CHECKPOINTS_DIR = MEMORY_DIR / "checkpoints"
MANIFEST_PATH = MEMORY_DIR / "manifest.json"
CURRENT_CONTEXT_PATH = MEMORY_DIR / "current_context.md"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "checkpoint"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def render_checkpoint(data):
    percent = int(data["percent"])
    title = data["title"].strip()
    lines = [
        f"# {percent}% Checkpoint: {title}",
        "",
        "## Summary",
        "",
        data["summary"].strip(),
        "",
        "## Completed",
        "",
    ]
    for item in data.get("completed", []):
        lines.append(f"- {item}")
    lines.extend(["", "## Decisions Locked", ""])
    for item in data.get("decisions_locked", []):
        lines.append(f"- {item}")
    lines.extend(["", "## Verification Evidence", ""])
    for item in data.get("verification_evidence", []):
        lines.append(f"- {item}")
    lines.extend(["", "## Files Touched", ""])
    for item in data.get("files_touched", []):
        lines.append(f"- {item}")
    lines.extend(["", "## Open Questions", ""])
    for item in data.get("open_questions", []):
        lines.append(f"- {item}")
    lines.extend(["", "## Next Steps", ""])
    for item in data.get("next_steps", []):
        lines.append(f"- {item}")
    lines.extend(["", "## Resume From", "", data["resume_from"].strip(), ""])
    return "\n".join(lines)


def render_current_context(data, checkpoint_file: Path):
    percent = int(data["percent"])
    return "\n".join(
        [
            "# Current Context",
            "",
            f"Latest checkpoint: `{checkpoint_file.name}`",
            f"Progress: `{percent}%`",
            "",
            "## Compressed State",
            "",
            data["summary"].strip(),
            "",
            "## Locked Decisions",
            "",
            *[f"- {item}" for item in data.get("decisions_locked", [])],
            "",
            "## Immediate Next Steps",
            "",
            *[f"- {item}" for item in data.get("next_steps", [])],
            "",
            "## Resume From",
            "",
            data["resume_from"].strip(),
            "",
        ]
    )


def main():
    if len(sys.argv) != 2:
        print("Usage: python record_checkpoint.py <checkpoint.json>")
        sys.exit(2)

    input_path = Path(sys.argv[1]).resolve()
    data = load_json(input_path)

    percent = int(data["percent"])
    title = data["title"]
    file_name = f"{percent:03d}_{slugify(title)}.md"
    checkpoint_path = CHECKPOINTS_DIR / file_name

    checkpoint_path.write_text(render_checkpoint(data), encoding="utf-8")

    manifest = load_json(MANIFEST_PATH)
    manifest["current_percent"] = percent
    manifest["latest_checkpoint"] = str(checkpoint_path.relative_to(ROOT)).replace("\\", "/")

    checkpoints = manifest.setdefault("checkpoints", [])
    checkpoints = [entry for entry in checkpoints if entry.get("percent") != percent]
    checkpoints.append(
        {
            "percent": percent,
            "title": title,
            "file": str(checkpoint_path.relative_to(ROOT)).replace("\\", "/"),
        }
    )
    checkpoints.sort(key=lambda entry: int(entry["percent"]))
    manifest["checkpoints"] = checkpoints
    write_json(MANIFEST_PATH, manifest)

    CURRENT_CONTEXT_PATH.write_text(
        render_current_context(data, checkpoint_path),
        encoding="utf-8",
    )

    print(f"Wrote checkpoint: {checkpoint_path}")
    print(f"Updated: {MANIFEST_PATH}")
    print(f"Updated: {CURRENT_CONTEXT_PATH}")


if __name__ == "__main__":
    main()

