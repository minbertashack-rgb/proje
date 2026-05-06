from __future__ import annotations

import math
import re


_WORD_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9_/%+\-=]+", re.UNICODE)
_ACRONYM_RE = re.compile(r"^[A-Z0-9]{2,}$")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?;\n]+")
_SYMBOL_RE = re.compile(r"[=/%+\-_:;(){}\[\]<>]")


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-float(value)))


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _tokenize(value: str) -> list[str]:
    return _WORD_RE.findall(_clean_text(value))


def analyze_cheatsheet_priority(text: str) -> dict:
    clean = _clean_text(text)
    tokens = _tokenize(clean)
    token_count = len(tokens)
    if not clean or token_count == 0:
        return {
            "cheatsheet_priority_score": 0.0,
            "is_cheatsheet": False,
            "cheatsheet_reason": "empty_content",
        }

    technical_hits = 0
    for token in tokens:
        if _ACRONYM_RE.match(token) or re.search(r"\d", token) or _SYMBOL_RE.search(token):
            technical_hits += 1

    tech_ratio = technical_hits / max(token_count, 1)
    length_score = max(0.0, 1.0 - (len(clean) / 400.0))
    score = _clamp01((0.6 * min(1.0, tech_ratio * 5.0)) + (0.4 * length_score))

    if score >= 0.70:
        reason = "cheatsheet_ready"
    elif tech_ratio >= 0.25:
        reason = "technical_but_long"
    else:
        reason = "low_density"

    return {
        "cheatsheet_priority_score": round(score, 4),
        "is_cheatsheet": score >= 0.70,
        "cheatsheet_reason": reason,
    }


def analyze_quiz_readiness(text: str, *, quality_score: float = 0.0) -> dict:
    clean = _clean_text(text)
    tokens = _tokenize(clean)
    sentences = [item.strip() for item in _SENTENCE_SPLIT_RE.split(clean) if item.strip()]
    factual_hits = 0
    for token in tokens:
        if re.search(r"\d", token) or _ACRONYM_RE.match(token):
            factual_hits += 1
        elif token[:1].isupper() and len(token) >= 3:
            factual_hits += 1

    fact_count = len(sentences) + min(factual_hits, 4)
    score = _clamp01(_clamp01(quality_score) * min(1.0, fact_count / 4.0))

    if score >= 0.70:
        reason = "quiz_ready"
    elif fact_count <= 1:
        reason = "too_few_facts"
    else:
        reason = "borderline_quiz"

    return {
        "quiz_readiness_score": round(score, 4),
        "quiz_ready": score >= 0.50,
        "quiz_reason": reason,
        "fact_count": int(fact_count),
    }


def compute_feedback_weight_score(
    *,
    text: str,
    dwell_seconds: float | int | None,
    user_reputation: float = 0.5,
) -> dict:
    tokens = _tokenize(text)
    word_count = len(tokens)
    expected_seconds = max(word_count * 0.25, 1.0)

    try:
        dwell_value = max(float(dwell_seconds or 0.0), 0.0)
    except Exception:
        dwell_value = 0.0

    read_ratio = dwell_value / expected_seconds
    weight = _clamp01((0.7 * min(1.0, read_ratio)) + (0.3 * _clamp01(user_reputation)))
    ignored = weight < 0.40

    if ignored:
        reason = "low_read_ratio"
    elif weight >= 0.75:
        reason = "trusted_feedback"
    else:
        reason = "partial_trust"

    return {
        "feedback_weight_score": round(weight, 4),
        "feedback_ignored": ignored,
        "feedback_reason": reason,
        "read_ratio": round(min(read_ratio, 4.0), 4),
        "expected_read_seconds": round(expected_seconds, 3),
        "observed_read_seconds": round(dwell_value, 3),
        "word_count": int(word_count),
    }


def feedback_vote_value(feedback_turu: str) -> float:
    mapping = {
        "iyi": 1.0,
        "eksik": 0.25,
        "kotu": 0.0,
        "alakasiz": 0.0,
    }
    return float(mapping.get(str(feedback_turu or "").strip().lower(), 0.5))


def apply_feedback_to_usefulness(
    *,
    base_usefulness: float,
    feedback_turu: str = "",
    feedback_weight_score: float = 0.0,
) -> dict:
    vote_value = feedback_vote_value(feedback_turu)
    shift = (vote_value - 0.5) * 2.0 * _clamp01(feedback_weight_score) * 0.30
    final = _clamp01(_clamp01(base_usefulness) + shift)
    return {
        "usefulness_score_v2": round(final, 4),
        "usefulness_feedback_shift": round(shift, 4),
        "feedback_vote_value": round(vote_value, 4),
    }


def compute_study_summary_importance(
    *,
    rerank_avg: float,
    heading_score: float,
    confusion_score: float,
) -> dict:
    score = _clamp01(
        (0.4 * _clamp01(rerank_avg))
        + (0.3 * _clamp01(heading_score))
        + (0.3 * _clamp01(confusion_score))
    )
    if score >= 0.65:
        reason = "summary_priority"
    elif heading_score >= 0.55:
        reason = "heading_supported"
    else:
        reason = "secondary_context"
    return {
        "study_summary_importance_score": round(score, 4),
        "study_summary_reason": reason,
    }


def compute_confusion_hint(
    *,
    anlamadim_ratio: float,
    quiz_fail_ratio: float,
    dwell_seconds: float,
) -> float:
    dwell_signal = _sigmoid((float(dwell_seconds) / 60.0) - 2.0)
    return round(
        _clamp01(
            (0.5 * _clamp01(anlamadim_ratio))
            + (0.3 * _clamp01(quiz_fail_ratio))
            + (0.2 * dwell_signal)
        ),
        4,
    )
