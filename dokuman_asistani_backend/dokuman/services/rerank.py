from __future__ import annotations

from django.conf import settings

from .retrieval_terms import normalize_query_terms, normalize_text_terms

SEMANTIC_WEIGHT = 0.50
LEXICAL_WEIGHT = 0.30
PATH_WEIGHT = 0.20
LOCALITY_BONUS = 0.05
WEAK_PENALTY = 0.15


def _coerce_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_hit_text(hit) -> str:
    return str(hit.get("metin") or hit.get("snippet") or "").strip()


def _safe_hit_path(hit) -> str:
    return str(hit.get("baslik_yolu") or hit.get("adres") or "").strip()


def _safe_hit_doc_id(hit):
    try:
        if hit.get("dokuman_id") in (None, ""):
            return None
        return int(hit.get("dokuman_id"))
    except Exception:
        return hit.get("dokuman_id")


def _coerce_int(value, default: int | None = None) -> int | None:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except Exception:
        return default


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _safe_hit_meta(hit) -> dict:
    meta = hit.get("meta") if isinstance(hit, dict) else {}
    return meta if isinstance(meta, dict) else {}


def _safe_chunk_index(hit, onceki_sira: int) -> int:
    meta = _safe_hit_meta(hit)
    return int(
        _coerce_int(hit.get("chunk_index"))
        or _coerce_int(hit.get("sira"))
        or _coerce_int(meta.get("chunk_index"))
        or _coerce_int(meta.get("sira"))
        or int(onceki_sira)
    )


def _infer_weak_content(hit, text: str, text_terms: list[str]) -> bool:
    meta = _safe_hit_meta(hit)
    if hit.get("weak_content") is not None:
        return bool(hit.get("weak_content"))
    if meta.get("weak_content") is not None:
        return bool(meta.get("weak_content"))

    unique_token_count = len(set(text_terms))
    return len(text) < 45 or unique_token_count < 5


def rerank_enabled() -> bool:
    return bool(getattr(settings, "DOCVERSE_RERANK_ENABLED", True))


def debug_summary_enabled() -> bool:
    return bool(getattr(settings, "DOCVERSE_DEBUG_SUMMARY_ENABLED", False))


def extract_rerank_features(query_terms: list[str], hit: dict, *, doc_support_hits: int = 0, onceki_sira: int = 1) -> dict:
    query_term_set = set(query_terms)
    text = _safe_hit_text(hit)
    path = _safe_hit_path(hit)
    text_terms = normalize_text_terms(text)
    path_terms = normalize_text_terms(path)
    text_term_set = set(text_terms)
    path_term_set = set(path_terms)
    matched_text = query_term_set & text_term_set
    matched_path = query_term_set & path_term_set
    has_any_match = bool(matched_text or matched_path)
    weak_content = _infer_weak_content(hit, text, text_terms)

    lexical_overlap = len(matched_text) / max(1, len(query_term_set))
    path_match = len(matched_path) / max(1, len(query_term_set))
    density_hits = sum(text_terms.count(token) for token in query_term_set)
    text_density = min(1.0, density_hits / max(1, len(text_terms) or 1))
    phrase_match = bool(
        query_terms
        and (
            " ".join(query_terms) in " ".join(text_terms)
            or " ".join(query_terms) in " ".join(path_terms)
        )
    )
    full_query_match = lexical_overlap >= 0.999
    exact_path_match = path_match >= 0.999
    locality_bonus = LOCALITY_BONUS if max(0, int(doc_support_hits)) > 0 else 0.0
    weak_penalty = WEAK_PENALTY if weak_content else 0.0

    return {
        "parca_id": hit.get("parca_id"),
        "doc_id": _safe_hit_doc_id(hit),
        "onceki_sira": int(onceki_sira),
        "chunk_index": _safe_chunk_index(hit, onceki_sira),
        "semantic_score": round(_clamp01(_coerce_float(hit.get("skor"))), 4),
        "lexical_overlap": round(lexical_overlap, 3),
        "path_match": round(path_match, 3),
        "text_density": round(text_density, 3),
        "locality_bonus": round(locality_bonus, 3),
        "weak_penalty": round(weak_penalty, 3),
        "weak_content": weak_content,
        "matched_text_terms": sorted(matched_text),
        "matched_path_terms": sorted(matched_path),
        "matched_terms": sorted(matched_text | matched_path),
        "phrase_match": phrase_match,
        "full_query_match": full_query_match,
        "exact_path_match": exact_path_match,
        "doc_support_hits": max(0, int(doc_support_hits)),
    }


def score_rerank_features(features: dict) -> float:
    semantic_score = _clamp01(_coerce_float(features.get("semantic_score")))
    lexical_overlap = _clamp01(_coerce_float(features.get("lexical_overlap")))
    path_match = _clamp01(_coerce_float(features.get("path_match")))
    locality_bonus = min(LOCALITY_BONUS, max(0.0, _coerce_float(features.get("locality_bonus"))))
    weak_penalty = min(WEAK_PENALTY, max(0.0, _coerce_float(features.get("weak_penalty"))))

    final_rerank = (
        (semantic_score * SEMANTIC_WEIGHT)
        + (lexical_overlap * LEXICAL_WEIGHT)
        + (path_match * PATH_WEIGHT)
        + locality_bonus
        - weak_penalty
    )
    return round(_clamp01(final_rerank), 4)


def _why_selected(features: dict) -> str:
    if _coerce_float(features.get("path_match")) >= 0.5:
        return "path_supported_match"
    if features.get("full_query_match"):
        return "full_query_match"
    if _coerce_float(features.get("lexical_overlap")) >= 0.5:
        return "lexical_supported_match"
    if _coerce_float(features.get("semantic_score")) >= 0.75:
        return "semantic_priority"
    return "balanced_match"


def _dropped_reason(features: dict, *, selected: bool) -> str:
    if selected:
        return ""
    if _coerce_float(features.get("weak_penalty")) >= WEAK_PENALTY:
        return "weak_content_penalty"
    if _coerce_float(features.get("path_match")) == 0 and _coerce_float(features.get("lexical_overlap")) == 0:
        return "low_query_alignment"
    if _coerce_float(features.get("semantic_score")) < 0.3:
        return "low_semantic_score"
    return "lower_final_rerank"


def build_rerank_debug_summary(features: dict, *, yeni_sira: int, selected: bool) -> dict:
    return {
        "parca_id": features.get("parca_id"),
        "onceki_sira": int(features.get("onceki_sira") or 0),
        "yeni_sira": int(yeni_sira),
        "semantic_score": round(_coerce_float(features.get("semantic_score")), 4),
        "lexical_overlap": round(_coerce_float(features.get("lexical_overlap")), 4),
        "path_match": round(_coerce_float(features.get("path_match")), 4),
        "locality_bonus": round(_coerce_float(features.get("locality_bonus")), 4),
        "weak_penalty": round(_coerce_float(features.get("weak_penalty")), 4),
        "final_rerank": round(_coerce_float(features.get("final_rerank")), 4),
        "why_selected": _why_selected(features) if selected else "",
        "dropped_reason": _dropped_reason(features, selected=selected),
    }


def _deterministic_sort_key(item: dict):
    features = item["features"]
    return (
        round(_coerce_float(features.get("final_rerank")), 4),
        round(_coerce_float(features.get("semantic_score")), 4),
        round(_coerce_float(features.get("lexical_overlap")), 4),
        round(_coerce_float(features.get("path_match")), 4),
        -int(features.get("chunk_index") or 0),
        -int(features.get("onceki_sira") or 0),
        -int(features.get("parca_id") or 0),
    )
