"""Optional fuzzy matching for unmapped test names.

Requires: pip install rapidfuzz  (or install with pip install biomarker-normalization-toolkit[fuzzy])
Falls back gracefully to empty results when rapidfuzz is not installed.
"""

from __future__ import annotations

from biomarker_normalization_toolkit.catalog import ALIAS_INDEX

_ALIAS_CHOICES: list[str] = []
_ALIAS_BIO_IDS: list[list[str]] = []
_BUILT = False


def _build_index() -> None:
    global _BUILT
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
            out.append((match_str, bio_id, score / 100.0))
    return sorted(out, key=lambda x: -x[2])
