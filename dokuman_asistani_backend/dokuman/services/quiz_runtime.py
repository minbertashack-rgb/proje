from __future__ import annotations

import threading

from django.core.cache import cache
from django.utils import timezone

from dokuman.models import Not
from dokuman.services.feature_flags import modul_acik_mi
from dokuman.services.metric_store import (
    compute_mastery_score,
    compute_quiz_readiness_score,
    kaydet_skor_olayi,
)

QUIZ_PROMPT_THRESHOLD = 0.75
_QUIZ_ACCEPT_COOLDOWN_SECONDS = 20 * 60
_QUIZ_DISMISS_COOLDOWN_SECONDS = 45 * 60


def quiz_runtime_enabled() -> bool:
    return modul_acik_mi("DOCVERSE_QUIZ_ENABLED", True)


def build_mini_quiz_gate(
    *,
    parca=None,
    text: str = "",
    quality_score: float | None = None,
    difficulty_score: float | None = None,
    weak_content: bool | None = None,
) -> dict:
    readiness = compute_quiz_readiness_score(
        parca=parca,
        text=text,
        quality_score=quality_score,
        difficulty_score=difficulty_score,
        weak_content=weak_content,
    )
    if not quiz_runtime_enabled():
        return {
            **readiness,
            "quiz_eligible": False,
            "quiz_skip_reason": "quiz_disabled",
        }

    if not readiness["quiz_eligible"]:
        return {
            **readiness,
            "quiz_skip_reason": readiness["quiz_reason"],
        }

    return {
        **readiness,
        "quiz_skip_reason": "",
    }


def _quiz_cooldown_key(*, user, parca) -> str:
    return f"docverse:quiz-cooldown:{getattr(user, 'id', 0)}:{getattr(parca, 'id', 0)}"


def _cooldown_window_seconds(action: str) -> int:
    if action in {"dismissed", "rejected"}:
        return _QUIZ_DISMISS_COOLDOWN_SECONDS
    return _QUIZ_ACCEPT_COOLDOWN_SECONDS


def mark_quiz_cooldown(*, user, parca, action: str) -> None:
    clean_action = str(action or "").strip().lower() or "accepted"
    cache.set(
        _quiz_cooldown_key(user=user, parca=parca),
        {
            "action": clean_action,
            "ts": timezone.now().timestamp(),
        },
        timeout=_cooldown_window_seconds(clean_action),
    )


def resolve_quiz_cooldown(*, user, parca) -> dict:
    payload = cache.get(_quiz_cooldown_key(user=user, parca=parca)) or {}
    action = str(payload.get("action") or "").strip().lower()
    ts = float(payload.get("ts") or 0.0)
    if not action or ts <= 0.0:
        return {
            "cooldown_factor": 1.0,
            "cooldown_action": "",
            "remaining_seconds": 0,
        }

    elapsed = max(0.0, timezone.now().timestamp() - ts)
    window = float(_cooldown_window_seconds(action))
    factor = max(0.0, min(1.0, elapsed / max(window, 1.0)))
    remaining = max(0, int(window - elapsed))
    return {
        "cooldown_factor": round(factor, 4),
        "cooldown_action": action,
        "remaining_seconds": remaining,
    }


def compute_runtime_quiz_readiness(
    *,
    user,
    parca,
    observed_read_seconds: float | int | None = None,
    expected_read_seconds: float | int | None = None,
    read_ratio: float | None = None,
    note_count: int | None = None,
) -> dict:
    content_gate = build_mini_quiz_gate(parca=parca, text=getattr(parca, "metin", "") or "")
    mastery_meta = compute_mastery_score(user=user, dokuman=getattr(parca, "dokuman", None))
    if read_ratio is None:
        try:
            observed = max(float(observed_read_seconds or 0.0), 0.0)
            expected = max(float(expected_read_seconds or 0.0), 0.0)
            read_ratio = observed / max(expected, 1.0) if expected > 0 else 0.0
        except Exception:
            read_ratio = 0.0
    if note_count is None:
        note_count = Not.objects.filter(owner=user, parca=parca).count()
    cooldown_meta = resolve_quiz_cooldown(user=user, parca=parca)
    base_score = (
        0.5 * float(mastery_meta["mastery_score"])
        + 0.3 * max(0.0, min(1.0, float(read_ratio or 0.0)))
        + 0.2 * max(0.0, min(1.0, float(note_count or 0) / 3.0))
    )
    quiz_readiness_score = max(
        0.0,
        min(1.0, base_score * float(cooldown_meta["cooldown_factor"])),
    )
    show_prompt = bool(
        quiz_runtime_enabled()
        and content_gate["quiz_eligible"]
        and quiz_readiness_score > QUIZ_PROMPT_THRESHOLD
    )
    if not quiz_runtime_enabled():
        reason = "quiz_disabled"
    elif not content_gate["quiz_eligible"]:
        reason = "content_not_ready"
    elif cooldown_meta["cooldown_factor"] < 1.0:
        reason = "cooldown_active"
    elif quiz_readiness_score > QUIZ_PROMPT_THRESHOLD:
        reason = "ready_for_prompt"
    else:
        reason = "below_prompt_threshold"
    return {
        "show_quiz_prompt": show_prompt,
        "quiz_readiness_score": round(quiz_readiness_score, 4),
        "quiz_readiness_threshold": QUIZ_PROMPT_THRESHOLD,
        "runtime_quiz_reason": reason,
        "mastery_score": mastery_meta["mastery_score"],
        "read_ratio": round(float(read_ratio or 0.0), 4),
        "note_count": int(note_count or 0),
        "cooldown_factor": cooldown_meta["cooldown_factor"],
        "cooldown_action": cooldown_meta["cooldown_action"],
        "cooldown_remaining_seconds": cooldown_meta["remaining_seconds"],
        "content_quiz_eligible": bool(content_gate["quiz_eligible"]),
        "content_quiz_reason": content_gate["quiz_reason"],
    }


def record_quiz_readiness_event(*, user, parca, gate_meta: dict):
    return kaydet_skor_olayi(
        kullanici=user,
        olay_turu="quiz_hazirlik_hesaplandi",
        kaynak_modul="quiz_runtime.ai2",
        dokuman=getattr(parca, "dokuman", None),
        parca=parca,
        score_map={
            "quiz_readiness_score": gate_meta.get("quiz_readiness_score", 0.0),
            "quiz_reason": gate_meta.get("quiz_reason", ""),
            "quiz_eligible": bool(gate_meta.get("quiz_eligible")),
            "quiz_skip_reason": gate_meta.get("quiz_skip_reason", ""),
        },
        durum="ok",
    )


def record_mini_quiz_event(*, user, parca, gate_meta: dict, generated_count: int):
    generated = int(generated_count or 0) > 0
    return kaydet_skor_olayi(
        kullanici=user,
        olay_turu="mini_quiz_uretildi" if generated else "mini_quiz_atlandi",
        kaynak_modul="quiz_runtime.ai2",
        dokuman=getattr(parca, "dokuman", None),
        parca=parca,
        score_map={
            "quiz_readiness_score": gate_meta.get("quiz_readiness_score", 0.0),
            "quiz_reason": gate_meta.get("quiz_reason", ""),
            "quiz_eligible": bool(gate_meta.get("quiz_eligible")),
            "quiz_skip_reason": "" if generated else gate_meta.get("quiz_skip_reason", "") or gate_meta.get("quiz_reason", ""),
            "toplam_soru": int(generated_count or 0),
        },
        durum="ok" if generated else "skipped",
    )


def record_quiz_prompt_event(*, user, parca, readiness_meta: dict):
    if not readiness_meta.get("show_quiz_prompt"):
        return None
    return kaydet_skor_olayi(
        kullanici=user,
        olay_turu="quiz_prompted",
        kaynak_modul="quiz_runtime.prompt",
        dokuman=getattr(parca, "dokuman", None),
        parca=parca,
        score_map={
            "quiz_readiness_score": readiness_meta.get("quiz_readiness_score", 0.0),
            "mastery_score": readiness_meta.get("mastery_score", 0.0),
            "read_ratio": readiness_meta.get("read_ratio", 0.0),
            "note_count": readiness_meta.get("note_count", 0),
            "cooldown_factor": readiness_meta.get("cooldown_factor", 1.0),
            "show_quiz_prompt": True,
        },
        durum="ok",
    )


def enqueue_quiz_acceptance_event(*, user, parca, dogru_sayisi: int, toplam_soru: int, sonuc_orani: float):
    def _writer():
        kaydet_skor_olayi(
            kullanici=user,
            olay_turu="quiz_accepted",
            kaynak_modul="quiz_runtime.result",
            dokuman=getattr(parca, "dokuman", None),
            parca=parca,
            score_map={
                "dogru_sayisi": int(dogru_sayisi or 0),
                "toplam_soru": int(toplam_soru or 0),
                "sonuc_orani": float(sonuc_orani or 0.0),
                "quiz_action": "accepted",
            },
            durum="ok",
        )

    thread = threading.Thread(target=_writer, daemon=True)
    thread.start()
    return thread
