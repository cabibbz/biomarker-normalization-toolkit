"""REST API for the Biomarker Normalization Toolkit.

Start with: bnt serve --port 8000
Or: uvicorn biomarker_normalization_toolkit.api:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
import os
import tempfile
import traceback
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from biomarker_normalization_toolkit import __version__
from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG
from biomarker_normalization_toolkit.fhir import build_bundle
from biomarker_normalization_toolkit.io_utils import read_input
from biomarker_normalization_toolkit.normalizer import normalize_rows

logger = logging.getLogger("bnt.api")

MAX_ROWS = 100_000
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_JSON_BODY_BYTES = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {".csv", ".json", ".hl7", ".oru", ".xml", ".xlsx", ".xls"}

CORS_ORIGINS = os.environ.get("BNT_CORS_ORIGINS", "*").split(",")

app = FastAPI(
    title="Biomarker Normalization Toolkit",
    description="Normalize messy lab data into canonical machine-readable output.",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


from starlette.middleware.base import BaseHTTPMiddleware


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_JSON_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"error": f"Request body too large. Maximum is {MAX_JSON_BODY_BYTES // (1024 * 1024)} MB."},
            )
        return await call_next(request)


app.add_middleware(BodySizeLimitMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


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


# --- Helpers ---

def _coerce_row(row: Any) -> dict[str, str]:
    """Coerce a row dict to string values, handling non-string inputs."""
    if not isinstance(row, dict):
        return {}
    return {str(k): str(v) if v is not None else "" for k, v in row.items()}


def _validate_rows(body: dict[str, Any]) -> tuple[list[dict[str, str]], str | None]:
    """Extract and validate rows from request body. Returns (rows, error_message)."""
    rows = body.get("rows")
    if not isinstance(rows, list) or not rows:
        return [], "No rows provided. Send {\"rows\": [{...}, ...]}"
    if len(rows) > MAX_ROWS:
        return [], f"Too many rows ({len(rows)}). Maximum is {MAX_ROWS}."
    non_dict = sum(1 for r in rows if not isinstance(r, dict))
    if non_dict:
        return [], f"{non_dict} row(s) are not objects. Each row must be a JSON object."
    return [_coerce_row(r) for r in rows], None


def _read_upload(file: UploadFile) -> tuple[list[dict[str, str]], str | None]:
    """Read an uploaded file with size and extension validation. Returns (rows, error_message)."""
    filename = Path(file.filename or "upload.csv").name  # Strip path components
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return [], f"Unsupported file type: {suffix}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"

    # Read with size limit
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        return [], f"File too large. Maximum is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        rows = read_input(tmp_path)
        return rows, None
    except Exception as exc:
        return [], f"Failed to parse file: {exc}"
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


# --- Normalize (JSON body) ---

@app.post("/normalize")
def normalize(
    body: dict[str, Any],
    emit_fhir: bool = Query(False, description="Include FHIR Bundle in response"),
    fuzzy_threshold: float = Query(0.0, description="Fuzzy matching threshold (0=disabled, 0.85=recommended)"),
) -> JSONResponse:
    rows, error = _validate_rows(body)
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    input_file = Path(str(body.get("input_file", ""))).name
    result = normalize_rows(rows, input_file=input_file, fuzzy_threshold=fuzzy_threshold)
    response = result.to_json_dict()

    if emit_fhir:
        response["fhir_bundle"] = build_bundle(result)

    # Longevity intelligence (always included when data is available)
    from biomarker_normalization_toolkit.derived import compute_derived_metrics
    from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges, summarize_optimal
    derived = compute_derived_metrics(result)
    if derived:
        response["derived_metrics"] = derived
    optimal = evaluate_optimal_ranges(result)
    if optimal:
        response["optimal_ranges"] = summarize_optimal(optimal)

    # PhenoAge if age provided
    age = body.get("chronological_age")
    if age is not None:
        from biomarker_normalization_toolkit.phenoage import compute_phenoage
        pheno = compute_phenoage(result, chronological_age=float(age))
        if pheno:
            response["phenoage"] = pheno

    return JSONResponse(content=response)


# --- Normalize (file upload) ---

@app.post("/normalize/upload")
def normalize_upload(
    file: UploadFile = File(...),
    emit_fhir: bool = Query(False, description="Include FHIR Bundle in response"),
    fuzzy_threshold: float = Query(0.0, description="Fuzzy matching threshold (0=disabled, 0.85=recommended)"),
) -> JSONResponse:
    rows, error = _read_upload(file)
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    safe_name = Path(file.filename or "").name
    result = normalize_rows(rows, input_file=safe_name, fuzzy_threshold=fuzzy_threshold)
    response = result.to_json_dict()
    if emit_fhir:
        response["fhir_bundle"] = build_bundle(result)
    return JSONResponse(content=response)


# --- Analyze (JSON body) ---

@app.post("/analyze")
def analyze(body: dict[str, Any]) -> JSONResponse:
    rows, error = _validate_rows(body)
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    input_file = Path(str(body.get("input_file", ""))).name
    result = normalize_rows(rows, input_file=input_file)
    return JSONResponse(content=_build_analysis(result))


# --- Analyze (file upload) ---

@app.post("/analyze/upload")
def analyze_upload(file: UploadFile = File(...)) -> JSONResponse:
    rows, error = _read_upload(file)
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    safe_name = Path(file.filename or "").name
    result = normalize_rows(rows, input_file=safe_name)
    return JSONResponse(content=_build_analysis(result))


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
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
