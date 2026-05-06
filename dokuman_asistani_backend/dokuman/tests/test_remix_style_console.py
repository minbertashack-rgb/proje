from __future__ import annotations

import json

import pytest
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import Dokuman, Parca


def _doc_with_part(user, *, title: str = "Remix Doc"):
    doc = Dokuman.objects.create(
        owner=user,
        baslik=title,
        mime="text/plain",
        durum="parcalandi",
    )
    doc.dosya.save(f"{title.lower().replace(' ', '-')}.txt", ContentFile(b"atp"), save=True)
    part = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Biyoloji > ATP",
        metin="ATP hucrede enerji aktarimini saglayan temel molekuldur. Fosfat baglari enerji tasir.",
        meta={"path": "Biyoloji > ATP"},
    )
    return doc, part


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_remix_valid_short_returns_200(test_kullanicisi, gecici_media_root, monkeypatch):
    _, part = _doc_with_part(test_kullanicisi)
    monkeypatch.setattr(
        "dokuman.views.chat",
        lambda *args, **kwargs: json.dumps(
            {"title": "Kisa anlatim", "content": "ATP enerji tasir.", "items": ["Enerji aktarir"], "table": []},
            ensure_ascii=False,
        ),
    )

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/remix/",
        {"style": "short", "source": {"one_liner": "ATP enerji tasir."}, "lang": "tr"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["enabled"] is True
    assert response.data["style"] == "short"
    assert response.data["source"] == "ai"


@pytest.mark.django_db
def test_remix_invalid_style_returns_error_code(test_kullanicisi, gecici_media_root):
    _, part = _doc_with_part(test_kullanicisi)

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/remix/",
        {"style": "unknown"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["error_code"] == "invalid_remix_style"
    assert response.data["detail"] == "Geçersiz remix stili."


@pytest.mark.django_db
def test_remix_fallback_when_ai_fails(test_kullanicisi, gecici_media_root, monkeypatch):
    _, part = _doc_with_part(test_kullanicisi)

    def failing_chat(*args, **kwargs):
        raise RuntimeError("ai down")

    monkeypatch.setattr("dokuman.views.chat", failing_chat)
    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/remix/",
        {"style": "simpler", "source": {"one_liner": "ATP enerji tasir."}},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["source"] == "fallback"
    assert response.data["style"] == "simpler"
    assert response.data["content"]


@pytest.mark.django_db
def test_remix_feature_flag_disabled_returns_disabled(test_kullanicisi, gecici_media_root, settings):
    _, part = _doc_with_part(test_kullanicisi)
    settings.DOCVERSE_STYLE_CONSOLE_ENABLED = False

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/remix/",
        {"style": "short"},
        format="json",
    )

    assert response.status_code == 403
    assert response.data["enabled"] is False
    assert response.data["error_code"] == "feature_disabled"


@pytest.mark.django_db
def test_remix_blocks_other_users_part(test_kullanicisi, django_user_model, gecici_media_root):
    other = django_user_model.objects.create_user(username="remix_other", password="12345678")
    _, part = _doc_with_part(other, title="Other Remix Doc")

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/remix/",
        {"style": "short"},
        format="json",
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_remix_response_shape_contains_stable_fields(test_kullanicisi, gecici_media_root, monkeypatch):
    _, part = _doc_with_part(test_kullanicisi)
    monkeypatch.setattr("dokuman.views.chat", lambda *args, **kwargs: "")

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/remix/",
        {"style": "table"},
        format="json",
    )

    assert response.status_code == 200
    for key in ["enabled", "style", "title", "content", "items", "table", "source", "warning"]:
        assert key in response.data


@pytest.mark.django_db
def test_remix_accept_language_tr_en(test_kullanicisi, gecici_media_root, monkeypatch):
    _, part = _doc_with_part(test_kullanicisi)
    monkeypatch.setattr("dokuman.views.chat", lambda *args, **kwargs: "")

    tr = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/remix/",
        {"style": "short"},
        format="json",
        HTTP_ACCEPT_LANGUAGE="tr",
    )
    en = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/remix/",
        {"style": "short"},
        format="json",
        HTTP_ACCEPT_LANGUAGE="en",
    )

    assert tr.status_code == 200
    assert en.status_code == 200
    assert tr.data["title"] == "Kısa anlatım"
    assert en.data["title"] == "Short version"
