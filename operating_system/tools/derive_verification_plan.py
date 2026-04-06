import json
import sys
from pathlib import Path


FRONTEND_EXTS = {".tsx", ".ts", ".jsx", ".js", ".html", ".css", ".scss"}
BACKEND_EXTS = {".py", ".go", ".rb", ".java", ".kt", ".cs"}


def load_record(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize_lower(items):
    return [str(item).lower() for item in items]


def infer_surfaces(data):
    changed_files = data.get("changed_files", [])
    touched = set(normalize_lower(data.get("touched_surfaces", [])))
    risks = set(normalize_lower(data.get("risk_keywords", [])))

    for file_name in changed_files:
        suffix = Path(file_name).suffix.lower()
        file_lower = file_name.lower()

        if suffix in FRONTEND_EXTS and any(token in file_lower for token in ["page", "component", "frontend", "ui", "view"]):
            touched.add("frontend")
        if suffix in BACKEND_EXTS and any(token in file_lower for token in ["api", "service", "server", "backend"]):
            touched.add("backend")
        if "api" in file_lower or "endpoint" in file_lower:
            touched.add("api")
        if "auth" in file_lower or "permission" in file_lower:
            touched.add("auth")
        if "upload" in file_lower:
            touched.add("file_upload")
        if any(token in file_lower for token in ["normalize", "mapping", "conversion", "parser", "transform"]):
            touched.add("normalization")

    if "responsive" in risks or "mobile" in risks:
        touched.add("frontend")

    return touched


def build_plan(data):
    touched = infer_surfaces(data)
    plan = []
    plan.append("Review the change summary, changed files, user-visible flows, and system flows before choosing tests.")
    plan.append("Identify the highest-risk happy path, highest-risk failure path, and highest-risk regression path.")

    if "frontend" in touched:
        plan.append("Run actual UI verification: load the changed screens, click through the primary user flow, confirm visible success states, empty states, and validation/error states.")
        plan.append("Check responsive behavior on at least desktop and mobile-width layouts if the changed UI is user-facing.")

    if "backend" in touched or "api" in touched:
        plan.append("Run backend and API verification with realistic inputs: verify success path, invalid input handling, and server-side error behavior.")
        plan.append("Confirm returned payloads or rendered state match the intended contract, not just that the process exits successfully.")

    if "file_upload" in touched:
        plan.append("Exercise the upload flow end-to-end with at least one valid file, one malformed file, and one edge-case file.")

    if "normalization" in touched:
        plan.append("Run fixture-based normalization regression checks: known aliases, supported unit conversions, ambiguous mappings, and unmapped rows.")
        plan.append("Verify the system never guesses on ambiguous mappings and always preserves provenance and explicit status.")

    if "auth" in touched:
        plan.append("Verify permission boundaries with allowed and disallowed users or roles, including direct URL or API access attempts.")

    if data.get("external_integrations"):
        plan.append("Validate external integration behavior using sandbox or mocked environments first, then confirm request/response handling and failure behavior.")

    plan.append("Record exact commands run, exact flows exercised, pass/fail results, unverified areas, and residual risk.")
    return plan, touched


def main():
    if len(sys.argv) != 2:
        print("Usage: python derive_verification_plan.py <change_record.json>")
        sys.exit(2)

    data = load_record(sys.argv[1])
    plan, touched = build_plan(data)

    print(f"Change: {data.get('name', 'unnamed')}")
    print(f"Inferred surfaces: {', '.join(sorted(touched)) or 'none'}")
    print("Verification plan:")
    for i, step in enumerate(plan, start=1):
        print(f"{i}. {step}")


if __name__ == "__main__":
    main()
