import pytest
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import Dokuman, MetrikKaydi, Parca


def _create_doc(user, *, title: str = "Boss Dok") -> Dokuman:
    doc = Dokuman.objects.create(owner=user, baslik=title, mime="application/pdf", durum="parcalandi")
    doc.dosya.save("boss.pdf", ContentFile(b"ornek"), save=True)
    return doc


def test_compute_boss_difficulty_score_direct(monkeypatch):
    import dokuman.services.metric_store as ms

    monkeypatch.setattr(ms, "compute_mastery_score", lambda user, dokuman: {"mastery_score": 0.9})
    monkeypatch.setattr(ms, "compute_learning_momentum_score", lambda user: {"learning_momentum_score": 0.8})

    out = ms.compute_boss_difficulty_score(user=None, dokuman=None, retry_count=0)
    assert pytest.approx(out["boss_difficulty_score"], rel=1e-3) == 0.86
    assert out["boss_difficulty_band"] == "hard"


@pytest.mark.django_db
def test_boss_readiness_view_returns_stable_shape_and_safe_metric_store(db, test_kullanicisi, monkeypatch, gecici_media_root):
    monkeypatch.setattr(
        "dokuman.services.metric_store.compute_mastery_score",
        lambda user, dokuman: {"mastery_score": 0.75},
    )
    monkeypatch.setattr(
        "dokuman.services.metric_store.compute_learning_momentum_score",
        lambda user: {"learning_momentum_score": 0.5},
    )

    doc = _create_doc(test_kullanicisi, title="Boss Readiness")
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="HAM_BOSS_READINESS_SECRET response icine girmemeli.",
        zorluk_skoru=0.63,
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    resp = client.get(f"/api/dokuman-asistani/analytics/boss-readiness/?dokuman_id={doc.id}")

    assert resp.status_code == 200
    assert set(resp.data.keys()) == {
        "boss_difficulty_score",
        "boss_difficulty_band",
        "boss_retry_count",
        "boss_instruction",
        "mastery_score",
        "learning_momentum_score",
    }
    assert resp.data["boss_difficulty_band"] == "medium"
    assert "HAM_BOSS_READINESS_SECRET" not in str(resp.data)

    kayit = MetrikKaydi.objects.get(olay_turu="boss_readiness_gosterildi")
    assert kayit.skor_ozeti == {
        "boss_difficulty_score": 0.65,
        "boss_difficulty_band": "medium",
        "boss_retry_count": 0.0,
        "mastery_score": 0.75,
        "learning_momentum_score": 0.5,
    }


@pytest.mark.django_db
def test_boss_readiness_flag_off_returns_404(settings, db, test_kullanicisi, gecici_media_root):
    settings.DOCVERSE_METRIC_STORE_ENABLED = False
    doc = _create_doc(test_kullanicisi, title="Boss Off")

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    resp = client.get(f"/api/dokuman-asistani/analytics/boss-readiness/?dokuman_id={doc.id}")

    assert resp.status_code == 404


def test_boss_readiness_serializer_validation():
    from dokuman.serializers import BossReadinessSerializer

    s = BossReadinessSerializer(data={"boss_difficulty_score": 0.5})
    assert not s.is_valid()
    assert "boss_difficulty_band" in s.errors or "boss_instruction" in s.errors
