from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import Dokuman, MetrikKaydi, Parca
from dokuman.services.metric_store import kaydet_skor_olayi


def _create_doc(user, *, title: str = "Learning Runtime"):
    doc = Dokuman.objects.create(
        owner=user,
        baslik=title,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save(f"{title.lower().replace(' ', '-')}.pdf", ContentFile(b"ornek"), save=True)
    return doc


def test_quiz_readiness_endpoint_uses_runtime_formula_and_cooldown(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_QUIZ_ENABLED = True
    cache.clear()
    doc = _create_doc(test_kullanicisi, title="Quiz Readiness Runtime")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="JWT exp=3600, refresh token rotation ve replay attack korunumu ayni akista anlatilir.",
        meta={"quality_score": 0.92, "difficulty_score": 0.74},
        zorluk_skoru=0.74,
    )
    kaydet_skor_olayi(
        kullanici=test_kullanicisi,
        olay_turu="ai2_cevap_degerlendirildi",
        kaynak_modul="test",
        dokuman=doc,
        parca=parca,
        score_map={"usefulness_score_v2": 0.92},
    )
    kaydet_skor_olayi(
        kullanici=test_kullanicisi,
        olay_turu="ai2_anlamadim_degerlendirildi",
        kaynak_modul="test",
        dokuman=doc,
        parca=parca,
        score_map={"completeness_score": 0.93},
    )
    kaydet_skor_olayi(
        kullanici=test_kullanicisi,
        olay_turu="mini_quiz_sonuclandi",
        kaynak_modul="test",
        dokuman=doc,
        parca=parca,
        score_map={"dogru_sayisi": 3, "toplam_soru": 3, "sonuc_orani": 1.0},
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    first = client.post(
        "/api/dokuman-asistani/quiz/readiness/",
        {
            "parca_id": parca.id,
            "observed_read_seconds": 120,
            "expected_read_seconds": 60,
            "note_count": 3,
        },
        format="json",
    )
    second = client.post(
        "/api/dokuman-asistani/quiz/readiness/",
        {
            "parca_id": parca.id,
            "observed_read_seconds": 120,
            "expected_read_seconds": 60,
            "note_count": 3,
            "quiz_action": "dismissed",
        },
        format="json",
    )

    assert first.status_code == 200
    assert first.data["show_quiz_prompt"] is True
    assert first.data["quiz_readiness_score"] > 0.75
    assert second.status_code == 200
    assert second.data["show_quiz_prompt"] is False
    assert second.data["cooldown_factor"] < 1.0
    assert MetrikKaydi.objects.filter(olay_turu="quiz_prompted").exists()


def test_learning_kpi_endpoint_aggregates_learning_events(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = _create_doc(test_kullanicisi, title="Learning KPI")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="2.1",
        metin="OAuth nonce ve refresh token rotation konu ozeti.",
    )
    other_user = get_user_model().objects.create_user(username="kpi_user_2", password="test12345")

    for user, delta in [(test_kullanicisi, 0.22), (other_user, 0.18)]:
        kaydet_skor_olayi(
            kullanici=user,
            olay_turu="mastery_delta_hesaplandi",
            kaynak_modul="test",
            dokuman=doc,
            parca=parca,
            score_map={"mastery_progress_delta": delta},
        )

    kaydet_skor_olayi(
        kullanici=test_kullanicisi,
        olay_turu="boss_baslatildi",
        kaynak_modul="test",
        dokuman=doc,
        parca=parca,
        score_map={"boss_difficulty_score": 0.61, "boss_difficulty_band": "medium"},
    )
    kaydet_skor_olayi(
        kullanici=test_kullanicisi,
        olay_turu="boss_deneme_tamamlandi",
        kaynak_modul="test",
        dokuman=doc,
        parca=parca,
        score_map={
            "dogru_sayisi": 3,
            "toplam_soru": 3,
            "sonuc_orani": 1.0,
            "boss_progress_score": 1.0,
            "boss_outcome": "boss_defeated",
        },
    )
    kaydet_skor_olayi(
        kullanici=test_kullanicisi,
        olay_turu="confusion_recovery_hesaplandi",
        kaynak_modul="test",
        dokuman=doc,
        parca=parca,
        score_map={
            "confusion_map_score": 0.91,
            "confusion_recovery_score": 0.91,
            "eureka_triggered": True,
        },
    )
    kaydet_skor_olayi(
        kullanici=test_kullanicisi,
        olay_turu="quiz_prompted",
        kaynak_modul="test",
        dokuman=doc,
        parca=parca,
        score_map={"quiz_readiness_score": 0.88, "show_quiz_prompt": True},
    )
    kaydet_skor_olayi(
        kullanici=test_kullanicisi,
        olay_turu="quiz_prompted",
        kaynak_modul="test",
        dokuman=doc,
        parca=parca,
        score_map={"quiz_readiness_score": 0.81, "show_quiz_prompt": True},
    )
    kaydet_skor_olayi(
        kullanici=test_kullanicisi,
        olay_turu="quiz_accepted",
        kaynak_modul="test",
        dokuman=doc,
        parca=parca,
        score_map={"dogru_sayisi": 2, "toplam_soru": 3, "sonuc_orani": 0.6667},
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/analytics/learning-kpi/?days=30")

    assert response.status_code == 200
    assert response.data["boss_win_rate"] == 1.0
    assert response.data["confusion_recovery_rate"] == 1.0
    assert response.data["quiz_engagement_ratio"] == 0.5
    assert response.data["platform_momentum_index"] > 0.0


def test_boss_answer_control_injects_difficulty_and_records_progress(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _create_doc(test_kullanicisi, title="Boss Prompt Injection")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="3.1",
        metin="Replay attack, nonce ve token rotation mekanigi.",
        meta={"difficulty_score": 0.84, "quality_score": 0.90},
        zorluk_skoru=0.84,
    )
    kaydet_skor_olayi(
        kullanici=test_kullanicisi,
        olay_turu="ai2_cevap_degerlendirildi",
        kaynak_modul="test",
        dokuman=doc,
        parca=parca,
        score_map={"usefulness_score_v2": 0.92},
    )
    kaydet_skor_olayi(
        kullanici=test_kullanicisi,
        olay_turu="ai2_anlamadim_degerlendirildi",
        kaynak_modul="test",
        dokuman=doc,
        parca=parca,
        score_map={"completeness_score": 0.9},
    )
    kaydet_skor_olayi(
        kullanici=test_kullanicisi,
        olay_turu="mastery_delta_hesaplandi",
        kaynak_modul="test",
        dokuman=doc,
        parca=parca,
        score_map={"mastery_progress_delta": 0.24},
    )

    def _fake_chat(messages, max_tokens=256):
        assert "BOSS ZORLUK BAGLAMI" in messages[0]["content"]
        return json.dumps(
            {
                "puan": 92,
                "dogru_kisimlar": ["Ana fikir dogru."],
                "yanlislar": [],
                "eksikler": [],
                "geri_bildirim": "Cevap yeterince net.",
            }
        )

    monkeypatch.setattr("dokuman.views.chat", _fake_chat)

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.post(
        f"/api/dokuman-asistani/parcalar/{parca.id}/boss-cevap-kontrol/",
        {"gorev": "Ana fikri acikla.", "yanit": "Replay attack tekrar gonderimi ile ilgilidir."},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["boss_progress_score"] >= 0.85
    assert response.data["boss_outcome"] == "boss_defeated"
    assert response.data["boss_difficulty"]["boss_difficulty_band"] in {"medium", "hard"}
    assert MetrikKaydi.objects.filter(olay_turu="boss_baslatildi").exists()
    assert MetrikKaydi.objects.filter(olay_turu="boss_deneme_tamamlandi").exists()
    assert MetrikKaydi.objects.filter(olay_turu="mastery_delta_hesaplandi").exists()
    assert "Replay attack" not in str(MetrikKaydi.objects.get(olay_turu="boss_deneme_tamamlandi").skor_ozeti)


def test_learning_runtime_feature_flags_controlled_when_disabled(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_QUIZ_ENABLED = False
    settings.DOCVERSE_METRIC_STORE_ENABLED = False
    doc = _create_doc(test_kullanicisi, title="Runtime Flags")
    parca = Parca.objects.create(dokuman=doc, sira=1, tur="bolum", adres="4.1", metin="Kisa ama teknik icerik.")

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    readiness = client.post(
        "/api/dokuman-asistani/quiz/readiness/",
        {"parca_id": parca.id, "read_ratio": 1.0, "note_count": 1},
        format="json",
    )
    learning_kpi = client.get("/api/dokuman-asistani/analytics/learning-kpi/")

    assert readiness.status_code == 404
    assert learning_kpi.status_code == 404
