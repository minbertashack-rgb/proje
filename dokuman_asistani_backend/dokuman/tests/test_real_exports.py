from __future__ import annotations

from io import BytesIO
import zipfile

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from rest_framework.test import APIClient

from dokuman.models import Dokuman, DokumanNotu, MetrikKaydi, Not, Parca


def _real_export_doc(user):
    doc = Dokuman.objects.create(
        owner=user,
        baslik="Platform Raporu",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("platform.pdf", ContentFile(b"ornek"), save=True)
    parca1 = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="3.1",
        metin="HAM_REAL_EXPORT_SECRET Kimlik akisi ve istek sirasi ilk bolumde sabitlenir.",
        meta={"quality_score": 0.88, "difficulty_score": 0.67},
        zorluk="zor",
        zorluk_skoru=0.67,
    )
    parca2 = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="3.2",
        metin="Raporlama hattinda timeout, retry ve cache davranisi ayrilmali.",
        meta={"quality_score": 0.84, "difficulty_score": 0.53},
        zorluk="orta",
        zorluk_skoru=0.53,
    )
    parca3 = Parca.objects.create(
        dokuman=doc,
        sira=3,
        tur="bolum",
        adres="3.3",
        metin="Sunum bolumunde karar notlari ve kaynak baglari korunur.",
        meta={"quality_score": 0.8, "difficulty_score": 0.45},
        zorluk="orta",
        zorluk_skoru=0.45,
    )
    Not.objects.create(
        owner=user,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Teslim Sirasi",
        metin="Once ozet, sonra notlar ve son olarak aksiyonlar paylasilsin.",
        not_turu="calisma",
        kaynak_parca_idleri=[parca1.id, parca2.id, parca3.id],
    )
    portal = DokumanNotu.objects.create(
        owner=user,
        dokuman=doc,
        parca=parca1,
        adres="portal:3",
        baslik="Rapor Portal",
        icerik="Portal baglaminda yonetici ozeti once gelir.",
        not_turu="portal_calisma",
    )
    portal.kaynak_parcalar.add(parca1, parca2, parca3)
    return doc, portal


@pytest.mark.django_db
def test_real_export_pdf_docx_pptx_minimum_uretim_yapar(
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_EXPORT_PLAN_ENABLED = True
    settings.DOCVERSE_REAL_EXPORTS_ENABLED = True
    settings.DOCVERSE_STUDY_SUMMARY_ENABLED = True
    doc, portal = _real_export_doc(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    url = reverse("dokuman-real-export", args=[doc.id])

    response_pdf = client.get(url, {"format": "pdf", "portal_not_id": portal.id})
    assert response_pdf.status_code == 200
    assert response_pdf["Content-Type"] == "application/pdf"
    assert response_pdf["X-DocVerse-Output-Format"] == "pdf"
    assert response_pdf.content.startswith(b"%PDF-")

    response_docx = client.get(url, {"format": "docx", "portal_not_id": portal.id})
    assert response_docx.status_code == 200
    assert response_docx["Content-Type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert response_docx.content[:2] == b"PK"
    with zipfile.ZipFile(BytesIO(response_docx.content)) as archive:
        assert "word/document.xml" in archive.namelist()

    response_pptx = client.get(url, {"format": "pptx", "portal_not_id": portal.id})
    assert response_pptx.status_code == 200
    assert response_pptx["Content-Type"] == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    assert response_pptx["X-DocVerse-Output-Format"] == "pptx"
    assert response_pptx.content[:2] == b"PK"
    with zipfile.ZipFile(BytesIO(response_pptx.content)) as archive:
        slide_files = [
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        ]
        assert 5 <= len(slide_files) <= 8


@pytest.mark.django_db
def test_real_export_json_shape_manifest_ve_metric_tutarli(
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_EXPORT_PLAN_ENABLED = True
    settings.DOCVERSE_REAL_EXPORTS_ENABLED = True
    settings.DOCVERSE_STUDY_SUMMARY_ENABLED = True
    settings.DOCVERSE_METRIC_STORE_ENABLED = True
    doc, portal = _real_export_doc(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(
        reverse("dokuman-real-export", args=[doc.id]),
        {"format": "pptx", "out": "json", "portal_not_id": portal.id},
    )

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "dokuman_id",
        "baslik",
        "hedef_format",
        "durum",
        "readiness",
        "download_ready",
        "manifest",
        "output_meta",
    }
    assert data["hedef_format"] == "pptx"
    assert data["manifest"]["hedef_format"] == "pptx"
    assert data["output_meta"]["source_parca_idleri"] == data["manifest"]["kaynak_parca_idleri"]
    assert data["output_meta"]["source_manifest_version"] == "2.0"
    assert data["output_meta"]["slide_count"] >= 5

    export_metric = MetrikKaydi.objects.get(olay_turu="export_generated")
    presentation_metric = MetrikKaydi.objects.get(olay_turu="presentation_generated")
    assert export_metric.skor_ozeti["output_format"] == "pptx"
    assert presentation_metric.skor_ozeti["slide_count"] >= 5
    assert "HAM_REAL_EXPORT_SECRET" not in str(export_metric.skor_ozeti)
    assert "HAM_REAL_EXPORT_SECRET" not in str(presentation_metric.skor_ozeti)


@pytest.mark.django_db
def test_real_export_flag_kapaliyken_404_ve_manifest_v2_shape_korunur(
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_EXPORT_PLAN_ENABLED = True
    settings.DOCVERSE_REAL_EXPORTS_ENABLED = False
    settings.DOCVERSE_STUDY_SUMMARY_ENABLED = True
    doc, _ = _real_export_doc(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(reverse("dokuman-real-export", args=[doc.id]), {"format": "pdf"})
    assert response.status_code == 404

    settings.DOCVERSE_REAL_EXPORTS_ENABLED = True
    manifest_response = client.get(reverse("dokuman-export-manifest-v2", args=[doc.id]), {"format": "pdf"})
    assert manifest_response.status_code == 200
    assert set(manifest_response.data.keys()) == {
        "dokuman_id",
        "portal_not_id",
        "baslik",
        "hedef_format",
        "bolumler",
        "kaynak_parca_idleri",
        "ozet_kaynaklari",
        "konusma_notu_var_mi",
        "tahmini_slayt_sayisi",
        "tahmini_bolum_sayisi",
    }
    assert manifest_response.data["hedef_format"] == "pdf"
