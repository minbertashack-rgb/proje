from __future__ import annotations

from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import AnlamadimKaydi, Dokuman, MetrikKaydi, Parca


def _create_doc(user, *, title: str = "Speedrun Runtime"):
    doc = Dokuman.objects.create(
        owner=user,
        baslik=title,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("speedrun-runtime.pdf", ContentFile(b"ornek"), save=True)
    return doc


def test_speedrun_payloadi_uretilir_ve_sade_kalir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = _create_doc(test_kullanicisi)
    secret = "HAM_SPEEDRUN_SECRET"
    parca1 = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin=f"JWT access token kullanicinin kimligini tasir. Refresh Token yeni access token alinmasini saglar. {secret}",
        meta={"quality_score": 0.9, "difficulty_score": 0.61},
        zorluk_skoru=0.61,
    )
    parca2 = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="1.2",
        metin="Nonce degeri replay attack riskini azaltir. Token rotation session guvenligini artirir.",
        meta={"quality_score": 0.88, "difficulty_score": 0.67},
        zorluk_skoru=0.67,
    )
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        cikti_json={"glossary": [{"terim": "JWT", "tanim": "Kimlik tokeni."}]},
    )
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc,
        parca=parca2,
        adres=parca2.adres,
        cikti_json={"glossary": [{"terim": "Nonce", "tanim": "Tek seferlik deger."}]},
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/speedrun/")

    assert response.status_code == 200
    assert set(response.data.keys()) == {"dokuman_id", "en_onemli_cumleler", "mini_quiz", "yanlis_tamir_adimi", "hedef_sure_saniye"}
    assert response.data["dokuman_id"] == doc.id
    assert len(response.data["en_onemli_cumleler"]) >= 1
    assert len(response.data["mini_quiz"]) >= 1
    assert 180 <= response.data["hedef_sure_saniye"] <= 360

    kayit = MetrikKaydi.objects.filter(olay_turu="speedrun_uretildi").latest("id")
    assert secret not in str(kayit.skor_ozeti)
    assert "speedrun_target_seconds" in kayit.skor_ozeti


def test_speedrun_tamamlanma_olayi_guvenli_yazilir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = _create_doc(test_kullanicisi, title="Speedrun Complete")
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="2.1",
        metin="JWT access token ve refresh token akisinin ozeti.",
        meta={"quality_score": 0.82, "difficulty_score": 0.54},
        zorluk_skoru=0.54,
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        f"/api/dokuman-asistani/dokumanlar/{doc.id}/speedrun/",
        {"dogru_sayisi": 2, "toplam_soru": 3, "hedef_sure_saniye": 240},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["tamamlandi_mi"] is True
    assert response.data["sonuc_orani"] == 0.6667

    kayit = MetrikKaydi.objects.filter(olay_turu="speedrun_tamamlandi").latest("id")
    assert kayit.skor_ozeti["dogru_sayisi"] == 2
    assert kayit.skor_ozeti["speedrun_status"] == "completed"
    assert "refresh token akisinin ozeti" not in str(kayit.skor_ozeti)


def test_speedrun_flag_kapaliyken_kontrollu_404_doner(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_SPEEDRUN_ENABLED = False
    doc = _create_doc(test_kullanicisi, title="Speedrun Flag")
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/speedrun/")

    assert response.status_code == 404
