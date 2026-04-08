# Deployment Compliance Guide

This guide provides recommendations for deploying the Biomarker Normalization Toolkit (BNT) in regulated environments. BNT is a self-hosted data normalization library -- it runs entirely within your infrastructure, processes data in memory, and makes no outbound network calls.

**Important:** This document provides deployment guidance, not certification claims. BNT itself is not HIPAA-certified or SOC 2-certified. These recommendations help your organization meet its own compliance obligations when deploying BNT as part of a larger system.

## Architecture Overview

### Data Flow

```
                    Your Infrastructure
  +----------------------------------------------------------+
  |                                                          |
  |  [Lab System / EHR / CSV Export]                         |
  |         |                                                |
  |         v                                                |
  |  [Your Application Layer]                                |
  |         |                                                |
  |         | HTTP POST (lab rows as JSON or file upload)    |
  |         v                                                |
  |  +-------------------------------------------+          |
  |  |  BNT API Container                        |          |
  |  |                                           |          |
  |  |  1. Validate input (schema, size, type)   |          |
  |  |  2. Normalize in memory                   |          |
  |  |  3. Return JSON response                  |          |
  |  |  4. Discard all data (nothing stored)     |          |
  |  |                                           |          |
  |  |  No outbound calls. No disk writes.       |          |
  |  |  No telemetry. No logs containing PHI.    |          |
  |  +-------------------------------------------+          |
  |         |                                                |
  |         v                                                |
  |  [Your Application Layer]                                |
  |  (stores results in your database)                       |
  |                                                          |
  +----------------------------------------------------------+
```

Key properties:
- Lab data enters BNT via your API call and exits as a normalized JSON response
- BNT does not persist any data to disk (except temporary file uploads, deleted immediately)
- BNT does not make outbound network connections
- BNT does not collect telemetry, analytics, or usage data beyond in-memory request counters
- All processing is stateless -- no session data, no caches, no databases

## HIPAA Deployment Recommendations

If your system handles Protected Health Information (PHI), the following recommendations apply to BNT deployment.

### Business Associate Agreement

If you license BNT as commercial software with support, contact sales@longevb2b.com to discuss BAA requirements. For self-hosted deployments where LongevB2B has no access to your data or systems, a BAA may not be required -- consult your compliance team.

### Technical Safeguards

#### Network Isolation

- Deploy BNT in a private subnet with no internet egress
- Expose the API only to your application layer via internal load balancer
- Do not expose BNT directly to end users or the public internet
- Use network policies (security groups, Kubernetes NetworkPolicy) to restrict access to the BNT container

```
# Example: Kubernetes NetworkPolicy
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: bnt-network-policy
spec:
  podSelector:
    matchLabels:
      app: bnt
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: your-backend
      ports:
        - port: 8000
  egress: []   # No egress needed -- BNT makes no outbound calls
```

#### Encryption in Transit

BNT serves HTTP by default. You must terminate TLS upstream.

**Option A: Reverse Proxy (recommended)**
```nginx
# nginx example
server {
    listen 443 ssl;
    server_name bnt.internal.yourcompany.com;

    ssl_certificate     /etc/ssl/certs/bnt.crt;
    ssl_certificate_key /etc/ssl/private/bnt.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://bnt-service:8000;
        proxy_set_header X-Request-Id $request_id;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Option B: Service Mesh**

If running in Kubernetes with a service mesh (Istio, Linkerd), mTLS between services is handled automatically.

**Option C: Cloud Load Balancer**

Terminate TLS at your cloud provider's load balancer (ALB, Cloud Load Balancing, Azure Application Gateway) with certificates from ACM, Let's Encrypt, or your internal CA.

#### Encryption at Rest

BNT does not store data, so encryption at rest applies to your storage layer, not BNT itself. Ensure:
- The database where you persist normalized results uses encrypted storage
- Container filesystem uses encrypted volumes (standard on AWS EBS, GCP PD, Azure Managed Disks)
- Any file uploads processed by BNT are on encrypted storage (the temp files exist for milliseconds)

#### Access Controls

- Require API keys for all requests (`X-API-Key` header)
- Use HMAC-signed keys with expiration for production (see SECURITY.md)
- Set `BNT_CORS_ORIGINS` to restrict cross-origin access
- Run the container as non-root (default in the provided Dockerfile)
- Apply the principle of least privilege to the service account running BNT

### Audit Logging

BNT includes structured logging support. To meet HIPAA audit requirements:

1. **Enable structured JSON logging** by installing `python-json-logger`:
   ```bash
   pip install python-json-logger
   ```
   BNT will automatically output JSON-formatted logs when this package is available.

2. **What BNT logs** (safe for compliance):
   - Request endpoint, HTTP method, status code
   - Request duration (latency)
   - Rate limit events
   - Error events (without PHI -- stack traces logged server-side only)
   - Request ID for correlation

3. **What BNT does NOT log:**
   - Patient names, identifiers, or demographics
   - Lab values or test results
   - Any field from the request or response body

4. **Log forwarding:** Ship BNT container logs to your centralized logging system (ELK, Splunk, CloudWatch, Datadog) for retention and audit. HIPAA requires 6 years of audit log retention.

5. **Metrics endpoint:** BNT exposes `/metrics` in Prometheus format for monitoring request volume, error rates, and latency without exposing PHI.

### Temporary File Handling

When processing file uploads (`/normalize/upload`, `/analyze/upload`):
- Files are written to the system temp directory
- Files are deleted in a `finally` block immediately after processing
- The temp directory should be on an encrypted filesystem
- Consider mounting a `tmpfs` (RAM-backed) volume for the container:

```yaml
# Docker Compose
volumes:
  - type: tmpfs
    target: /tmp
    tmpfs:
      size: 100M
```

```yaml
# Kubernetes
volumes:
  - name: tmp
    emptyDir:
      medium: Memory
      sizeLimit: 100Mi
containers:
  - name: bnt
    volumeMounts:
      - name: tmp
        mountPath: /tmp
```

## GDPR Considerations

BNT has a favorable GDPR profile because of its architecture:

| Concern | BNT Posture |
|---------|-------------|
| Data residency | BNT runs in your infrastructure, in your chosen region. No data leaves your environment. |
| Data collection | BNT collects zero data. No telemetry, analytics, tracking, or usage reporting. |
| Data storage | BNT stores nothing. All processing is stateless and in-memory. |
| Data transfers | No outbound network calls. No third-party data sharing. |
| Right to erasure | No data to erase from BNT. Your application layer handles deletion obligations. |
| Data processing agreement | May not be required since BNT vendor has no access to personal data in self-hosted deployments. Consult your DPO. |
| Lawful basis | Determined by your application, not BNT. BNT is a processing tool, not a data controller. |

### Recommendations

- Document BNT in your Record of Processing Activities (ROPA) as a sub-processor component
- Confirm that your hosting region meets data residency requirements
- Ensure your application layer handles consent and right-to-erasure for the normalized data it stores

## SOC 2 Relevant Controls

For SOC 2 Type II audits, BNT supports the following Trust Service Criteria:

### CC6: Logical and Physical Access Controls

| Control | BNT Implementation |
|---------|-------------------|
| CC6.1 - Access control | API key authentication with HMAC validation; tiered access (free/pro/enterprise) |
| CC6.3 - Authentication | Constant-time key comparison (`hmac.compare_digest`); invalid keys rejected with 401 |
| CC6.6 - System boundaries | Container runs as non-root; no shell access; minimal base image |
| CC6.8 - Unauthorized access prevention | Rate limiting (configurable per key); request size limits; file type allowlisting |

### CC7: System Operations

| Control | BNT Implementation |
|---------|-------------------|
| CC7.1 - Infrastructure monitoring | `/health` endpoint for liveness checks; `/metrics` endpoint with Prometheus support |
| CC7.2 - Anomaly detection | Rate limit violations logged; error rate tracking in metrics |
| CC7.3 - Change management | Versioned API (`/v1/` prefix); semantic versioning; Docker image tags |

### CC8: Change Management

| Control | BNT Implementation |
|---------|-------------------|
| CC8.1 - Change authorization | Source-controlled; tested against 124K real-world lab events; CI pipeline |

### Availability

| Control | BNT Implementation |
|---------|-------------------|
| A1.1 - Processing capacity | Configurable rate limits; row count limits per tier; 37K rows/sec throughput |
| A1.2 - Recovery | Stateless design; no data to recover; container restart recovers full functionality |

### Confidentiality

| Control | BNT Implementation |
|---------|-------------------|
| C1.1 - Confidential information | No data persistence; no logging of request/response bodies; generic error messages |
| C1.2 - Disposal | Temp files deleted immediately; in-memory data released after response |

## Deployment Checklist

Use this checklist when deploying BNT in a regulated environment:

### Network

- [ ] BNT deployed in private subnet with no public IP
- [ ] TLS 1.2+ terminated at reverse proxy or load balancer
- [ ] Network policies restrict ingress to your application layer only
- [ ] Egress rules confirm no outbound access (defense in depth)

### Authentication

- [ ] API keys configured (`BNT_LICENSE_SECRET` or `BNT_PRO_KEY`/`BNT_ENTERPRISE_KEY`)
- [ ] API key values are high-entropy (32+ characters)
- [ ] HMAC-signed keys used in production with reasonable expiry
- [ ] `BNT_CORS_ORIGINS` set to specific allowed origins (not empty, not wildcard)

### Container

- [ ] Running provided Dockerfile (non-root user, multi-stage build)
- [ ] Image scanned for vulnerabilities before deployment
- [ ] Read-only root filesystem (mount `/tmp` as tmpfs)
- [ ] Resource limits set (CPU, memory) to prevent noisy neighbor issues
- [ ] Health check endpoint (`/health`) integrated with orchestrator

### Logging and Monitoring

- [ ] `python-json-logger` installed for structured logs
- [ ] Container logs forwarded to centralized logging system
- [ ] `/metrics` endpoint scraped by monitoring system
- [ ] Alerting configured for error rate spikes and health check failures
- [ ] Log retention meets regulatory requirements (6 years for HIPAA)

### Temporary Files

- [ ] `/tmp` mounted as tmpfs (RAM-backed) or on encrypted storage
- [ ] Container filesystem is read-only except `/tmp`

### Secrets

- [ ] API keys and license secrets passed via environment variables or secrets manager
- [ ] No secrets in Docker image, environment files committed to source control, or logs
- [ ] Key rotation process documented and tested
