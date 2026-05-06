from __future__ import annotations

from dokuman.models import KullaniciGeriBildirim
from dokuman.services.metric_store import (
    compute_confusion_map_score,
    compute_feedback_weight_score as compute_feedback_weight_score_v2,
    compute_mastery_score,
    guvenli_metrik_kaydi_olustur,
)
from dokuman.services.phase2_scores import compute_feedback_weight_score as compute_feedback_weight_score_v1


def _feedback_source_text(*, parca=None, not_kaydi=None, portal_not=None) -> str:
    if portal_not is not None:
        return str(getattr(portal_not, "icerik", "") or "")
    if not_kaydi is not None:
        return str(getattr(not_kaydi, "metin", "") or "")
    if parca is not None:
        return str(getattr(parca, "metin", "") or "")
    return ""


def kaydet_geri_bildirim(
    *,
    kullanici,
    feedback_turu: str,
    kaynak_modul: str,
    kisa_not: str = "",
    dokuman=None,
    parca=None,
    not_kaydi=None,
    portal_not=None,
    okuma_suresi_saniye=None,
):
    hedef_dokuman = dokuman or getattr(parca, "dokuman", None) or getattr(not_kaydi, "dokuman", None) or getattr(portal_not, "dokuman", None)
    hedef_parca = parca or getattr(not_kaydi, "parca", None) or getattr(portal_not, "parca", None)

    legacy_feedback_meta = compute_feedback_weight_score_v1(
        text=_feedback_source_text(parca=parca, not_kaydi=not_kaydi, portal_not=portal_not),
        dwell_seconds=okuma_suresi_saniye,
        # Faz 2'de reputation sinyalini henuz agresif baglamiyoruz; yeni kullanici zemini sabit.
        user_reputation=0.5,
    )
    behavioral_feedback_meta = compute_feedback_weight_score_v2(
        user=kullanici,
        dokuman=hedef_dokuman,
        parca=hedef_parca,
        feedback_turu=feedback_turu,
        kisa_not_uzunlugu=len((kisa_not or "").strip()),
        okuma_suresi_saniye=okuma_suresi_saniye,
        beklenen_okuma_suresi_saniye=legacy_feedback_meta["expected_read_seconds"],
    )
    feedback = KullaniciGeriBildirim.objects.create(
        owner=kullanici,
        dokuman=hedef_dokuman,
        parca=hedef_parca,
        not_kaydi=not_kaydi,
        portal_not=portal_not,
        feedback_turu=feedback_turu,
        kisa_not=(kisa_not or "").strip()[:280],
        kaynak_modul=(kaynak_modul or "dokuman.api").strip()[:64] or "dokuman.api",
    )
    feedback_weight_score = round(
        (
            legacy_feedback_meta["feedback_weight_score"] * 0.45
            + behavioral_feedback_meta["feedback_weight_score"] * 0.55
        ),
        4,
    )
    feedback_ignored = bool(
        legacy_feedback_meta["feedback_ignored"]
        or behavioral_feedback_meta["feedback_weight_score"] < 0.35
    )
    mastery_meta = compute_mastery_score(
        user=kullanici,
        dokuman=hedef_dokuman,
    )
    confusion_meta = compute_confusion_map_score(
        user=kullanici,
        dokuman=hedef_dokuman,
        parca=hedef_parca,
    )

    # Feedback metnini degil, yalnizca guvenli baglam sinyallerini metriğe yazariz.
    guvenli_metrik_kaydi_olustur(
        kullanici=kullanici,
        olay_turu="feedback_verildi",
        kaynak_modul="feedback.api",
        dokuman=hedef_dokuman,
        parca=hedef_parca,
        ilgili_not_id=getattr(not_kaydi, "id", None),
        ilgili_portal_not_id=getattr(portal_not, "id", None),
        ilgili_feedback_id=feedback.id,
        skor_ozeti={
            "feedback_turu": feedback.feedback_turu,
            "kaynak_modul": feedback.kaynak_modul,
            "kisa_not_uzunlugu": len(feedback.kisa_not or ""),
            "feedback_weight_score": feedback_weight_score,
            "feedback_ignored": feedback_ignored,
            "feedback_reason": behavioral_feedback_meta["feedback_weight_reason"],
            "feedback_weight_reason": behavioral_feedback_meta["feedback_weight_reason"],
            "read_ratio": legacy_feedback_meta["read_ratio"],
            "expected_read_seconds": legacy_feedback_meta["expected_read_seconds"],
            "observed_read_seconds": legacy_feedback_meta["observed_read_seconds"],
            "feedback_speed_score": behavioral_feedback_meta["feedback_speed_score"],
            "feedback_spam_penalty": behavioral_feedback_meta["feedback_spam_penalty"],
            "feedback_context_bonus": behavioral_feedback_meta["feedback_context_bonus"],
            "mastery_score": mastery_meta["mastery_score"],
            "mastery_reason": mastery_meta["mastery_reason"],
            "confusion_map_score": confusion_meta["confusion_map_score"],
            "confusion_reason": confusion_meta["confusion_reason"],
            "dokuman_var_mi": hedef_dokuman is not None,
            "parca_var_mi": hedef_parca is not None,
            "not_var_mi": not_kaydi is not None,
            "portal_not_var_mi": portal_not is not None,
        },
        durum="ignored" if feedback_ignored else "ok",
    )
    return feedback
