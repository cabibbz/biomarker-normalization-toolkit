"""Optional fuzzy matching for unmapped test names.

Requires: pip install rapidfuzz  (or install with pip install biomarker-normalization-toolkit[fuzzy])
Falls back gracefully to empty results when rapidfuzz is not installed.
"""

from __future__ import annotations

import threading

from biomarker_normalization_toolkit.catalog import ALIAS_INDEX

_ALIAS_CHOICES: list[str] = []
_ALIAS_BIO_IDS: list[list[str]] = []
_BUILT = False
_LOCK = threading.Lock()

# Known false-positive pairs: (query_substring, biomarker_id) that should never fuzzy-match.
# These are semantically distinct tests that happen to have similar names.
_BLOCKLIST: set[tuple[str, str]] = {
    # Hemoglobin electrophoresis variants are NOT HbA1c
    ("hemoglobin c", "hba1c"),
    ("hemoglobin s", "hba1c"),
    ("hemoglobin f", "hba1c"),
    ("hemogloblin a", "hba1c"),
    ("hemogloblin s", "hba1c"),
    ("hemoglobin a2", "hba1c"),
    # ALT and ALP are different liver enzymes
    ("alt", "alp"),
    ("alp", "alt"),
}

# Query patterns that should NEVER fuzzy-match at all.
# Qualitative "[Presence]" tests must not match quantitative biomarkers.
_QUERY_BLOCKLIST_PATTERNS: list[str] = [
    "presence",
    "ige ab",
    "antibod",
    "blood pressure",
    "ejection fraction",
    "ventilator",
]


def _build_index() -> None:
    global _BUILT
    with _LOCK:
        if _BUILT:
            return
        for alias_key, bio_ids in ALIAS_INDEX.items():
            _ALIAS_CHOICES.append(alias_key)
            _ALIAS_BIO_IDS.append(bio_ids)
        _BUILT = True


def fuzzy_match(query: str, threshold: float = 0.70) -> list[tuple[str, str, float]]:
    """Find fuzzy matches for query against all known alias keys.

    Returns list of (matched_alias_key, biomarker_id, score) tuples, sorted by score desc.
    Score is 0.0-1.0.  Returns [] if rapidfuzz is not installed or no match above threshold.
    """
    try:
        from rapidfuzz import fuzz, process
    except ImportError:
        return []

    # Reject queries that contain blocklisted patterns
    query_lower = query.lower()
    if any(pat in query_lower for pat in _QUERY_BLOCKLIST_PATTERNS):
        return []

    _build_index()
    if not _ALIAS_CHOICES:
        return []

    results = process.extract(
        query, _ALIAS_CHOICES,
        scorer=fuzz.ratio,
        score_cutoff=threshold * 100,
        limit=5,
    )

    out: list[tuple[str, str, float]] = []
    for match_str, score, idx in results:
        for bio_id in _ALIAS_BIO_IDS[idx]:
            # Check blocklist (case-insensitive substring matching)
            blocked = any(
                substr in query.lower() and bio_id == blocked_bio
                for substr, blocked_bio in _BLOCKLIST
            )
            if blocked:
                continue
            out.append((match_str, bio_id, score / 100.0))
    return sorted(out, key=lambda x: -x[2])
