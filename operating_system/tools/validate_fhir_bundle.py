from __future__ import annotations

import json
from pathlib import Path
import sys

from fhir.resources.bundle import Bundle


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_fhir_bundle.py <fhir_bundle.json>")
        return 2

    path = Path(sys.argv[1])
    payload = path.read_text(encoding="utf-8")
    bundle = Bundle.model_validate_json(payload)

    entry_count = len(bundle.entry or [])
    print(f"Validated FHIR Bundle: {path}")
    print(f"Entry count: {entry_count}")

    bundle_json = json.loads(payload)
    for index, entry in enumerate(bundle_json.get("entry", []), start=1):
        resource = entry.get("resource", {})
        resource_type = resource.get("resourceType", "")
        if resource_type != "Observation":
            raise ValueError(f"Entry {index} is not an Observation resource: {resource_type}")

    print("All bundle entries are Observation resources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

