from __future__ import annotations

from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import AnlamadimKaydi, Dokuman, MetrikKaydi, Parca


def _make_doc(user, *, title: str = "Concept Fusion"):
    doc = Dokuman.objects.create(
        owner=user,
        baslik=title,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("concept-fusion.pdf", ContentFile(b"ornek"), save=True)
    parca1 = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="JWT access token tarafinda kimlik tasir. HAM_FUSION_SECRET bu metinden sizmamali.",
        meta={"quality_score": 0.83},
        zorluk="orta",
        zorluk_skoru=0.56,
    )
    parca2 = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="1.2",
        metin="Refresh Token yeni access token uretimini ve oturum surekliligini destekler.",
        meta={"quality_score": 0.8},
        zorluk="zor",
        zorluk_skoru=0.66,
    )
    AnlamadimKaydi.objects.create(
        kullanici=user,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        cikti_json={
            "glossary": [
                {"terim": "JWT", "tanim": "Kimlik bilgisini tasiyan token."},
                {"terim": "Refresh Token", "tanim": "Yeni access token almak icin kullanilan token."},
            ]
        },
    )
    return doc, parca1, parca2


def test_concept_fusion_endpoint_calisir_ve_sade_payload_doner(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, _, _ = _make_doc(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        f"/api/dokuman-asistani/dokumanlar/{doc.id}/concepts/fusion/",
        {"kavram_a": "JWT", "kavram_b": "Refresh Token"},
        format="json",
    )

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "dokuman_id",
        "kavram_a",
        "kavram_b",
        "ortak_yonler",
        "farklar",
        "birlikte_kullanim_ornegi",
        "mini_soru",
    }
    assert data["kavram_a"] == "JWT"
    assert data["kavram_b"] == "Refresh Token"
    assert len(data["ortak_yonler"]) >= 1
    assert len(data["farklar"]) >= 1
    assert "HAM_FUSION_SECRET" not in str(data)

    kayit = MetrikKaydi.objects.filter(olay_turu="concept_fusion_uretildi").latest("id")
    assert "HAM_FUSION_SECRET" not in str(kayit.skor_ozeti)


def test_concept_fusion_flag_kapaliyken_kontrollu_davranir(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    doc, _, _ = _make_doc(test_kullanicisi, title="Concept Fusion Flag")
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    settings.DOCVERSE_FUSION_ENABLED = False
    response = client.post(
        f"/api/dokuman-asistani/dokumanlar/{doc.id}/concepts/fusion/",
        {"kavram_a": "JWT", "kavram_b": "Refresh Token"},
        format="json",
    )

    assert response.status_code == 404
