from __future__ import annotations

import io

from django.core.files.base import ContentFile
from PIL import Image

from dokuman.models import Dokuman, MetrikKaydi, Parca
from dokuman.services import ocr


def _ocr_doc_olustur(test_kullanicisi):
    buffer = io.BytesIO()
    Image.new("RGB", (64, 32), color="white").save(buffer, format="PNG")
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="OCR Test",
        mime="image/png",
        durum="yuklendi",
    )
    doc.dosya.save("ocr-test.png", ContentFile(buffer.getvalue()), save=True)
    return doc


def _pdf_doc_olustur(test_kullanicisi):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="PDF OCR Test",
        mime="application/pdf",
        durum="yuklendi",
    )
    doc.dosya.save("ocr-test.pdf", ContentFile(b"%PDF-1.4\nfake"), save=True)
    return doc


def test_ocr_ingestion_adresli_parcalar_olusturur(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _ocr_doc_olustur(test_kullanicisi)

    monkeypatch.setattr("dokuman.services.ocr.extract_text_from_image", lambda path: "Ilk satir\n\nIkinci satir")
    monkeypatch.setattr("dokuman.services.ocr.split_text_into_chunks", lambda text, max_chars=1200: ["Ilk satir", "Ikinci satir"])
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"denendi": True})

    ocr.gorseli_ocr_ile_parcala_ve_kaydet(doc)
    doc.refresh_from_db()
    parcalar = list(Parca.objects.filter(dokuman=doc).order_by("sira"))

    assert doc.durum == "parcalandi"
    assert doc.mime == "image/png"
    assert doc.hata == ""
    assert [parca.adres for parca in parcalar] == ["ocr:1", "ocr:2"]
    assert parcalar[0].tur == "ocr"
    assert parcalar[0].meta["kaynak"] == "ocr"
    assert parcalar[0].meta["path"] == "ocr:1"
    assert parcalar[0].meta["source_address"] == "ocr:1"
    assert parcalar[0].meta["chunk_index"] == 1
    assert parcalar[0].meta["ocr"] is True
    assert parcalar[0].meta["ocr_kullanildi"] is True
    assert parcalar[0].meta["ocr_kaynak_turu"] == "image_ocr"
    assert parcalar[0].meta["chunk_title"] == "Gorsel OCR parcasi 1"
    assert "ocr_quality_score" in parcalar[0].meta
    assert parcalar[0].meta["ocr_confidence_band"] in {"dusuk", "orta", "yuksek"}
    assert "ocr_warning" in parcalar[0].meta
    assert "difficulty_score" in parcalar[0].meta
    assert "quality_score" in parcalar[0].meta
    assert parcalar[1].meta["path"] == "ocr:2"
    metric = MetrikKaydi.objects.get(olay_turu="ocr_ingestion_score_snapshot")
    assert metric.dokuman_id == doc.id
    assert "ocr_quality_score" in metric.skor_ozeti
    assert "difficulty_score" in metric.skor_ozeti
    assert "Ilk satir" not in str(metric.skor_ozeti)


def test_pdf_ocr_ingestion_page_adresli_parcalar_olusturur(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _pdf_doc_olustur(test_kullanicisi)

    monkeypatch.setattr(
        "dokuman.services.ocr.extract_text_from_pdf_pages",
        lambda path: [
            {"page": 1, "text": "Ilk PDF OCR satiri", "image_width": 1000, "image_height": 1400},
            {"page": 2, "text": "Ikinci PDF OCR satiri", "image_width": 1000, "image_height": 1400},
        ],
    )
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"denendi": True})

    ocr.pdf_ocr_ile_parcala_ve_kaydet(doc)
    doc.refresh_from_db()
    parcalar = list(Parca.objects.filter(dokuman=doc).order_by("sira"))

    assert doc.durum == "parcalandi"
    assert [parca.adres for parca in parcalar] == ["pdf:page:1#ocr:1", "pdf:page:2#ocr:1"]
    assert parcalar[0].meta["format"] == "pdf"
    assert parcalar[0].meta["ocr_fallback"] is True
    assert parcalar[0].meta["ocr_kullanildi"] is True
    assert parcalar[0].meta["ocr_kaynak_turu"] == "pdf_ocr_fallback"
    assert parcalar[0].meta["ocr_confidence_band"] in {"dusuk", "orta", "yuksek"}
    assert "ocr_warning" in parcalar[0].meta
    assert parcalar[0].meta["office_unit_kind"] == "page"
    assert parcalar[0].meta["source_address"] == "pdf:page:1#ocr:1"
    metric = MetrikKaydi.objects.filter(dokuman=doc, olay_turu="multiformat_chunk_created").latest("id")
    assert metric.skor_ozeti["format"] == "pdf"
    assert "Ilk PDF OCR satiri" not in str(metric.skor_ozeti)


def test_ocr_quality_score_bos_ve_gurultulu_metin_icin_dusuk_kalir():
    bos = ocr.analyze_ocr_quality("")
    gurultu = ocr.analyze_ocr_quality("|| -- ?? ~~")

    assert bos["ocr_quality_score"] == 0.0
    assert bos["ocr_quality_reason"] == "empty_ocr"
    assert bos["ocr_confidence_band"] == "dusuk"
    assert bos["ocr_warning"] == "low_quality_ocr"
    assert gurultu["ocr_quality_score"] < 0.4
    assert gurultu["ocr_confidence_band"] == "dusuk"
    assert gurultu["weak_content"] is True


def test_ocr_quality_score_kisa_ama_anlamli_icerigi_tamamen_oldurmez():
    analiz = ocr.analyze_ocr_quality("JWT token")

    assert analiz["ocr_quality_score"] >= 0.42
    assert analiz["ocr_short_meaningful"] is True
    assert analiz["gate_ok"] is True
    assert analiz["ocr_confidence_band"] in {"dusuk", "orta", "yuksek"}
    assert analiz["ocr_warning"] == ""


def test_ocr_quality_score_marks_fragmented_and_upper_cluster_noise():
    analiz = ocr.analyze_ocr_quality("A B C D E\nABC DEF GHI JKL\n1 2 3 4 5")

    assert analiz["ocr_quality_score"] < 0.5
    assert analiz["ocr_single_char_token_ratio"] > 0.3
    assert analiz["ocr_upper_cluster_ratio"] > 0.3
    assert analiz["ocr_warning"] in {"single_char_fragmentation", "upper_cluster_noise", "low_quality_ocr"}
    assert analiz["gate_ok"] is False


def test_ocr_quality_score_marks_broken_lines_and_column_noise():
    analiz = ocr.analyze_ocr_quality(
        "JWT\nakisi\nyenileme-\nkontrolu\n\nKOD 01 TBL 02 NET 03 TOP 04"
    )

    assert analiz["ocr_broken_line_ratio"] > 0.3
    assert analiz["ocr_column_noise_ratio"] > 0.0
    assert analiz["ocr_warning"] in {"broken_lines", "column_noise", "low_quality_ocr"}
    assert analiz["weak_content"] is True


def test_ocr_quality_score_does_not_flag_short_meaningful_two_line_text_as_broken():
    analiz = ocr.analyze_ocr_quality("Gorsel OCR metni\n\nAksiyon maddeleri")

    assert analiz["ocr_broken_line_ratio"] < 0.45
    assert analiz["ocr_warning"] != "broken_lines"
    assert analiz["ocr_quality_score"] >= 0.5


def test_ocr_ingestion_kayit_yoksa_sahte_parcalandi_yazmaz(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _ocr_doc_olustur(test_kullanicisi)

    monkeypatch.setattr("dokuman.services.ocr.extract_text_from_image", lambda path: "Tek anlamli OCR parcasi")
    monkeypatch.setattr(ocr.Parca.objects, "bulk_create", lambda bulk: None)

    ocr.gorseli_ocr_ile_parcala_ve_kaydet(doc)
    doc.refresh_from_db()

    assert doc.durum == "hata"
    assert doc.parcalar.count() == 0
    assert "kaydedilemedi" in doc.hata.lower()


def test_ocr_ingestion_dusuk_kaliteli_gurultuyu_basari_gibi_isaretlemez(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _ocr_doc_olustur(test_kullanicisi)

    monkeypatch.setattr("dokuman.services.ocr.extract_text_from_image", lambda path: "|| -- ?? ~~")

    ocr.gorseli_ocr_ile_parcala_ve_kaydet(doc)
    doc.refresh_from_db()

    assert doc.durum == "hata"
    assert doc.parcalar.count() == 0
    assert "kalitesi dusuk" in doc.hata.lower() or "anlamsiz" in doc.hata.lower()
