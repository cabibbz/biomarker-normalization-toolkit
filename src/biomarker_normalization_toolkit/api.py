"""REST API for the Biomarker Normalization Toolkit.

Start with: bnt serve --port 8000
Or: uvicorn biomarker_normalization_toolkit.api:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import time
import traceback
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Header, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from biomarker_normalization_toolkit import __version__
from biomarker_normalization_toolkit.catalog import BIOMARKER_CATALOG, ALIAS_INDEX, normalize_key, normalize_specimen
from biomarker_normalization_toolkit.derived import compute_derived_metrics
from biomarker_normalization_toolkit.fhir import build_bundle
from biomarker_normalization_toolkit.io_utils import read_input
from biomarker_normalization_toolkit.licensing import validate_api_key
from biomarker_normalization_toolkit.longitudinal import compare_results
from biomarker_normalization_toolkit.normalizer import normalize_rows
from biomarker_normalization_toolkit.optimal_ranges import evaluate_optimal_ranges, summarize_optimal
from biomarker_normalization_toolkit.phenoage import compute_phenoage

logger = logging.getLogger("bnt.api")

# Structured JSON logging if python-json-logger is available
try:
    from pythonjsonlogger.json import JsonFormatter
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logging.getLogger("bnt").addHandler(handler)
    logging.getLogger("bnt").setLevel(logging.INFO)
except ImportError:
    pass  # Fall back to stdlib logging

MAX_ROWS = 100_000
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_JSON_BODY_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".csv", ".json", ".hl7", ".oru", ".xml", ".xlsx", ".xls"}
CORS_ORIGINS = os.environ.get("BNT_CORS_ORIGINS", "").split(",")
CORS_ORIGINS = [o.strip() for o in CORS_ORIGINS if o.strip()]  # No wildcard by default
RATE_LIMIT_REQUESTS = int(os.environ.get("BNT_RATE_LIMIT", "60"))  # per minute per key
RATE_LIMIT_WINDOW = 60  # seconds
_INTERNAL_ROWS_HEADER = "X-BNT-Rows-Processed"


# ─── Pydantic Models ─────────────────────────────────────


class NormalizeRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(..., description="List of lab result row objects")
    input_file: str = ""
    chronological_age: float | None = Field(None, ge=0, description="Patient age for PhenoAge (Pro tier)")
    sex: str | None = Field(None, description="Patient sex (male/female) for sex-specific optimal ranges")


class CompareRequest(BaseModel):
    before: dict[str, Any] = Field(..., description='{"rows": [...]} for baseline results')
    after: dict[str, Any] = Field(..., description='{"rows": [...]} for follow-up results')
    days_between: float | None = Field(None, ge=0, description="Days between the two tests")


class PhenoAgeRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(..., description="Lab result rows (need 9 biomarkers)")
    chronological_age: float = Field(..., ge=0, description="Patient age in years")


# ─── Rate Limiter ─────────────────────────────────────────

class RateLimiter:
    """Thread-safe in-memory sliding window rate limiter per API key."""

    MAX_KEYS = 10_000

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        import threading
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            if len(self._requests) > self.MAX_KEYS:
                stale = [k for k, v in self._requests.items() if not v or v[-1] < cutoff]
                for k in stale:
                    del self._requests[k]
            entries = self._requests[key]
            self._requests[key] = [t for t in entries if t > cutoff]
            entries = self._requests[key]
            if len(entries) >= self.max_requests:
                return False, 0
            entries.append(now)
            return True, self.max_requests - len(entries)

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()


_rate_limiter = RateLimiter(max_requests=RATE_LIMIT_REQUESTS, window_seconds=RATE_LIMIT_WINDOW)


# ─── Metrics Collector ────────────────────────────────────

class MetricsCollector:
    """Thread-safe in-memory metrics for /metrics endpoint."""

    def __init__(self) -> None:
        import threading
        self._lock = threading.Lock()
        self.request_count: int = 0
        self.error_count: int = 0
        self.total_rows_processed: int = 0
        self.total_latency_ms: float = 0.0
        self.endpoint_counts: dict[str, int] = defaultdict(int)
        self.status_counts: dict[int, int] = defaultdict(int)
        self.start_time: float = time.time()

    def record(self, endpoint: str, status: int, latency_ms: float, rows: int = 0) -> None:
        with self._lock:
            self.request_count += 1
            self.endpoint_counts[endpoint] += 1
            self.status_counts[status] += 1
            self.total_latency_ms += latency_ms
            self.total_rows_processed += rows
            if status >= 400:
                self.error_count += 1

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            uptime = time.time() - self.start_time
            avg_latency = self.total_latency_ms / self.request_count if self.request_count else 0
            return {
                "uptime_seconds": round(uptime, 1),
                "total_requests": self.request_count,
                "total_errors": self.error_count,
                "error_rate": round(self.error_count / self.request_count * 100, 2) if self.request_count else 0,
                "total_rows_processed": self.total_rows_processed,
                "avg_latency_ms": round(avg_latency, 2),
                "requests_per_endpoint": dict(self.endpoint_counts),
                "status_code_counts": dict(self.status_counts),
            }

    def to_prometheus(self) -> str:
        _KNOWN_ENDPOINTS = {"/normalize", "/normalize/upload", "/analyze",
                            "/analyze/upload", "/phenoage", "/optimal-ranges",
                            "/compare", "/lookup", "/catalog",
                            "/health", "/metrics",
                            "/v1/health", "/v1/metrics", "/v1/catalog", "/v1/lookup",
                            "/v1/normalize", "/v1/normalize/upload", "/v1/analyze",
                            "/v1/analyze/upload", "/v1/phenoage", "/v1/optimal-ranges",
                            "/v1/compare"}
        with self._lock:
            req_count = self.request_count
            err_count = self.error_count
            rows_proc = self.total_rows_processed
            avg = self.total_latency_ms / req_count if req_count else 0
            endpoint_snapshot = dict(self.endpoint_counts)
        lines = []
        lines.append(f"# HELP bnt_requests_total Total API requests")
        lines.append(f"# TYPE bnt_requests_total counter")
        lines.append(f"bnt_requests_total {req_count}")
        lines.append(f"# HELP bnt_errors_total Total API errors")
        lines.append(f"# TYPE bnt_errors_total counter")
        lines.append(f"bnt_errors_total {err_count}")
        lines.append(f"# HELP bnt_rows_processed_total Total lab rows processed")
        lines.append(f"# TYPE bnt_rows_processed_total counter")
        lines.append(f"bnt_rows_processed_total {rows_proc}")
        lines.append(f"# HELP bnt_avg_latency_ms Average request latency")
        lines.append(f"# TYPE bnt_avg_latency_ms gauge")
        lines.append(f"bnt_avg_latency_ms {avg:.2f}")
        for ep, count in endpoint_snapshot.items():
            if ep not in _KNOWN_ENDPOINTS:
                ep = "/unknown"
            safe_ep = re.sub(r"[^a-zA-Z0-9_/]", "", ep).replace("/", "_").strip("_")
            lines.append(f'bnt_endpoint_requests{{endpoint="{safe_ep}"}} {count}')
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self.request_count = 0
            self.error_count = 0
            self.total_rows_processed = 0
            self.total_latency_ms = 0.0
            self.endpoint_counts.clear()
            self.status_counts.clear()
            self.start_time = time.time()


_metrics = MetricsCollector()


# ─── App Setup ────────────────────────────────────────────

app = FastAPI(
    title="Biomarker Normalization Toolkit",
        description=(
            "Normalize messy lab data into canonical machine-readable output. "
            "282 biomarkers, PhenoAge biological age, optimal longevity ranges, "
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


class RequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # Enforce body size limit (checks header AND actual body for chunked transfers)
        content_length = request.headers.get("content-length")
        try:
            if content_length and int(content_length) > MAX_JSON_BODY_BYTES:
                return JSONResponse(status_code=413, content={
                    "error": f"Request body too large. Maximum is {MAX_JSON_BODY_BYTES // (1024 * 1024)} MB."})
        except (ValueError, TypeError):
            pass
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()
            if len(body) > MAX_JSON_BODY_BYTES:
                return JSONResponse(status_code=413, content={
                    "error": f"Request body too large. Maximum is {MAX_JSON_BODY_BYTES // (1024 * 1024)} MB."})

        # Rate limiting
        api_key = request.headers.get("x-api-key", "anonymous")
        allowed, remaining = _rate_limiter.check(api_key)
        if not allowed:
            return JSONResponse(status_code=429, content={
                "error": f"Rate limit exceeded. Maximum {RATE_LIMIT_REQUESTS} requests per minute."
            }, headers={"Retry-After": str(RATE_LIMIT_WINDOW), "X-RateLimit-Remaining": "0"})

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        rows_processed = 0
        raw_rows = response.headers.get(_INTERNAL_ROWS_HEADER, "0")
        if _INTERNAL_ROWS_HEADER in response.headers:
            del response.headers[_INTERNAL_ROWS_HEADER]
        try:
            rows_processed = max(0, int(raw_rows))
        except (TypeError, ValueError):
            rows_processed = 0

        response.headers["X-Request-Duration-Ms"] = str(round(elapsed_ms, 1))
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-Request-Id"] = str(uuid.uuid4())

        _metrics.record(request.url.path, response.status_code, elapsed_ms, rows=rows_processed)
        return response


app.add_middleware(RequestMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = str(uuid.uuid4())
    logger.error("Unhandled error [request_id=%s]: %s\n%s", request_id, exc, traceback.format_exc())
    return JSONResponse(status_code=500, content={
        "error": "Internal server error",
        "request_id": request_id,
    })


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


def _apply_tier_filter(result: "NormalizationResult", allowed_ids: set[str] | list[str] | None) -> "NormalizationResult":
    """Filter biomarkers not in allowed_ids for free-tier enforcement."""
    if allowed_ids is None:
        return result
    from biomarker_normalization_toolkit.models import NormalizedRecord
    filtered = []
    for r in result.records:
        if r.canonical_biomarker_id and r.canonical_biomarker_id not in allowed_ids:
            filtered.append(NormalizedRecord(
                source_row_number=r.source_row_number, source_row_id=r.source_row_id,
                source_lab_name=r.source_lab_name, source_panel_name=r.source_panel_name,
                source_test_name=r.source_test_name, alias_key=r.alias_key,
                raw_value=r.raw_value, source_unit=r.source_unit,
                specimen_type=r.specimen_type, source_reference_range=r.source_reference_range,
                canonical_biomarker_id="", canonical_biomarker_name="",
                loinc="", mapping_status="review_needed", match_confidence="none",
                status_reason="biomarker_requires_pro_tier",
                mapping_rule="", normalized_value="", normalized_unit="",
                normalized_reference_range="", provenance=r.provenance,
            ))
        else:
            filtered.append(r)
    return result.__class__(
        input_file=result.input_file,
        summary={
            "total_rows": len(filtered),
            "mapped": sum(1 for r in filtered if r.mapping_status == "mapped"),
            "review_needed": sum(1 for r in filtered if r.mapping_status == "review_needed"),
            "unmapped": sum(1 for r in filtered if r.mapping_status == "unmapped"),
            "confidence_breakdown": {
                "high": sum(1 for r in filtered if r.match_confidence == "high"),
                "medium": sum(1 for r in filtered if r.match_confidence == "medium"),
                "low": sum(1 for r in filtered if r.match_confidence == "low"),
                "none": sum(1 for r in filtered if r.match_confidence == "none"),
            },
        },
        records=filtered,
        warnings=result.warnings,
    )


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
        logger.warning("File parse error for %s: %s", suffix, exc, exc_info=True)
        return [], f"Failed to parse uploaded {suffix} file. Ensure the file is valid and not corrupted."
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _enrich_response(
    result: Any, response: dict[str, Any], features: dict[str, bool],
    chronological_age: float | None = None, sex: str | None = None,
) -> None:
    derived = compute_derived_metrics(result)
    if derived and features.get("derived_metrics"):
        response["derived_metrics"] = derived
    elif derived:
        response["derived_metrics"] = {"status": "upgrade_required", "message": "Derived metrics require Pro tier."}
    if features.get("optimal_ranges"):
        optimal = evaluate_optimal_ranges(result, sex=sex)
        if optimal:
            response["optimal_ranges"] = summarize_optimal(optimal)
    else:
        response["optimal_ranges"] = {"status": "upgrade_required", "message": "Optimal ranges require Pro tier."}
    if chronological_age is not None and features.get("phenoage"):
        pheno = compute_phenoage(result, chronological_age=chronological_age)
        if pheno:
            response["phenoage"] = pheno
    elif chronological_age is not None and not features.get("phenoage"):
        response["phenoage"] = {"error": "PhenoAge requires Pro tier."}


def _get_license(x_api_key: str | None) -> dict[str, Any]:
    info = validate_api_key(x_api_key)
    # If a key was provided but is invalid, we still allow free tier
    # but include a warning in the response
    return info


def _check_key_validity(license_info: dict[str, Any], x_api_key: str | None) -> JSONResponse | None:
    """Return a 401 response if an API key was provided but is invalid."""
    if x_api_key and not license_info.get("valid", True):
        return JSONResponse(status_code=401, content={
            "error": "Invalid API key. Check your X-API-Key header.",
            "tier": "free",
        })
    return None


def _with_rows_processed(response: JSONResponse, rows: int) -> JSONResponse:
    if rows > 0:
        response.headers[_INTERNAL_ROWS_HEADER] = str(rows)
    return response


# ─── Health + Metrics ─────────────────────────────────────

@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": __version__, "biomarkers": len(BIOMARKER_CATALOG)}


@app.get("/metrics")
def metrics(accept: Annotated[str, Header()] = "application/json") -> Any:
    """Prometheus-compatible metrics endpoint."""
    if "text/plain" in accept or "prometheus" in accept.lower():
        from starlette.responses import PlainTextResponse
        return PlainTextResponse(_metrics.to_prometheus(), media_type="text/plain")
    return _metrics.to_dict()


# ─── Catalog ──────────────────────────────────────────────

@app.get("/catalog")
def catalog(
    search: Annotated[str | None, Query(description="Filter by name, LOINC, or alias")] = None,
    limit: Annotated[int | None, Query(description="Max results to return", ge=0)] = None,
    offset: Annotated[int, Query(description="Skip first N results", ge=0)] = 0,
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
    page = entries[offset:] if limit is None else entries[offset:offset + limit]
    return {"biomarkers": page, "count": len(page), "total": total, "offset": offset}


# ─── Lookup ───────────────────────────────────────────────

@app.get("/lookup")
def lookup(
    test_name: Annotated[str, Query(description="Test name to look up")],
    specimen: Annotated[str, Query(description="Specimen type (optional)")] = "",
) -> dict[str, Any]:
    key = normalize_key(test_name)
    candidates = ALIAS_INDEX.get(key, [])
    specimen_key = normalize_specimen(specimen) if specimen else None
    if specimen_key:
        candidates = [
            bio_id
            for bio_id in candidates
            if not BIOMARKER_CATALOG[bio_id].allowed_specimens
            or specimen_key in BIOMARKER_CATALOG[bio_id].allowed_specimens
        ]
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


# ─── V1 Router (versioned) ───────────────────────────────
# All endpoints are also available under /v1/ prefix for API versioning.

from fastapi import APIRouter
v1 = APIRouter(prefix="/v1", tags=["v1"])


# ─── Normalize ────────────────────────────────────────────

def _handle_normalize(body: dict[str, Any], emit_fhir: bool, fuzzy_threshold: float,
                      x_api_key: str | None) -> JSONResponse:
    license_info = _get_license(x_api_key)
    features = license_info["features"]

    # Reject invalid API keys with 401
    rejection = _check_key_validity(license_info, x_api_key)
    if rejection:
        return rejection

    rows, error = _validate_rows(body)
    if error:
        return JSONResponse(status_code=400, content={"error": error})
    if len(rows) > license_info["max_rows"]:
        return JSONResponse(status_code=400, content={
            "error": f"Row limit exceeded ({license_info['tier']} tier: {license_info['max_rows']} max)."})
    if fuzzy_threshold > 0 and not features.get("fuzzy"):
        fuzzy_threshold = 0.0
    input_file = Path(str(body.get("input_file", ""))).name
    result = normalize_rows(rows, input_file=input_file, fuzzy_threshold=fuzzy_threshold)

    # Enforce biomarker filtering for free tier
    result = _apply_tier_filter(result, license_info.get("biomarker_ids"))

    # Row count tracked via middleware record() call — no double-counting
    response = result.to_json_dict(include_generated_at=True)
    response["tier"] = license_info["tier"]
    if emit_fhir:
        response["fhir_bundle"] = build_bundle(result)
    _enrich_response(result, response, features, chronological_age=body.get("chronological_age"), sex=body.get("sex"))
    return _with_rows_processed(JSONResponse(content=response), len(rows))


@app.post("/normalize")
def normalize(body: NormalizeRequest,
              emit_fhir: bool = Query(False), fuzzy_threshold: float = Query(0.0),
              x_api_key: str | None = Header(None, alias="X-API-Key")) -> JSONResponse:
    return _handle_normalize(body.model_dump(), emit_fhir, fuzzy_threshold, x_api_key)


@v1.post("/normalize")
def normalize_v1(body: NormalizeRequest,
                 emit_fhir: bool = Query(False), fuzzy_threshold: float = Query(0.0),
                 x_api_key: str | None = Header(None, alias="X-API-Key")) -> JSONResponse:
    return _handle_normalize(body.model_dump(), emit_fhir, fuzzy_threshold, x_api_key)


@v1.post("/analyze")
def analyze_v1(body: NormalizeRequest, x_api_key: str | None = Header(None, alias="X-API-Key")) -> JSONResponse:
    return analyze(body, x_api_key)


@v1.post("/phenoage")
def phenoage_v1(body: PhenoAgeRequest, x_api_key: str | None = Header(None, alias="X-API-Key")) -> JSONResponse:
    return phenoage_endpoint(body, x_api_key)


@v1.post("/optimal-ranges")
def optimal_ranges_v1(body: NormalizeRequest, x_api_key: str | None = Header(None, alias="X-API-Key")) -> JSONResponse:
    return optimal_ranges_endpoint(body, x_api_key)


@v1.post("/compare")
def compare_v1(body: CompareRequest, x_api_key: str | None = Header(None, alias="X-API-Key")) -> JSONResponse:
    return compare_endpoint(body, x_api_key)


@v1.get("/health")
def health_v1() -> dict[str, Any]:
    return health()


@v1.get("/metrics")
def metrics_v1(accept: Annotated[str, Header()] = "application/json") -> Any:
    return metrics(accept)


@v1.get("/catalog")
def catalog_v1(
    search: Annotated[str | None, Query(description="Filter by name, LOINC, or alias")] = None,
    limit: Annotated[int | None, Query(description="Max results to return", ge=0)] = None,
    offset: Annotated[int, Query(description="Skip first N results", ge=0)] = 0,
) -> dict[str, Any]:
    return catalog(search, limit, offset)


@v1.get("/lookup")
def lookup_v1(
    test_name: Annotated[str, Query(description="Test name to look up")],
    specimen: Annotated[str, Query(description="Specimen type (optional)")] = "",
) -> dict[str, Any]:
    return lookup(test_name, specimen)


# ─── Normalize Upload ────────────────────────────────────

@app.post("/normalize/upload")
def normalize_upload(file: UploadFile = File(...),
                     emit_fhir: bool = Query(False), fuzzy_threshold: float = Query(0.0),
                     x_api_key: str | None = Header(None, alias="X-API-Key")) -> JSONResponse:
    license_info = _get_license(x_api_key)
    features = license_info["features"]

    rejection = _check_key_validity(license_info, x_api_key)
    if rejection:
        return rejection

    rows, error = _read_upload(file)
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    # Enforce row limits (same as JSON endpoint)
    if len(rows) > license_info["max_rows"]:
        return JSONResponse(status_code=400, content={
            "error": f"Row limit exceeded ({license_info['tier']} tier: {license_info['max_rows']} max)."})

    if fuzzy_threshold > 0 and not features.get("fuzzy"):
        fuzzy_threshold = 0.0
    safe_name = Path(file.filename or "").name
    result = normalize_rows(rows, input_file=safe_name, fuzzy_threshold=fuzzy_threshold)

    # Enforce biomarker filtering for free tier
    result = _apply_tier_filter(result, license_info.get("biomarker_ids"))

    response = result.to_json_dict(include_generated_at=True)
    response["tier"] = license_info["tier"]
    if emit_fhir:
        response["fhir_bundle"] = build_bundle(result)
    _enrich_response(result, response, features)
    return _with_rows_processed(JSONResponse(content=response), len(rows))


@v1.post("/normalize/upload")
def normalize_upload_v1(file: UploadFile = File(...),
                        emit_fhir: bool = Query(False), fuzzy_threshold: float = Query(0.0),
                        x_api_key: str | None = Header(None, alias="X-API-Key")) -> JSONResponse:
    return normalize_upload(file, emit_fhir, fuzzy_threshold, x_api_key)


# ─── Analyze ──────────────────────────────────────────────

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
        "input_file": result.input_file, "summary": result.summary,
        "mapping_rate": round(mapped_pct, 1),
        "mapped_biomarkers": dict(sorted(mapped_biomarkers.items(), key=lambda x: -x[1])),
        "unmapped_tests": dict(sorted(unmapped_tests.items(), key=lambda x: -x[1])),
        "review_reasons": dict(sorted(review_reasons.items(), key=lambda x: -x[1])),
        "unsupported_units": dict(sorted(unsupported_units.items(), key=lambda x: -x[1])),
        "warnings": list(result.warnings),
    }


@app.post("/analyze")
def analyze(body: NormalizeRequest, x_api_key: str | None = Header(None, alias="X-API-Key")) -> JSONResponse:
    license_info = _get_license(x_api_key)
    rejection = _check_key_validity(license_info, x_api_key)
    if rejection:
        return rejection
    rows, error = _validate_rows(body.model_dump())
    if error:
        return JSONResponse(status_code=400, content={"error": error})
    if len(rows) > license_info["max_rows"]:
        return JSONResponse(status_code=400, content={
            "error": f"Row limit exceeded ({license_info['tier']} tier: {license_info['max_rows']} max)."})
    result = normalize_rows(rows, input_file=Path(body.input_file).name if body.input_file else "")
    response = _build_analysis(result)
    response["tier"] = license_info["tier"]
    return _with_rows_processed(JSONResponse(content=response), len(rows))


@app.post("/analyze/upload")
def analyze_upload(file: UploadFile = File(...),
                   x_api_key: str | None = Header(None, alias="X-API-Key")) -> JSONResponse:
    license_info = _get_license(x_api_key)
    rejection = _check_key_validity(license_info, x_api_key)
    if rejection:
        return rejection
    rows, error = _read_upload(file)
    if error:
        return JSONResponse(status_code=400, content={"error": error})
    if len(rows) > license_info["max_rows"]:
        return JSONResponse(status_code=400, content={
            "error": f"Row limit exceeded ({license_info['tier']} tier: {license_info['max_rows']} max)."})
    result = normalize_rows(rows, input_file=Path(file.filename or "").name)
    response = _build_analysis(result)
    response["tier"] = license_info["tier"]
    return _with_rows_processed(JSONResponse(content=response), len(rows))


@v1.post("/analyze/upload")
def analyze_upload_v1(file: UploadFile = File(...),
                      x_api_key: str | None = Header(None, alias="X-API-Key")) -> JSONResponse:
    return analyze_upload(file, x_api_key)


# ─── PhenoAge ─────────────────────────────────────────────

@app.post("/phenoage")
def phenoage_endpoint(body: PhenoAgeRequest,
                      x_api_key: str | None = Header(None, alias="X-API-Key")) -> JSONResponse:
    """Compute PhenoAge biological age. Requires 9 biomarkers + chronological_age."""
    license_info = _get_license(x_api_key)
    rejection = _check_key_validity(license_info, x_api_key)
    if rejection:
        return rejection
    if not license_info["features"].get("phenoage"):
        return JSONResponse(status_code=403, content={"error": "PhenoAge requires Pro tier."})
    rows, error = _validate_rows(body.model_dump())
    if error:
        return JSONResponse(status_code=400, content={"error": error})
    if len(rows) > license_info["max_rows"]:
        return JSONResponse(status_code=400, content={
            "error": f"Row limit exceeded ({license_info['tier']} tier: {license_info['max_rows']} max)."})
    result = normalize_rows(rows)
    pheno = compute_phenoage(result, chronological_age=body.chronological_age)
    return _with_rows_processed(JSONResponse(content=pheno or {"error": "Could not compute PhenoAge"}), len(rows))


# ─── Optimal Ranges ───────────────────────────────────────

@app.post("/optimal-ranges")
def optimal_ranges_endpoint(body: NormalizeRequest,
                            x_api_key: str | None = Header(None, alias="X-API-Key")) -> JSONResponse:
    """Evaluate biomarker values against longevity-optimal ranges."""
    license_info = _get_license(x_api_key)
    rejection = _check_key_validity(license_info, x_api_key)
    if rejection:
        return rejection
    if not license_info["features"].get("optimal_ranges"):
        return JSONResponse(status_code=403, content={"error": "Optimal ranges require Pro tier."})
    rows, error = _validate_rows(body.model_dump())
    if error:
        return JSONResponse(status_code=400, content={"error": error})
    if len(rows) > license_info["max_rows"]:
        return JSONResponse(status_code=400, content={
            "error": f"Row limit exceeded ({license_info['tier']} tier: {license_info['max_rows']} max)."})
    result = normalize_rows(rows)
    return _with_rows_processed(
        JSONResponse(content=summarize_optimal(evaluate_optimal_ranges(result, sex=body.sex))),
        len(rows),
    )


# ─── Compare (Longitudinal) ──────────────────────────────

@app.post("/compare")
def compare_endpoint(body: CompareRequest,
                     x_api_key: str | None = Header(None, alias="X-API-Key")) -> JSONResponse:
    """Compare before/after lab results for longitudinal tracking."""
    license_info = _get_license(x_api_key)
    rejection = _check_key_validity(license_info, x_api_key)
    if rejection:
        return rejection
    if not license_info["features"].get("optimal_ranges"):
        return JSONResponse(status_code=403, content={"error": "Longitudinal tracking requires Pro tier."})
    before_validated, before_err = _validate_rows(body.before)
    if before_err:
        return JSONResponse(status_code=400, content={"error": f"before: {before_err}"})
    after_validated, after_err = _validate_rows(body.after)
    if after_err:
        return JSONResponse(status_code=400, content={"error": f"after: {after_err}"})
    max_rows = license_info["max_rows"]
    if len(before_validated) > max_rows or len(after_validated) > max_rows:
        return JSONResponse(status_code=400, content={
            "error": f"Row limit exceeded ({license_info['tier']} tier: {max_rows} max per set)."})
    before_result = normalize_rows(before_validated)
    after_result = normalize_rows(after_validated)
    comparison = compare_results(before_result, after_result,
                                days_between=body.days_between)
    return _with_rows_processed(JSONResponse(content=comparison), len(before_validated) + len(after_validated))


# ─── Register v1 router ──────────────────────────────────

app.include_router(v1)


# ─── Entry point ──────────────────────────────────────────

def main() -> None:
    """Entry point for bnt serve."""
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
