# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | Yes                |
| 0.1.x   | Security fixes only|
| < 0.1   | No                 |

## Reporting a Vulnerability

If you discover a security vulnerability in the Biomarker Normalization Toolkit, please report it responsibly.

**Email:** security@longevb2b.com

Include the following in your report:

- Description of the vulnerability
- Steps to reproduce
- Affected version(s)
- Potential impact assessment
- Any suggested remediation (optional)

**Do not** open a public GitHub issue for security vulnerabilities.

### Response Timeline

| Stage | Target |
|-------|--------|
| Acknowledgment | Within 2 business days |
| Initial assessment | Within 5 business days |
| Fix for critical issues | Within 14 days |
| Fix for non-critical issues | Next scheduled release |
| Public disclosure | After fix is released |

We will coordinate disclosure timing with you and credit reporters unless anonymity is requested.

## Scope

### In Scope

- The `biomarker_normalization_toolkit` Python package and its dependencies
- The REST API (`api.py`) and all exposed endpoints
- The Docker image and container configuration
- API key validation and license gating logic
- File upload handling and temporary file management
- Input parsing (CSV, FHIR, HL7, C-CDA, Excel)

### Out of Scope

- Customer infrastructure, network configuration, or deployment environment
- Third-party dependencies with their own security policies (report upstream)
- Denial of service via expected rate limiting behavior
- Issues requiring physical access to the host system
- Social engineering attacks

## Security Features

### API Security

- **API key authentication** via `X-API-Key` header with HMAC-signed key validation using constant-time comparison (`hmac.compare_digest`)
- **Rate limiting** per API key (configurable via `BNT_RATE_LIMIT`, default 60 requests/minute) with sliding window enforcement
- **Request body size limits** enforced at 50 MB for both JSON payloads and file uploads, checked against both `Content-Length` header and actual body size
- **CORS** restricted by default (no origins allowed unless explicitly configured via `BNT_CORS_ORIGINS`)
- **File type allowlisting** for uploads (`.csv`, `.json`, `.hl7`, `.oru`, `.xml`, `.xlsx`, `.xls` only)
- **Row count limits** enforced per tier to prevent resource exhaustion
- **Global exception handler** that returns generic error messages, preventing internal stack trace leakage to clients
- **Request ID tracking** via `X-Request-Id` response header for audit correlation

### Container Security

- **Multi-stage Docker build** to minimize image size and exclude build tooling
- **Non-root user** (`bnt`) for container runtime
- **Minimal base image** (`python:3.12-slim`)
- **Health check** endpoint for orchestrator integration
- **No secrets baked into the image** -- all credentials passed via environment variables at runtime

### Data Handling

- **No telemetry or phone-home** -- the toolkit makes zero outbound network calls
- **No data persistence** -- lab data is processed in memory and returned; nothing is stored
- **Temporary files cleaned up** immediately after processing file uploads (explicit `unlink` in `finally` block)
- **Full provenance** preserved so customers can audit normalization decisions
- **No PHI in logs** -- structured logging captures request metadata (endpoint, status, latency) without recording patient data

### Input Validation

- Pydantic model validation on all request bodies
- Row count validation before processing
- File extension validation before parsing
- Path traversal prevention via `Path.name` extraction on filenames
- Input coercion to string types to prevent injection via non-string values

## Security Configuration

Operators deploying BNT should review these environment variables:

| Variable | Purpose | Recommendation |
|----------|---------|----------------|
| `BNT_CORS_ORIGINS` | Allowed CORS origins (comma-separated) | Set to specific origins; never use `*` |
| `BNT_RATE_LIMIT` | Requests per minute per API key | Default 60; adjust based on expected load |
| `BNT_LICENSE_SECRET` | HMAC secret for signed API keys | Use 32+ character random string; rotate periodically |
| `BNT_PRO_KEY` | Static Pro tier API key | Use high-entropy value; prefer HMAC keys instead |
| `BNT_ENTERPRISE_KEY` | Static Enterprise tier API key | Use high-entropy value; prefer HMAC keys instead |

## Dependency Management

We monitor dependencies for known vulnerabilities. The toolkit has a minimal dependency footprint:

- **Runtime:** FastAPI, Uvicorn, Pydantic, openpyxl, python-multipart
- **Optional:** python-json-logger (structured logging), rapidfuzz (fuzzy matching)

We recommend customers run their own dependency scanning (e.g., `pip-audit`, Snyk, Dependabot) as part of their deployment pipeline.
