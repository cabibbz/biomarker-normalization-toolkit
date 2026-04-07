"""REST API for the Biomarker Normalization Toolkit.

Start with: bnt serve --port 8000
Or: uvicorn biomarker_normalization_toolkit.api:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Header, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from biomarker_normalization_toolkit import __version__
from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG, ALIAS_INDEX, normalize_key
from biomarker_normalization_toolkit.derived import compute_derived_metrics
from biomarker_normalization_toolkit.fhir import build_bundle
from biomarker_normalization_toolkit.io_utils import read_input
from biomarker_normalization_toolkit.licensing import validate_api_key
from biomarker_normalization_toolkit.longitudinal import compare_results
from biomarker_normalization_toolkit.normalizer import normalize_rows
from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges, summarize_optimal
from biomarker_normalization_toolkit.phenoage import compute_phenoage

logger = logging.getLogger("bnt.api")

MAX_ROWS = 100_000
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_JSON_BODY_BYTES = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {".csv", ".json", ".hl7", ".oru", ".xml", ".xlsx", ".xls"}

CORS_ORIGINS = os.environ.get("BNT_CORS_ORIGINS", "*").split(",")

app = FastAPI(
    title="Biomarker Normalization Toolkit",
    description=(
        "Normalize messy lab data into canonical machine-readable output. "
        "183 biomarkers, PhenoAge biological age, optimal longevity ranges, "
        "derived metabolic metrics, longitudinal tracking."
    ),
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_JSON_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"error": f"Request body too large. Maximum is {MAX_JSON_BODY_BYTES // (1024 * 1024)} MB."},
            )
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        response.headers["X-Request-Duration-Ms"] = str(round(elapsed * 1000, 1))
        return response


app.add_middleware(BodySizeLimitMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ─── Helpers ──────────────────────────────────────────────

def _coerce_row(row: Any) -> dict[str, str]:
    if not isinstance(row, dict):
        return {}
    return {str(k): str(v) if v is not None else "" for k, v in row.items()}


def _validate_rows(body: dict[str, Any]) -> tuple[list[dict[str, str]], str | None]:
    rows = body.get("rows")
    if not isinstance(rows, list) or not rows:
        return [], 'No rows provided. Send {"rows": [{...}, ...]}'
    if len(rows) > MAX_ROWS:
        return [], f"Too many rows ({len(rows)}). Maximum is {MAX_ROWS}."
    non_dict = sum(1 for r in rows if not isinstance(r, dict))
    if non_dict:
        return [], f"{non_dict} row(s) are not objects. Each row must be a JSON object."
    return [_coerce_row(r) for r in rows], None


def _read_upload(file: UploadFile) -> tuple[list[dict[str, str]], str | None]:
    filename = Path(file.filename or "upload.csv").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return [], f"Unsupported file type: {suffix}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        return [], f"File too large. Maximum is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        return read_input(tmp_path), None
    except Exception as exc:
        return [], f"Failed to parse file: {exc}"
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _enrich_response(
    result: Any, response: dict[str, Any], features: dict[str, bool],
    chronological_age: float | None = None,
) -> None:
    """Add derived metrics, optimal ranges, and PhenoAge to a response dict."""
    derived = compute_derived_metrics(result)
    if derived and features.get("derived_metrics"):
        response["derived_metrics"] = derived

    if features.get("optimal_ranges"):
        optimal = evaluate_optimal_ranges(result)
        if optimal:
            response["optimal_ranges"] = summarize_optimal(optimal)

    if chronological_age is not None and features.get("phenoage"):
        pheno = compute_phenoage(result, chronological_age=chronological_age)
        if pheno:
            response["phenoage"] = pheno
    elif chronological_age is not None and not features.get("phenoage"):
        response["phenoage"] = {"error": "PhenoAge requires Pro tier."}


def _get_license(x_api_key: str | None) -> dict[str, Any]:
    return validate_api_key(x_api_key)


# ─── Health ───────────────────────────────────────────────

@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "biomarkers": len(BIOMARKER_CATALOG),
    }


# ─── Catalog ──────────────────────────────────────────────

@app.get("/catalog")
def catalog(
    search: str | None = Query(None, description="Filter by name, LOINC, or alias"),
    limit: int = Query(200, description="Max results to return"),
    offset: int = Query(0, description="Skip first N results"),
) -> dict[str, Any]:
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
    total = len(entries)
    page = entries[offset:offset + limit]
    return {"biomarkers": page, "count": len(page), "total": total, "offset": offset}


# ─── Lookup (lightweight single-biomarker check) ─────────

@app.get("/lookup")
def lookup(
    test_name: str = Query(..., description="Test name to look up"),
    specimen: str = Query("", description="Specimen type (optional)"),
) -> dict[str, Any]:
    key = normalize_key(test_name)
    candidates = ALIAS_INDEX.get(key, [])
    if not candidates:
        return {"matched": False, "test_name": test_name, "alias_key": key, "candidates": []}
    results = []
    for bio_id in candidates:
        bio = BIOMARKER_CATALOG[bio_id]
        results.append({
            "biomarker_id": bio.biomarker_id,
            "canonical_name": bio.canonical_name,
            "loinc": bio.loinc,
            "normalized_unit": bio.normalized_unit,
        })
    return {"matched": True, "test_name": test_name, "alias_key": key, "candidates": results}


# ─── Normalize (JSON body) ───────────────────────────────

@app.post("/normalize")
def normalize(
    body: dict[str, Any],
    emit_fhir: bool = Query(False, description="Include FHIR Bundle in response"),
    fuzzy_threshold: float = Query(0.0, description="Fuzzy matching threshold (0=disabled, 0.85=recommended)"),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> JSONResponse:
    license_info = _get_license(x_api_key)
    features = license_info["features"]

    rows, error = _validate_rows(body)
    if error:
        return JSONResponse(status_code=400, content={"error": error})
    if len(rows) > license_info["max_rows"]:
        return JSONResponse(status_code=400, content={
            "error": f"Row limit exceeded ({license_info['tier']} tier: {license_info['max_rows']} max).",
        })

    if fuzzy_threshold > 0 and not features.get("fuzzy"):
        fuzzy_threshold = 0.0

    input_file = Path(str(body.get("input_file", ""))).name
    result = normalize_rows(rows, input_file=input_file, fuzzy_threshold=fuzzy_threshold)
    response = result.to_json_dict()
    response["tier"] = license_info["tier"]

    if emit_fhir:
        response["fhir_bundle"] = build_bundle(result)

    _enrich_response(result, response, features, chronological_age=body.get("chronological_age"))
    return JSONResponse(content=response)


# ─── Normalize (file upload) ─────────────────────────────

@app.post("/normalize/upload")
def normalize_upload(
    file: UploadFile = File(...),
    emit_fhir: bool = Query(False, description="Include FHIR Bundle in response"),
    fuzzy_threshold: float = Query(0.0, description="Fuzzy matching threshold"),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> JSONResponse:
    license_info = _get_license(x_api_key)
    features = license_info["features"]

    rows, error = _read_upload(file)
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    if fuzzy_threshold > 0 and not features.get("fuzzy"):
        fuzzy_threshold = 0.0

    safe_name = Path(file.filename or "").name
    result = normalize_rows(rows, input_file=safe_name, fuzzy_threshold=fuzzy_threshold)
    response = result.to_json_dict()
    response["tier"] = license_info["tier"]

    if emit_fhir:
        response["fhir_bundle"] = build_bundle(result)

    _enrich_response(result, response, features)
    return JSONResponse(content=response)


# ─── Analyze ──────────────────────────────────────────────

@app.post("/analyze")
def analyze(
    body: dict[str, Any],
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> JSONResponse:
    license_info = _get_license(x_api_key)
    rows, error = _validate_rows(body)
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    input_file = Path(str(body.get("input_file", ""))).name
    result = normalize_rows(rows, input_file=input_file)
    response = _build_analysis(result)
    response["tier"] = license_info["tier"]
    return JSONResponse(content=response)


@app.post("/analyze/upload")
def analyze_upload(
    file: UploadFile = File(...),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> JSONResponse:
    license_info = _get_license(x_api_key)
    rows, error = _read_upload(file)
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    safe_name = Path(file.filename or "").name
    result = normalize_rows(rows, input_file=safe_name)
    response = _build_analysis(result)
    response["tier"] = license_info["tier"]
    return JSONResponse(content=response)


# ─── PhenoAge (dedicated endpoint) ───────────────────────

@app.post("/phenoage")
def phenoage_endpoint(
    body: dict[str, Any],
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> JSONResponse:
    """Compute PhenoAge biological age from biomarker values.

    Required: chronological_age (number) and rows with at least
    albumin, creatinine, glucose, CRP, lymphocytes %, MCV, RDW, ALP, WBC.
    """
    license_info = _get_license(x_api_key)
    if not license_info["features"].get("phenoage"):
        return JSONResponse(status_code=403, content={"error": "PhenoAge requires Pro tier."})

    age = body.get("chronological_age")
    if age is None:
        return JSONResponse(status_code=400, content={"error": "chronological_age is required."})

    rows, error = _validate_rows(body)
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    result = normalize_rows(rows)
    pheno = compute_phenoage(result, chronological_age=float(age))
    return JSONResponse(content=pheno or {"error": "Could not compute PhenoAge"})


# ─── Optimal Ranges (dedicated endpoint) ─────────────────

@app.post("/optimal-ranges")
def optimal_ranges_endpoint(
    body: dict[str, Any],
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> JSONResponse:
    """Evaluate biomarker values against longevity-optimal ranges."""
    license_info = _get_license(x_api_key)
    if not license_info["features"].get("optimal_ranges"):
        return JSONResponse(status_code=403, content={"error": "Optimal ranges require Pro tier."})

    rows, error = _validate_rows(body)
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    result = normalize_rows(rows)
    evals = evaluate_optimal_ranges(result)
    return JSONResponse(content=summarize_optimal(evals))


# ─── Compare (longitudinal tracking) ─────────────────────

@app.post("/compare")
def compare_endpoint(
    body: dict[str, Any],
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> JSONResponse:
    """Compare two sets of lab results (before/after) for longitudinal tracking.

    Body: {"before": {"rows": [...]}, "after": {"rows": [...]}, "days_between": 90}
    """
    license_info = _get_license(x_api_key)
    if not license_info["features"].get("optimal_ranges"):
        return JSONResponse(status_code=403, content={"error": "Longitudinal tracking requires Pro tier."})

    before_data = body.get("before", {})
    after_data = body.get("after", {})

    before_rows = before_data.get("rows", [])
    after_rows = after_data.get("rows", [])

    if not before_rows or not after_rows:
        return JSONResponse(status_code=400, content={
            "error": 'Provide {"before": {"rows": [...]}, "after": {"rows": [...]}}',
        })

    before_result = normalize_rows([_coerce_row(r) for r in before_rows])
    after_result = normalize_rows([_coerce_row(r) for r in after_rows])

    days = body.get("days_between")
    comparison = compare_results(before_result, after_result, days_between=float(days) if days else None)
    return JSONResponse(content=comparison)


# ─── Analysis helper ──────────────────────────────────────

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


# ─── Entry point ──────────────────────────────────────────

def main() -> None:
    """Entry point for bnt serve."""
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
