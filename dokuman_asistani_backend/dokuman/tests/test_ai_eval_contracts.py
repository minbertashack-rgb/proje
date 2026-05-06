from __future__ import annotations

import pytest
from django.core.files.base import ContentFile

from dokuman.models import Dokuman, Parca
from dokuman.services.ai_eval_contracts import (
    build_docverse_eval_entry,
    build_explanation_dataset_entry,
    build_fusion_dataset_entry,
    build_quiz_boss_eval_entry,
    build_self_check_dataset_entry,
    get_docverse_eval_extractors,
    get_docverse_eval_contracts,
    redact_docverse_eval_text,
    sanitize_docverse_eval_payload,
)


@pytest.mark.django_db
def test_explanation_eval_contract_redacts_secret_and_drops_denylisted_fields(test_kullanicisi, gecici_media_root):
    doc = Dokuman.objects.create(owner=test_kullanicisi, baslik="Eval Doc", mime="application/pdf", durum="parcalandi")
    doc.dosya.save("eval.pdf", ContentFile(b"ornek"), save=True)
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="HAM_SECRET token akisinda redakte edilmelidir.",
        meta={"chunk_kind": "paragraph", "format": "pdf"},
    )

    payload = {
        "one_liner": "HAM_SECRET kismi response datasetine ham girmemeli.",
        "very_simple": "secret token akisi",
        "note_text": "bu alan tasinmamali",
        "examples": ["JWT ornegi"],
    }
    entry = build_explanation_dataset_entry(parca=parca, payload=payload, retrieval_ozeti={"unsupported_reason": "HAM_SECRET"})

    assert entry["module"] == "explanation"
    assert "note_text" not in entry["target"]
    assert "HAM_SECRET" not in str(entry)
    assert "[redacted]" in entry["source"]["source_text"]


@pytest.mark.django_db
def test_self_check_eval_contract_excludes_user_free_text_and_has_stable_schema(test_kullanicisi, gecici_media_root):
    doc = Dokuman.objects.create(owner=test_kullanicisi, baslik="Self Check Eval", mime="application/pdf", durum="parcalandi")
    doc.dosya.save("selfcheck.pdf", ContentFile(b"ornek"), save=True)
    parca = Parca.objects.create(dokuman=doc, sira=1, tur="bolum", adres="1.1", metin="Kaynak parca")

    entry = build_self_check_dataset_entry(
        parca=parca,
        result={
            "dogru_noktalar": ["dogru"],
            "duzeltilecek_noktalar": ["yanlis"],
            "eksik_noktalar": ["eksik"],
            "self_check_score": 0.72,
            "kullanici_mesaj": "ham kullanici metni yazilmamali",
        },
    )
    contracts = get_docverse_eval_contracts()

    assert entry["source"]["user_free_text_included"] is False
    assert "kullanici_mesaj" not in entry["labels"]
    assert contracts == {
        "contract_version": "1.0",
        "field_allowlist": {
            "explanation": [
                "alternatif_ornek",
                "examples",
                "glossary",
                "mini_quiz",
                "one_liner",
                "steps",
                "tema_bazli_ornek",
                "trap",
                "very_simple",
            ],
            "self_check": [
                "dogru_noktalar",
                "duzeltilecek_noktalar",
                "eksik_noktalar",
                "self_check_score",
            ],
            "fusion": [
                "birlikte_kullanim_ornegi",
                "farklar",
                "kavram_a",
                "kavram_b",
                "mini_soru",
                "ortak_yonler",
            ],
            "quiz_boss": [
                "boss_difficulty_band",
                "boss_difficulty_score",
                "boss_progress_score",
                "boss_retry_count",
                "dogru_sayisi",
                "quiz_readiness_score",
                "sonuc_orani",
                "toplam_soru",
            ],
        },
        "field_denylist": [
            "feedback_text",
            "ham_metin",
            "kullanici_mesaj",
            "note_text",
            "portal_note_text",
            "raw_payload",
            "raw_text",
        ],
        "extraction_points": {
            "explanation": {
                "builder": "build_explanation_dataset_entry",
                "source_fields": ["dokuman_id", "parca_id", "chunk_kind", "format", "source_text"],
                "target_key": "target",
                "user_free_text_included": False,
            },
            "self_check": {
                "builder": "build_self_check_dataset_entry",
                "source_fields": ["dokuman_id", "parca_id", "chunk_kind", "format", "source_text", "user_free_text_included"],
                "target_key": "labels",
                "user_free_text_included": False,
            },
            "fusion": {
                "builder": "build_fusion_dataset_entry",
                "source_fields": ["dokuman_id", "baslik"],
                "target_key": "target",
                "user_free_text_included": False,
            },
            "quiz_boss": {
                "builder": "build_quiz_boss_eval_entry",
                "source_fields": ["dokuman_id", "baslik"],
                "target_key": "labels",
                "user_free_text_included": False,
            },
        },
        "no_leak_preprocessing": {
            "redaction_function": "redact_docverse_eval_text",
            "payload_sanitizer": "sanitize_docverse_eval_payload",
            "user_free_text_included": False,
        },
        "schemas": {
            "explanation": {
                "contract_version": "1.0",
                "required": ["module", "source", "target", "metadata"],
                "target_fields": [
                    "alternatif_ornek",
                    "examples",
                    "glossary",
                    "mini_quiz",
                    "one_liner",
                    "steps",
                    "tema_bazli_ornek",
                    "trap",
                    "very_simple",
                ],
            },
            "self_check": {
                "contract_version": "1.0",
                "required": ["module", "source", "labels", "metadata"],
                "label_fields": [
                    "dogru_noktalar",
                    "duzeltilecek_noktalar",
                    "eksik_noktalar",
                    "self_check_score",
                ],
            },
            "fusion": {
                "contract_version": "1.0",
                "required": ["module", "source", "target", "metadata"],
                "target_fields": [
                    "birlikte_kullanim_ornegi",
                    "farklar",
                    "kavram_a",
                    "kavram_b",
                    "mini_soru",
                    "ortak_yonler",
                ],
            },
            "quiz_boss": {
                "contract_version": "1.0",
                "required": ["module", "source", "labels", "metadata"],
                "label_fields": [
                    "boss_difficulty_band",
                    "boss_difficulty_score",
                    "boss_progress_score",
                    "boss_retry_count",
                    "dogru_sayisi",
                    "quiz_readiness_score",
                    "sonuc_orani",
                    "toplam_soru",
                ],
            },
        },
    }


@pytest.mark.django_db
def test_fusion_and_quiz_boss_eval_contracts_apply_allowlist_and_redaction(test_kullanicisi, gecici_media_root):
    doc = Dokuman.objects.create(owner=test_kullanicisi, baslik="Fusion Eval", mime="application/pdf", durum="parcalandi")
    doc.dosya.save("fusion.pdf", ContentFile(b"ornek"), save=True)
    Parca.objects.create(dokuman=doc, sira=1, tur="bolum", adres="1.1", metin="HAM_SECRET kaynak metin")

    fusion_entry = build_fusion_dataset_entry(
        doc=doc,
        payload={
            "kavram_a": "vektor",
            "kavram_b": "matris",
            "ortak_yonler": ["lineer cebir"],
            "mini_soru": "secret token nerede?",
            "portal_note_text": "ham tasinmamali",
        },
    )
    quiz_boss_entry = build_quiz_boss_eval_entry(
        doc=doc,
        payload={
            "dogru_sayisi": 3,
            "toplam_soru": 5,
            "boss_difficulty_band": "medium",
            "quiz_readiness_score": 0.64,
            "raw_text": "HAM_SECRET",
        },
    )

    assert fusion_entry["module"] == "fusion"
    assert "portal_note_text" not in fusion_entry["target"]
    assert "HAM_SECRET" not in str(fusion_entry)
    assert quiz_boss_entry["module"] == "quiz_boss"
    assert "raw_text" not in quiz_boss_entry["labels"]
    assert quiz_boss_entry["labels"]["dogru_sayisi"] == 3
    assert quiz_boss_entry["labels"]["boss_difficulty_band"] == "medium"


@pytest.mark.django_db
def test_eval_extractor_registry_and_dispatcher_stay_stable(test_kullanicisi, gecici_media_root):
    doc = Dokuman.objects.create(owner=test_kullanicisi, baslik="Dispatcher Eval", mime="application/pdf", durum="parcalandi")
    doc.dosya.save("dispatcher.pdf", ContentFile(b"ornek"), save=True)
    parca = Parca.objects.create(dokuman=doc, sira=1, tur="bolum", adres="1.1", metin="HAM_SECRET dispatcher kaynak metni")

    extractors = get_docverse_eval_extractors()
    dispatched = build_docverse_eval_entry(
        "explanation",
        parca=parca,
        payload={"one_liner": "HAM_SECRET kismini gizle", "note_text": "tasinmamali"},
        retrieval_ozeti={"supported": True},
    )

    assert extractors == {
        "explanation": {
            "builder": "build_explanation_dataset_entry",
            "source_fields": ["dokuman_id", "parca_id", "chunk_kind", "format", "source_text"],
            "target_key": "target",
            "user_free_text_included": False,
        },
        "self_check": {
            "builder": "build_self_check_dataset_entry",
            "source_fields": ["dokuman_id", "parca_id", "chunk_kind", "format", "source_text", "user_free_text_included"],
            "target_key": "labels",
            "user_free_text_included": False,
        },
        "fusion": {
            "builder": "build_fusion_dataset_entry",
            "source_fields": ["dokuman_id", "baslik"],
            "target_key": "target",
            "user_free_text_included": False,
        },
        "quiz_boss": {
            "builder": "build_quiz_boss_eval_entry",
            "source_fields": ["dokuman_id", "baslik"],
            "target_key": "labels",
            "user_free_text_included": False,
        },
    }
    assert dispatched["module"] == "explanation"
    assert "HAM_SECRET" not in str(dispatched)


def test_eval_preprocessing_helpers_redact_and_allowlist():
    assert redact_docverse_eval_text("HAM_SECRET token", limit=80) == "[redacted] [redacted]"
    assert sanitize_docverse_eval_payload(
        {
            "one_liner": "ham metin",
            "raw_text": "tasinmamali",
            "examples": ["secret token", "guvenli"],
        },
        surface="explanation",
    ) == {
        "one_liner": "ham metin",
        "examples": ["[redacted] [redacted]", "guvenli"],
    }


@pytest.mark.django_db
def test_explanation_eval_contract_keeps_shape_stable_when_code_quality_fields_exist(test_kullanicisi, gecici_media_root):
    doc = Dokuman.objects.create(owner=test_kullanicisi, baslik="Code Eval", mime="text/x-python", durum="parcalandi")
    doc.dosya.save("code.py", ContentFile(b"ornek"), save=True)
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="kod",
        adres="code:python:test_function:1",
        metin="def test_create(): pass",
        meta={"chunk_kind": "code_block", "format": "code", "language": "python"},
    )

    entry = build_explanation_dataset_entry(
        parca=parca,
        payload={
            "one_liner": "Kod test akisini acikliyor.",
            "steps": ["Hazirlik", "Cagri", "Dogrulama"],
            "examples": ["HTTP 201 kontrolu."],
            "function_purpose": "Ham kod amaci eval payload shape'ine tasinmamali.",
            "flow_summary": "Hazirlik -> cagri -> assertion",
            "block_comments": ["Ham blok yorumu"],
            "line_comments": ["Ham satir yorumu"],
            "raw_text": "HAM_SECRET",
        },
        retrieval_ozeti={"unsupported_reason": "HAM_SECRET"},
    )

    assert set(entry["target"]) == {"one_liner", "steps", "examples"}
    assert "function_purpose" not in entry["target"]
    assert "flow_summary" not in entry["target"]
    assert "block_comments" not in entry["target"]
    assert "line_comments" not in entry["target"]
    assert "HAM_SECRET" not in str(entry)
