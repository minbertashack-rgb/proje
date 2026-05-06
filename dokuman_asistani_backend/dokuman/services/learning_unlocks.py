from __future__ import annotations

from dokuman.models import Dokuman, MetrikKaydi
from dokuman.services.concept_runtime import compute_concept_candidates
from dokuman.services.escape_room_runtime import build_escape_room_payload
from dokuman.services.feature_flags import modul_acik_mi
from dokuman.services.metric_store import (
    compute_confusion_map_score,
    compute_mastery_score,
    compute_quiz_readiness_score,
    compute_study_summary_importance_score,
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def _safe_float(value) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _safe_avg(values) -> float:
    clean = []
    for value in values or []:
        try:
            clean.append(float(value))
        except Exception:
            continue
    if not clean:
        return 0.0
    return sum(clean) / len(clean)


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return _clamp01(float(numerator) / float(denominator))


def _metric_avg(*, user, doc, olay_turu: str, score_key: str, limit: int = 16) -> float:
    qs = MetrikKaydi.objects.filter(
        kullanici=user,
        dokuman=doc,
        olay_turu=olay_turu,
    ).order_by("-created_at", "-id")[:limit]
    return _safe_avg((kayit.skor_ozeti or {}).get(score_key) for kayit in qs)


def _resolve_doc(*, user, doc=None):
    if doc is not None:
        return doc
    return Dokuman.objects.filter(owner=user).order_by("id").first()


def _boss_candidate_signals(*, doc, user) -> tuple[int, float]:
    count = 0
    top_score = 0.0
    for parca in doc.parcalar.all().order_by("id"):
        meta = dict(getattr(parca, "meta", {}) or {})
        if bool(meta.get("weak_content")):
            continue
        confusion_meta = compute_confusion_map_score(user=user, dokuman=doc, parca=parca)
        importance_meta = compute_study_summary_importance_score(
            user=user,
            dokuman=doc,
            parca=parca,
            confusion_map_score=confusion_meta["confusion_map_score"],
        )
        difficulty_score = max(
            _safe_float(meta.get("difficulty_score")),
            _safe_float(getattr(parca, "zorluk_skoru", 0.0)),
        )
        candidate_score = _clamp01(
            (difficulty_score * 0.42)
            + (confusion_meta["confusion_map_score"] * 0.30)
            + (importance_meta["study_summary_importance_score"] * 0.28)
        )
        top_score = max(top_score, candidate_score)
        if candidate_score >= 0.56:
            count += 1
    return count, round(top_score, 4)


def build_learning_unlock_snapshot(*, user, doc=None) -> dict:
    active_doc = _resolve_doc(user=user, doc=doc)
    if active_doc is None:
        return {
            "roulette_hazir_mi": False,
            "roulette_reason": "no_chunk_context",
            "escape_room_hazir_mi": False,
            "escape_room_reason": "no_chunk_context",
            "speedrun_hazir_mi": False,
            "speedrun_reason": "no_chunk_context",
            "boss_hazir_mi": False,
            "boss_reason": "no_chunk_context",
            "self_check_hazir_mi": False,
            "self_check_reason": "no_chunk_context",
            "_meta": {
                "unlock_reason_code": "no_chunk_context",
                "quiz_readiness_score": 0.0,
                "mastery_score": 0.0,
                "confusion_map_score": 0.0,
            },
        }

    parcalar = list(active_doc.parcalar.all().order_by("id"))
    total_chunks = len(parcalar)
    ready_chunks = 0
    quiz_readiness_values = []
    for parca in parcalar:
        readiness = compute_quiz_readiness_score(parca=parca)
        quiz_readiness_values.append(readiness["quiz_readiness_score"])
        if readiness["quiz_eligible"]:
            ready_chunks += 1

    quiz_ready_ratio = _safe_ratio(ready_chunks, total_chunks)
    avg_quiz_readiness = round(_safe_avg(quiz_readiness_values), 4)
    max_quiz_readiness = round(max(quiz_readiness_values or [0.0]), 4)
    concept_count = len(compute_concept_candidates(doc=active_doc, user=user, limit=8))
    self_check_avg = round(
        _metric_avg(user=user, doc=active_doc, olay_turu="self_check_calistirildi", score_key="self_check_score"),
        4,
    )
    recent_quiz_success = round(
        max(
            _metric_avg(user=user, doc=active_doc, olay_turu="mini_quiz_sonuclandi", score_key="sonuc_orani"),
            _metric_avg(user=user, doc=active_doc, olay_turu="boss_deneme_tamamlandi", score_key="sonuc_orani"),
        ),
        4,
    )
    speedrun_success = round(
        _metric_avg(user=user, doc=active_doc, olay_turu="speedrun_tamamlandi", score_key="sonuc_orani"),
        4,
    )
    mastery_meta = compute_mastery_score(user=user, dokuman=active_doc)
    confusion_meta = compute_confusion_map_score(user=user, dokuman=active_doc)
    escape_payload = build_escape_room_payload(doc=active_doc, user=user)
    escape_meta = dict(escape_payload.get("_meta") or {})
    escape_progress = _safe_float(escape_meta.get("escape_progress_score"))
    escape_target_count = int(escape_meta.get("escape_target_count") or 0)
    boss_candidate_count, top_boss_candidate_score = _boss_candidate_signals(doc=active_doc, user=user)

    roulette_enabled = modul_acik_mi("DOCVERSE_ROULETTE_ENABLED", True)
    escape_enabled = modul_acik_mi("DOCVERSE_ESCAPE_ROOM_ENABLED", True)
    speedrun_enabled = modul_acik_mi("DOCVERSE_SPEEDRUN_ENABLED", True)
    boss_enabled = modul_acik_mi("DOCVERSE_BOSS_ENABLED", True)
    self_check_enabled = modul_acik_mi("DOCVERSE_SELF_CHECK_ENABLED", True)

    roulette_ready = bool(
        roulette_enabled
        and ready_chunks >= 1
        and (quiz_ready_ratio >= 0.2 or max_quiz_readiness >= 0.36)
    )
    if not roulette_enabled:
        roulette_reason = "module_disabled"
    elif total_chunks <= 0:
        roulette_reason = "no_chunk_context"
    elif ready_chunks <= 0:
        roulette_reason = "no_quiz_ready_chunk"
    elif quiz_ready_ratio < 0.2 and max_quiz_readiness < 0.36:
        roulette_reason = "low_quiz_readiness"
    else:
        roulette_reason = "quiz_ready_chunk_available"

    escape_ready = bool(
        escape_enabled
        and escape_target_count >= 2
        and escape_progress >= 0.44
        and (self_check_avg >= 0.25 or recent_quiz_success >= 0.40)
    )
    if not escape_enabled:
        escape_reason = "module_disabled"
    elif total_chunks <= 0:
        escape_reason = "no_chunk_context"
    elif escape_target_count < 2:
        escape_reason = "no_concept_route"
    elif self_check_avg < 0.25 and recent_quiz_success < 0.40:
        escape_reason = "needs_self_check_or_quiz_signal"
    elif escape_progress < 0.44:
        escape_reason = "escape_progress_low"
    else:
        escape_reason = "escape_path_ready"

    speedrun_ready = bool(
        speedrun_enabled
        and total_chunks >= 2
        and max(avg_quiz_readiness, mastery_meta["mastery_score"], speedrun_success) >= 0.52
    )
    if not speedrun_enabled:
        speedrun_reason = "module_disabled"
    elif total_chunks < 2:
        speedrun_reason = "needs_more_chunks"
    elif max(avg_quiz_readiness, mastery_meta["mastery_score"], speedrun_success) < 0.52:
        speedrun_reason = "low_mastery_and_readiness"
    else:
        speedrun_reason = "speedrun_route_ready"

    boss_ready = bool(
        boss_enabled
        and (
            boss_candidate_count >= 1
            or (
                mastery_meta["mastery_score"] >= 0.58
                and confusion_meta["confusion_map_score"] >= 0.32
            )
        )
    )
    if not boss_enabled:
        boss_reason = "module_disabled"
    elif total_chunks <= 0:
        boss_reason = "no_chunk_context"
    elif boss_candidate_count >= 1:
        boss_reason = "boss_candidate_available"
    elif mastery_meta["mastery_score"] >= 0.58 and confusion_meta["confusion_map_score"] >= 0.32:
        boss_reason = "mastery_confusion_gate_open"
    else:
        boss_reason = "no_boss_candidate"

    self_check_ready = bool(
        self_check_enabled
        and total_chunks >= 1
        and (concept_count >= 1 or max_quiz_readiness >= 0.30)
    )
    if not self_check_enabled:
        self_check_reason = "module_disabled"
    elif total_chunks <= 0:
        self_check_reason = "no_chunk_context"
    elif concept_count < 1 and max_quiz_readiness < 0.30:
        self_check_reason = "no_concept_anchor"
    else:
        self_check_reason = "self_check_route_ready"

    primary_reason = "all_modes_ready"
    for candidate in (
        roulette_reason if not roulette_ready else "",
        escape_reason if not escape_ready else "",
        speedrun_reason if not speedrun_ready else "",
        boss_reason if not boss_ready else "",
        self_check_reason if not self_check_ready else "",
    ):
        if candidate and candidate != "module_disabled":
            primary_reason = candidate
            break

    return {
        "roulette_hazir_mi": roulette_ready,
        "roulette_reason": roulette_reason,
        "escape_room_hazir_mi": escape_ready,
        "escape_room_reason": escape_reason,
        "speedrun_hazir_mi": speedrun_ready,
        "speedrun_reason": speedrun_reason,
        "boss_hazir_mi": boss_ready,
        "boss_reason": boss_reason,
        "self_check_hazir_mi": self_check_ready,
        "self_check_reason": self_check_reason,
        "_meta": {
            "unlock_reason_code": primary_reason,
            "quiz_readiness_score": avg_quiz_readiness,
            "mastery_score": round(mastery_meta["mastery_score"], 4),
            "confusion_map_score": round(confusion_meta["confusion_map_score"], 4),
            "critical_concept_count": concept_count,
            "escape_progress_score": round(escape_progress, 4),
            "boss_candidate_score": top_boss_candidate_score,
            "secilen_parca_sayisi": ready_chunks,
        },
    }
