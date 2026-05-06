import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from dokuman.models import Dokuman, Parca


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _doc(owner, *, mime="application/pdf", text="guvenli", tur="tablo", meta=None):
    doc = Dokuman.objects.create(owner=owner, baslik="Surface Doc", mime=mime, durum="parcalandi")
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur=tur,
        adres="1.1",
        metin=text,
        zorluk_skoru=0.82,
        meta=meta or {"quality_score": 0.9, "heading_score": 0.8},
    )
    return doc


@pytest.mark.django_db
def test_boss_rush_panel_url_and_owner_wiring(settings, test_kullanicisi, django_user_model):
    settings.DOCVERSE_BOSS_ENABLED = True
    settings.DOCVERSE_BOSS_RUSH_PANEL_ENABLED = True
    owner_doc = _doc(test_kullanicisi, text="SADECE_OWNER")
    other = django_user_model.objects.create_user(username="phase4_other", password="12345678")
    other_doc = _doc(other, text="BASKASININ_DOCU")
    client = _client(test_kullanicisi)

    own_resp = client.get(reverse("dokuman-boss-rush-panel", args=[owner_doc.id]))
    foreign_resp = client.get(reverse("dokuman-boss-rush-panel", args=[other_doc.id]))

    assert own_resp.status_code == 200
    assert foreign_resp.status_code == 404


@pytest.mark.django_db
def test_export_readiness_panel_url_and_no_leak(settings, test_kullanicisi):
    settings.DOCVERSE_EXPORT_PLAN_ENABLED = True
    settings.DOCVERSE_EXPORT_READINESS_ENABLED = True
    doc = _doc(test_kullanicisi, text="HAM_EXPORT_PANEL_TEXT")

    resp = _client(test_kullanicisi).get(reverse("dokuman-export-readiness", args=[doc.id]))

    assert resp.status_code == 200
    assert "HAM_EXPORT_PANEL_TEXT" not in str(resp.data)
    assert resp.data["onerilen_format"] in {"docx", "pptx", "pdf", "readme", "yok"}


@pytest.mark.django_db
def test_personalization_confidence_route_stays_registered(settings, test_kullanicisi):
    settings.DOCVERSE_PERSONALIZATION_ENABLED = True

    resp = _client(test_kullanicisi).get(reverse("profil-personalization-confidence"))

    assert resp.status_code == 200
    assert "personalization_confidence_score" in resp.data
