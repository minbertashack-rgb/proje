from __future__ import annotations

import json

import pytest
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import Dokuman, Parca


def _doc_with_part(user, *, title: str = "Directors Cut Doc"):
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
@pytest.mark.parametrize("cut_type", ["quick", "story", "exam"])
def test_directors_cut_valid_types_return_200(test_kullanicisi, gecici_media_root, monkeypatch, cut_type):
    _, part = _doc_with_part(test_kullanicisi)
    monkeypatch.setattr(
        "dokuman.views.chat",
        lambda *args, **kwargs: json.dumps(
            {
                "title": "AI Cut",
                "summary": "ATP enerji aktarir.",
                "sections": [{"title": "Bolum", "items": ["Madde"]}],
                "quiz": [{"question": "ATP nedir?", "answer": "Enerji molekulu."}] if cut_type == "exam" else [],
            },
            ensure_ascii=False,
        ),
    )

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/directors-cut/",
        {"cut_type": cut_type, "source": {"one_liner": "ATP enerji tasir."}, "lang": "tr"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["enabled"] is True
    assert response.data["cut_type"] == cut_type
    assert response.data["source"] == "ai"


@pytest.mark.django_db
def test_directors_cut_invalid_type_returns_error_code(test_kullanicisi, gecici_media_root):
    _, part = _doc_with_part(test_kullanicisi)

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/directors-cut/",
        {"cut_type": "cinema"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["error_code"] == "invalid_directors_cut_type"
    assert response.data["detail"] == "Geçersiz Director’s Cut türü."


@pytest.mark.django_db
def test_directors_cut_fallback_when_ai_fails(test_kullanicisi, gecici_media_root, monkeypatch):
    _, part = _doc_with_part(test_kullanicisi)

    def failing_chat(*args, **kwargs):
        raise RuntimeError("ai down")

    monkeypatch.setattr("dokuman.views.chat", failing_chat)

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/directors-cut/",
        {"cut_type": "quick", "source": {"one_liner": "ATP enerji tasir."}},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["source"] == "fallback"
    assert response.data["summary"]
    assert response.data["sections"]


@pytest.mark.django_db
def test_directors_cut_feature_flag_disabled(test_kullanicisi, gecici_media_root, settings):
    _, part = _doc_with_part(test_kullanicisi)
    settings.DOCVERSE_DIRECTORS_CUT_ENABLED = False

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/directors-cut/",
        {"cut_type": "quick"},
        format="json",
    )

    assert response.status_code == 403
    assert response.data["enabled"] is False
    assert response.data["error_code"] == "feature_disabled"


@pytest.mark.django_db
def test_directors_cut_blocks_other_users_part(test_kullanicisi, django_user_model, gecici_media_root):
    other = django_user_model.objects.create_user(username="directors_other", password="12345678")
    _, part = _doc_with_part(other, title="Other Directors Doc")

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/directors-cut/",
        {"cut_type": "quick"},
        format="json",
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_directors_cut_response_shape_contains_stable_fields(test_kullanicisi, gecici_media_root, monkeypatch):
    _, part = _doc_with_part(test_kullanicisi)
    monkeypatch.setattr("dokuman.views.chat", lambda *args, **kwargs: "")

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/directors-cut/",
        {"cut_type": "exam"},
        format="json",
    )

    assert response.status_code == 200
    for key in ["enabled", "cut_type", "title", "summary", "sections", "quiz", "source", "warning"]:
        assert key in response.data
    assert response.data["quiz"]


@pytest.mark.django_db
def test_directors_cut_accept_language_tr_en(test_kullanicisi, gecici_media_root, monkeypatch):
    _, part = _doc_with_part(test_kullanicisi)
    monkeypatch.setattr("dokuman.views.chat", lambda *args, **kwargs: "")

    tr = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/directors-cut/",
        {"cut_type": "quick"},
        format="json",
        HTTP_ACCEPT_LANGUAGE="tr",
    )
    en = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/directors-cut/",
        {"cut_type": "quick"},
        format="json",
        HTTP_ACCEPT_LANGUAGE="en",
    )

    assert tr.status_code == 200
    assert en.status_code == 200
    assert tr.data["title"] == "Hızlı Cut"
    assert en.data["title"] == "Quick Cut"
