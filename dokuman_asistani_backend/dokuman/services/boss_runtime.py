from __future__ import annotations

from dokuman.services.boss import boss_uret
from dokuman.services.feature_flags import modul_acik_mi
from dokuman.services.metric_store import (
    compute_boss_difficulty_score,
    compute_boss_progress_score,
    compute_confusion_map_score,
    compute_confusion_recovery_score,
    compute_learning_momentum_score,
    compute_mastery_progress_delta,
    compute_reward_priority_score,
    compute_study_summary_importance_score,
    compute_mastery_score,
    kaydet_skor_olayi,
)


def boss_runtime_enabled() -> bool:
    return modul_acik_mi("DOCVERSE_BOSS_ENABLED", True)


def _safe_snippet_signal(text: str) -> str:
    clean = " ".join(str(text or "").split()).strip()
    if not clean:
        return ""
    return f"Parca sinyali: {len(clean.split())} kelime, {len(clean)} karakter."


def _boss_candidate_meta(*, parca, user) -> dict:
    meta = dict(getattr(parca, "meta", {}) or {})
    difficulty_score = max(
        float(meta.get("difficulty_score") or 0.0),
        float(getattr(parca, "zorluk_skoru", 0.0) or 0.0),
    )
    confusion_meta = compute_confusion_map_score(
        user=user,
        dokuman=getattr(parca, "dokuman", None),
        parca=parca,
    )
    importance_meta = compute_study_summary_importance_score(
        user=user,
        dokuman=getattr(parca, "dokuman", None),
        parca=parca,
        confusion_map_score=confusion_meta["confusion_map_score"],
    )
    candidate_score = max(
        0.0,
        min(
            1.0,
            difficulty_score * 0.36
            + confusion_meta["confusion_map_score"] * 0.30
            + importance_meta["study_summary_importance_score"] * 0.24
            + (0.10 if not bool(meta.get("weak_content")) else 0.0),
        ),
    )
    if confusion_meta["confusion_map_score"] >= 0.45:
        reason = "confusion_priority"
    elif difficulty_score >= 0.65:
        reason = "difficulty_priority"
    else:
        reason = "balanced_priority"
    return {
        "boss_candidate_score": round(candidate_score, 4),
        "boss_reason": reason,
        "confusion_map_score": confusion_meta["confusion_map_score"],
        "difficulty_score": round(float(difficulty_score), 4),
        "study_summary_importance_score": importance_meta["study_summary_importance_score"],
    }


def build_boss_payload(*, parca, user) -> dict:
    boss_meta = _boss_candidate_meta(parca=parca, user=user)
    difficulty_meta = compute_boss_difficulty_score(
        user=user,
        dokuman=getattr(parca, "dokuman", None),
    )
    return {
        "session_key": f"doc-{parca.dokuman_id}-parca-{parca.id}",
        "parca": {
            "id": parca.id,
            "adres": getattr(parca, "adres", "") or "",
            "zorluk": getattr(parca, "zorluk", "") or "",
            "zorluk_skoru": float(getattr(parca, "zorluk_skoru", 0.0) or 0.0),
        },
        "boss_meta": boss_meta,
        "boss_difficulty": difficulty_meta,
        "boss_fight": boss_uret(
            getattr(parca, "metin", "") or "",
            difficulty_meta=difficulty_meta,
        ),
    }


def select_boss_candidates(*, doc, user, limit: int = 5) -> list[dict]:
    candidates = []
    for parca in doc.parcalar.all().order_by("id"):
        payload = build_boss_payload(parca=parca, user=user)
        payload["snippet"] = _safe_snippet_signal(getattr(parca, "metin", "") or "")
        candidates.append(payload)
    candidates.sort(
        key=lambda item: (
            -float(item["boss_meta"]["boss_candidate_score"]),
            item["parca"]["id"],
        )
    )
    return candidates[: max(1, int(limit or 1))]


def build_boss_rush_payload(*, doc, user, limit: int = 5) -> dict:
    arena = select_boss_candidates(doc=doc, user=user, limit=limit)
    return {
        "dokuman": {
            "id": doc.id,
            "baslik": doc.baslik,
            "parca_sayisi": doc.parcalar.count(),
        },
        "boss_rush": {
            "limit": max(1, int(limit or 1)),
            "arena_sayisi": len(arena),
            "arena": [
                {
                    "sira": index,
                    "parca_id": item["parca"]["id"],
                    "adres": item["parca"]["adres"],
                    "zorluk": item["parca"]["zorluk"],
                    "zorluk_skoru": item["parca"]["zorluk_skoru"],
                    "snippet": item["snippet"],
                    "boss_meta": item["boss_meta"],
                    "boss_difficulty": item["boss_difficulty"],
                    "boss_fight": item["boss_fight"],
                }
                for index, item in enumerate(arena, start=1)
            ],
        },
    }


def record_boss_candidate_event(*, user, parca, boss_meta: dict, selected_count: int = 1):
    return kaydet_skor_olayi(
        kullanici=user,
        olay_turu="boss_adayi_secildi",
        kaynak_modul="boss_runtime.api",
        dokuman=getattr(parca, "dokuman", None),
        parca=parca,
        score_map={
            "boss_candidate_score": boss_meta.get("boss_candidate_score", 0.0),
            "boss_reason": boss_meta.get("boss_reason", ""),
            "confusion_map_score": boss_meta.get("confusion_map_score", 0.0),
            "difficulty_score": boss_meta.get("difficulty_score", 0.0),
            "study_summary_importance_score": boss_meta.get("study_summary_importance_score", 0.0),
            "secilen_parca_sayisi": int(selected_count or 1),
        },
        durum="ok",
    )


def record_boss_start_event(*, user, doc, parca=None, boss_difficulty: dict | None = None, arena_sayisi: int = 1):
    return kaydet_skor_olayi(
        kullanici=user,
        olay_turu="boss_baslatildi",
        kaynak_modul="boss_runtime.api",
        dokuman=doc,
        parca=parca,
        score_map={
            "boss_difficulty_score": (boss_difficulty or {}).get("boss_difficulty_score", 0.0),
            "boss_difficulty_band": (boss_difficulty or {}).get("boss_difficulty_band", ""),
            "boss_retry_count": (boss_difficulty or {}).get("boss_retry_count", 0),
            "learning_momentum_score": (boss_difficulty or {}).get("learning_momentum_score", 0.0),
            "mastery_score": (boss_difficulty or {}).get("mastery_score", 0.0),
            "arena_sayisi": int(arena_sayisi or 1),
        },
        durum="ok",
    )


def build_learning_outcome_events(
    *,
    user,
    dokuman,
    parca=None,
    previous_mastery_score: float,
    previous_confusion_score: float | None = None,
    sonuc_orani: float,
    boss_kill: bool,
) -> list[dict]:
    mastery_after = compute_mastery_score(user=user, dokuman=dokuman)
    delta_meta = compute_mastery_progress_delta(
        old_score=previous_mastery_score,
        new_score=mastery_after["mastery_score"],
    )
    recovery_meta = compute_confusion_recovery_score(
        user=user,
        dokuman=dokuman,
        parca=parca,
        quiz_score=sonuc_orani,
        confusion_map_score=previous_confusion_score,
    )
    momentum_meta = compute_learning_momentum_score(user=user)
    reward_meta = compute_reward_priority_score(
        recovery_score=recovery_meta["confusion_recovery_score"],
        momentum_score=momentum_meta["learning_momentum_score"],
        boss_kill=boss_kill,
    )
    return [
        {
            "olay_turu": "mastery_delta_hesaplandi",
            "durum": "ok",
            "score_map": {
                "mastery_progress_delta": delta_meta["mastery_progress_delta"],
                "mastery_score": mastery_after["mastery_score"],
                "mastery_reason": mastery_after["mastery_reason"],
            },
        },
        {
            "olay_turu": "learning_momentum_snapshot",
            "durum": "ok",
            "score_map": {
                "learning_momentum_score": momentum_meta["learning_momentum_score"],
            },
        },
        {
            "olay_turu": "confusion_recovery_hesaplandi",
            "durum": "ok",
            "score_map": {
                "confusion_recovery_score": recovery_meta["confusion_recovery_score"],
                "confusion_map_score": recovery_meta["confusion_map_score"],
                "recovery_reason": recovery_meta["recovery_reason"],
                "eureka_triggered": recovery_meta["eureka_triggered"],
            },
        },
        {
            "olay_turu": "reward_priority_hesaplandi",
            "durum": "ok",
            "score_map": {
                "reward_priority_score": reward_meta["reward_priority_score"],
                "reward_priority_reason": reward_meta["reward_priority_reason"],
            },
        },
    ]


def record_learning_outcome_events(
    *,
    user,
    dokuman,
    parca=None,
    previous_mastery_score: float,
    previous_confusion_score: float | None = None,
    sonuc_orani: float,
    boss_kill: bool,
):
    for event in build_learning_outcome_events(
        user=user,
        dokuman=dokuman,
        parca=parca,
        previous_mastery_score=previous_mastery_score,
        previous_confusion_score=previous_confusion_score,
        sonuc_orani=sonuc_orani,
        boss_kill=boss_kill,
    ):
        kaydet_skor_olayi(
            kullanici=user,
            olay_turu=event["olay_turu"],
            kaynak_modul="learning_runtime.snapshot",
            dokuman=dokuman,
            parca=parca,
            score_map=event["score_map"],
            durum=event["durum"],
        )


def record_boss_attempt_event(*, user, doc, parcalar, dogru_sayisi: int, toplam_soru: int, ipucu_sayisi: int = 0):
    parca_idleri = [int(getattr(item, "id", 0) or 0) for item in parcalar if getattr(item, "id", None) is not None]
    progress_meta = compute_boss_progress_score(
        dogru_sayisi=int(dogru_sayisi or 0),
        toplam_soru=int(toplam_soru or 0),
        ipucu_sayisi=int(ipucu_sayisi or 0),
    )
    return kaydet_skor_olayi(
        kullanici=user,
        olay_turu="boss_deneme_tamamlandi",
        kaynak_modul="boss_runtime.api",
        dokuman=doc,
        parca=parcalar[0] if parcalar else None,
        score_map={
            "dogru_sayisi": int(dogru_sayisi or 0),
            "toplam_soru": int(toplam_soru or 0),
            "sonuc_orani": progress_meta["sonuc_orani"],
            "boss_progress_score": progress_meta["boss_progress_score"],
            "boss_outcome": progress_meta["boss_outcome"],
            "boss_progress_reason": progress_meta["boss_progress_reason"],
            "ipucu_sayisi": progress_meta["ipucu_sayisi"],
            "secilen_parca_sayisi": len(parca_idleri),
            "boss_parca_idleri": parca_idleri[:12],
        },
        durum="ok",
    )
