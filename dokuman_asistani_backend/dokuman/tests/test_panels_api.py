from __future__ import annotations

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from rest_framework.test import APIClient

from dokuman.models import Dokuman, DokumanNotu, KullaniciTercih, MetrikKaydi, Not, Parca
from dokuman.services import product_panels


pytestmark = pytest.mark.django_db


PANEL_ROUTE_ALIASES = (
    ("dokuman-boss-rush-panel", "boss-rush-panel", {"pk": 1}),
    ("dokuman-export-readiness", "export-readiness", {"pk": 1}),
    ("analytics-weekly-progress", "weekly-progress", {}),
    ("analytics-achievement-progress", "achievement-progress", {}),
    ("profil-personalization-confidence", "personalization-confidence", {}),
)


def _client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _create_doc(user, *, title: str = "Panel Doc") -> Dokuman:
    doc = Dokuman.objects.create(owner=user, baslik=title, mime="application/pdf", durum="parcalandi")
    doc.dosya.save(f"{title.lower().replace(' ', '_')}.pdf", ContentFile(b"ornek"), save=True)
    return doc


def _create_parca(
    doc: Dokuman,
    *,
    sira: int,
    tur: str = "bolum",
    text: str = "guvenli panel parcasi",
    zorluk_skoru: float = 0.2,
    meta: dict | None = None,
) -> Parca:
    return Parca.objects.create(
        dokuman=doc,
        sira=sira,
        tur=tur,
        adres=f"1.{sira}",
        metin=text,
        zorluk_skoru=zorluk_skoru,
        zorluk="zor" if zorluk_skoru >= 0.6 else "orta",
        meta=meta or {},
    )


def _seed_secret_notes(user, doc: Dokuman, parca: Parca, *, secret: str) -> None:
    Not.objects.create(
        owner=user,
        dokuman=doc,
        parca=parca,
        adres=parca.adres,
        baslik="Gizli Not",
        metin=f"{secret} not panel response icine girmemeli.",
        not_turu="calisma",
    )
    DokumanNotu.objects.create(
        owner=user,
        dokuman=doc,
        parca=parca,
        adres=f"portal:{parca.id}",
        baslik="Portal Gizli Not",
        icerik=f"{secret} portal note panel response icine girmemeli.",
        not_turu="portal_calisma",
    )


def _metric_event(event_name: str) -> MetrikKaydi:
    return MetrikKaydi.objects.filter(olay_turu=event_name).latest("id")


def test_panel_alias_routes_stay_registered_and_match_canonical_paths():
    for canonical_name, legacy_name, kwargs in PANEL_ROUTE_ALIASES:
        assert reverse(canonical_name, kwargs=kwargs or None) == reverse(legacy_name, kwargs=kwargs or None)


def test_kpi_routes_stay_registered_with_separate_shapes():
    assert reverse("analytics-kpi") == "/api/dokuman-asistani/analytics/kpi/"
    assert reverse("panels-kpi") == "/api/dokuman-asistani/analytics/panels-kpi/"


def test_panels_views_aliases_point_to_canonical_panel_views():
    from dokuman import panels_views, views

    assert panels_views.BossRushPanelView is views.BossRushPanelAPIView
    assert panels_views.ExportReadinessView is views.ExportReadinessPanelAPIView
    assert panels_views.WeeklyGoalProgressView is views.WeeklyProgressPanelAPIView
    assert panels_views.AchievementProgressView is views.AchievementProgressAPIView
    assert panels_views.PersonalizationConfidenceView is views.PersonalizationConfidencePanelAPIView


def test_boss_rush_panel_happy_path_no_leak_shape_and_metric_fields(settings, test_kullanicisi, gecici_media_root):
    settings.DOCVERSE_BOSS_ENABLED = True
    settings.DOCVERSE_BOSS_RUSH_PANEL_ENABLED = True
    settings.DOCVERSE_METRIC_STORE_ENABLED = True
    secret = "HAM_BOSS_PANEL_SECRET"
    doc = _create_doc(test_kullanicisi, title="Boss Panel")
    parca = _create_parca(doc, sira=1, text=secret, zorluk_skoru=0.82, meta={"confusion_map_score": 0.7})
    _create_parca(doc, sira=2, zorluk_skoru=0.78)
    _create_parca(doc, sira=3, zorluk_skoru=0.71)
    _seed_secret_notes(test_kullanicisi, doc, parca, secret=secret)

    response = _client(test_kullanicisi).get(reverse("dokuman-boss-rush-panel", kwargs={"pk": doc.id}))

    assert response.status_code == 200
    assert set(response.data.keys()) == {
        "hazir_mi",
        "hazirlik_skoru",
        "boss_rush_readiness_score",
        "boss_adayi_sayisi",
        "tahmini_boss_rush_suresi_dk",
        "zorluk_bandi",
        "onerilen_baslangic",
    }
    assert response.data["boss_adayi_sayisi"] == 3
    assert 0.0 <= response.data["boss_rush_readiness_score"] <= 1.0
    assert secret not in str(response.data)

    kayit = _metric_event("boss_rush_panel_gosterildi")
    assert kayit.skor_ozeti["boss_rush_readiness_score"] == response.data["boss_rush_readiness_score"]
    assert kayit.skor_ozeti["selection_state"] == "fallback"
    assert kayit.skor_ozeti["candidate_chunk_count"] == 3.0
    assert kayit.skor_ozeti["boss_difficulty_band"] in {"kolay", "orta", "zor"}
    assert kayit.skor_ozeti["boss_rush_state"] in {"ready", "needs_more_coverage", "cooldown", "empty"}
    assert secret not in str(kayit.skor_ozeti)


def test_boss_rush_panel_empty_doc_stays_safe_and_not_ready(settings, test_kullanicisi, gecici_media_root):
    settings.DOCVERSE_BOSS_ENABLED = True
    settings.DOCVERSE_BOSS_RUSH_PANEL_ENABLED = True
    doc = _create_doc(test_kullanicisi, title="Boss Empty")

    response = _client(test_kullanicisi).get(reverse("boss-rush-panel", kwargs={"pk": doc.id}))

    assert response.status_code == 200
    assert response.data["hazir_mi"] is False
    assert response.data["boss_adayi_sayisi"] == 0
    assert response.data["tahmini_boss_rush_suresi_dk"] == 0


def test_boss_rush_panel_flag_off_returns_404(settings, test_kullanicisi, gecici_media_root):
    settings.DOCVERSE_BOSS_ENABLED = True
    settings.DOCVERSE_BOSS_RUSH_PANEL_ENABLED = False
    doc = _create_doc(test_kullanicisi, title="Boss Disabled")

    response = _client(test_kullanicisi).get(reverse("boss-rush-panel", kwargs={"pk": doc.id}))

    assert response.status_code == 404


def test_export_readiness_panel_empty_doc_keeps_shape_and_empty_state(settings, test_kullanicisi, gecici_media_root):
    settings.DOCVERSE_EXPORT_PLAN_ENABLED = True
    settings.DOCVERSE_EXPORT_READINESS_ENABLED = True
    settings.DOCVERSE_METRIC_STORE_ENABLED = True
    doc = _create_doc(test_kullanicisi, title="Export Empty")

    response = _client(test_kullanicisi).get(reverse("dokuman-export-readiness", kwargs={"pk": doc.id}))

    assert response.status_code == 200
    assert set(response.data.keys()) == {
        "pdf_hazirlik",
        "docx_hazirlik",
        "pptx_hazirlik",
        "readme_hazirlik",
        "export_readiness_score",
        "onerilen_format",
        "eksik_bilesenler",
    }
    assert response.data["onerilen_format"] == "yok"
    assert response.data["eksik_bilesenler"] == ["icerik"]

    kayit = _metric_event("export_readiness_panel_gosterildi")
    assert kayit.skor_ozeti["export_readiness_score"] == 0.0
    assert kayit.skor_ozeti["selection_state"] == "fallback"
    assert kayit.skor_ozeti["export_readiness_state"] == "missing_content"
    assert kayit.skor_ozeti["hedef_format"] == "yok"


def test_export_readiness_panel_no_leak_with_low_data(settings, test_kullanicisi, gecici_media_root):
    settings.DOCVERSE_EXPORT_PLAN_ENABLED = True
    settings.DOCVERSE_EXPORT_READINESS_ENABLED = True
    settings.DOCVERSE_METRIC_STORE_ENABLED = True
    doc = _create_doc(test_kullanicisi, title="Export Leak")
    parca = _create_parca(
        doc,
        sira=1,
        text="HAM_EXPORT_PANEL_SECRET",
        meta={"quality_score": 0.2, "heading_score": 0.1},
    )
    _seed_secret_notes(test_kullanicisi, doc, parca, secret="HAM_EXPORT_PANEL_SECRET")

    response = _client(test_kullanicisi).get(reverse("dokuman-export-readiness", kwargs={"pk": doc.id}))

    assert response.status_code == 200
    assert response.data["onerilen_format"] in {"pdf", "docx", "pptx", "readme", "yok"}
    assert "HAM_EXPORT_PANEL_SECRET" not in str(response.data)
    kayit = _metric_event("export_readiness_panel_gosterildi")
    assert "HAM_EXPORT_PANEL_SECRET" not in str(kayit.skor_ozeti)


def test_export_readiness_panel_flag_off_returns_404(settings, test_kullanicisi, gecici_media_root):
    settings.DOCVERSE_EXPORT_PLAN_ENABLED = True
    settings.DOCVERSE_EXPORT_READINESS_ENABLED = False
    doc = _create_doc(test_kullanicisi, title="Export Disabled")

    response = _client(test_kullanicisi).get(reverse("export-readiness", kwargs={"pk": doc.id}))

    assert response.status_code == 404


def test_personalization_panel_new_user_no_leak_shape_and_metric_fields(settings, test_kullanicisi, gecici_media_root):
    settings.DOCVERSE_PERSONALIZATION_ENABLED = True
    settings.DOCVERSE_METRIC_STORE_ENABLED = True
    doc = _create_doc(test_kullanicisi, title="Personalization Doc")
    parca = _create_parca(doc, sira=1, text="HAM_PERSONALIZATION_SECRET")
    _seed_secret_notes(test_kullanicisi, doc, parca, secret="HAM_PERSONALIZATION_SECRET")

    response = _client(test_kullanicisi).get(reverse("profil-personalization-confidence"))

    assert response.status_code == 200
    assert set(response.data.keys()) == {
        "aktif_tema",
        "aktif_ton",
        "onerilen_tema",
        "onerilen_ton",
        "personalization_confidence",
        "personalization_confidence_score",
        "neden_bu_oneri",
    }
    assert response.data["aktif_tema"] == "genel"
    assert "HAM_PERSONALIZATION_SECRET" not in str(response.data)

    kayit = _metric_event("personalization_confidence_gosterildi")
    assert 0.0 <= kayit.skor_ozeti["personalization_confidence_score"] <= 1.0
    assert kayit.skor_ozeti["selection_state"] == "fallback"
    assert kayit.skor_ozeti["personalization_state"] in {"default_profile", "low_data", "custom_profile", "spam_cooldown"}
    assert "HAM_PERSONALIZATION_SECRET" not in str(kayit.skor_ozeti)


def test_personalization_panel_flag_off_returns_404(settings, test_kullanicisi):
    settings.DOCVERSE_PERSONALIZATION_ENABLED = False

    response = _client(test_kullanicisi).get(reverse("personalization-confidence"))

    assert response.status_code == 404


def test_weekly_progress_panel_low_data_repeated_open_and_safe_metric_fields(settings, test_kullanicisi):
    settings.DOCVERSE_METRIC_STORE_ENABLED = True
    settings.DOCVERSE_WEEKLY_PROGRESS_ENABLED = True
    MetrikKaydi.objects.create(
        kullanici=test_kullanicisi,
        olay_turu="mini_quiz_sonuclandi",
        kaynak_modul="test.runtime",
        skor_ozeti={"sonuc_orani": 0.8},
    )

    client = _client(test_kullanicisi)
    first = client.get(reverse("analytics-weekly-progress"))
    second = client.get(reverse("weekly-progress"))

    assert first.status_code == 200
    assert second.status_code == 200
    assert set(first.data.keys()) == {
        "haftalik_gorevler",
        "tamamlanan_gorev_sayisi",
        "tamamlanma_orani",
        "sonraki_rozet",
        "ne_eksik",
        "haftalik_ilerleme_skoru",
        "weekly_goal_progress_score",
    }
    assert 0.0 <= first.data["weekly_goal_progress_score"] <= 1.0
    assert first.data == second.data

    kayit = _metric_event("weekly_progress_panel_gosterildi")
    assert kayit.skor_ozeti["weekly_goal_progress_score"] == first.data["weekly_goal_progress_score"]
    assert kayit.skor_ozeti["selection_state"] == "fallback"
    assert "goal_volume_score" in kayit.skor_ozeti
    assert "development_score" in kayit.skor_ozeti
    assert "variety_score" in kayit.skor_ozeti


def test_weekly_progress_panel_flag_off_returns_404(settings, test_kullanicisi):
    settings.DOCVERSE_METRIC_STORE_ENABLED = True
    settings.DOCVERSE_WEEKLY_PROGRESS_ENABLED = False

    response = _client(test_kullanicisi).get(reverse("weekly-progress"))

    assert response.status_code == 404


def test_weekly_and_achievement_panels_require_metric_store(settings, test_kullanicisi):
    settings.DOCVERSE_METRIC_STORE_ENABLED = False
    settings.DOCVERSE_WEEKLY_PROGRESS_ENABLED = True
    settings.DOCVERSE_ACHIEVEMENT_PROGRESS_ENABLED = True
    client = _client(test_kullanicisi)

    weekly_response = client.get(reverse("analytics-weekly-progress"))
    achievement_response = client.get(reverse("analytics-achievement-progress"))

    assert weekly_response.status_code == 404
    assert achievement_response.status_code == 404


def test_achievement_panel_new_user_shape_no_leak_and_metric_fields(settings, test_kullanicisi, gecici_media_root):
    settings.DOCVERSE_METRIC_STORE_ENABLED = True
    settings.DOCVERSE_ACHIEVEMENT_PROGRESS_ENABLED = True
    doc = _create_doc(test_kullanicisi, title="Achievement Doc")
    parca = _create_parca(doc, sira=1, text="HAM_ACHIEVEMENT_SECRET")
    _seed_secret_notes(test_kullanicisi, doc, parca, secret="HAM_ACHIEVEMENT_SECRET")

    response = _client(test_kullanicisi).get(reverse("analytics-achievement-progress"))

    assert response.status_code == 200
    assert set(response.data.keys()) == {
        "derived_xp",
        "derived_level",
        "active_title",
        "achievements",
        "streak",
        "reward_hint",
        "quiz_count",
        "boss_count",
        "boss_wins",
        "self_check_count",
        "quiz_avg",
        "boss_avg",
        "self_check_avg",
        "achievement_progress_score",
    }
    assert response.data["derived_xp"] == 0
    assert response.data["derived_level"] == 1
    assert "HAM_ACHIEVEMENT_SECRET" not in str(response.data)

    kayit = _metric_event("achievement_panel_gosterildi")
    assert kayit.skor_ozeti["achievement_progress_score"] == response.data["achievement_progress_score"]
    assert kayit.skor_ozeti["selection_state"] == "fallback"
    assert kayit.skor_ozeti["achievement_state"] == "new_user"
    assert "unlock_reason_code" in kayit.skor_ozeti
    assert "HAM_ACHIEVEMENT_SECRET" not in str(kayit.skor_ozeti)


def test_achievement_panel_flag_off_returns_404(settings, test_kullanicisi):
    settings.DOCVERSE_METRIC_STORE_ENABLED = True
    settings.DOCVERSE_ACHIEVEMENT_PROGRESS_ENABLED = False

    response = _client(test_kullanicisi).get(reverse("achievement-progress"))

    assert response.status_code == 404


def test_panels_kpi_returns_stable_shape_and_no_leak(settings, test_kullanicisi, gecici_media_root):
    settings.DOCVERSE_METRIC_STORE_ENABLED = True
    settings.DOCVERSE_BOSS_ENABLED = True
    settings.DOCVERSE_BOSS_RUSH_PANEL_ENABLED = True
    settings.DOCVERSE_EXPORT_PLAN_ENABLED = True
    settings.DOCVERSE_EXPORT_READINESS_ENABLED = True
    settings.DOCVERSE_PERSONALIZATION_ENABLED = True
    doc = _create_doc(test_kullanicisi, title="KPI Doc")
    parca = _create_parca(doc, sira=1, text="HAM_KPI_SECRET", zorluk_skoru=0.82, meta={"quality_score": 0.9, "heading_score": 0.8})
    _seed_secret_notes(test_kullanicisi, doc, parca, secret="HAM_KPI_SECRET")

    response = _client(test_kullanicisi).get(reverse("panels-kpi"))

    assert response.status_code == 200
    assert set(response.data.keys()) == {
        "boss_rush_ready_ratio",
        "weekly_goal_completion_avg",
        "achievement_progress_avg",
        "export_readiness_avg",
        "personalization_confidence_avg",
    }
    assert "HAM_KPI_SECRET" not in str(response.data)


def test_panels_kpi_flag_off_returns_404(settings, test_kullanicisi):
    settings.DOCVERSE_METRIC_STORE_ENABLED = False

    response = _client(test_kullanicisi).get(reverse("panels-kpi"))

    assert response.status_code == 404


def test_analytics_kpi_legacy_shape_stays_compatible(settings, test_kullanicisi):
    settings.DOCVERSE_METRIC_STORE_ENABLED = True

    response = _client(test_kullanicisi).get(reverse("analytics-kpi"))

    assert response.status_code == 200
    assert set(response.data.keys()) == {
        "net_usefulness_score",
        "global_confusion_index",
        "feedback_trust_ratio",
        "cheatsheet_yield",
    }


def test_personalization_helper_keeps_shape_with_invalid_preference_values(settings, test_kullanicisi):
    settings.DOCVERSE_PANEL_SCORE_OVERRIDES = {"personalization_confidence_score": "not-a-number"}
    KullaniciTercih.objects.create(
        kullanici=test_kullanicisi,
        tema="HAM_THEME_SECRET",
        ton="HAM_TONE_SECRET",
    )

    payload = product_panels.build_personalization_confidence_payload(test_kullanicisi)

    assert payload["aktif_tema"] == "genel"
    assert payload["aktif_ton"] == "teknik"
    assert 0.0 <= payload["personalization_confidence_score"] <= 1.0
    assert payload["_meta"]["selection_state"] == "override"
    assert payload["_meta"]["personalization_state"] in {"default_profile", "low_data", "spam_cooldown"}


def test_boss_panel_score_hook_error_falls_back_safely(settings, test_kullanicisi, gecici_media_root):
    settings.DOCVERSE_PANEL_SCORE_HOOKS = {
        "boss_rush_readiness_score": lambda **kwargs: (_ for _ in ()).throw(RuntimeError("hook failed")),
    }
    doc = _create_doc(test_kullanicisi, title="Boss Hook")
    _create_parca(doc, sira=1, zorluk_skoru=0.61)
    _create_parca(doc, sira=2, zorluk_skoru=0.62)

    payload = product_panels.build_boss_rush_panel_payload(doc)

    assert 0.0 <= payload["boss_rush_readiness_score"] <= 1.0
    assert payload["boss_rush_readiness_score"] == payload["hazirlik_skoru"]
    assert payload["_meta"]["selection_state"] == "hook"


def test_panel_score_hook_contracts_stay_stable():
    assert product_panels.get_panel_score_hook_contracts() == {
        "boss_rush_readiness_score": {
            "context_fields": ["doc_id", "boss_adayi_sayisi", "ortalama_zorluk", "legacy_score"],
            "fallback_mode": "legacy_payload_score",
            "response_fields": ["hazirlik_skoru", "boss_rush_readiness_score"],
        },
        "weekly_goal_progress_score": {
            "context_fields": ["quiz_sayisi", "boss_sayisi", "ozet_sayisi", "tamamlanan_gorev_sayisi", "legacy_score"],
            "fallback_mode": "legacy_payload_score",
            "response_fields": ["tamamlanma_orani", "haftalik_ilerleme_skoru", "weekly_goal_progress_score"],
        },
        "achievement_progress_score": {
            "context_fields": ["derived_xp", "derived_level", "quiz_count", "boss_count", "boss_wins", "self_check_count", "legacy_score"],
            "fallback_mode": "latest_metric_score",
            "response_fields": ["achievement_progress_score"],
        },
        "export_readiness_score": {
            "context_fields": ["doc_id", "chunk_count", "avg_quality", "avg_heading", "table_count", "code_count", "legacy_score", "onerilen_format"],
            "fallback_mode": "legacy_payload_score",
            "response_fields": ["export_readiness_score"],
        },
        "personalization_confidence_score": {
            "context_fields": ["aktif_tema", "aktif_ton", "is_default", "legacy_score"],
            "fallback_mode": "legacy_payload_score",
            "response_fields": ["personalization_confidence", "personalization_confidence_score"],
        },
    }
