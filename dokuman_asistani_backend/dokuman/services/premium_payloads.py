from __future__ import annotations

from dokuman.models import MetrikKaydi
from dokuman.services.cheatsheet_builder import build_cheatsheet_payload
from dokuman.services.study_summary import build_study_summary_payload


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def _safe_avg(values: list[float]) -> float:
    clean = []
    for value in values:
        try:
            clean.append(float(value))
        except Exception:
            continue
    if not clean:
        return 0.0
    return sum(clean) / len(clean)


def _badge_level(value: float) -> str:
    if value >= 0.7:
        return "yuksek"
    if value >= 0.4:
        return "orta"
    return "dusuk"


def build_premium_payload(
    *,
    doc,
    user,
    portal_not=None,
    cheatsheet_enabled: bool = True,
    style_enabled: bool = True,
    directors_cut_enabled: bool = True,
    export_plan_enabled: bool = True,
    quiz_enabled: bool = True,
) -> dict:
    summary = build_study_summary_payload(doc=doc, user=user, portal_not=portal_not)
    cheatsheet = build_cheatsheet_payload(doc=doc, user=user, portal_not=portal_not) if cheatsheet_enabled else {}
    kaynak_ids = list(summary.get("bagli_parca_idleri") or cheatsheet.get("bagli_parca_idleri") or [])[:6]
    if not kaynak_ids:
        kaynak_ids = list(doc.parcalar.order_by("-zorluk_skoru", "id").values_list("id", flat=True)[:4])

    metric_qs = MetrikKaydi.objects.filter(kullanici=user, dokuman=doc).order_by("-created_at")
    confusion_avg = _safe_avg([
        (kayit.skor_ozeti or {}).get("confusion_map_score")
        for kayit in metric_qs[:24]
    ])
    quiz_ready_ratio = _safe_avg([
        1.0 if float((kayit.skor_ozeti or {}).get("quiz_readiness_score") or 0.0) >= 0.6 else 0.0
        for kayit in metric_qs.filter(olay_turu__in=["quiz_prompt_gosterildi", "quiz_readiness_degerlendirildi"])[:12]
    ])
    ornek_coverage = min(
        1.0,
        (
            len(list(cheatsheet.get("glossary") or []))
            + len(list(summary.get("ana_maddeler") or []))
        ) / 8.0,
    )

    netlik = round(_clamp01(1.0 - confusion_avg), 4)
    ornek = round(_clamp01(ornek_coverage), 4)
    test = round(_clamp01(quiz_ready_ratio), 4)

    base_path = f"/api/dokuman-asistani/dokumanlar/{doc.id}"
    return {
        "dokuman_id": doc.id,
        "portal_not_id": getattr(portal_not, "id", None),
        "spotlight_payload": {
            "baslik": doc.baslik or f"Dokuman {doc.id}",
            "netlik_gostergesi": netlik,
            "ornek_gostergesi": ornek,
            "test_gostergesi": test,
            "highlight_parca_idleri": kaynak_ids,
        },
        "teleport_links": [
            {
                "hedef": "tanima",
                "etiket": "Temel Kavrama",
                "href": f"{base_path}/style-console/?stil=kisa&ton=hoca",
                "aktif": bool(style_enabled),
            },
            {
                "hedef": "ornege",
                "etiket": "Story Cut",
                "href": f"{base_path}/directors-cut/?mod=story_cut",
                "aktif": bool(directors_cut_enabled),
            },
            {
                "hedef": "teste",
                "etiket": "Exam Route",
                "href": f"{base_path}/directors-cut/?mod=exam_cut",
                "aktif": bool(directors_cut_enabled and quiz_enabled),
            },
        ],
        "cevap_bilekligi_gostergeleri": [
            {"kod": "netlik", "deger": netlik, "seviye": _badge_level(netlik)},
            {"kod": "ornek", "deger": ornek, "seviye": _badge_level(ornek)},
            {"kod": "test", "deger": test, "seviye": _badge_level(test)},
        ],
    }
