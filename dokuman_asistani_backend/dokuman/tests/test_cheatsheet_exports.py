from __future__ import annotations

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from rest_framework.test import APIClient

from dokuman.models import AnlamadimKaydi, Dokuman, DokumanNotu, MetrikKaydi, Not, Parca


def _export_doc(user):
    doc = Dokuman.objects.create(
        owner=user,
        baslik="Guvenlik Cekirdegi",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("guvenlik.pdf", ContentFile(b"ornek"), save=True)
    parca1 = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="HAM_CHEATSHEET_SECRET JWT dogrulama akisinda access token ve nonce birlikteligini kontrol et.",
        meta={"quality_score": 0.86, "difficulty_score": 0.64},
        zorluk="zor",
        zorluk_skoru=0.64,
    )
    parca2 = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="1.2",
        metin="Refresh token yalnizca guvenli yenileme akisi icin ayrilmali.",
        meta={"quality_score": 0.83, "difficulty_score": 0.58},
        zorluk="orta",
        zorluk_skoru=0.58,
    )
    note = Not.objects.create(
        owner=user,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Token Kontrolu",
        metin="Nonce ve refresh token akislarini ayri izle.",
        not_turu="calisma",
        kaynak_parca_idleri=[parca1.id, parca2.id],
    )
    portal = DokumanNotu.objects.create(
        owner=user,
        dokuman=doc,
        parca=parca1,
        adres="portal:1",
        baslik="Guvenlik Portal Notu",
        icerik="Portal notu uzerinden tekrar akisi sabitlendi.",
        not_turu="portal_calisma",
    )
    portal.kaynak_parcalar.add(parca1, parca2)
    portal.bagli_notlar.add(note)
    AnlamadimKaydi.objects.create(
        kullanici=user,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        cikti_json={
            "glossary": [
                {"terim": "JWT", "tanim": "Kimlik aktarimi icin tasiyici token."},
                {"terim": "Nonce", "tanim": "Tek seferlik dogrulama girdisi."},
            ]
        },
    )
    return doc, portal


@pytest.mark.django_db
def test_cheatsheet_export_pdf_uretir_ve_metric_ham_icerik_yazmaz(
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_CHEATSHEET_EXPORT_ENABLED = True
    settings.DOCVERSE_STUDY_SUMMARY_ENABLED = True
    settings.DOCVERSE_METRIC_STORE_ENABLED = True
    doc, portal = _export_doc(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(
        reverse("dokuman-cheatsheet-export", args=[doc.id]),
        {"out": "pdf", "portal_not_id": portal.id},
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["X-DocVerse-Output-Format"] == "pdf"
    assert response["X-DocVerse-Source-Manifest-Version"] == "2.0"
    assert response.content.startswith(b"%PDF-")

    metric = MetrikKaydi.objects.get(olay_turu="cheatsheet_export_generated")
    legacy_metric = MetrikKaydi.objects.get(olay_turu="cheatsheet_export_uretildi")
    assert metric.skor_ozeti["output_format"] == "pdf"
    assert legacy_metric.skor_ozeti["format"] == "pdf"
    assert "HAM_CHEATSHEET_SECRET" not in str(metric.skor_ozeti)
    assert "HAM_CHEATSHEET_SECRET" not in str(legacy_metric.skor_ozeti)


@pytest.mark.django_db
def test_cheatsheet_export_json_manifest_ve_output_meta_tutarli(
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_CHEATSHEET_EXPORT_ENABLED = True
    settings.DOCVERSE_STUDY_SUMMARY_ENABLED = True
    doc, portal = _export_doc(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(
        reverse("dokuman-cheatsheet-export", args=[doc.id]),
        {"out": "json", "portal_not_id": portal.id},
    )

    assert response.status_code == 200
    data = response.data
    assert data["dokuman_id"] == doc.id
    assert "manifest" in data
    assert "output_meta" in data
    assert data["manifest"]["portal_not_id"] == portal.id
    assert data["output_meta"]["source_manifest_version"] == "2.0"
    assert data["output_meta"]["source_parca_idleri"] == data["manifest"]["kaynak_parca_idleri"]
    assert data["output_meta"]["section_count"] >= 5


@pytest.mark.django_db
def test_cheatsheet_export_flag_kapaliyken_404_doner(
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_CHEATSHEET_EXPORT_ENABLED = False
    doc, _ = _export_doc(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(reverse("dokuman-cheatsheet-export", args=[doc.id]), {"out": "json"})

    assert response.status_code == 404
