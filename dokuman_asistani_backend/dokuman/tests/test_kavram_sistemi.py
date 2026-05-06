import pytest
from rest_framework.test import APIClient

from dokuman.models import Dokuman, Parca
from dokuman.services.concepts import extract_concepts_from_text


pytestmark = pytest.mark.django_db


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _doc_with_parts(user):
    doc = Dokuman.objects.create(owner=user, baslik="ATP Notlari", dosya="dummy.pdf")
    part1 = Parca.objects.create(
        dokuman=doc,
        sira=1,
        adres="1. ATP Nedir?",
        metin="ATP hucrede enerji tasiyan molekuldur. ATP fosfat bagi ile enerji aktarir.",
    )
    part2 = Parca.objects.create(
        dokuman=doc,
        sira=2,
        adres="2. Glikoz ve Solunum",
        metin="Glikoz hucre solunumu sirasinda ATP uretimi icin kullanilir.",
    )
    return doc, part1, part2


def test_extract_concepts_from_text_teknik_terimi_yakalar():
    concepts = extract_concepts_from_text("ATP hucrede enerji tasir. ATP tekrar kullanilir.")
    terms = {item["term"] for item in concepts}
    assert "ATP" in terms


def test_extract_concepts_from_text_kisa_anlamsiz_terimleri_filtreler():
    concepts = extract_concepts_from_text("ve ile bu şu 12 mi mu")
    assert concepts == []


def test_parca_kavram_endpointi_concepts_ve_relations_dondurur(test_kullanicisi):
    _, part, _ = _doc_with_parts(test_kullanicisi)
    response = _client(test_kullanicisi).get(f"/api/dokuman-asistani/parcalar/{part.id}/kavramlar/")
    assert response.status_code == 200
    assert "concepts" in response.data
    assert "relations" in response.data
    assert any(item["term"] == "ATP" for item in response.data["concepts"])


def test_dokuman_kavram_endpointi_summary_dondurur(test_kullanicisi):
    doc, _, _ = _doc_with_parts(test_kullanicisi)
    response = _client(test_kullanicisi).get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/kavramlar/")
    assert response.status_code == 200
    assert response.data["enabled"] is True
    assert response.data["summary"]["concept_count"] >= 1
    assert "relation_count" in response.data["summary"]


def test_kavram_arama_mentions_dondurur(test_kullanicisi):
    doc, _, _ = _doc_with_parts(test_kullanicisi)
    response = _client(test_kullanicisi).get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/kavramlar/ara/?q=ATP")
    assert response.status_code == 200
    assert response.data["query"] == "ATP"
    assert response.data["concept"]["term"] == "ATP"
    assert response.data["mentions"]
    assert {"part_id", "title", "path", "snippet"}.issubset(response.data["mentions"][0])


def test_feature_flag_kapaliyken_enabled_false_doner(settings, test_kullanicisi):
    settings.DOCVERSE_CONCEPTS_ENABLED = False
    doc, _, _ = _doc_with_parts(test_kullanicisi)
    response = _client(test_kullanicisi).get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/kavramlar/")
    assert response.status_code == 200
    assert response.data["enabled"] is False
    assert response.data["concepts"] == []
    assert response.data["relations"] == []


def test_baskasinin_dokumanina_erisim_engellenir(test_kullanicisi, django_user_model):
    other = django_user_model.objects.create_user(username="other_user", password="12345678")
    doc, _, _ = _doc_with_parts(other)
    response = _client(test_kullanicisi).get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/kavramlar/")
    assert response.status_code == 404


def test_response_shape_concepts_relations_mentions_alanlarini_icerir(test_kullanicisi):
    doc, part, _ = _doc_with_parts(test_kullanicisi)
    part_response = _client(test_kullanicisi).get(f"/api/dokuman-asistani/parcalar/{part.id}/kavramlar/")
    search_response = _client(test_kullanicisi).get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/kavramlar/ara/?q=ATP")
    assert {"concepts", "relations"}.issubset(part_response.data)
    assert {"concept", "mentions"}.issubset(search_response.data)
