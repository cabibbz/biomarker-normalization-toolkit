"""REST API for the Biomarker Normalization Toolkit.

Start with: bnt serve --host 0.0.0.0 --port 8000
Or: uvicorn biomarker_normalization_toolkit.api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from biomarker_normalization_toolkit import __version__
from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG, load_custom_aliases
from biomarker_normalization_toolkit.fhir import build_bundle
from biomarker_normalization_toolkit.io_utils import read_input
from biomarker_normalization_toolkit.normalizer import normalize_rows


app = FastAPI(
    title="Biomarker Normalization Toolkit",
    description="Normalize messy lab data into canonical machine-readable output.",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health ---

@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "biomarkers": len(BIOMARKER_CATALOG),
    }


# --- Catalog ---

@app.get("/catalog")
def catalog(search: str | None = Query(None, description="Filter by name, LOINC, or alias")) -> dict[str, Any]:
    entries = []
    for bio_id, bio in sorted(BIOMARKER_CATALOG.items()):
        if search:
            query = search.lower()
            searchable = f"{bio.biomarker_id} {bio.canonical_name} {bio.loinc} {' '.join(bio.aliases)}".lower()
            if query not in searchable:
                continue
        entries.append({
            "biomarker_id": bio.biomarker_id,
            "canonical_name": bio.canonical_name,
            "loinc": bio.loinc,
            "normalized_unit": bio.normalized_unit,
            "allowed_specimens": sorted(bio.allowed_specimens),
            "aliases": list(bio.aliases),
        })
    return {"biomarkers": entries, "count": len(entries)}


# --- Normalize (JSON body) ---

@app.post("/normalize")
def normalize(
    body: dict[str, Any],
    emit_fhir: bool = Query(False, description="Include FHIR Bundle in response"),
) -> dict[str, Any]:
    rows = body.get("rows", [])
    input_file = body.get("input_file", "")

    if not rows:
        return {"error": "No rows provided. Send {\"rows\": [...]}"}

    result = normalize_rows(rows, input_file=input_file)
    response = result.to_json_dict()

    if emit_fhir:
        response["fhir_bundle"] = build_bundle(result)

    return response


# --- Normalize (file upload) ---

@app.post("/normalize/upload")
def normalize_upload(
    file: UploadFile = File(...),
    emit_fhir: bool = Query(False, description="Include FHIR Bundle in response"),
) -> dict[str, Any]:
    suffix = Path(file.filename or "upload.csv").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = file.file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        rows = read_input(tmp_path)
        result = normalize_rows(rows, input_file=file.filename or "")
        response = result.to_json_dict()
        if emit_fhir:
            response["fhir_bundle"] = build_bundle(result)
        return response
    finally:
        tmp_path.unlink(missing_ok=True)


# --- Analyze (JSON body) ---

@app.post("/analyze")
def analyze(body: dict[str, Any]) -> dict[str, Any]:
    rows = body.get("rows", [])
    input_file = body.get("input_file", "")

    if not rows:
        return {"error": "No rows provided. Send {\"rows\": [...]}"}

    result = normalize_rows(rows, input_file=input_file)
    return _build_analysis(result)


# --- Analyze (file upload) ---

@app.post("/analyze/upload")
def analyze_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(file.filename or "upload.csv").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = file.file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        rows = read_input(tmp_path)
        result = normalize_rows(rows, input_file=file.filename or "")
        return _build_analysis(result)
    finally:
        tmp_path.unlink(missing_ok=True)


def _build_analysis(result: Any) -> dict[str, Any]:
    mapped_biomarkers: dict[str, int] = {}
    unmapped_tests: dict[str, int] = {}
    review_reasons: dict[str, int] = {}
    unsupported_units: dict[str, int] = {}

    for r in result.records:
        if r.mapping_status == "mapped":
            mapped_biomarkers[r.canonical_biomarker_name] = mapped_biomarkers.get(r.canonical_biomarker_name, 0) + 1
        elif r.mapping_status == "unmapped":
            unmapped_tests[r.source_test_name] = unmapped_tests.get(r.source_test_name, 0) + 1
        elif r.mapping_status == "review_needed":
            key = f"{r.source_test_name} ({r.status_reason})"
            review_reasons[key] = review_reasons.get(key, 0) + 1
            if r.status_reason == "unsupported_unit_for_biomarker":
                ukey = f"{r.source_test_name}: {r.source_unit}"
                unsupported_units[ukey] = unsupported_units.get(ukey, 0) + 1

    total = result.summary["total_rows"]
    mapped_pct = result.summary["mapped"] / total * 100 if total else 0

    return {
        "input_file": result.input_file,
        "summary": result.summary,
        "mapping_rate": round(mapped_pct, 1),
        "mapped_biomarkers": dict(sorted(mapped_biomarkers.items(), key=lambda x: -x[1])),
        "unmapped_tests": dict(sorted(unmapped_tests.items(), key=lambda x: -x[1])),
        "review_reasons": dict(sorted(review_reasons.items(), key=lambda x: -x[1])),
        "unsupported_units": dict(sorted(unsupported_units.items(), key=lambda x: -x[1])),
        "warnings": list(result.warnings),
    }


def main() -> None:
    """Entry point for bnt serve."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
