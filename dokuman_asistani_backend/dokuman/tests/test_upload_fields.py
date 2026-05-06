from __future__ import annotations

import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from rest_framework.test import APIClient

from dokuman.models import Dokuman, Parca


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


def _fake_ocr_ingestion_success(doc):
    doc.durum = "parcalandi"
    doc.hata = ""
    doc.save(update_fields=["durum", "hata"])
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="ocr",
        adres="ocr:1",
        metin="Gorsel OCR metni",
        meta={
            "kaynak": "ocr",
            "ocr": True,
            "ocr_kullanildi": True,
            "ocr_kaynak_turu": "image_ocr",
            "ocr_quality_score": 0.781,
            "ocr_confidence_band": "yuksek",
            "ocr_warning": "",
            "ocr_debug_dump": "HAM_OCR_DEBUG",
            "ocr_raw_text": "HAM_OCR_TEXT",
        },
    )
    return doc


def _auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture(autouse=True)
def _clear_upload_throttle_cache():
    cache.clear()
    yield
    cache.clear()


def _zip_upload(name: str, *, entries: dict[str, bytes], content_type: str) -> SimpleUploadedFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, value in entries.items():
            archive.writestr(path, value)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=content_type)


def _docx_upload(name: str = "ornek.docx") -> SimpleUploadedFile:
    return _zip_upload(
        name,
        entries={
            "[Content_Types].xml": b"<Types></Types>",
            "word/document.xml": b"<w:document></w:document>",
        },
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _xlsx_upload(name: str = "ornek.xlsx") -> SimpleUploadedFile:
    return _zip_upload(
        name,
        entries={
            "[Content_Types].xml": b"<Types></Types>",
            "xl/workbook.xml": b"<workbook></workbook>",
        },
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _pptx_upload(name: str = "ornek.pptx") -> SimpleUploadedFile:
    return _zip_upload(
        name,
        entries={
            "[Content_Types].xml": b"<Types></Types>",
            "ppt/presentation.xml": b"<presentation></presentation>",
        },
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


def _png_upload(name: str = "ornek.png") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name,
        (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
            b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01"
            b"\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
        ),
        content_type="image/png",
    )


def _legacy_upload(name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name,
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy-office-content",
        content_type="application/octet-stream",
    )


def test_upload_dosya_alani_ile_basarili(db, test_kullanicisi, gecici_media_root, monkeypatch):
    monkeypatch.setattr("dokuman.views.dokumani_parcala_ve_kaydet", _fake_ingestion_success)
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "baslik": "Dosya Alanli Belge",
            "dosya": _docx_upload(),
        },
        format="multipart",
    )

    assert response.status_code == 201
    assert response.data["durum"] == "parcalandi"
    assert response.data["doc_id"] == response.data["id"]
    assert response.data["parca_sayisi"] == 1
    assert response.data["processing_state"] == "ready"
    assert response.data["status_text"] == "Dokuman hazir."
    assert response.data["warning_code"] == ""
    assert response.data["ingestion_ozeti"]["processing_state"] == "ready"
    assert response.data["ingestion_ozeti"]["status_text"] == "Dokuman hazir."
    assert response.data["ingestion_ozeti"]["parca_uretildi"] is True
    assert response.data["ingestion_ozeti"]["parca_turleri"] == ["bolum"]
    assert Dokuman.objects.filter(owner=test_kullanicisi, id=response.data["id"]).exists()


def test_upload_file_alani_ile_basarili(db, test_kullanicisi, gecici_media_root, monkeypatch):
    monkeypatch.setattr("dokuman.views.dokumani_parcala_ve_kaydet", _fake_ingestion_success)
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/word/",
        {
            "baslik": "File Alanli Belge",
            "file": _docx_upload(),
        },
        format="multipart",
    )

    assert response.status_code == 201
    assert response.data["durum"] == "parcalandi"
    assert response.data["doc_id"] == response.data["id"]
    assert response.data["parca_sayisi"] == 1
    assert response.data["processing_state"] == "ready"
    assert response.data["status_text"] == "Dokuman hazir."
    assert response.data["warning_code"] == ""
    assert response.data["ingestion_ozeti"]["durum"] == "parcalandi"
    assert Dokuman.objects.filter(owner=test_kullanicisi, id=response.data["id"]).exists()


def test_upload_ingestion_ozeti_ocr_sinyalini_guvenli_bicimde_acar(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
    settings,
):
    settings.DOCVERSE_UPLOAD_EXTENSIONS = [".pdf", ".docx", ".png"]
    settings.DOCVERSE_IMAGE_UPLOAD_ENABLED = True
    monkeypatch.setattr("dokuman.views.gorseli_ocr_ile_parcala_ve_kaydet", _fake_ocr_ingestion_success)
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "baslik": "OCR Upload",
            "dosya": _png_upload(),
        },
        format="multipart",
    )

    assert response.status_code == 201
    assert response.data["ocr"] is True
    assert response.data["processing_state"] == "ready"
    assert response.data["status_text"] == "Dokuman hazir. OCR sinyali mevcut."
    assert response.data["warning_code"] == ""
    assert response.data["ingestion_ozeti"]["ocr_kullanildi"] is True
    assert response.data["ingestion_ozeti"]["ocr_kaynak_turu"] == "image_ocr"
    assert response.data["ingestion_ozeti"]["ocr_quality_score"] == 0.781
    assert response.data["ingestion_ozeti"]["ocr_confidence_band"] == "yuksek"
    assert response.data["ingestion_ozeti"]["ocr_warning"] == ""
    assert response.data["ingestion_ozeti"]["ocr_fallback_used"] is False
    assert response.data["ingestion_ozeti"]["processing_state"] == "ready"
    assert response.data["ingestion_ozeti"]["status_text"] == "Dokuman hazir. OCR sinyali mevcut."
    assert "ocr_raw_text" not in response.data["ingestion_ozeti"]
    assert "ocr_debug_dump" not in response.data["ingestion_ozeti"]


def test_upload_ingestion_ozeti_ocrsiz_belgede_guvenli_default_tasir(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    monkeypatch.setattr("dokuman.views.dokumani_parcala_ve_kaydet", _fake_ingestion_success)
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "baslik": "No OCR Upload",
            "dosya": _docx_upload(),
        },
        format="multipart",
    )

    assert response.status_code == 201
    assert response.data["ocr"] is False
    assert response.data["processing_state"] == "ready"
    assert response.data["status_text"] == "Dokuman hazir."
    assert response.data["warning_code"] == ""
    assert response.data["ingestion_ozeti"]["ocr_kullanildi"] is False
    assert response.data["ingestion_ozeti"]["ocr_kaynak_turu"] == ""
    assert response.data["ingestion_ozeti"]["ocr_quality_score"] == 0.0
    assert response.data["ingestion_ozeti"]["ocr_confidence_band"] == ""
    assert response.data["ingestion_ozeti"]["ocr_warning"] == ""
    assert response.data["ingestion_ozeti"]["ocr_fallback_used"] is False
    assert response.data["ingestion_ozeti"]["processing_state"] == "ready"
    assert response.data["ingestion_ozeti"]["status_text"] == "Dokuman hazir."


def test_upload_dosya_yoksa_anlamli_hata_doner(db, test_kullanicisi, gecici_media_root):
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/pdf/",
        {"baslik": "Eksik Dosya"},
        format="multipart",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "dosya veya file zorunlu"
    assert response.data["accepted_fields"] == ["dosya", "file"]
    assert response.data["error_code"] == "missing_upload_file"
    assert response.data["processing_state"] == "failed"
    assert response.data["status_text"] == "dosya veya file zorunlu"


def test_varsayilan_allowlist_pdf_docx_kabul_eder(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    monkeypatch.setattr("dokuman.views.dokumani_parcala_ve_kaydet", _fake_ingestion_success)
    client = _auth_client(test_kullanicisi)
    uploads = [
        _docx_upload("ornek.docx"),
        _xlsx_upload("ornek.xlsx"),
        _pptx_upload("ornek.pptx"),
        SimpleUploadedFile("ornek.pdf", b"%PDF-1.4 guvenli", content_type="application/pdf"),
        SimpleUploadedFile("ornek.txt", b"duz metin icerigi", content_type="text/plain"),
        SimpleUploadedFile("ornek.csv", b"a,b,c\n1,2,3\n", content_type="text/csv"),
        SimpleUploadedFile("ornek.py", b"def kontrol():\n    return True\n", content_type="text/x-python"),
        _legacy_upload("ornek.doc"),
    ]

    for upload in uploads:
        response = client.post(
            "/api/dokuman-asistani/dokumanlar/yukle/",
            {
                "dosya": upload,
            },
            format="multipart",
        )

        assert response.status_code == 201, upload.name
        assert response.data["durum"] == "parcalandi"


def test_varsayilan_allowlist_xlsx_ve_pptx_kabul_eder(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    monkeypatch.setattr("dokuman.views.dokumani_parcala_ve_kaydet", _fake_ingestion_success)
    client = _auth_client(test_kullanicisi)

    xlsx_response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "dosya": _xlsx_upload(),
        },
        format="multipart",
    )
    pptx_response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "dosya": _pptx_upload(),
        },
        format="multipart",
    )

    assert xlsx_response.status_code == 201
    assert pptx_response.status_code == 201


def test_image_flag_kapaliyken_image_upload_reddedilir(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_UPLOAD_EXTENSIONS = [".pdf", ".docx", ".png"]
    settings.DOCVERSE_IMAGE_UPLOAD_ENABLED = False
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "dosya": _png_upload(),
        },
        format="multipart",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Bu dosya türü desteklenmiyor."
    assert ".png" not in response.data["allowed"]
    assert response.data["error_code"] == "unsupported_extension"
    assert response.data["processing_state"] == "failed"


def test_legacy_office_binary_formatlari_destek_kapsamina_girip_kontrolu_ingestion_sonucuyla_sonlanir(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    monkeypatch.setattr("dokuman.views.dokumani_parcala_ve_kaydet", _fake_ingestion_success)
    client = _auth_client(test_kullanicisi)

    for filename in [
        "eski.doc",
        "eski.xls",
        "eski.ppt",
    ]:
        response = client.post(
            "/api/dokuman-asistani/dokumanlar/yukle/",
            {
                "dosya": _legacy_upload(filename),
            },
            format="multipart",
        )

        assert response.status_code == 201
        assert response.data["durum"] == "parcalandi"


def test_legacy_upload_kontrollu_redde_ingestion_ozeti_ekler(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "dosya": SimpleUploadedFile(
                "bozuk.xls",
                b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x01\x02",
                content_type="application/octet-stream",
            ),
        },
        format="multipart",
    )

    assert response.status_code == 422
    assert response.data["durum"] == "hata"
    assert response.data["processing_state"] == "failed"
    assert response.data["status_text"] == "Belge donusturme gerektiriyor."
    assert response.data["warning_code"] == "legacy_conversion_required"
    assert response.data["error_code"] == "upload_ingestion_failed"
    assert response.data["ingestion_ozeti"]["legacy_durum"] == "conversion_required"
    assert response.data["ingestion_ozeti"]["parse_yontemleri"] == ["legacy_conversion_required"]
    assert response.data["ingestion_ozeti"]["processing_state"] == "failed"
    assert response.data["ingestion_ozeti"]["warning_code"] == "legacy_conversion_required"


def test_empty_upload_reddedilir(db, test_kullanicisi, gecici_media_root):
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "dosya": SimpleUploadedFile("bos.pdf", b"", content_type="application/pdf"),
        },
        format="multipart",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Bos dosya yuklenemez."
    assert response.data["status_text"] == response.data["detail"]
    assert response.data["error_code"] == "empty_upload"
    assert response.data["warning_code"] == "empty_upload"


def test_tiny_upload_reddedilir(db, test_kullanicisi, gecici_media_root, settings):
    settings.DOCVERSE_UPLOAD_MIN_BYTES = 12
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "dosya": SimpleUploadedFile("kucuk.pdf", b"%PDF-1.4", content_type="application/pdf"),
        },
        format="multipart",
    )

    assert response.status_code == 400
    assert response.data["error_code"] == "suspicious_upload"
    assert response.data["warning_code"] == "suspicious_upload"
    assert response.data["status_text"] == response.data["detail"]


def test_fake_pdf_ingestiona_gitmeden_reddedilir(db, test_kullanicisi, gecici_media_root):
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "dosya": SimpleUploadedFile("sahte.pdf", b"not-a-real-pdf", content_type="application/pdf"),
        },
        format="multipart",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "PDF dosyasi beklenen imzayi tasimiyor."
    assert response.data["error_code"] == "suspicious_upload"
    assert response.data["warning_code"] == "suspicious_upload"


def test_fake_docx_ingestiona_gitmeden_reddedilir(db, test_kullanicisi, gecici_media_root):
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "dosya": SimpleUploadedFile(
                "sahte.docx",
                b"PK\x03\x04bozuk-zip",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        },
        format="multipart",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "DOCX dosyasi bozuk veya beklenen paket yapisini tasimiyor."
    assert response.data["error_code"] == "suspicious_upload"
    assert response.data["warning_code"] == "suspicious_upload"


def test_fake_image_ingestiona_gitmeden_reddedilir(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_UPLOAD_EXTENSIONS = [".pdf", ".docx", ".png"]
    settings.DOCVERSE_IMAGE_UPLOAD_ENABLED = True
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "dosya": SimpleUploadedFile("sahte.png", b"not-a-real-image", content_type="image/png"),
        },
        format="multipart",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Gorsel dosyasi beklenen imzayi tasimiyor."
    assert response.data["error_code"] == "suspicious_upload"
    assert response.data["warning_code"] == "suspicious_upload"


def test_blocked_extension_reddedilir(db, test_kullanicisi, gecici_media_root):
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {"dosya": SimpleUploadedFile("zararli.exe", b"MZ fake exe", content_type="application/octet-stream")},
        format="multipart",
    )

    assert response.status_code == 400
    assert response.data["error_code"] == "blocked_extension"
    assert response.data["detail"] == "Bu dosya türü güvenlik nedeniyle yüklenemez."


def test_unknown_extension_reddedilir(db, test_kullanicisi, gecici_media_root):
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {"dosya": SimpleUploadedFile("belge.unknown", b"unknown content", content_type="text/plain")},
        format="multipart",
    )

    assert response.status_code == 400
    assert response.data["error_code"] == "unsupported_extension"
    assert response.data["detail"] == "Bu dosya türü desteklenmiyor."


def test_parser_destegi_olmayan_allowlist_dosyasi_kontrollu_doner(db, test_kullanicisi, gecici_media_root):
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {"dosya": SimpleUploadedFile("kitap.epub", b"epub placeholder", content_type="application/octet-stream")},
        format="multipart",
    )

    assert response.status_code == 422
    assert response.data["error_code"] == "parser_not_available"
    assert response.data["durum"] == "parser_desteklenmiyor"
    assert response.data["parca_sayisi"] == 0
    assert response.data["detail"] == "Bu dosya türü yüklenebilir ancak şu anda içerik çıkarma desteği yok."


def test_uppercase_extension_normalize_edilir(db, test_kullanicisi, gecici_media_root, monkeypatch):
    monkeypatch.setattr("dokuman.views.dokumani_parcala_ve_kaydet", _fake_ingestion_success)
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {"dosya": SimpleUploadedFile("TEST.PDF", b"%PDF-1.4 guvenli", content_type="application/pdf")},
        format="multipart",
    )

    assert response.status_code == 201
    assert response.data["durum"] == "parcalandi"


def test_zip_archive_unsafe_path_reddedilir(db, test_kullanicisi, gecici_media_root):
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "dosya": _zip_upload(
                "unsafe.zip",
                entries={"../evil.txt": b"escape"},
                content_type="application/zip",
            )
        },
        format="multipart",
    )

    assert response.status_code == 400
    assert response.data["error_code"] == "archive_unsafe_path"


def test_upload_filename_control_character_helper_reddeder():
    from dokuman.views import _filename_has_control_chars

    assert _filename_has_control_chars("bad\x00name.pdf") is True
    assert _filename_has_control_chars("normal.pdf") is False


def test_oversize_upload_413_doner(db, test_kullanicisi, gecici_media_root, settings):
    settings.DOCVERSE_UPLOAD_MAX_BYTES = 8
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "dosya": SimpleUploadedFile("buyuk.pdf", b"%PDF-1.4 buyuk-icerik", content_type="application/pdf"),
        },
        format="multipart",
    )

    assert response.status_code == 413
    assert response.data["detail"] == "Dosya boyutu siniri asildi."
    assert response.data["error_code"] == "payload_too_large"
    assert response.data["warning_code"] == "payload_too_large"


def test_upload_ingestion_hatasi_path_ve_raw_exception_sizdirmaz(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    def _raise_ingestion(_doc):
        raise RuntimeError(r"C:\secret\invoice.pdf tesseract failed RAW_SECRET")

    monkeypatch.setattr("dokuman.views.dokumani_parcala_ve_kaydet", _raise_ingestion)
    client = _auth_client(test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "dosya": _docx_upload(),
        },
        format="multipart",
    )

    assert response.status_code == 422
    assert response.data["detail"] == "Dosya yuklendi ancak guvenli bicimde islenemedi."
    assert response.data["status_text"] == "Dokuman islenemedi."
    assert response.data["error_code"] == "upload_ingestion_failed"
    assert "secret" not in str(response.data).lower()
    assert "tesseract" not in str(response.data).lower()
    assert "invoice.pdf" not in str(response.data).lower()
    assert response.data["ingestion_ozeti"]["hata"] == "Dosya yuklendi ancak guvenli bicimde islenemedi."


def test_parcalar_endpoint_smoke_icin_doc_id_ve_parca_sayisi_sunar(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    monkeypatch.setattr("dokuman.views.dokumani_parcala_ve_kaydet", _fake_ingestion_success)
    client = _auth_client(test_kullanicisi)

    upload_response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "baslik": "Parcalar Smoke",
            "dosya": _docx_upload(),
        },
        format="multipart",
    )

    doc_id = upload_response.data["doc_id"]

    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc_id}/parcalar/")

    assert response.status_code == 200
    assert response.data["doc_id"] == doc_id
    assert response.data["parca_sayisi"] == 1
    assert response.data["ocr"] is False
    assert response.data["processing_state"] == "ready"
    assert response.data["status_text"] == "Dokuman hazir."
    assert response.data["warning_code"] == ""
    assert response.data["ingestion_ozeti"]["adres_ornekleri"] == ["1"]
    assert response.data["ingestion_ozeti"]["processing_state"] == "ready"
    assert len(response.data["parcalar"]) == 1
    assert response.data["parcalar"][0]["id"] > 0


def test_dokuman_liste_endpoint_additive_durum_alanlari_sunar(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    monkeypatch.setattr("dokuman.views.dokumani_parcala_ve_kaydet", _fake_ingestion_success)
    client = _auth_client(test_kullanicisi)

    upload_response = client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "baslik": "Liste Smoke",
            "dosya": _docx_upload("liste.docx"),
        },
        format="multipart",
    )

    response = client.get("/api/dokuman-asistani/dokumanlar/")

    assert response.status_code == 200
    item = next(obj for obj in response.data if obj["id"] == upload_response.data["id"])
    assert item["parca_sayisi"] == 1
    assert item["ocr"] is False
    assert item["processing_state"] == "ready"
    assert item["status_text"] == "Dokuman hazir."
    assert item["warning_code"] == ""
