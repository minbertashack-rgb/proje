from __future__ import annotations

from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import AnlamadimKaydi, Dokuman, MetrikKaydi, Parca
from dokuman.services.metric_store import kaydet_skor_olayi


def _create_doc(user, *, title: str = "Escape Room Runtime"):
    doc = Dokuman.objects.create(
        owner=user,
        baslik=title,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("escape-room-runtime.pdf", ContentFile(b"ornek"), save=True)
    return doc


def test_escape_room_payloadi_uretilir_ve_guvenli_metric_yazar(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = _create_doc(test_kullanicisi)
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="JWT access token kullanicinin kimligini tasir. Refresh Token yeni access token alinmasini saglar.",
        meta={"quality_score": 0.87, "difficulty_score": 0.58},
        zorluk_skoru=0.58,
    )
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc,
        parca=parca,
        adres=parca.adres,
        cikti_json={
            "glossary": [
                {"terim": "JWT", "tanim": "Kimlik tokeni."},
                {"terim": "Refresh Token", "tanim": "Yeni access token verir."},
                {"terim": "Access Token", "tanim": "API erisim belirteci."},
            ]
        },
    )
    kaydet_skor_olayi(
        kullanici=test_kullanicisi,
        olay_turu="self_check_calistirildi",
        kaynak_modul="test.self_check",
        dokuman=doc,
        parca=parca,
        score_map={"self_check_score": 0.72},
    )
    kaydet_skor_olayi(
        kullanici=test_kullanicisi,
        olay_turu="mini_quiz_sonuclandi",
        kaynak_modul="test.quiz",
        dokuman=doc,
        parca=parca,
        score_map={"sonuc_orani": 0.67, "dogru_sayisi": 2, "toplam_soru": 3},
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/escape-room/")

    assert response.status_code == 200
    assert set(response.data.keys()) == {"dokuman_id", "hedef_kavramlar", "gereken_adimlar", "ilerleme_durumu", "tamamlandi_mi"}
    assert response.data["dokuman_id"] == doc.id
    assert len(response.data["hedef_kavramlar"]) >= 2
    assert response.data["ilerleme_durumu"]["toplam_adim"] == 3

    kayit = MetrikKaydi.objects.filter(olay_turu="escape_room_basladi").latest("id")
    assert "Refresh Token yeni access token" not in str(kayit.skor_ozeti)
    assert "escape_progress_score" in kayit.skor_ozeti


def test_escape_room_tamamlanma_olayi_yazilir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = _create_doc(test_kullanicisi, title="Escape Room Complete")
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="2.1",
        metin="OAuth token rotation ve replay attack korunumu aciklanir.",
        meta={"quality_score": 0.89, "difficulty_score": 0.68},
        zorluk_skoru=0.68,
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        f"/api/dokuman-asistani/dokumanlar/{doc.id}/escape-room/",
        {"tamamlandi_mi": True, "tamamlanan_adim_sayisi": 3},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["tamamlandi_mi"] is True
    kayit = MetrikKaydi.objects.filter(olay_turu="escape_room_tamamlandi").latest("id")
    assert kayit.skor_ozeti["escape_status"] == "completed"


def test_escape_room_flag_kapaliyken_kontrollu_404_doner(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_ESCAPE_ROOM_ENABLED = False
    doc = _create_doc(test_kullanicisi, title="Escape Room Flag")
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/escape-room/")

    assert response.status_code == 404
