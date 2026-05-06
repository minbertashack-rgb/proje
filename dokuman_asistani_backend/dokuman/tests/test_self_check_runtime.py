from __future__ import annotations

from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import AnlamadimKaydi, Dokuman, MetrikKaydi, Parca


def _make_doc(user, *, title: str = "Self Check Runtime"):
    doc = Dokuman.objects.create(
        owner=user,
        baslik=title,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("self-check.pdf", ContentFile(b"ornek"), save=True)
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="JWT access token kullanicinin kimligini tasir. Refresh Token yeni access token alinmasini saglar.",
        meta={"quality_score": 0.86},
        zorluk="orta",
        zorluk_skoru=0.51,
    )
    AnlamadimKaydi.objects.create(
        kullanici=user,
        dokuman=doc,
        parca=parca,
        adres=parca.adres,
        cikti_json={
            "glossary": [
                {"terim": "JWT", "tanim": "Kimlik bilgisini tasiyan token."},
                {"terim": "Refresh Token", "tanim": "Yeni access token almak icin kullanilan token."},
            ]
        },
    )
    return doc, parca


def test_self_check_endpoint_calisir_ve_dogru_eksik_ayrimi_yapar(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    _, parca = _make_doc(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        f"/api/dokuman-asistani/parcalar/{parca.id}/self-check/",
        {"kullanici_aciklamasi": "JWT kullanicinin kimligini tasir."},
        format="json",
    )

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {"dogru_noktalar", "duzeltilecek_noktalar", "eksik_noktalar", "self_check_score"}
    assert data["self_check_score"] > 0.2
    assert any("JWT" in item for item in data["dogru_noktalar"])
    assert any("Refresh Token" in item for item in data["eksik_noktalar"])


def test_self_check_yanlis_ve_uydurma_kavrami_isaretler_metricte_ham_yazi_tutmaz(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    _, parca = _make_doc(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    gizli = "SELFCHECK_SECRET"

    response = client.post(
        f"/api/dokuman-asistani/parcalar/{parca.id}/self-check/",
        {"kullanici_aciklamasi": f"{gizli} OAuth Scope JWT ile ayni sey ve her zaman kullanilir."},
        format="json",
    )

    assert response.status_code == 200
    data = response.data
    assert data["self_check_score"] < 0.5
    assert any("OAuth" in item for item in data["duzeltilecek_noktalar"])
    assert any("Refresh Token" in item for item in data["eksik_noktalar"])
    assert gizli not in str(data)

    kayit = MetrikKaydi.objects.filter(olay_turu="self_check_calistirildi").latest("id")
    assert gizli not in str(kayit.skor_ozeti)
    assert "OAuth Scope" not in str(kayit.skor_ozeti)


def test_self_check_flag_kapaliyken_kontrollu_404_doner(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    _, parca = _make_doc(test_kullanicisi, title="Self Check Flag")
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    settings.DOCVERSE_SELF_CHECK_ENABLED = False
    response = client.post(
        f"/api/dokuman-asistani/parcalar/{parca.id}/self-check/",
        {"kullanici_aciklamasi": "JWT kimlik tasir."},
        format="json",
    )

    assert response.status_code == 404
