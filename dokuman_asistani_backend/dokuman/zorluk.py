from __future__ import annotations

from typing import Dict, List, Tuple

from dokuman.services.difficulty import (
    calculate_part_difficulty,
    difficulty_label_from_score,
)


def difficulty_label_for_score(score: float | None) -> str:
    return difficulty_label_from_score(score)


def compute_difficulty_profile(
    text: str,
    *,
    metadata: dict | None = None,
    language: str = "tr",
) -> Tuple[float, str, List[str], Dict[str, float]]:
    profile = calculate_part_difficulty(text, metadata, language=language)
    return (
        float(profile["difficulty_score"]),
        str(profile["difficulty_label"]),
        list(profile["difficulty_reasons"]),
        dict(profile["metrics"]),
    )


def compute_zorluk_skoru(text: str) -> Tuple[float, Dict[str, float]]:
    score, _label, reasons, metrics = compute_difficulty_profile(text)
    metrics["difficulty_reasons_count"] = float(len(reasons))
    return score, metrics
