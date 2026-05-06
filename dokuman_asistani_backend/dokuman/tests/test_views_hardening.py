from __future__ import annotations

import json

from django.core.files.base import ContentFile
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from dokuman import views
from dokuman import views_ai2
from dokuman import views_ingestion
from dokuman.models import Dokuman, Parca


def _auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _create_doc(user, *, title: str = "Hardening Doc") -> Dokuman:
    doc = Dokuman.objects.create(owner=user, baslik=title, mime="application/pdf", durum="parcalandi")
    doc.dosya.save(f"{title.lower().replace(' ', '_')}.pdf", ContentFile(b"ornek"), save=True)
    return doc


def _create_parca(doc: Dokuman, *, text: str, meta: dict | None = None) -> Parca:
    return Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin=text,
        meta=meta or {},
        zorluk="orta",
        zorluk_skoru=0.42,
    )


def test_dokuman_parcalar_endpoint_redacts_raw_text_and_wide_meta(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = _create_doc(test_kullanicisi, title="Parca Hardening")
    raw_text = ("HAM_PARCA_SECRET " * 40).strip()
    _create_parca(
        doc,
        text=raw_text,
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "quality_score": 0.91,
            "source_address": "raw/source/path",
            "path": "gizli/ham/yol",
            "header_value_pairs": ["token=secret"],
        },
    )

    response = _auth_client(test_kullanicisi).get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/parcalar/")

    assert response.status_code == 200
    item = response.data["parcalar"][0]
    assert item["metin"] != raw_text
    assert len(item["metin"]) < len(raw_text)
    assert item["meta"]["format"] == "code"
    assert item["meta"]["chunk_kind"] == "code_block"
    assert "source_address" not in item["meta"]
    assert "path" not in item["meta"]
    assert "header_value_pairs" not in item["meta"]


def test_dokuman_parcalar_endpoint_exposes_only_response_safe_ocr_meta(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = _create_doc(test_kullanicisi, title="OCR Surface")
    _create_parca(
        doc,
        text="OCR ile uretilen bu parca sadece kisa preview ile donmeli.",
        meta={
            "format": "pdf",
            "chunk_kind": "visual_ocr",
            "ocr": True,
            "ocr_fallback": True,
            "ocr_kullanildi": True,
            "ocr_kaynak_turu": "pdf_ocr_fallback",
            "ocr_quality_score": 0.613,
            "ocr_confidence_band": "orta",
            "ocr_warning": "broken_lines",
            "ocr_raw_text": "HAM_OCR_TEXT",
            "tesseract_debug": "HAM_TESSERACT_DEBUG",
            "source_address": "pdf:page:1#ocr:1",
        },
    )

    response = _auth_client(test_kullanicisi).get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/parcalar/")

    assert response.status_code == 200
    item = response.data["parcalar"][0]
    assert item["meta"]["ocr_kullanildi"] is True
    assert item["meta"]["ocr_kaynak_turu"] == "pdf_ocr_fallback"
    assert item["meta"]["ocr_quality_score"] == 0.613
    assert item["meta"]["ocr_confidence_band"] == "orta"
    assert item["meta"]["ocr_warning"] == "broken_lines"
    assert item["meta"]["ocr_fallback_used"] is True
    assert "ocr_raw_text" not in item["meta"]
    assert "tesseract_debug" not in item["meta"]
    assert "source_address" not in item["meta"]


def test_views_ingestion_parcalar_surface_keeps_preview_but_not_raw_meta(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = _create_doc(test_kullanicisi, title="Legacy Ingestion Surface")
    raw_text = ("DEBUG_INGESTION_SECRET " * 30).strip()
    _create_parca(
        doc,
        text=raw_text,
        meta={
            "format": "pptx",
            "chunk_kind": "slide_summary",
            "code_unit_name": "internal_symbol",
            "source_address": "slide/raw/path",
            "b": 12,
            "e": 84,
        },
    )

    factory = APIRequestFactory()
    request = factory.get(f"/legacy-ingestion/dokumanlar/{doc.id}/parcalar/")
    force_authenticate(request, user=test_kullanicisi)
    response = views_ingestion.DokumanParcalari.as_view()(request, doc_id=doc.id)
    response.render()

    assert response.status_code == 200
    item = response.data[0]
    assert item["metin"] != raw_text
    assert len(item["metin"]) < len(raw_text)
    assert item["meta"]["format"] == "pptx"
    assert item["meta"]["chunk_kind"] == "slide_summary"
    assert "source_address" not in item["meta"]
    assert "b" not in item["meta"]
    assert "e" not in item["meta"]


def test_llm_durum_requires_auth_and_omits_internal_path(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
    settings,
):
    settings.YEREL_MODEL_ETKIN = True
    settings.ANA_GGUF_YOLU = r"C:\secret\models\prod.gguf"

    unauth_response = APIClient().get("/api/dokuman-asistani/llm-durum/")
    assert unauth_response.status_code in {401, 403}

    monkeypatch.setattr("dokuman.views.yerel_modeli_al", lambda: object())
    response = _auth_client(test_kullanicisi).get("/api/dokuman-asistani/llm-durum/")

    assert response.status_code == 200
    assert set(response.data.keys()) == {"yerel_model_etkin", "model_var", "model_yuklu", "durum"}
    assert "ana_gguf_yolu" not in response.data
    assert "hata" not in response.data


def test_ai2_kanitli_cevap_omits_debug_field_and_raw_evidence_text(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _create_doc(test_kullanicisi, title="AI2 No Leak")
    second = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="RAG > Kaynak",
        metin="Kaynakli cevapta secili kanit response'ta ham metin tasimadan gosterilmeli.",
        meta={"path": "RAG > Kaynak"},
    )
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="RAG > Giris",
        metin="Ilk kanit parcasi.",
        meta={"path": "RAG > Giris"},
    )

    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: (
            '{"answer":"Parca kimligi secili kaniti gosterir.",'
            f'"supported":true,"citations":[{second.id}],"missing":[],"followups":[]}}'
        ),
    )

    response = _auth_client(test_kullanicisi).post(
        "/api/dokuman-asistani/ai2/kanitli-cevap/",
        {"question": "Secili kanit nasil gosteriliyor?", "doc_id": doc.id, "top_k": 2},
        format="json",
    )

    assert response.status_code == 200
    assert "_evidence_used" not in response.data
    assert "metin" not in response.data["kullanilan_kanitlar"][0]
    assert response.data["kullanilan_kanitlar"][0]["snippet"]


def test_anlat_kontrol_response_redacts_raw_source_and_user_text(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _create_doc(test_kullanicisi, title="Anlat Kontrol Safety")
    parca = _create_parca(doc, text="HAM_ANLAT_SECRET kaynak metin burada duruyor.")
    monkeypatch.setattr("dokuman.views.chat", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("HAM_DEBUG_PATH")))

    response = _auth_client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{parca.id}/anlat-kontrol/",
        {"yanit": "HAM_OGRENCI_SECRET bu cevabin response echo alanina sizmamasi gerekir."},
        format="json",
    )

    assert response.status_code == 200
    assert "HAM_ANLAT_SECRET" not in str(response.data)
    assert "HAM_OGRENCI_SECRET" not in str(response.data)
    assert "kelime" in response.data["parca"]["snippet"]
    assert "kelime" in response.data["ogrenci_yanit"]


def test_boss_cevap_kontrol_response_redacts_raw_source_and_user_text(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
    settings,
):
    settings.DOCVERSE_BOSS_ENABLED = True
    doc = _create_doc(test_kullanicisi, title="Boss Kontrol Safety")
    parca = _create_parca(doc, text="HAM_BOSS_KAYNAK_SECRET boss kaynak metni.")
    monkeypatch.setattr("dokuman.views.chat", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("HAM_DEBUG_PATH")))

    response = _auth_client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{parca.id}/boss-cevap-kontrol/",
        {
            "gorev": "HAM_GOREV_SECRET gorev tanimi",
            "yanit": "HAM_BOSS_OGRENCI_SECRET ogrenci cevabi",
        },
        format="json",
    )

    assert response.status_code == 200
    assert "HAM_BOSS_KAYNAK_SECRET" not in str(response.data)
    assert "HAM_GOREV_SECRET" not in str(response.data)
    assert "HAM_BOSS_OGRENCI_SECRET" not in str(response.data)
    assert "kelime" in response.data["parca"]["snippet"]
    assert "kelime" in response.data["gorev"]
    assert "kelime" in response.data["ogrenci_yanit"]


def test_anlamadim_debug_ozeti_raw_debug_metinlerini_redact_eder():
    debug = views._anlamadim_v2_debug_ozeti(
        ai2_debug={
            "kullanilan_url": "http://127.0.0.1:11434/v1/chat/completions",
            "model_alias": "gpt-test",
            "yanit_modeli": "gpt-test",
            "ai2_cevap_ozeti": "HAM_DEBUG_RESPONSE detayli model cevabi",
            "hata_mesaji": r"C:\secret\raw_prompt.txt okunamadi",
            "response_status": 500,
        },
        raw_text="ham cevap govdesi",
        obj={"ok": True},
        parsed_ham={},
        parsed_final={},
        fallback_nedeni="ai2_short_output",
        json_bulundu_mu=True,
        json_cozumleme_hatasi="HAM_JSON_PARSE raw body",
        prompt_meta={"parca_metin_uzunlugu": 42, "prompt_parca_metin_uzunlugu": 21},
        merge_analiz={},
    )

    assert debug["kullanilan_url"] == "configured_endpoint"
    assert "HAM_DEBUG_RESPONSE" not in debug["ai2_cevap_ozeti"]
    assert "secret" not in debug["hata_mesaji"].lower()
    assert "HAM_JSON_PARSE" not in debug["json_cozumleme_hatasi"]


def test_parca_anlamadim_v2_debug_param_does_not_open_debug_in_production(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
    settings,
):
    settings.DEBUG = False
    doc = _create_doc(test_kullanicisi, title="Prod Debug Gate")
    parca = _create_parca(doc, text="JWT access token kimlik tasir.")

    monkeypatch.setattr(
        "dokuman.views.chat",
        lambda messages, max_tokens=256: json.dumps(
            {
                "one_liner": "JWT kimlik tasir.",
                "very_simple": "Access token kimlik tasir.",
                "glossary": [{"terim": "JWT", "aciklama": "Kimlik bilgisi tasir."}],
                "steps": ["Tokeni oku.", "Amacini ayir."],
                "examples": ["Oturum acarken kullanilir."],
                "trap": "Refresh ile karistirma.",
                "mini_quiz": [],
                "dokumanda_yok": False,
            },
            ensure_ascii=False,
        ),
    )

    response = _auth_client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{parca.id}/anlamadim-v2/",
        {"mesaj": "acikla", "debug_ai2": True},
        format="json",
    )

    assert response.status_code == 200
    assert "debug_ai2" not in response.data
    assert "view_marker" not in response.data
    assert "kayit_hata" not in response.data


def test_get_parca_for_user_does_not_fallback_to_unowned_lookup_on_query_errors(monkeypatch):
    class _FakeQuerySet:
        def __init__(self, result):
            self._result = result

        def filter(self, **kwargs):
            raise RuntimeError("owner filter unavailable")

        def first(self):
            return self._result

    class _FakeManager:
        def select_related(self, *_args, **_kwargs):
            raise views_ai2.FieldError("dokuman__owner unavailable")

        def filter(self, **kwargs):
            raise RuntimeError("owner field unavailable")

    class _FakeParca:
        objects = _FakeManager()

    monkeypatch.setattr(views_ai2, "Parca", _FakeParca)

    result = views_ai2.get_parca_for_user(99, object())

    assert result is None


def test_get_doc_parcalar_for_user_does_not_fallback_to_unowned_doc_lookup(monkeypatch):
    class _FakeDocManager:
        def filter(self, **kwargs):
            raise RuntimeError("owner lookup unavailable")

    class _FakeDoc:
        objects = _FakeDocManager()

    monkeypatch.setattr(views_ai2, "Dokuman", _FakeDoc)

    doc, parcalar = views_ai2.get_doc_parcalar_for_user(77, object(), limit=5)

    assert doc is None
    assert parcalar == []
