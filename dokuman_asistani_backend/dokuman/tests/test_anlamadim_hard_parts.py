from __future__ import annotations

from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import AnlamadimKaydi, Dokuman, MetrikKaydi, Parca
from dokuman.services.anlamadim_engine import build_hardest_parts_payload


def _hard_doc(test_kullanicisi):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Zor Bolumler",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("zor.pdf", ContentFile(b"ornek"), save=True)
    p1 = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="p:1#1",
        metin="HAMICERIK birinci bolum token yenileme ve izin akisini anlatiyor.",
        zorluk_skoru=0.86,
        meta={"baslik": "Token Akisi", "difficulty_score": 0.86, "quality_score": 0.42},
    )
    p2 = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="kod",
        adres="code:python:block:1",
        metin="HAMICERIK ikinci bolum fonksiyon ve cache akisina odaklaniyor.",
        zorluk_skoru=0.74,
        meta={"baslik": "Cache Fonksiyonu", "difficulty_score": 0.74, "quality_score": 0.48, "chunk_kind": "code_block"},
    )
    p3 = Parca.objects.create(
        dokuman=doc,
        sira=3,
        tur="tablo",
        adres="xlsx:sheet:veri#rows:2-5",
        metin="HAMICERIK ucuncu bolum tablo sutunlarini ozetliyor.",
        zorluk_skoru=0.63,
        meta={"baslik": "KPI Tablosu", "difficulty_score": 0.63, "quality_score": 0.61, "chunk_kind": "table_rows"},
    )
    Parca.objects.create(
        dokuman=doc,
        sira=4,
        tur="paragraf",
        adres="p:2#1",
        metin="Kolay bir genel ozet.",
        zorluk_skoru=0.18,
        meta={"baslik": "Ozet", "difficulty_score": 0.18, "quality_score": 0.92},
    )
    AnlamadimKaydi.objects.create(kullanici=test_kullanicisi, dokuman=doc, parca=p1, adres=p1.adres, cikti_text="x")
    AnlamadimKaydi.objects.create(kullanici=test_kullanicisi, dokuman=doc, parca=p1, adres=p1.adres, cikti_text="y")
    return doc, p1, p2, p3


def test_build_hardest_parts_payload_returns_safe_top_three(db, test_kullanicisi):
    doc, p1, p2, p3 = _hard_doc(test_kullanicisi)

    payload = build_hardest_parts_payload(doc=doc, user=test_kullanicisi, limit=3, feature_enabled=True)

    assert [item["parca_id"] for item in payload["oneriler"]] == [p1.id, p2.id, p3.id]
    assert all(set(item) == {"parca_id", "adres", "neden_zor", "kisa_baslik"} for item in payload["oneriler"])
    assert "HAMICERIK" not in str(payload)


def test_dokuman_anlamadim_endpoint_returns_safe_hardest_parts_when_no_selection(
    db,
    test_kullanicisi,
):
    doc, _, _, _ = _hard_doc(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(f"/api/dokuman-asistani/dokumanlar/{doc.id}/anlamadim/", {}, format="json")

    assert response.status_code == 200
    data = response.data
    assert len(data["oneriler"]) == 3
    assert "snippet" not in str(data["oneriler"])
    metric = MetrikKaydi.objects.filter(dokuman=doc, olay_turu="hardest_parts_suggested").latest("id")
    assert metric.skor_ozeti["selection_state"] == "no_selection"
    assert "HAMICERIK" not in str(metric.skor_ozeti)


def test_dokuman_anlamadim_endpoint_feature_flag_off_keeps_controlled_basic_order(
    db,
    test_kullanicisi,
    settings,
):
    settings.DOCVERSE_HARDEST_PARTS_ENABLED = False
    doc, p1, p2, p3 = _hard_doc(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/anlamadim/")

    assert response.status_code == 200
    data = response.data
    assert [item["parca_id"] for item in data["oneriler"]] == [p1.id, p2.id, p3.id]
    assert all(item["neden_zor"] == "zorluk_skoru_yuksek" for item in data["oneriler"])
    assert "HAMICERIK" not in str(data)
