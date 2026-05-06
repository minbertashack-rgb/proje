from __future__ import annotations

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from rest_framework.test import APIClient

from dokuman.models import Dokuman, MetrikKaydi, Not, Parca


def _readme_doc(user):
    doc = Dokuman.objects.create(
        owner=user,
        baslik="Servis Entegrasyonu",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("servis.pdf", ContentFile(b"ornek"), save=True)
    parca1 = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="2.1",
        metin="HAM_README_SECRET giris noktasinda token kontrolunu ve retry politikasini birlestir.",
        meta={"quality_score": 0.81, "difficulty_score": 0.49},
        zorluk="orta",
        zorluk_skoru=0.49,
    )
    parca2 = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="2.2",
        metin="API istemcisi timeout ve backoff mantigi ile calismalidir.",
        meta={"quality_score": 0.84, "difficulty_score": 0.55},
        zorluk="zor",
        zorluk_skoru=0.55,
    )
    Not.objects.create(
        owner=user,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Kurulum Akisi",
        metin="Ortam degiskenlerini ayarla ve ilk saglik kontrolunu calistir.",
        not_turu="calisma",
        kaynak_parca_idleri=[parca1.id, parca2.id],
    )
    return doc


@pytest.mark.django_db
def test_readme_export_json_payload_stabil_ve_metric_guvenli(
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_README_EXPORT_ENABLED = True
    settings.DOCVERSE_STUDY_SUMMARY_ENABLED = True
    settings.DOCVERSE_METRIC_STORE_ENABLED = True
    doc = _readme_doc(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(reverse("dokuman-readme-export", args=[doc.id]), {"out": "json"})

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "dokuman_id",
        "baslik",
        "proje_ozeti",
        "kurulum",
        "kullanim",
        "kritik_bilesenler",
        "kaynak_parca_idleri",
        "manifest",
        "output_meta",
    }
    assert data["output_meta"]["source_parca_idleri"] == data["manifest"]["kaynak_parca_idleri"]
    assert data["output_meta"]["source_manifest_version"] == "2.0"

    metric = MetrikKaydi.objects.get(olay_turu="readme_generated")
    assert metric.skor_ozeti["output_format"] == "json"
    assert "HAM_README_SECRET" not in str(metric.skor_ozeti)


@pytest.mark.django_db
def test_readme_export_markdown_uretir(
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_README_EXPORT_ENABLED = True
    settings.DOCVERSE_STUDY_SUMMARY_ENABLED = True
    doc = _readme_doc(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(reverse("dokuman-readme-export", args=[doc.id]), {"out": "md"})

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert content.startswith("# Servis Entegrasyonu README")
    assert "## Kurulum" in content
    assert "## Output Meta" in content


@pytest.mark.django_db
def test_readme_export_flag_kapaliyken_kontrollu_doner(
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_README_EXPORT_ENABLED = False
    doc = _readme_doc(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(reverse("dokuman-readme-export", args=[doc.id]), {"out": "json"})

    assert response.status_code == 404
