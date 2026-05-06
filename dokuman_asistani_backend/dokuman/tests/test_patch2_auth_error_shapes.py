import pytest
from django.urls import reverse
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient, APIRequestFactory

from dokuman.models import Dokuman
from dokuman.views_kimlik import docverse_exception_handler


def _client(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_register_missing_fields_returns_additive_validation_shape():
    response = APIClient().post(reverse("kayit"), {"username": "   "}, format="json")

    assert response.status_code == 400
    assert response.data["detail"] == "Bu alan zorunludur."
    assert response.data["status_text"] == response.data["detail"]
    assert response.data["error_code"] == "validation_error"
    assert set(response.data["field_errors"]) == {"username", "password"}


@pytest.mark.django_db
def test_register_duplicate_username_returns_field_error(django_user_model):
    django_user_model.objects.create_user(username="mevcut_kullanici", password="12345678")

    response = APIClient().post(
        reverse("kayit"),
        {"username": "mevcut_kullanici", "password": "12345678"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Bu kullanıcı adı zaten kullanımda."
    assert response.data["status_text"] == response.data["detail"]
    assert response.data["error_code"] == "validation_error"
    assert response.data["field_errors"]["username"] == ["Bu kullanıcı adı zaten kullanımda."]


@pytest.mark.django_db
def test_register_accepts_password_confirm_aliases_and_returns_json_success():
    response = APIClient().post(
        reverse("kayit"),
        {
            "username": "yeni_kullanici",
            "email": "yeni@example.com",
            "password": "GucluSifre123!",
            "password2": "GucluSifre123!",
            "password_confirm": "GucluSifre123!",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response["Content-Type"].startswith("application/json")
    assert response.data["detail"] == "Kayıt başarılı."
    assert response.data["status_text"] == response.data["detail"]
    assert response.data["username"] == "yeni_kullanici"
    assert response.data["email"] == "yeni@example.com"


@pytest.mark.django_db
def test_register_password_confirm_mismatch_returns_field_error():
    response = APIClient().post(
        reverse("kayit"),
        {
            "username": "uyumsuz_kullanici",
            "email": "uyumsuz@example.com",
            "password": "GucluSifre123!",
            "password2": "farkliSifre123!",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["error_code"] == "validation_error"
    assert response.data["field_errors"]["password_confirm"] == ["Şifre tekrar alanları eşleşmiyor."]


@pytest.mark.django_db
def test_register_accept_text_html_still_returns_json():
    response = APIClient().post(
        reverse("kayit"),
        {"username": "demo_user", "password": "12345678"},
        format="json",
        HTTP_ACCEPT="text/html",
    )

    assert response.status_code == 201
    assert response["Content-Type"].startswith("application/json")


@pytest.mark.django_db
def test_register_malformed_json_still_returns_json_error():
    response = APIClient().generic(
        "POST",
        reverse("kayit"),
        data="{bozuk-json",
        content_type="application/json",
        HTTP_ACCEPT="text/html",
    )

    assert response.status_code == 400
    assert response["Content-Type"].startswith("application/json")
    assert response.data["detail"]


@pytest.mark.django_db
def test_register_accepts_android_emulator_host_and_still_returns_json():
    response = APIClient().post(
        reverse("kayit"),
        {
            "username": "emulator_host_test_001",
            "email": "emulator_host_test_001@example.com",
            "password": "GucluSifre123!",
            "password2": "GucluSifre123!",
        },
        format="json",
        HTTP_HOST="10.0.2.2:8001",
        HTTP_ACCEPT="application/json",
    )

    assert response.status_code == 201
    assert response["Content-Type"].startswith("application/json")
    assert response.data["detail"] == "Kayıt başarılı."
    assert response.data["status_text"] == response.data["detail"]


@pytest.mark.django_db
def test_token_obtain_success_keeps_tokens_and_adds_metadata(test_kullanicisi):
    response = APIClient().post(
        reverse("token_al"),
        {"username": test_kullanicisi.username, "password": "12345678"},
        format="json",
    )

    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data
    assert response.data["token_type"]
    assert isinstance(response.data["expires_in"], int)
    assert response.data["expires_in"] > 0
    assert response.data["status_text"] == "Oturum acildi."


@pytest.mark.django_db
def test_token_obtain_invalid_credentials_returns_distinct_error_code(test_kullanicisi):
    response = APIClient().post(
        reverse("token_al"),
        {"username": test_kullanicisi.username, "password": "yanlis-sifre"},
        format="json",
    )

    assert response.status_code == 401
    assert response.data["error_code"] == "invalid_credentials"
    assert response.data["status_text"] == response.data["detail"]
    assert response.data["detail"]


@pytest.mark.django_db
def test_token_refresh_success_keeps_access_and_adds_metadata(test_kullanicisi):
    client = APIClient()
    obtain = client.post(
        reverse("token_al"),
        {"username": test_kullanicisi.username, "password": "12345678"},
        format="json",
    )

    response = client.post(
        reverse("token_yenile"),
        {"refresh": obtain.data["refresh"]},
        format="json",
    )

    assert response.status_code == 200
    assert "access" in response.data
    assert response.data["token_type"]
    assert isinstance(response.data["expires_in"], int)
    assert response.data["expires_in"] > 0
    assert response.data["status_text"] == "Token yenilendi."


@pytest.mark.django_db
def test_token_refresh_invalid_token_returns_token_invalid_shape():
    response = APIClient().post(
        reverse("token_yenile"),
        {"refresh": "bozuk-token"},
        format="json",
    )

    assert response.status_code == 401
    assert response.data["error_code"] == "token_invalid"
    assert response.data["status_text"] == response.data["detail"]
    assert response.data["detail"]


@pytest.mark.django_db
def test_auth_credentials_missing_error_payload_is_consistent():
    response = APIClient().get("/api/dokuman-asistani/notlar/")

    assert response.status_code == 401
    assert response.data["error_code"] == "auth_credentials_missing"
    assert response.data["status_text"] == response.data["detail"]
    assert response.data["detail"]


@pytest.mark.django_db
def test_ownership_not_found_payload_is_consistent(settings, test_kullanicisi, django_user_model):
    settings.DOCVERSE_BOSS_ENABLED = True
    settings.DOCVERSE_BOSS_RUSH_PANEL_ENABLED = True
    other = django_user_model.objects.create_user(username="patch2_owner_other", password="12345678")
    foreign_doc = Dokuman.objects.create(
        owner=other,
        baslik="Foreign Doc",
        mime="application/pdf",
        durum="parcalandi",
    )

    response = _client(test_kullanicisi).get(reverse("dokuman-boss-rush-panel", kwargs={"pk": foreign_doc.id}))

    assert response.status_code == 404
    assert response.data["error_code"] == "resource_not_found"
    assert response.data["status_text"] == response.data["detail"]
    assert response.data["detail"]


@pytest.mark.django_db
def test_validation_error_payload_includes_field_errors(test_kullanicisi):
    response = _client(test_kullanicisi).post(
        "/api/export/cheatsheet/",
        {"format": "zip"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["error_code"] == "validation_error"
    assert response.data["status_text"] == response.data["detail"]
    assert set(response.data["field_errors"]) == {"dokuman_id", "format"}


def test_permission_denied_handler_returns_consistent_shape():
    request = APIRequestFactory().get("/api/dokuman-asistani/ornek-korumali/")

    response = docverse_exception_handler(PermissionDenied("Bu isleme izin yok."), {"request": request})

    assert response.status_code == 403
    assert response.data["detail"] == "Bu isleme izin yok."
    assert response.data["status_text"] == response.data["detail"]
    assert response.data["error_code"] == "permission_denied"
