# Deployment Compliance Guide

This guide summarizes common deployment considerations for regulated environments. It is deployment guidance only, not a certification claim.

## Project Posture

The toolkit is designed to run inside your environment.

- no built-in telemetry
- no outbound network calls during normalization
- no persistent application database
- in-memory processing with optional file-upload temp storage

## Important Boundaries

This repository does not make claims such as:

- HIPAA certification
- SOC 2 certification
- FDA clearance
- automatic legal compliance for your deployment

Those obligations belong to the system that deploys and operates the toolkit.

## Recommended Controls

### Network

- run the API behind TLS termination
- restrict access to trusted internal services where possible
- block unnecessary outbound traffic as defense in depth

### Storage

- keep downstream result storage encrypted at rest
- mount `/tmp` on encrypted or memory-backed storage if you accept uploads
- treat uploaded source files as sensitive until deleted

### Access Control

- implement authentication and authorization in the surrounding application or gateway
- avoid exposing the raw normalization API directly to untrusted public traffic
- log access at the platform edge if you need audit trails

### Logging

- forward logs to a centralized logging system
- avoid logging request or response bodies containing sensitive data
- retain logs according to your own compliance requirements

### Monitoring

- monitor `/health`
- scrape `/metrics`
- alert on elevated error rates, sustained latency, or repeated 4xx/5xx patterns

## Data Protection Notes

- the toolkit preserves source provenance because traceability matters in medical data pipelines
- normalization output should still be treated as sensitive when linked to patient context
- deletion, retention, residency, and consent obligations remain the responsibility of the deploying system

## Suggested Deployment Pattern

1. Source system exports lab data.
2. Your application sends rows or files to the toolkit.
3. The toolkit returns normalized results.
4. Your application stores, audits, and governs the resulting data.

## Operator Checklist

- TLS termination configured
- CORS restricted with `BNT_CORS_ORIGINS`
- `BNT_RATE_LIMIT` reviewed for expected traffic
- logs centralized and retained appropriately
- downstream storage encrypted
- temp storage strategy defined
- access control implemented outside the toolkit
- validation and release process documented for your environment
