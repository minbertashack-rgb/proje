from __future__ import annotations

import json

from django.core.files.base import ContentFile
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from dokuman.models import Dokuman, MetrikKaydi, Parca
from dokuman.services.metric_store import compute_mastery_score, compute_quiz_readiness_score, kaydet_skor_olayi
from dokuman.views_ai2 import AnlamadimAI2APIView


def _anlamadim_ai2_post(user, parca_id: int, payload: dict):
    factory = APIRequestFactory()
    request = factory.post(
        f"/api/dokuman-asistani/ai2/parcalar/{parca_id}/anlamadim/",
        payload,
        format="json",
    )
    force_authenticate(request, user=user)
    response = AnlamadimAI2APIView.as_view()(request, parca_id=parca_id)
    response.render()
    return response


def _create_doc(user, *, title: str = "Quiz Runtime"):
    doc = Dokuman.objects.create(
        owner=user,
        baslik=title,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save(f"{title.lower().replace(' ', '-')}.pdf", ContentFile(b"ornek"), save=True)
    return doc


def test_quiz_readiness_score_hesaplanabilir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = _create_doc(test_kullanicisi, title="Quiz Readiness")
    iyi = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="JWT exp=3600 ve refresh token akisinda access token yenilenir; aud=api bilgisi dogrulamayi etkiler.",
        meta={"quality_score": 0.88, "difficulty_score": 0.66},
        zorluk_skoru=0.66,
    )
    zayif = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="1.2",
        metin="Not.",
        meta={"quality_score": 0.12, "difficulty_score": 0.08, "weak_content": True},
        zorluk_skoru=0.08,
    )

    iyi_meta = compute_quiz_readiness_score(parca=iyi)
    zayif_meta = compute_quiz_readiness_score(parca=zayif)

    assert 0.0 <= iyi_meta["quiz_readiness_score"] <= 1.0
    assert 0.0 <= zayif_meta["quiz_readiness_score"] <= 1.0
    assert iyi_meta["quiz_readiness_score"] > zayif_meta["quiz_readiness_score"]
    assert iyi_meta["quiz_eligible"] is True
    assert zayif_meta["quiz_eligible"] is False


def test_quiz_uygun_parcada_uretim_ve_metric_gating_calisir(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _create_doc(test_kullanicisi, title="Quiz Eligible")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="2.1",
        metin="JWT exp=3600 ve refresh token ile yeni access token alma akisi API istemcisinde dogrulama icin kullanilir.",
        meta={"quality_score": 0.91, "difficulty_score": 0.64},
        zorluk_skoru=0.64,
    )

    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: json.dumps(
            {
                "one_liner": "JWT suresi dolunca refresh token ile yenileme yapilir.",
                "very_simple": "Sistem eski token bitince yeni token verir.",
                "glossary": [{"terim": "JWT", "tanim": "Kimlik tasiyan token yapisidir."}],
                "steps": ["Token gonderilir.", "Sure dolunca refresh token devreye girer."],
                "examples": ["Mobil uygulama API cagirirken bu akis kullanilir."],
                "trap": "Access token ile refresh tokeni ayni gorevde sanmaktir.",
                "mini_quiz": [
                    {"q": "JWT ne zaman yenilenir?", "a": "Sure dolunca."},
                    {"q": "Refresh token ne yapar?", "a": "Yeni access token alir."},
                    {"q": "Tuzak nedir?", "a": "Iki tokeni ayni sanmaktir."},
                ],
            },
            ensure_ascii=False,
        ),
    )

    response = _anlamadim_ai2_post(test_kullanicisi, parca.id, {"tema": "teknoloji"})

    assert response.status_code == 200
    assert len(response.data["mini_test"]) == 3
    hazirlik = MetrikKaydi.objects.get(olay_turu="quiz_hazirlik_hesaplandi")
    uretilen = MetrikKaydi.objects.get(olay_turu="mini_quiz_uretildi")
    assert hazirlik.skor_ozeti["quiz_eligible"] is True
    assert uretilen.skor_ozeti["toplam_soru"] == 3


def test_mini_quiz_sonucu_metric_store_ve_mastery_sinyali_uretir(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _create_doc(test_kullanicisi, title="Quiz Result")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="3.1",
        metin="JWT token akisi ve dogrulama mantigi.",
        meta={"quality_score": 0.78, "difficulty_score": 0.58},
        zorluk_skoru=0.58,
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    monkeypatch.setattr(
        "dokuman.views_ai2.enqueue_quiz_acceptance_event",
        lambda **kwargs: kaydet_skor_olayi(
            kullanici=kwargs["user"],
            olay_turu="quiz_accepted",
            kaynak_modul="test.sync",
            dokuman=getattr(kwargs["parca"], "dokuman", None),
            parca=kwargs["parca"],
            score_map={
                "dogru_sayisi": kwargs["dogru_sayisi"],
                "toplam_soru": kwargs["toplam_soru"],
                "sonuc_orani": kwargs["sonuc_orani"],
            },
        ),
    )

    response = client.post(
        f"/api/dokuman-asistani/ai2/parcalar/{parca.id}/mini-quiz-sonuc/",
        {"dogru_sayisi": 2, "toplam_soru": 3},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["sonuc_orani"] == 0.6667
    kayit = MetrikKaydi.objects.get(olay_turu="mini_quiz_sonuclandi")
    assert kayit.skor_ozeti["dogru_sayisi"] == 2
    assert kayit.skor_ozeti["toplam_soru"] == 3
    assert "JWT token akisi" not in str(kayit.skor_ozeti)
    assert MetrikKaydi.objects.filter(olay_turu="quiz_accepted").exists()
    assert MetrikKaydi.objects.filter(olay_turu="mastery_delta_hesaplandi").exists()
    assert MetrikKaydi.objects.filter(olay_turu="confusion_recovery_hesaplandi").exists()

    mastery = compute_mastery_score(user=test_kullanicisi, dokuman=doc)
    assert mastery["mastery_quiz_success_ratio"] >= 0.6


def test_quiz_feature_flag_kapaliyken_kontrollu_davranis_korunur(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_QUIZ_ENABLED = False
    doc = _create_doc(test_kullanicisi, title="Quiz Flag Off")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="4.1",
        metin="JWT token akisi.",
        meta={"quality_score": 0.88, "difficulty_score": 0.62},
        zorluk_skoru=0.62,
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        f"/api/dokuman-asistani/ai2/parcalar/{parca.id}/mini-quiz-sonuc/",
        {"dogru_sayisi": 1, "toplam_soru": 1},
        format="json",
    )

    assert response.status_code == 404
