# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.3.x   | Yes       |
| 0.2.x   | Best effort |
| < 0.2   | No        |

## Reporting a Vulnerability

Do not open a public GitHub issue for sensitive security problems.

Preferred path:

1. Use GitHub private vulnerability reporting for the repository.
2. If private reporting is unavailable, follow the maintainer contact path in [SUPPORT.md](SUPPORT.md).

Include:

- a description of the issue
- affected versions
- steps to reproduce
- impact assessment
- any suggested remediation

## Scope

### In Scope

- the `biomarker_normalization_toolkit` Python package
- REST API endpoints and middleware
- file upload handling and temporary-file cleanup
- input parsing for CSV, FHIR, HL7, C-CDA, and Excel
- Docker packaging and container defaults in this repository

### Out of Scope

- downstream deployment infrastructure
- third-party dependency vulnerabilities that should be reported upstream
- expected rate limiting behavior
- physical host compromise
- social engineering

## Security Posture

### API and Runtime

- configurable in-memory rate limiting
- request body size limits
- upload allowlist by file extension
- generic error responses with request IDs
- restricted CORS by default unless explicitly configured

### Data Handling

- no telemetry or phone-home behavior
- no persistent application database
- uploaded temp files deleted immediately after processing
- source provenance preserved in normalized output
- no request or response bodies logged by default

### Container

- non-root runtime in the provided Dockerfile
- minimal base image
- health endpoint for orchestration

## Recommended Deployment Controls

- terminate TLS upstream
- run the API on private networks where possible
- forward logs to a central logging system
- keep `/tmp` on encrypted or memory-backed storage
- scan dependencies regularly with tools such as `pip-audit`, Dependabot, or Snyk
- pin and review deployment-specific authn/authz in the surrounding system

## Security Configuration

Operators should review:

| Variable | Purpose |
| -------- | ------- |
| `BNT_CORS_ORIGINS` | Allowed CORS origins |
| `BNT_RATE_LIMIT` | Requests per minute per client |

This project intentionally does not ship built-in feature gates or license-key enforcement.
