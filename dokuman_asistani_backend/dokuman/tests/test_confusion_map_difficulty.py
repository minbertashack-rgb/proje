from __future__ import annotations

from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import Dokuman, Parca
from dokuman.services.difficulty import calculate_part_difficulty


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _doc(user):
    doc = Dokuman.objects.create(owner=user, baslik="Confusion Map", mime="text/plain", durum="parcalandi")
    doc.dosya.save("confusion-map.txt", ContentFile(b"ornek"), save=True)
    return doc


def test_short_simple_text_is_easy():
    profile = calculate_part_difficulty("Bu kisa ve sade bir ozet cumlesidir.")
    score = profile["difficulty_score"]

    assert 0.0 <= score <= 0.39
    assert profile["difficulty_label"] == "kolay"
    assert profile["difficulty_reasons"]


def test_long_technical_text_is_hard():
    text = (
        "JWT, OAuth, RBAC, API gateway, telemetry, observability, latency ve throughput "
        "metrikleri ayni islem hattinda degerlendirilir; cache invalidation, SQL JOIN, "
        "index secimi ve authorization policy baglamlari uzun bir karar cumlesi icinde "
        "birbirine baglanir. "
    ) * 3

    profile = calculate_part_difficulty(text)
    score = profile["difficulty_score"]

    assert score >= 0.70
    assert profile["difficulty_label"] == "zor"
    assert any("Terim" in reason or "Teknik" in reason for reason in profile["difficulty_reasons"])


def test_table_formula_text_is_hard():
    text = "KPI | Formul | Esik\nLatency | =P95_MS/COUNT(API) | >= 250\nThroughput | SUM(req)/AVG(sec) | < 10"

    profile = calculate_part_difficulty(text)

    assert profile["difficulty_score"] >= 0.70
    assert profile["difficulty_label"] == "zor"
    assert any("Sembol" in reason or "Kod/tablo" in reason for reason in profile["difficulty_reasons"])


def test_parts_response_includes_difficulty_fields(db, test_kullanicisi, gecici_media_root):
    doc = _doc(test_kullanicisi)
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="JWT ve OAuth authorization policy ayrintili olarak anlatilir.",
    )

    response = _client(test_kullanicisi).get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/parcalar/")

    assert response.status_code == 200
    item = response.data["parcalar"][0]
    assert "difficulty_score" in item
    assert "difficulty_label" in item
    assert "difficulty_reasons" in item
    assert isinstance(item["difficulty_reasons"], list)


def test_hard_places_endpoint_returns_top_three_and_summary(db, test_kullanicisi, gecici_media_root):
    doc = _doc(test_kullanicisi)
    texts = [
        "Kisa ozet.",
        "JWT OAuth RBAC API gateway telemetry observability latency throughput SQL JOIN index policy detaylari.",
        "KPI | Formul | Esik\nLatency | =P95_MS/COUNT(API) | >= 250",
        ("Cache invalidation, authorization policy, telemetry pipeline ve SQL index stratejileri " * 5),
        "Sade giris metni.",
    ]
    for index, text in enumerate(texts, start=1):
        profile = calculate_part_difficulty(text)
        Parca.objects.create(
            dokuman=doc,
            sira=index,
            tur="bolum",
            adres=f"p:{index}",
            metin=text,
            zorluk_skoru=profile["difficulty_score"],
            zorluk=profile["difficulty_label"],
        )

    response = _client(test_kullanicisi).get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/zor-yerler/?limit=3")

    assert response.status_code == 200
    assert response.data["document_id"] == doc.id
    assert len(response.data["hardest_parts"]) == 3
    scores = [item["difficulty_score"] for item in response.data["hardest_parts"]]
    assert scores == sorted(scores, reverse=True)
    assert set(response.data["summary"]) == {"easy", "medium", "hard"}


def test_hard_places_endpoint_disabled_by_flag(db, test_kullanicisi, gecici_media_root, settings):
    settings.DOCVERSE_HARDEST_PARTS_ENABLED = False
    doc = _doc(test_kullanicisi)
    Parca.objects.create(dokuman=doc, sira=1, tur="bolum", adres="p:1", metin="JWT OAuth API")

    response = _client(test_kullanicisi).get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/zor-yerler/")

    assert response.status_code == 200
    assert response.data["enabled"] is False
    assert response.data["hardest_parts"] == []
    assert response.data["summary"] == {"easy": 0, "medium": 0, "hard": 0}


def test_hard_places_endpoint_blocks_other_users(db, test_kullanicisi, django_user_model, gecici_media_root):
    other = django_user_model.objects.create_user(username="diger", password="x")
    doc = _doc(other)

    response = _client(test_kullanicisi).get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/zor-yerler/")

    assert response.status_code == 404


def test_accept_language_maps_reasons_tr_en(db, test_kullanicisi, gecici_media_root):
    doc = _doc(test_kullanicisi)
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="p:1",
        metin="JWT OAuth API gateway telemetry observability latency throughput SQL JOIN index.",
    )
    client = _client(test_kullanicisi)

    tr_response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/zor-yerler/", HTTP_ACCEPT_LANGUAGE="tr")
    en_response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/zor-yerler/", HTTP_ACCEPT_LANGUAGE="en")

    assert tr_response.status_code == 200
    assert en_response.status_code == 200
    assert any("Terim" in reason for reason in tr_response.data["hardest_parts"][0]["difficulty_reasons"])
    assert any("Term" in reason for reason in en_response.data["hardest_parts"][0]["difficulty_reasons"])
