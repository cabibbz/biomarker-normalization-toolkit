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
from pathlib import PurePosixPath
from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, File, Header, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from biomarker_normalization_toolkit import __version__
from biomarker_normalization_toolkit.catalog import ALIAS_INDEX, BIOMARKER_CATALOG, normalize_key, normalize_specimen
from biomarker_normalization_toolkit.derived import compute_derived_metrics
from biomarker_normalization_toolkit.fhir import build_bundle
from biomarker_normalization_toolkit.io_utils import read_input
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
RATE_LIMIT_REQUESTS = int(os.environ.get("BNT_RATE_LIMIT", "60"))  # per minute per client
RATE_LIMIT_WINDOW = 60  # seconds
_INTERNAL_ROWS_HEADER = "X-BNT-Rows-Processed"


class NormalizeRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(..., description="List of lab result row objects")
    input_file: str = ""
    chronological_age: float | None = Field(None, ge=0, allow_inf_nan=False, description="Patient age for PhenoAge")
    sex: str | None = Field(None, description="Patient sex (male/female) for sex-specific optimal ranges")


class CompareRequest(BaseModel):
    before: dict[str, Any] = Field(..., description='{"rows": [...]} for baseline results')
    after: dict[str, Any] = Field(..., description='{"rows": [...]} for follow-up results')
    days_between: float | None = Field(None, ge=0, allow_inf_nan=False, description="Days between the two tests")


class PhenoAgeRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(..., description="Lab result rows (need 9 biomarkers)")
    chronological_age: float = Field(..., ge=0, allow_inf_nan=False, description="Patient age in years")


class RateLimiter:
    """Thread-safe in-memory sliding window rate limiter per client."""

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
        known_endpoints = {
            "/normalize",
            "/normalize/upload",
            "/analyze",
            "/analyze/upload",
            "/phenoage",
            "/optimal-ranges",
            "/compare",
            "/lookup",
            "/catalog",
            "/health",
            "/metrics",
            "/v1/health",
            "/v1/metrics",
            "/v1/catalog",
            "/v1/lookup",
            "/v1/normalize",
            "/v1/normalize/upload",
            "/v1/analyze",
            "/v1/analyze/upload",
            "/v1/phenoage",
            "/v1/optimal-ranges",
            "/v1/compare",
        }
        with self._lock:
            req_count = self.request_count
            err_count = self.error_count
            rows_proc = self.total_rows_processed
            avg = self.total_latency_ms / req_count if req_count else 0
            endpoint_snapshot = dict(self.endpoint_counts)
        lines = [
            "# HELP bnt_requests_total Total API requests",
            "# TYPE bnt_requests_total counter",
            f"bnt_requests_total {req_count}",
            "# HELP bnt_errors_total Total API errors",
            "# TYPE bnt_errors_total counter",
            f"bnt_errors_total {err_count}",
            "# HELP bnt_rows_processed_total Total lab rows processed",
            "# TYPE bnt_rows_processed_total counter",
            f"bnt_rows_processed_total {rows_proc}",
            "# HELP bnt_avg_latency_ms Average request latency",
            "# TYPE bnt_avg_latency_ms gauge",
            f"bnt_avg_latency_ms {avg:.2f}",
        ]
        for endpoint, count in endpoint_snapshot.items():
            safe_endpoint = endpoint if endpoint in known_endpoints else "/unknown"
            safe_endpoint = re.sub(r"[^a-zA-Z0-9_/]", "", safe_endpoint).replace("/", "_").strip("_")
            lines.append(f'bnt_endpoint_requests{{endpoint="{safe_endpoint}"}} {count}')
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


def _client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "anonymous"
    if request.client and request.client.host:
        return request.client.host
    return "anonymous"


app = FastAPI(
    title="Biomarker Normalization Toolkit",
    description=(
        "Normalize messy lab data into canonical machine-readable output. "
        "297 biomarkers, PhenoAge biological age, curated optimal-range review, "
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
        content_length = request.headers.get("content-length")
        try:
            if content_length and int(content_length) > MAX_JSON_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"error": f"Request body too large. Maximum is {MAX_JSON_BODY_BYTES // (1024 * 1024)} MB."},
                )
        except (ValueError, TypeError):
            pass

        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()
            if len(body) > MAX_JSON_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"error": f"Request body too large. Maximum is {MAX_JSON_BODY_BYTES // (1024 * 1024)} MB."},
                )

        client_id = _client_identifier(request)
        allowed, remaining = _rate_limiter.check(client_id)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error": f"Rate limit exceeded. Maximum {RATE_LIMIT_REQUESTS} requests per minute."},
                headers={"Retry-After": str(RATE_LIMIT_WINDOW), "X-RateLimit-Remaining": "0"},
            )

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

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
    return JSONResponse(status_code=500, content={"error": "Internal server error", "request_id": request_id})


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
    non_dict = sum(1 for row in rows if not isinstance(row, dict))
    if non_dict:
        return [], f"{non_dict} row(s) are not objects. Each row must be a JSON object."
    return [_coerce_row(row) for row in rows], None


def _validate_upload_rows(rows: list[dict[str, str]]) -> str | None:
    if len(rows) > MAX_ROWS:
        return f"Too many rows ({len(rows)}). Maximum is {MAX_ROWS}."
    return None


def _sanitize_client_filename(value: object, default: str = "") -> str:
    raw = str(value or default).replace("\\", "/")
    filename = PurePosixPath(raw).name
    filename = " ".join(filename.split())
    return filename or default


def _read_upload(file: UploadFile) -> tuple[list[dict[str, str]], str | None]:
    filename = _sanitize_client_filename(file.filename, default="upload.csv")
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
    result: Any,
    response: dict[str, Any],
    chronological_age: float | None = None,
    sex: str | None = None,
) -> None:
    derived = compute_derived_metrics(result)
    if derived:
        response["derived_metrics"] = derived

    optimal = evaluate_optimal_ranges(result, sex=sex)
    if optimal:
        response["optimal_ranges"] = summarize_optimal(optimal)

    if chronological_age is not None:
        pheno = compute_phenoage(result, chronological_age=chronological_age)
        if pheno:
            response["phenoage"] = pheno


def _with_rows_processed(response: JSONResponse, rows: int) -> JSONResponse:
    if rows > 0:
        response.headers[_INTERNAL_ROWS_HEADER] = str(rows)
    return response


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


@app.get("/catalog")
def catalog(
    search: Annotated[str | None, Query(description="Filter by name, LOINC, or alias")] = None,
    limit: Annotated[int | None, Query(description="Max results to return", ge=0)] = None,
    offset: Annotated[int, Query(description="Skip first N results", ge=0)] = 0,
) -> dict[str, Any]:
    entries = []
    for _, biomarker in sorted(BIOMARKER_CATALOG.items()):
        if search:
            query = search.lower()
            searchable = (
                f"{biomarker.biomarker_id} {biomarker.canonical_name} "
                f"{biomarker.loinc} {' '.join(biomarker.aliases)}"
            ).lower()
            if query not in searchable:
                continue
        entries.append(
            {
                "biomarker_id": biomarker.biomarker_id,
                "canonical_name": biomarker.canonical_name,
                "loinc": biomarker.loinc,
                "normalized_unit": biomarker.normalized_unit,
                "allowed_specimens": sorted(biomarker.allowed_specimens),
                "aliases": list(biomarker.aliases),
            }
        )
    total = len(entries)
    page = entries[offset:] if limit is None else entries[offset : offset + limit]
    return {"biomarkers": page, "count": len(page), "total": total, "offset": offset}


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
            biomarker_id
            for biomarker_id in candidates
            if not BIOMARKER_CATALOG[biomarker_id].allowed_specimens
            or specimen_key in BIOMARKER_CATALOG[biomarker_id].allowed_specimens
        ]
    if not candidates:
        return {"matched": False, "test_name": test_name, "alias_key": key, "candidates": []}

    results = []
    for biomarker_id in candidates:
        biomarker = BIOMARKER_CATALOG[biomarker_id]
        results.append(
            {
                "biomarker_id": biomarker.biomarker_id,
                "canonical_name": biomarker.canonical_name,
                "loinc": biomarker.loinc,
                "normalized_unit": biomarker.normalized_unit,
            }
        )
    return {"matched": True, "test_name": test_name, "alias_key": key, "candidates": results}


v1 = APIRouter(prefix="/v1", tags=["v1"])


def _handle_normalize(body: dict[str, Any], emit_fhir: bool, fuzzy_threshold: float) -> JSONResponse:
    rows, error = _validate_rows(body)
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    input_file = _sanitize_client_filename(body.get("input_file", ""))
    result = normalize_rows(rows, input_file=input_file, fuzzy_threshold=fuzzy_threshold)

    response = result.to_json_dict(include_generated_at=True)
    if emit_fhir:
        response["fhir_bundle"] = build_bundle(result)
    _enrich_response(result, response, chronological_age=body.get("chronological_age"), sex=body.get("sex"))
    return _with_rows_processed(JSONResponse(content=response), len(rows))


@app.post("/normalize")
def normalize(
    body: NormalizeRequest,
    emit_fhir: bool = Query(False),
    fuzzy_threshold: float = Query(0.0, ge=0.0, le=1.0, allow_inf_nan=False),
) -> JSONResponse:
    return _handle_normalize(body.model_dump(), emit_fhir, fuzzy_threshold)


@v1.post("/normalize")
def normalize_v1(
    body: NormalizeRequest,
    emit_fhir: bool = Query(False),
    fuzzy_threshold: float = Query(0.0, ge=0.0, le=1.0, allow_inf_nan=False),
) -> JSONResponse:
    return _handle_normalize(body.model_dump(), emit_fhir, fuzzy_threshold)


@app.post("/normalize/upload")
def normalize_upload(
    file: UploadFile = File(...),
    emit_fhir: bool = Query(False),
    fuzzy_threshold: float = Query(0.0, ge=0.0, le=1.0, allow_inf_nan=False),
) -> JSONResponse:
    rows, error = _read_upload(file)
    if error:
        return JSONResponse(status_code=400, content={"error": error})
    row_error = _validate_upload_rows(rows)
    if row_error:
        return JSONResponse(status_code=400, content={"error": row_error})

    safe_name = _sanitize_client_filename(file.filename)
    result = normalize_rows(rows, input_file=safe_name, fuzzy_threshold=fuzzy_threshold)

    response = result.to_json_dict(include_generated_at=True)
    if emit_fhir:
        response["fhir_bundle"] = build_bundle(result)
    _enrich_response(result, response)
    return _with_rows_processed(JSONResponse(content=response), len(rows))


@v1.post("/normalize/upload")
def normalize_upload_v1(
    file: UploadFile = File(...),
    emit_fhir: bool = Query(False),
    fuzzy_threshold: float = Query(0.0, ge=0.0, le=1.0, allow_inf_nan=False),
) -> JSONResponse:
    return normalize_upload(file, emit_fhir, fuzzy_threshold)


def _build_analysis(result: Any) -> dict[str, Any]:
    mapped_biomarkers: dict[str, int] = {}
    unmapped_tests: dict[str, int] = {}
    review_reasons: dict[str, int] = {}
    unsupported_units: dict[str, int] = {}
    for record in result.records:
        if record.mapping_status == "mapped":
            mapped_biomarkers[record.canonical_biomarker_name] = mapped_biomarkers.get(record.canonical_biomarker_name, 0) + 1
        elif record.mapping_status == "unmapped":
            unmapped_tests[record.source_test_name] = unmapped_tests.get(record.source_test_name, 0) + 1
        elif record.mapping_status == "review_needed":
            key = f"{record.source_test_name} ({record.status_reason})"
            review_reasons[key] = review_reasons.get(key, 0) + 1
            if record.status_reason == "unsupported_unit_for_biomarker":
                unit_key = f"{record.source_test_name}: {record.source_unit}"
                unsupported_units[unit_key] = unsupported_units.get(unit_key, 0) + 1
    total = result.summary["total_rows"]
    mapped_pct = result.summary["mapped"] / total * 100 if total else 0
    return {
        "input_file": result.input_file,
        "summary": result.summary,
        "mapping_rate": round(mapped_pct, 1),
        "mapped_biomarkers": dict(sorted(mapped_biomarkers.items(), key=lambda item: -item[1])),
        "unmapped_tests": dict(sorted(unmapped_tests.items(), key=lambda item: -item[1])),
        "review_reasons": dict(sorted(review_reasons.items(), key=lambda item: -item[1])),
        "unsupported_units": dict(sorted(unsupported_units.items(), key=lambda item: -item[1])),
        "warnings": list(result.warnings),
    }


@app.post("/analyze")
def analyze(body: NormalizeRequest) -> JSONResponse:
    rows, error = _validate_rows(body.model_dump())
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    result = normalize_rows(
        rows,
        input_file=_sanitize_client_filename(body.input_file) if body.input_file else "",
    )
    response = _build_analysis(result)
    return _with_rows_processed(JSONResponse(content=response), len(rows))


@v1.post("/analyze")
def analyze_v1(body: NormalizeRequest) -> JSONResponse:
    return analyze(body)


@app.post("/analyze/upload")
def analyze_upload(file: UploadFile = File(...)) -> JSONResponse:
    rows, error = _read_upload(file)
    if error:
        return JSONResponse(status_code=400, content={"error": error})
    row_error = _validate_upload_rows(rows)
    if row_error:
        return JSONResponse(status_code=400, content={"error": row_error})

    result = normalize_rows(rows, input_file=_sanitize_client_filename(file.filename))
    response = _build_analysis(result)
    return _with_rows_processed(JSONResponse(content=response), len(rows))


@v1.post("/analyze/upload")
def analyze_upload_v1(file: UploadFile = File(...)) -> JSONResponse:
    return analyze_upload(file)


@app.post("/phenoage")
def phenoage_endpoint(body: PhenoAgeRequest) -> JSONResponse:
    """Compute PhenoAge biological age. Requires 9 biomarkers + chronological_age."""
    rows, error = _validate_rows(body.model_dump())
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    result = normalize_rows(rows)
    pheno = compute_phenoage(result, chronological_age=body.chronological_age)
    return _with_rows_processed(JSONResponse(content=pheno or {"error": "Could not compute PhenoAge"}), len(rows))


@v1.post("/phenoage")
def phenoage_v1(body: PhenoAgeRequest) -> JSONResponse:
    return phenoage_endpoint(body)


@app.post("/optimal-ranges")
def optimal_ranges_endpoint(body: NormalizeRequest) -> JSONResponse:
    """Evaluate biomarker values against optimal biomarker ranges."""
    rows, error = _validate_rows(body.model_dump())
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    result = normalize_rows(rows)
    summary = summarize_optimal(evaluate_optimal_ranges(result, sex=body.sex))
    return _with_rows_processed(JSONResponse(content=summary), len(rows))


@v1.post("/optimal-ranges")
def optimal_ranges_v1(body: NormalizeRequest) -> JSONResponse:
    return optimal_ranges_endpoint(body)


@app.post("/compare")
def compare_endpoint(body: CompareRequest) -> JSONResponse:
    """Compare before/after lab results for longitudinal tracking."""
    before_validated, before_err = _validate_rows(body.before)
    if before_err:
        return JSONResponse(status_code=400, content={"error": f"before: {before_err}"})

    after_validated, after_err = _validate_rows(body.after)
    if after_err:
        return JSONResponse(status_code=400, content={"error": f"after: {after_err}"})

    before_result = normalize_rows(before_validated)
    after_result = normalize_rows(after_validated)
    comparison = compare_results(before_result, after_result, days_between=body.days_between)
    return _with_rows_processed(JSONResponse(content=comparison), len(before_validated) + len(after_validated))


@v1.post("/compare")
def compare_v1(body: CompareRequest) -> JSONResponse:
    return compare_endpoint(body)


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


app.include_router(v1)


def main() -> None:
    """Entry point for bnt serve."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
