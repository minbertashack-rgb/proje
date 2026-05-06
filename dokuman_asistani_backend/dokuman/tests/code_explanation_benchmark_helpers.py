from __future__ import annotations

import re
from statistics import mean
from typing import Any

from .code_explanation_benchmark_data import CODE_EXPLANATION_AXIS_MATRIX


_WORD_RE = re.compile(r"[A-Za-z0-9_.-]+")
_WEAK_GENERIC_RE = re.compile(
    r"\b(kontrol eder|kontrol ediyor|yonetir|isler|calisir|bir sey yapar|bir is yapar|durumu aciklar)\b",
    re.IGNORECASE,
)


def _norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _field_text(payload: dict, field: str) -> str:
    value = (payload or {}).get(field)
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(" ".join(_norm_text(v) for v in item.values() if _norm_text(v)))
            else:
                parts.append(_norm_text(item))
        return " ".join(part for part in parts if part)
    if isinstance(value, dict):
        return " ".join(_norm_text(v) for v in value.values() if _norm_text(v))
    return _norm_text(value)


def _all_text(payload: dict) -> str:
    fields = (
        "one_liner",
        "very_simple",
        "glossary",
        "steps",
        "examples",
        "trap",
        "function_purpose",
        "flow_summary",
        "block_comments",
        "line_comments",
    )
    return " ".join(_field_text(payload, field) for field in fields if _field_text(payload, field))


def _keyword_hits(text: str, keywords: list[str]) -> int:
    lowered = _norm_text(text).lower()
    return sum(1 for keyword in keywords if _norm_text(keyword).lower() in lowered)


def _list_count(payload: dict, field: str) -> int:
    value = (payload or {}).get(field)
    return len(value) if isinstance(value, list) else 0


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(_norm_text(text)))


def _flat_required_keywords(case: dict) -> list[str]:
    required = []
    for items in dict(case.get("required_keywords") or {}).values():
        required.extend(list(items or []))
    return [item for item in required if _norm_text(item)]


def _weak_generic_item_hits(case: dict, payload: dict) -> int:
    reference_terms = [*_flat_required_keywords(case), *list(case.get("specific_terms") or [])]
    weak_hits = 0
    for field in ("function_purpose", "flow_summary"):
        text = _field_text(payload, field)
        if _WEAK_GENERIC_RE.search(text) and _keyword_hits(text, reference_terms) == 0:
            weak_hits += 1
    for field in ("block_comments", "line_comments"):
        for item in list((payload or {}).get(field) or []):
            text = _norm_text(item)
            if not text:
                continue
            if _WEAK_GENERIC_RE.search(text) and _keyword_hits(text, reference_terms) == 0 and _word_count(text) <= 12:
                weak_hits += 1
    return weak_hits


def evaluate_code_explanation_case(case: dict, payload: dict) -> dict:
    axis_cfg = CODE_EXPLANATION_AXIS_MATRIX[case["axis"]]
    required_keywords = dict(case.get("required_keywords") or {})
    actual_counts = {field: _list_count(payload, field) for field in ("steps", "glossary", "block_comments", "line_comments")}
    text_by_field = {field: _field_text(payload, field) for field in required_keywords}
    total_required = sum(len(items) for items in required_keywords.values())
    required_hits = sum(_keyword_hits(text_by_field.get(field, ""), items) for field, items in required_keywords.items())
    coverage_ratio = required_hits / max(total_required, 1)

    all_text = _all_text(payload)
    specific_terms = list(case.get("specific_terms") or [])
    specific_hits = _keyword_hits(all_text, specific_terms)
    specific_ratio = specific_hits / max(len(specific_terms), 1)

    min_counts = dict(case.get("min_counts") or {})
    count_hits = sum(1 for field, minimum in min_counts.items() if actual_counts.get(field, 0) >= minimum)
    clarity_parts = [
        bool(_field_text(payload, "function_purpose")),
        bool(_field_text(payload, "flow_summary")),
        count_hits >= max(3, len(min_counts) - 1),
    ]
    clarity_score = 2 if all(clarity_parts) else 1 if any(clarity_parts) else 0

    generic_hits = _keyword_hits(all_text, list(case.get("forbidden_generic_phrases") or []))
    weak_generic_hits = _weak_generic_item_hits(case, payload)
    anti_generic = 2
    if generic_hits or weak_generic_hits:
        anti_generic = 1
    if (generic_hits >= 2) or (weak_generic_hits >= 2) or ((generic_hits or weak_generic_hits) and specific_hits < max(2, len(specific_terms) // 2 or 1)):
        anti_generic = 0

    hallucination_hits = _keyword_hits(all_text, list(case.get("hallucination_forbidden") or []))
    anti_hallucination = 2 if hallucination_hits == 0 else 0

    line_block_hits = _keyword_hits(_field_text(payload, "line_comments"), required_keywords.get("line_comments", []))
    block_hits = _keyword_hits(_field_text(payload, "block_comments"), required_keywords.get("block_comments", []))
    line_block_alignment = 2 if (
        actual_counts["line_comments"] >= min_counts.get("line_comments", 0)
        and actual_counts["block_comments"] >= min_counts.get("block_comments", 0)
        and line_block_hits >= max(1, len(required_keywords.get("line_comments", [])) // 2)
    ) else 1 if actual_counts["line_comments"] >= 1 and actual_counts["block_comments"] >= 1 else 0

    readability_issues = 0
    if _word_count(_field_text(payload, "function_purpose")) > 26:
        readability_issues += 1
    if _word_count(_field_text(payload, "flow_summary")) > 22:
        readability_issues += 1
    if any(_word_count(item) > 18 for item in (payload.get("line_comments") or []) if isinstance(item, str)):
        readability_issues += 1
    if any(_word_count(item) > 22 for item in (payload.get("block_comments") or []) if isinstance(item, str)):
        readability_issues += 1
    concise_readable = 2 if readability_issues == 0 else 1 if readability_issues == 1 else 0

    scores = {
        "accuracy": 2 if coverage_ratio >= 0.8 else 1 if coverage_ratio >= 0.55 else 0,
        "specificity": 2 if specific_ratio >= 0.6 else 1 if specific_ratio >= 0.35 else 0,
        "clarity": clarity_score,
        "anti_generic": anti_generic,
        "anti_hallucination": anti_hallucination,
        "line_block_alignment": line_block_alignment,
        "concise_readable": concise_readable,
    }
    total = sum(scores.values())
    floor_failures = [
        field
        for field, minimum in axis_cfg["dimension_floor"].items()
        if scores.get(field, 0) < minimum
    ]
    passed = total >= axis_cfg["minimum_total"] and not floor_failures
    return {
        "slug": case["slug"],
        "axis": case["axis"],
        "scores": scores,
        "total": total,
        "minimum_total": axis_cfg["minimum_total"],
        "passed": passed,
        "floor_failures": floor_failures,
        "required_hits": required_hits,
        "total_required": total_required,
        "specific_hits": specific_hits,
        "weak_generic_hits": weak_generic_hits,
        "actual_counts": actual_counts,
    }


def summarize_code_explanation_results(results: list[dict]) -> dict:
    valid = [item for item in results if isinstance(item, dict)]
    axis_summary = {}
    for axis in CODE_EXPLANATION_AXIS_MATRIX:
        axis_results = [item for item in valid if item.get("axis") == axis]
        if not axis_results:
            continue
        axis_summary[axis] = {
            "count": len(axis_results),
            "avg_total": round(mean(item.get("total", 0) for item in axis_results), 2),
            "failed": [item.get("slug") for item in axis_results if not item.get("passed")],
        }
    return {
        "case_count": len(valid),
        "failed_cases": [item.get("slug") for item in valid if not item.get("passed")],
        "axis_summary": axis_summary,
    }


def format_code_explanation_result(result: dict) -> str:
    score_bits = ", ".join(f"{key}={value}" for key, value in sorted((result.get("scores") or {}).items()))
    return (
        f"{result.get('slug')} total={result.get('total')}/{result.get('minimum_total')} "
        f"floors={result.get('floor_failures')} counts={result.get('actual_counts')} "
        f"keywords={result.get('required_hits')}/{result.get('total_required')} "
        f"specific={result.get('specific_hits')} weak_generic={result.get('weak_generic_hits')} {score_bits}"
    )
