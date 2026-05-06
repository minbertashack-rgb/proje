from __future__ import annotations

import pytest
from django.core.files.base import ContentFile

from dokuman.models import Dokuman, KullaniciTercih, MetrikKaydi, Parca
from dokuman.services import product_panels

pytestmark = pytest.mark.django_db


def _doc(user, *, title: str = "Helper Doc", chunks: list[dict] | None = None) -> Dokuman:
    doc = Dokuman.objects.create(owner=user, baslik=title, mime="application/pdf", durum="parcalandi")
    doc.dosya.save(f"{title.lower().replace(' ', '-')}.pdf", ContentFile(b"ornek"), save=True)
    for index, item in enumerate(chunks or [], start=1):
        Parca.objects.create(
            dokuman=doc,
            sira=index,
            tur=item.get("tur", "bolum"),
            adres=f"1.{index}",
            metin=item.get("metin", f"HAM_HELPER_{index}"),
            meta=item.get("meta", {}),
            zorluk_skoru=item.get("zorluk_skoru", 0.0),
            zorluk=item.get("zorluk", "orta"),
        )
    return doc


def _metric(user, *, olay_turu: str, score_map: dict | None = None):
    return MetrikKaydi.objects.create(
        kullanici=user,
        olay_turu=olay_turu,
        kaynak_modul="tests.helper",
        skor_ozeti=score_map or {},
        durum="ok",
    )


def test_panel_helpers_return_safe_fallback_scores_without_config(settings, test_kullanicisi, gecici_media_root):
    settings.DOCVERSE_PANEL_SCORE_OVERRIDES = {}
    settings.DOCVERSE_PANEL_SCORE_HOOKS = {}
    doc = _doc(
        test_kullanicisi,
        chunks=[
            {"tur": "tablo", "zorluk_skoru": 0.8, "meta": {"quality_score": 0.9, "heading_score": 0.7}},
            {"tur": "kod", "zorluk_skoru": 0.7, "meta": {"quality_score": 0.8, "heading_score": 0.6}},
            {"tur": "bolum", "zorluk_skoru": 0.65, "meta": {"quality_score": 0.7, "heading_score": 0.7}},
        ],
    )
    KullaniciTercih.objects.create(kullanici=test_kullanicisi, tema="genel", ton="teknik")
    _metric(test_kullanicisi, olay_turu="mini_quiz_sonuclandi", score_map={"sonuc_orani": 0.8})
    _metric(test_kullanicisi, olay_turu="boss_deneme_tamamlandi", score_map={"boss_progress_score": 0.9})

    boss = product_panels.build_boss_rush_panel_payload(doc)
    export = product_panels.build_export_readiness_payload(doc)
    personalization = product_panels.build_personalization_confidence_payload(test_kullanicisi)
    weekly = product_panels.build_weekly_progress_payload(test_kullanicisi)
    achievement = product_panels.build_achievement_progress_payload(test_kullanicisi)

    assert boss["boss_rush_readiness_score"] == boss["hazirlik_skoru"]
    assert export["export_readiness_score"] >= 0.0
    assert personalization["personalization_confidence_score"] == personalization["personalization_confidence"]
    assert weekly["weekly_goal_progress_score"] == weekly["haftalik_ilerleme_skoru"]
    assert achievement["achievement_progress_score"] >= 0.0
    assert boss["_meta"]["selection_state"] == "fallback"
    assert export["_meta"]["selection_state"] == "fallback"
    assert personalization["_meta"]["selection_state"] == "fallback"
    assert weekly["_meta"]["selection_state"] == "fallback"
    assert achievement["_meta"]["selection_state"] == "fallback"
    assert "HAM_HELPER" not in str(
        {
            "boss": boss,
            "export": export,
            "personalization": personalization,
            "weekly": weekly,
            "achievement": achievement,
        }
    )


def test_panel_score_overrides_and_hooks_are_applied_safely(settings, test_kullanicisi, gecici_media_root):
    doc = _doc(test_kullanicisi, title="Override Doc", chunks=[{"zorluk_skoru": 0.9, "meta": {"quality_score": 0.8, "heading_score": 0.8}}])
    settings.DOCVERSE_PANEL_SCORE_OVERRIDES = {"boss_rush_readiness_score": 0.41, "achievement_progress_score": 0.77}
    settings.DOCVERSE_PANEL_SCORE_HOOKS = {
        "export_readiness_score": lambda **kwargs: 0.63,
        "weekly_goal_progress_score": lambda **kwargs: 0.52,
        "personalization_confidence_score": lambda **kwargs: 0.38,
    }

    boss = product_panels.build_boss_rush_panel_payload(doc)
    export = product_panels.build_export_readiness_payload(doc)
    personalization = product_panels.build_personalization_confidence_payload(test_kullanicisi)
    weekly = product_panels.build_weekly_progress_payload(test_kullanicisi)
    achievement = product_panels.build_achievement_progress_payload(test_kullanicisi)

    assert boss["boss_rush_readiness_score"] == 0.41
    assert boss["_meta"]["selection_state"] == "override"
    assert export["export_readiness_score"] == 0.63
    assert export["_meta"]["selection_state"] == "hook"
    assert personalization["personalization_confidence_score"] == 0.38
    assert personalization["_meta"]["selection_state"] == "hook"
    assert weekly["weekly_goal_progress_score"] == 0.52
    assert weekly["_meta"]["selection_state"] == "hook"
    assert achievement["achievement_progress_score"] == 0.77
    assert achievement["_meta"]["selection_state"] == "override"


def test_achievement_helper_keeps_safe_snapshot_counts_in_meta(settings, test_kullanicisi):
    settings.DOCVERSE_PANEL_SCORE_OVERRIDES = {}
    _metric(test_kullanicisi, olay_turu="mini_quiz_sonuclandi", score_map={"sonuc_orani": 0.8})
    _metric(test_kullanicisi, olay_turu="self_check_calistirildi", score_map={"self_check_score": 0.7})

    payload = product_panels.build_achievement_progress_payload(test_kullanicisi)

    assert payload["_meta"]["quiz_count"] == 1.0
    assert payload["_meta"]["self_check_count"] == 1.0
    assert payload["_meta"]["achievement_state"] in {"new_user", "in_progress", "boss_ready"}
    assert "HAM_" not in str(payload["_meta"])
