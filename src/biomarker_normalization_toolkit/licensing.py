"""API key validation and feature gating for BNT.

Tiers:
- free: 50 core biomarkers, no PhenoAge, no optimal ranges, 1000 rows/request
- pro: All 282 biomarkers, PhenoAge, optimal ranges, derived metrics, 100K rows/request
- enterprise: Everything in pro + priority support + custom aliases

Validation methods (checked in order):
1. HMAC-signed keys: BNT_LICENSE_SECRET env var signs keys with expiry
2. Static keys: BNT_PRO_KEY / BNT_ENTERPRISE_KEY env vars (simple deployment)

For customer-run deployments, the licensing is advisory — the code is open
under BSL 1.1 and a determined user can bypass it. The value is in the
support, updates, and alias additions that come with a license.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any

# Free tier biomarkers (core clinical chemistry only)
FREE_BIOMARKER_IDS = frozenset({
    "glucose_serum", "hba1c", "total_cholesterol", "ldl_cholesterol",
    "hdl_cholesterol", "triglycerides", "creatinine", "bun", "egfr",
    "sodium", "potassium", "chloride", "bicarbonate", "calcium",
    "alt", "ast", "alp", "total_bilirubin", "albumin", "total_protein",
    "tsh", "free_t4", "wbc", "hemoglobin", "hematocrit", "platelets",
    "rbc", "mcv", "mch", "mchc", "rdw", "neutrophils", "lymphocytes",
    "monocytes", "eosinophils", "basophils", "iron", "ferritin",
    "vitamin_d", "vitamin_b12", "folate", "hscrp", "crp",
    "pt", "inr", "ptt", "magnesium", "phosphate", "uric_acid",
    "globulin",
})

FREE_MAX_ROWS = 1000
PRO_MAX_ROWS = 100_000


class LicenseTier:
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


def validate_api_key(api_key: str | None) -> dict[str, Any]:
    """Validate an API key and return the tier and permissions.

    For now, uses simple key validation. In production, this would
    check against Stripe or a license server.
    """
    if not api_key:
        return {
            "tier": LicenseTier.FREE,
            "valid": True,
            "max_rows": FREE_MAX_ROWS,
            "biomarker_ids": FREE_BIOMARKER_IDS,
            "features": {"phenoage": False, "optimal_ranges": False, "derived_metrics": True, "fuzzy": False},
        }

    # Method 1: HMAC-signed keys (format: "tier:expiry_unix:signature")
    license_secret = os.environ.get("BNT_LICENSE_SECRET", "")
    if license_secret and ":" in api_key:
        parts = api_key.split(":", 2)
        if len(parts) == 3:
            tier_claim, expiry_str, signature = parts
            try:
                expiry = int(expiry_str)
                expected_sig = hmac.new(
                    license_secret.encode(), f"{tier_claim}:{expiry_str}".encode(), hashlib.sha256
                ).hexdigest()[:32]
                if tier_claim not in ("pro", "enterprise"):
                    pass  # Invalid tier claim — fall through to static key check
                elif hmac.compare_digest(signature.encode(), expected_sig.encode()) and time.time() < expiry:
                    tier = LicenseTier.ENTERPRISE if tier_claim == "enterprise" else LicenseTier.PRO
                    return {
                        "tier": tier,
                        "valid": True,
                        "max_rows": PRO_MAX_ROWS,
                        "biomarker_ids": None,
                        "features": {"phenoage": True, "optimal_ranges": True, "derived_metrics": True, "fuzzy": True},
                    }
            except (ValueError, TypeError):
                pass

    # Method 2: Static keys (simple deployment)
    env_key = os.environ.get("BNT_PRO_KEY", "")
    env_enterprise_key = os.environ.get("BNT_ENTERPRISE_KEY", "")

    if env_enterprise_key and hmac.compare_digest(api_key.encode(), env_enterprise_key.encode()):
        return {
            "tier": LicenseTier.ENTERPRISE,
            "valid": True,
            "max_rows": PRO_MAX_ROWS,
            "biomarker_ids": None,  # None = all biomarkers
            "features": {"phenoage": True, "optimal_ranges": True, "derived_metrics": True, "fuzzy": True},
        }

    if env_key and hmac.compare_digest(api_key.encode(), env_key.encode()):
        return {
            "tier": LicenseTier.PRO,
            "valid": True,
            "max_rows": PRO_MAX_ROWS,
            "biomarker_ids": None,  # None = all biomarkers
            "features": {"phenoage": True, "optimal_ranges": True, "derived_metrics": True, "fuzzy": True},
        }

    # Invalid key — explicitly marked
    return {
        "tier": LicenseTier.FREE,
        "valid": False,
        "error": "Invalid API key. Ignored — using free tier.",
        "max_rows": FREE_MAX_ROWS,
        "biomarker_ids": FREE_BIOMARKER_IDS,
        "features": {"phenoage": False, "optimal_ranges": False, "derived_metrics": True, "fuzzy": False},
    }
