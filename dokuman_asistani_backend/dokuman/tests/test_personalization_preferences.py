from __future__ import annotations

import json

import pytest
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import Dokuman, KullaniciTercih, Parca
from dokuman.services.personalization import themed_example_for_text


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _doc_with_part(user, *, text: str = "ATP hucrede enerji aktarimini saglayan temel molekuldur."):
    doc = Dokuman.objects.create(
        owner=user,
        baslik="Personalization Doc",
        mime="text/plain",
        durum="parcalandi",
    )
    doc.dosya.save("personalization.txt", ContentFile(b"atp"), save=True)
    part = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Biyoloji > ATP",
        metin=text,
        meta={"path": "Biyoloji > ATP"},
    )
    return doc, part


@pytest.mark.django_db
def test_tercihlerim_get_returns_default_preferences(test_kullanicisi, settings):
    settings.DOCVERSE_PERSONALIZATION_ENABLED = True

    response = _client(test_kullanicisi).get("/api/dokuman-asistani/tercihlerim/")

    assert response.status_code == 200
    assert response.data["enabled"] is True
    assert response.data["theme"] == "default"
    assert response.data["explanation_style"] == "adim_adim"
    assert response.data["level"] == "baslangic"
    assert response.data["example_density"] == "normal"
    assert "oyun" in response.data["options"]["themes"]


@pytest.mark.django_db
def test_tercihlerim_post_saves_valid_preferences(test_kullanicisi, settings):
    settings.DOCVERSE_PERSONALIZATION_ENABLED = True

    response = _client(test_kullanicisi).post(
        "/api/dokuman-asistani/tercihlerim/",
        {
            "theme": "oyun",
            "explanation_style": "bol_ornek",
            "level": "baslangic",
            "example_density": "cok",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["theme"] == "oyun"
    saved = KullaniciTercih.objects.get(kullanici=test_kullanicisi)
    assert saved.tema == "oyun"
    assert saved.tarz == "bol_ornek"
    assert saved.detay_seviyesi == "cok"


@pytest.mark.django_db
def test_tercihlerim_invalid_theme_returns_invalid_preference(test_kullanicisi, settings):
    settings.DOCVERSE_PERSONALIZATION_ENABLED = True

    response = _client(test_kullanicisi).post(
        "/api/dokuman-asistani/tercihlerim/",
        {"theme": "uzay"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["error_code"] == "invalid_preference"
    assert "theme" in response.data["field_errors"]
    assert response.data["status_text"] == response.data["detail"]


@pytest.mark.django_db
def test_tercihlerim_feature_flag_disabled_returns_safe_payload(test_kullanicisi, settings):
    settings.DOCVERSE_PERSONALIZATION_ENABLED = False

    response = _client(test_kullanicisi).get("/api/dokuman-asistani/tercihlerim/")

    assert response.status_code == 200
    assert response.data == {
        "enabled": False,
        "detail": "Kişiselleştirme şu anda kapalı.",
        "error_code": "feature_disabled",
    }


@pytest.mark.django_db
def test_anlamadim_response_includes_personalization_and_themed_examples(
    test_kullanicisi,
    settings,
    gecici_media_root,
    monkeypatch,
):
    settings.DOCVERSE_PERSONALIZATION_ENABLED = True
    settings.DOCVERSE_THEMED_EXAMPLES_ENABLED = True
    _, part = _doc_with_part(test_kullanicisi)

    monkeypatch.setattr(
        "dokuman.views.chat",
        lambda *args, **kwargs: json.dumps(
            {
                "one_liner": "ATP enerji aktarir.",
                "very_simple": "Hucre ATP ile is yapar.",
                "examples": [],
                "mini_quiz": [],
                "dokumanda_yok": False,
            },
            ensure_ascii=False,
        ),
    )

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/anlamadim-v2/",
        {
            "preferences": {
                "theme": "oyun",
                "explanation_style": "bol_ornek",
                "level": "baslangic",
                "example_density": "cok",
            }
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["personalization"]["theme"] == "oyun"
    assert response.data["personalization"]["example_density"] == "cok"
    assert response.data["themed_examples"] == ["Bunu oyundaki enerji barı gibi düşünebilirsin."]


@pytest.mark.django_db
def test_request_body_preferences_override_db_preferences(
    test_kullanicisi,
    settings,
    gecici_media_root,
    monkeypatch,
):
    settings.DOCVERSE_PERSONALIZATION_ENABLED = True
    settings.DOCVERSE_THEMED_EXAMPLES_ENABLED = True
    KullaniciTercih.objects.create(kullanici=test_kullanicisi, tema="spor", tarz="kisa")
    _, part = _doc_with_part(test_kullanicisi)

    monkeypatch.setattr(
        "dokuman.views.chat",
        lambda *args, **kwargs: json.dumps({"one_liner": "ATP enerji aktarir.", "dokumanda_yok": False}),
    )

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{part.id}/anlamadim-v2/",
        {"preferences": {"theme": "teknoloji", "explanation_style": "adim_adim"}},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["personalization"]["theme"] == "teknoloji"
    assert response.data["themed_examples"] == ["Bunu sistemin güç kaynağı gibi düşünebilirsin."]


def test_themed_fallback_examples_cover_core_themes(settings):
    settings.DOCVERSE_THEMED_EXAMPLES_ENABLED = True

    assert "enerji barı" in themed_example_for_text("ATP", "oyun", "tr")
    assert "maç" in themed_example_for_text("ATP", "spor", "tr")
    assert "güç kaynağı" in themed_example_for_text("ATP", "teknoloji", "tr")


@pytest.mark.django_db
def test_other_users_preferences_are_not_read(test_kullanicisi, django_user_model, settings):
    settings.DOCVERSE_PERSONALIZATION_ENABLED = True
    other = django_user_model.objects.create_user(username="pref_other", password="12345678")
    KullaniciTercih.objects.create(kullanici=other, tema="oyun", tarz="bol_ornek", detay_seviyesi="cok")

    response = _client(test_kullanicisi).get("/api/dokuman-asistani/tercihlerim/")

    assert response.status_code == 200
    assert response.data["theme"] == "default"
    assert response.data["example_density"] == "normal"


@pytest.mark.django_db
def test_tercihlerim_accept_language_tr_en_messages(test_kullanicisi, settings):
    settings.DOCVERSE_PERSONALIZATION_ENABLED = True

    tr = _client(test_kullanicisi).post(
        "/api/dokuman-asistani/tercihlerim/",
        {"theme": "bad"},
        format="json",
        HTTP_ACCEPT_LANGUAGE="tr",
    )
    en = _client(test_kullanicisi).post(
        "/api/dokuman-asistani/tercihlerim/",
        {"theme": "bad"},
        format="json",
        HTTP_ACCEPT_LANGUAGE="en",
    )

    assert tr.status_code == 400
    assert en.status_code == 400
    assert tr.data["detail"] == "Geçersiz tercih."
    assert en.data["detail"] == "Invalid preference."
