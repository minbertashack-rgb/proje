from __future__ import annotations

import io
import json
import zipfile

import pytest
from django.conf import settings as django_settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from dokuman.models import Dokuman, Not, Parca


def _auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


def _override_throttle_rates(**rates):
    rest_framework = dict(getattr(django_settings, "REST_FRAMEWORK", {}) or {})
    throttle_rates = dict(rest_framework.get("DEFAULT_THROTTLE_RATES", {}) or {})
    throttle_rates.update(rates)
    rest_framework["DEFAULT_THROTTLE_RATES"] = throttle_rates
    rest_framework.setdefault("EXCEPTION_HANDLER", "dokuman.views_kimlik.docverse_exception_handler")
    return override_settings(REST_FRAMEWORK=rest_framework)


def _assert_rate_limited(response):
    assert response.status_code == 429
    assert response.data["detail"] == "Cok fazla istek gonderildi. Lutfen tekrar deneyin."
    assert response.data["status_text"] == response.data["detail"]
    assert response.data["error_code"] == "rate_limited"
    assert isinstance(response.data["retry_after"], int)
    assert response.data["retry_after"] >= 1


def _docx_upload(name: str = "ornek.docx"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types></Types>")
        archive.writestr("word/document.xml", b"<w:document></w:document>")
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        name,
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _fake_ingestion_success(doc):
    doc.durum = "parcalandi"
    doc.hata = ""
    doc.save(update_fields=["durum", "hata"])
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1",
        metin="Ornek parca metni",
        meta={"kaynak": "test"},
    )
    return doc


def _doc_with_parca(user, *, title="Throttle Doc", text="JWT access token kimlik tasir.", adres="1.1"):
    doc = Dokuman.objects.create(
        owner=user,
        baslik=title,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("throttle.pdf", ContentFile(b"ornek"), save=True)
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres=adres,
        metin=text,
        meta={"path": adres, "baslik": title},
    )
    return doc, parca


@pytest.mark.django_db
def test_token_obtain_throttle_returns_patch5_style_payload(test_kullanicisi):
    cache.clear()
    with _override_throttle_rates(token_obtain="1/min"):
        client = APIClient()
        first = client.post(
            reverse("token_al"),
            {"username": test_kullanicisi.username, "password": "12345678"},
            format="json",
        )
        second = client.post(
            reverse("token_al"),
            {"username": test_kullanicisi.username, "password": "12345678"},
            format="json",
        )

    assert first.status_code == 200
    _assert_rate_limited(second)


@pytest.mark.django_db
def test_token_refresh_throttle_returns_patch5_style_payload(test_kullanicisi):
    obtain = APIClient().post(
        reverse("token_al"),
        {"username": test_kullanicisi.username, "password": "12345678"},
        format="json",
    )

    cache.clear()
    with _override_throttle_rates(token_refresh="1/min"):
        client = APIClient()
        first = client.post(reverse("token_yenile"), {"refresh": obtain.data["refresh"]}, format="json")
        second = client.post(reverse("token_yenile"), {"refresh": obtain.data["refresh"]}, format="json")

    assert first.status_code == 200
    _assert_rate_limited(second)


@pytest.mark.django_db
def test_upload_throttle_returns_consistent_payload(test_kullanicisi, gecici_media_root, monkeypatch):
    monkeypatch.setattr("dokuman.views.dokumani_parcala_ve_kaydet", _fake_ingestion_success)
    cache.clear()
    with _override_throttle_rates(upload="1/min"):
        client = _auth_client(test_kullanicisi)
        first = client.post(
            "/api/dokuman-asistani/dokumanlar/yukle/",
            {"dosya": _docx_upload()},
            format="multipart",
        )
        second = client.post(
            "/api/dokuman-asistani/dokumanlar/yukle/",
            {"dosya": _docx_upload("ikinci.docx")},
            format="multipart",
        )

    assert first.status_code == 201
    _assert_rate_limited(second)


@pytest.mark.django_db
def test_anlamadim_throttle_returns_consistent_payload(test_kullanicisi, gecici_media_root):
    _, parca = _doc_with_parca(test_kullanicisi, title="Explain Throttle")

    cache.clear()
    with _override_throttle_rates(anlamadim="1/min"):
        client = _auth_client(test_kullanicisi)
        first = client.post(
            f"/api/dokuman-asistani/parcalar/{parca.id}/anlamadim/",
            {"tema": "genel", "seviye": "orta"},
            format="json",
        )
        second = client.post(
            f"/api/dokuman-asistani/parcalar/{parca.id}/anlamadim/",
            {"tema": "genel", "seviye": "orta"},
            format="json",
        )

    assert first.status_code == 200
    _assert_rate_limited(second)


@pytest.mark.django_db
def test_ai2_kanitli_cevap_throttle_returns_consistent_payload(
    test_kullanicisi,
    monkeypatch,
    gecici_media_root,
):
    doc, _ = _doc_with_parca(
        test_kullanicisi,
        title="Evidence Throttle",
        text="RAG once ilgili parcayi bulur sonra cevap icin kanit kullanir.",
        adres="RAG > Giris",
    )
    second = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="RAG > Kaynak",
        metin="Parca kimligi secili kaniti gosterir.",
        meta={"path": "RAG > Kaynak"},
    )

    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: (
            '{"answer":"Parca kimligi secili kaniti gosterir.",'
            f'"supported":true,"citations":[{second.id}],"missing":[],"followups":[]}}'
        ),
    )

    cache.clear()
    with _override_throttle_rates(kanitli_cevap="1/min"):
        client = _auth_client(test_kullanicisi)
        first = client.post(
            "/api/dokuman-asistani/ai2/kanitli-cevap/",
            {"question": "Hangi kanit kullanildi?", "doc_id": doc.id, "top_k": 2},
            format="json",
        )
        second_response = client.post(
            "/api/dokuman-asistani/ai2/kanitli-cevap/",
            {"question": "Hangi kanit kullanildi?", "doc_id": doc.id, "top_k": 2},
            format="json",
        )

    assert first.status_code == 200
    _assert_rate_limited(second_response)


@pytest.mark.django_db
def test_notes_write_throttle_shared_between_create_and_update(test_kullanicisi, gecici_media_root):
    cache.clear()
    with _override_throttle_rates(notes_write="1/min"):
        client = _auth_client(test_kullanicisi)
        create_response = client.post(
            "/api/dokuman-asistani/notlar/",
            {"baslik": "JWT", "metin": "Access ve refresh farki."},
            format="json",
        )
        update_response = client.patch(
            f"/api/dokuman-asistani/notlar/{create_response.data['id']}/",
            {"metin": "Guncel not"},
            format="json",
        )

    assert create_response.status_code == 201
    _assert_rate_limited(update_response)
