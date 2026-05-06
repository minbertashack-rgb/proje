import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import Dokuman, MetrikKaydi, Parca


def _create_doc(user, *, title: str = "Export Doc") -> Dokuman:
    doc = Dokuman.objects.create(owner=user, baslik=title, mime="application/pdf", durum="parcalandi")
    doc.dosya.save("export.pdf", ContentFile(b"ornek"), save=True)
    return doc


@pytest.mark.django_db
def test_export_readiness_high_ready(monkeypatch, db, test_kullanicisi, gecici_media_root):
    # Hazırlık: Yüksek skor üreten (örneğin %90 ve %85) metrikleri dönmesi için yardımcı fonksiyonlar mock'lanır.
    study_stub = lambda *args, **kwargs: {"study_summary_importance_score": 0.9}
    quiz_stub = lambda parca=None, text=None, quality_score=None, difficulty_score=None, weak_content=None: {"quiz_readiness_score": 0.85}
    monkeypatch.setattr("dokuman.views.compute_study_summary_importance_score", study_stub)
    monkeypatch.setattr("dokuman.views.compute_quiz_readiness_score", quiz_stub)
    monkeypatch.setattr("dokuman.services.metric_store.compute_study_summary_importance_score", study_stub)
    monkeypatch.setattr("dokuman.services.metric_store.compute_quiz_readiness_score", quiz_stub)

    # Hazırlık: Kalitesi maksimum düzeyde olan bir doküman parçası oluştur.
    doc = _create_doc(test_kullanicisi, title="Export Ready")
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="some text",
        meta={"quality_score": 1.0},
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    
    # Çağrı: Belgenin sunum/export için ne kadar hazır (readiness) olduğunu sorgula.
    resp = client.get(f"/api/dokuman-asistani/analytics/export-readiness/?dokuman_id={doc.id}&hedef_format=pptx")

    # Doğrulama: Modelin bu belgeyi export'a uygun bulması ve skorun yüksek olması (yaklaşık 0.895) beklenir.
    assert resp.status_code == 200
    assert resp.data["readiness"] == "ready"
    assert resp.data["download_ready"] is True
    assert resp.data["export_readiness_score"] == pytest.approx(0.895, rel=1e-4)

    # Final State Kontrolü: Export skorunun, log sistemine (metrik deposuna) doğru değerlerle düştüğü teyit edilir.
    kayit = MetrikKaydi.objects.get(olay_turu="export_readiness_hesaplandi")
    assert kayit.skor_ozeti == {
        "export_readiness_score": 0.895,
        "export_readiness_state": "ready",
        "format": "pptx",
    }


@pytest.mark.django_db
def test_export_readiness_requires_owner(db, test_kullanicisi, gecici_media_root):
    other = get_user_model().objects.create_user(username="o2", password="pwd")
    doc = _create_doc(other, title="Other")

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    resp = client.get(f"/api/dokuman-asistani/analytics/export-readiness/?dokuman_id={doc.id}")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_export_readiness_includes_manifest_and_has_stable_shape(monkeypatch, db, test_kullanicisi, gecici_media_root):
    manifest = {"_meta": {"format": "pptx"}, "dokuman_id": 1, "bolumler": []}
    monkeypatch.setattr(
        "dokuman.services.export_manifest_v2.build_export_manifest_v2_payload",
        lambda doc, user, portal_not=None, hedef_format="pptx", cheatsheet_enabled=True, concepts_enabled=True: manifest,
    )
    study_stub = lambda *args, **kwargs: {"study_summary_importance_score": 0.1}
    quiz_stub = lambda parca=None, text=None, quality_score=None, difficulty_score=None, weak_content=None: {"quiz_readiness_score": 0.1}
    monkeypatch.setattr("dokuman.views.compute_study_summary_importance_score", study_stub)
    monkeypatch.setattr("dokuman.views.compute_quiz_readiness_score", quiz_stub)
    monkeypatch.setattr("dokuman.services.metric_store.compute_study_summary_importance_score", study_stub)
    monkeypatch.setattr("dokuman.services.metric_store.compute_quiz_readiness_score", quiz_stub)

    doc = _create_doc(test_kullanicisi, title="ManifestDoc")
    Parca.objects.create(dokuman=doc, sira=1, tur="bolum", adres="1.1", metin="HAM_EXPORT_ANALYTICS_SECRET")

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    resp = client.get(f"/api/dokuman-asistani/analytics/export-readiness/?dokuman_id={doc.id}")

    assert resp.status_code == 200
    assert set(resp.data.keys()) == {
        "dokuman_id",
        "baslik",
        "hedef_format",
        "durum",
        "readiness",
        "export_readiness_score",
        "download_ready",
        "manifest",
        "output_meta",
    }
    assert resp.data["manifest"] == manifest
    assert resp.data["output_meta"] == manifest["_meta"]
    assert "HAM_EXPORT_ANALYTICS_SECRET" not in str(resp.data)


@pytest.mark.django_db
def test_export_readiness_flag_off_returns_404(settings, db, test_kullanicisi, gecici_media_root):
    settings.DOCVERSE_METRIC_STORE_ENABLED = False
    doc = _create_doc(test_kullanicisi, title="Export Off")

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    resp = client.get(f"/api/dokuman-asistani/analytics/export-readiness/?dokuman_id={doc.id}")

    assert resp.status_code == 404
