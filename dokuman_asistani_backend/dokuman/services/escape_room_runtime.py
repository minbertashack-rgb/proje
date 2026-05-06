from __future__ import annotations

from dokuman.models import MetrikKaydi
from dokuman.services.concept_runtime import compute_concept_candidates
from dokuman.services.feature_flags import modul_acik_mi
from dokuman.services.metric_store import kaydet_skor_olayi


def escape_room_runtime_enabled() -> bool:
    return modul_acik_mi("DOCVERSE_ESCAPE_ROOM_ENABLED", True)


def _avg(values) -> float:
    clean = []
    for value in values or []:
        try:
            clean.append(float(value))
        except Exception:
            continue
    if not clean:
        return 0.0
    return sum(clean) / len(clean)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def _metric_avg(*, user, doc, olay_turu: str, score_key: str) -> float:
    qs = MetrikKaydi.objects.filter(
        kullanici=user,
        dokuman=doc,
        olay_turu=olay_turu,
    ).order_by("-id")[:12]
    return _avg((kayit.skor_ozeti or {}).get(score_key) for kayit in qs)


def build_escape_room_payload(
    *,
    doc,
    user,
    completed_step_count: int | None = None,
    force_completed: bool = False,
) -> dict:
    kavramlar = compute_concept_candidates(doc=doc, user=user, limit=6)
    hedef_kavramlar = [item["kavram"] for item in kavramlar[:3]]
    concept_progress = _clamp01(len(hedef_kavramlar) / 3.0)
    self_check_progress = _clamp01(_metric_avg(user=user, doc=doc, olay_turu="self_check_calistirildi", score_key="self_check_score") / 0.7)
    quiz_progress = _clamp01(
        max(
            _metric_avg(user=user, doc=doc, olay_turu="mini_quiz_sonuclandi", score_key="sonuc_orani"),
            _metric_avg(user=user, doc=doc, olay_turu="boss_deneme_tamamlandi", score_key="sonuc_orani"),
        )
    )

    gereken_adimlar = [
        {
            "kod": "anahtar_kavram",
            "etiket": "3 anahtar kavrami tanimla",
            "tamamlandi_mi": concept_progress >= 1.0,
        },
        {
            "kod": "kendin_acikla",
            "etiket": "Kavramlari kendi cumlenle acikla",
            "tamamlandi_mi": self_check_progress >= 0.6,
        },
        {
            "kod": "kapi_testi",
            "etiket": "Kisa kontrol testini gec",
            "tamamlandi_mi": quiz_progress >= 0.6,
        },
    ]
    auto_completed_count = sum(1 for item in gereken_adimlar if item["tamamlandi_mi"])
    if completed_step_count is not None:
        auto_completed_count = max(auto_completed_count, max(0, min(3, int(completed_step_count))))
    progress_score = _clamp01(
        (concept_progress * 0.34) + (self_check_progress * 0.28) + (quiz_progress * 0.38)
    )
    tamamlandi_mi = bool(force_completed or auto_completed_count >= len(gereken_adimlar) or progress_score >= 0.9)

    return {
        "dokuman_id": doc.id,
        "hedef_kavramlar": hedef_kavramlar,
        "gereken_adimlar": gereken_adimlar,
        "ilerleme_durumu": {
            "tamamlanan_adim_sayisi": int(auto_completed_count),
            "toplam_adim": len(gereken_adimlar),
            "ilerleme_skoru": round(progress_score, 4),
        },
        "tamamlandi_mi": tamamlandi_mi,
        "_meta": {
            "escape_target_count": len(hedef_kavramlar),
            "escape_step_count": len(gereken_adimlar),
            "escape_completed_step_count": int(auto_completed_count),
            "escape_progress_score": round(progress_score, 4),
            "escape_status": "completed" if tamamlandi_mi else "active",
        },
    }


def record_escape_room_event(*, user, doc, payload: dict, completed: bool = False):
    return kaydet_skor_olayi(
        kullanici=user,
        olay_turu="escape_room_tamamlandi" if completed else "escape_room_basladi",
        kaynak_modul="escape_room_runtime.api",
        dokuman=doc,
        score_map=dict(payload.get("_meta") or {}),
        durum="ok" if completed else "active",
    )
