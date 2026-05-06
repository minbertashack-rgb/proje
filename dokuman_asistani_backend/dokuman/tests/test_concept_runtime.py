from __future__ import annotations

from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import AnlamadimKaydi, Dokuman, MetrikKaydi, Parca
from dokuman.services.concept_runtime import compute_concept_candidates


def _make_doc(user, *, title: str = "Concept Runtime"):
    doc = Dokuman.objects.create(
        owner=user,
        baslik=title,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("concept-runtime.pdf", ContentFile(b"ornek"), save=True)
    parca1 = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="JWT access token, kullanicinin kimligini tasir. HAM_CONCEPT_SECRET metne sizmamali.",
        meta={"quality_score": 0.82},
        zorluk="orta",
        zorluk_skoru=0.48,
    )
    parca2 = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="1.2",
        metin="Refresh Token yeni access token uretiminde kullanilir. Refresh Token akis kontrolu saglar.",
        meta={"quality_score": 0.78},
        zorluk="zor",
        zorluk_skoru=0.71,
    )
    Parca.objects.create(
        dokuman=doc,
        sira=3,
        tur="bolum",
        adres="1.3",
        metin="GHOSTTERM yalnizca zayif icerikte geciyor.",
        meta={"weak_content": True, "quality_score": 0.12},
        zorluk="kolay",
        zorluk_skoru=0.11,
    )
    return doc, parca1, parca2


def _add_glossary(user, doc, parca):
    return AnlamadimKaydi.objects.create(
        kullanici=user,
        dokuman=doc,
        parca=parca,
        adres=parca.adres,
        cikti_json={
            "glossary": [
                {"terim": "JWT", "tanim": "JSON Web Token kimlik bilgisini tasir."},
                {"terim": "Refresh Token", "tanim": "Yeni access token alinmasini saglar."},
            ]
        },
    )


def test_kavram_adaylari_deterministik_ve_weak_content_duyarli_uretilir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _make_doc(test_kullanicisi)
    _add_glossary(test_kullanicisi, doc, parca1)

    kavramlar = compute_concept_candidates(doc=doc, user=test_kullanicisi, limit=8)

    isimler = {item["kavram"] for item in kavramlar}
    assert "JWT" in isimler
    assert "Refresh Token" in isimler
    assert "GHOSTTERM" not in isimler
    assert all(set(item.keys()) == {"kavram", "kaynak_parca_idleri", "gecme_sayisi", "kisa_tanim"} for item in kavramlar)


def test_weak_only_tekrarlanan_tokenlar_kavram_adayi_olmaz(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, _, _ = _make_doc(test_kullanicisi, title="Weak Only Concepts")
    Parca.objects.create(
        dokuman=doc,
        sira=4,
        tur="bolum",
        adres="1.4",
        metin="GHOSTTERM yalnizca zayif bir OCR benzeri parcada tekrar ediyor.",
        meta={"weak_content": True, "quality_score": 0.15},
        zorluk="kolay",
        zorluk_skoru=0.12,
    )

    kavramlar = compute_concept_candidates(doc=doc, user=test_kullanicisi, limit=12)

    isimler = {item["kavram"] for item in kavramlar}
    assert "GHOSTTERM" not in isimler


def test_concept_surface_ve_detail_guvenli_payload_doner_ve_metric_store_ham_yazmaz(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _make_doc(test_kullanicisi, title="Concept Surface")
    _add_glossary(test_kullanicisi, doc, parca1)

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response_surface = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/concepts/")
    response_detail = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/concepts/detail/?kavram=JWT")

    assert response_surface.status_code == 200
    assert response_detail.status_code == 200

    surface = response_surface.data
    detail = response_detail.data
    assert set(surface.keys()) == {"dokuman_id", "toplam_kavram", "kavramlar"}
    assert surface["dokuman_id"] == doc.id
    assert surface["toplam_kavram"] >= 2
    assert set(detail.keys()) == {"dokuman_id", "kavram", "kisa_tanim", "bagli_parca_idleri", "ornek_gecis_sayisi"}
    assert detail["kavram"] == "JWT"
    assert detail["ornek_gecis_sayisi"] >= 1
    assert "HAM_CONCEPT_SECRET" not in str(surface)
    assert "HAM_CONCEPT_SECRET" not in str(detail)

    kayitlar = MetrikKaydi.objects.filter(olay_turu__in=["concept_surface_goruntulendi", "concept_detail_uretildi"]).order_by("id")
    assert kayitlar.count() == 2
    for kayit in kayitlar:
        assert "HAM_CONCEPT_SECRET" not in str(kayit.skor_ozeti)


def test_concept_flag_kapaliyken_kontrollu_davranis_korunur(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    doc, _, _ = _make_doc(test_kullanicisi, title="Concept Flags")
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    settings.DOCVERSE_CONCEPTS_ENABLED = False
    response_surface = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/concepts/")
    response_detail = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/concepts/detail/?kavram=JWT")

    assert response_surface.status_code == 404
    assert response_detail.status_code == 404
