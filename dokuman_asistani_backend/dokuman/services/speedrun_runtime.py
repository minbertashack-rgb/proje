from __future__ import annotations

import re

from dokuman.services.concept_runtime import compute_concept_candidates
from dokuman.services.feature_flags import modul_acik_mi
from dokuman.services.metric_store import compute_quiz_readiness_score, kaydet_skor_olayi
from dokuman.services.study_summary import build_study_summary_payload

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def speedrun_runtime_enabled() -> bool:
    return modul_acik_mi("DOCVERSE_SPEEDRUN_ENABLED", True)


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _sentences(text: str) -> list[str]:
    clean = _clean_text(text)
    if not clean:
        return []
    chunks = [item.strip() for item in _SENTENCE_SPLIT_RE.split(clean) if item.strip()]
    return chunks or [clean]


def _target_parcalar(*, doc, user, limit: int = 3):
    summary = build_study_summary_payload(doc=doc, user=user, include_internal=True)
    ids = list(summary.get("bagli_parca_idleri") or [])[:limit]
    parcalar = list(doc.parcalar.filter(id__in=ids).order_by("id"))
    if len(parcalar) < limit:
        eksik = (
            doc.parcalar.exclude(id__in=[item.id for item in parcalar])
            .order_by("-zorluk_skoru", "id")[: max(0, limit - len(parcalar))]
        )
        parcalar.extend(list(eksik))
    return parcalar[:limit], summary


def build_speedrun_payload(*, doc, user) -> dict:
    parcalar, summary = _target_parcalar(doc=doc, user=user, limit=3)
    onemli_cumleler = []
    readiness_values = []
    for parca in parcalar:
        sentence = (_sentences(getattr(parca, "metin", "") or "") or [""])[0]
        if sentence:
            onemli_cumleler.append(sentence[:180])
        readiness_values.append(compute_quiz_readiness_score(parca=parca)["quiz_readiness_score"])

    if not onemli_cumleler:
        onemli_cumleler = list(summary.get("ana_maddeler") or [])[:3]

    quiz_items = []
    for parca in parcalar[:2]:
        concept = compute_concept_candidates(doc=doc, user=user, parca=parca, limit=1)
        hedef = (concept[0]["kavram"] if concept else (getattr(parca, "adres", "") or "Ana kavram"))
        quiz_items.append(
            {
                "mod": "mini_test",
                "soru": f"Speedrun sonunda hangi kavrami hatirlamalisin? ({getattr(parca, 'adres', '')})",
                "beklenen_cevap": hedef[:80],
            }
        )

    ortalama_readiness = sum(readiness_values) / len(readiness_values) if readiness_values else 0.0
    hedef_sure = int(max(180, min(360, 150 + (len(onemli_cumleler) * 45) + (ortalama_readiness * 60))))
    tamir_adimi = "Yanlis kalirsan ilk odak cumleyi 60 saniye tekrar oku ve mini testi yeniden dene."
    if parcalar:
        tamir_adimi = f"Yanlis kalirsan {getattr(parcalar[0], 'adres', '')} parcasini 60 saniye tekrar oku."

    return {
        "dokuman_id": doc.id,
        "en_onemli_cumleler": onemli_cumleler[:3],
        "mini_quiz": quiz_items[:2],
        "yanlis_tamir_adimi": tamir_adimi,
        "hedef_sure_saniye": hedef_sure,
        "_meta": {
            "speedrun_target_seconds": hedef_sure,
            "speedrun_sentence_count": len(onemli_cumleler[:3]),
            "quiz_readiness_score": round(ortalama_readiness, 4),
            "speedrun_status": "generated",
        },
    }


def record_speedrun_generated(*, user, doc, payload: dict):
    return kaydet_skor_olayi(
        kullanici=user,
        olay_turu="speedrun_uretildi",
        kaynak_modul="speedrun_runtime.api",
        dokuman=doc,
        score_map=dict(payload.get("_meta") or {}),
        durum="ok",
    )


def record_speedrun_completed(
    *,
    user,
    doc,
    dogru_sayisi: int,
    toplam_soru: int,
    hedef_sure_saniye: int,
):
    toplam = max(int(toplam_soru or 0), 1)
    oran = round(max(0.0, min(1.0, int(dogru_sayisi or 0) / toplam)), 4)
    return kaydet_skor_olayi(
        kullanici=user,
        olay_turu="speedrun_tamamlandi",
        kaynak_modul="speedrun_runtime.api",
        dokuman=doc,
        score_map={
            "dogru_sayisi": int(dogru_sayisi or 0),
            "toplam_soru": toplam,
            "sonuc_orani": oran,
            "speedrun_target_seconds": int(hedef_sure_saniye or 0),
            "speedrun_status": "completed",
        },
        durum="ok",
    )
