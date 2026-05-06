"""Fallback aciklamalarinin kod, tablo ve gorsel yuzeylerde tutarli kaldigini dogrulayan testler."""

from __future__ import annotations

import json

import pytest
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.ai2.prompts import build_anlamadim_prompt
from dokuman.models import Dokuman, MetrikKaydi, Parca
from dokuman.services.code_structure import build_code_segments
from dokuman.views import _anlamadim_chunk_context, _fallback_sections_v2
from .code_explanation_benchmark_data import (
    CODE_EXPLANATION_AXIS_MATRIX,
    CODE_EXPLANATION_BENCHMARK_CASES,
    CODE_EXPLANATION_REQUIRED_COVERAGE_TAGS,
)
from .code_explanation_benchmark_helpers import (
    evaluate_code_explanation_case,
    format_code_explanation_result,
    summarize_code_explanation_results,
)


def test_table_fallback_builds_special_explanation_and_themed_examples():
    # Hazırlık: İçinde tablo başlıkları ve satır verileri olan ham metin ile tablo bağlamını (chunk_context) oluştur.
    text = "Basliklar: Urun | Adet | Tutar\nSatir 2: Elma | 4 | 120"
    context = _anlamadim_chunk_context(
        text=text,
        adres="xlsx:sheet:siparisler#rows:2-2",
        meta={"format": "xlsx", "chunk_kind": "table_rows", "header_preview": ["Urun", "Adet", "Tutar"]},
        tur="tablo",
    )

    # Çağrı: Tablo formatına özel kural tabanlı fallback açıklamasını üret.
    out = _fallback_sections_v2(text, "oyun", "adim_adim", "baslangic", chunk_context=context)

    # Doğrulama: Tablo formatına özel uyarıların ve tema bazlı (oyun) örneklerin çıktıda yer aldığını teyit et.
    assert "kritik sutunlar" in out["very_simple"].lower()
    assert "Bu tablo ne diyor" in out["examples"][0]
    assert out["tema_bazli_ornek"]
    assert out["alternatif_ornek"]


def test_visual_fallback_mentions_main_purpose_and_ocr_summary():
    # Hazirlik: OCR kaynakli kisa gorsel aciklamasi ve visual_ocr chunk baglami kur.
    text = "JWT diyagrami giris ve yenileme adimlarini gosteriyor."
    context = _anlamadim_chunk_context(
        text=text,
        adres="ocr:1",
        meta={"ocr": True, "format": "image", "chunk_kind": "visual_ocr"},
        tur="ocr",
    )

    # Cagri: Gorsel odakli fallback aciklamasini uret.
    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    # Dogrulama: Gorselin amaci ve OCR ozeti ayni sade aciklamada gorunmeli.
    assert "gorselin ana amaci" in out["very_simple"].lower()
    assert "ocr ozeti" in out["very_simple"].lower()


def test_presentation_fallback_mentions_main_message_and_key_bullets():
    # Hazirlik: Bullet agirlikli slayt metni ve presentation baglami sagla.
    text = "Madde 1: Problem tanimi\nMadde 2: Cozum yaklasimi\nMadde 3: Beklenen etki"
    context = _anlamadim_chunk_context(
        text=text,
        adres="pptx:slide:2:bullets:1",
        meta={"format": "pptx", "chunk_kind": "slide_bullets", "slide_title": "Proje Ozeti"},
        tur="slayt",
    )

    # Cagri: Slayt fallback'inin mesaj ve ana maddeleri ayrimasini iste.
    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    # Dogrulama: Chunk kind presentation olarak algilanmali ve cikti ana mesaji ozetlemeli.
    assert context["kind"] == "presentation"
    assert "ana mesaji" in out["examples"][0].lower()
    assert "onemli maddeler" in out["very_simple"].lower()
    assert "slaytin vermek istedigi mesaj" in out["very_simple"].lower()


def test_code_fallback_for_api_test_separates_setup_call_and_assertions():
    text = """def test_author_can_create_document_with_hash(self):
    self.client.force_authenticate(user=self.author_user)
    data = {"title": "DocVerse Manifesto", "content": "Our mission is to manage docs."}
    response = self.client.post('/api/v1/author/documents/', data)
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    self.assertIn('version_hash', response.data)
    self.document.refresh_from_db()
    self.assertEqual(self.document.status, 'DRAFT')
"""
    # Hazirlik: API testi icin satir araligi ve sembol bilgisi ver.
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:python:code_block:2",
        meta={"format": "code", "chunk_kind": "code_block", "symbol": "test_author_can_create_document_with_hash", "line_start": 18, "line_end": 25},
        tur="kod",
    )

    # Cagri: fallback'in arrange / act / assert aciklamalarini uretmesini iste.
    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    # Dogrulama: hazirlik, payload, cagri ve final state kontrolleri ayri gorunmeli.
    assert "post" in out["one_liner"].lower()
    assert any("Hazirlik" in item for item in out["steps"])
    assert any("Input" in item for item in out["steps"])
    assert any("Cagri" in item for item in out["steps"])
    assert any("Dogrulama" in item for item in out["steps"])
    assert any("Assertion mantigi" in item for item in out["examples"])
    assert any(item["terim"] in {"authenticate", "POST cagrisi", "assertion", "final state assert"} for item in out["glossary"])
    assert "test ortamini kurar" in out["function_purpose"].lower()
    assert "hazirlik" in out["flow_summary"].lower()
    assert any("payload" in item.lower() for item in out["block_comments"])
    assert any("yetkilendirir" in item.lower() for item in out["line_comments"])
    assert any("http 201" in item.lower() for item in out["line_comments"])
    assert any("version_hash" in item.lower() for item in out["line_comments"])
    assert any("draft" in item.lower() for item in out["line_comments"])


def test_code_fallback_for_python_api_client_mock_and_nested_assertions():
    text = """def test_create_document_with_mock(api_client, author_user, monkeypatch):
    api_client.force_authenticate(user=author_user)
    monkeypatch.setattr(notifications, 'send', fake_send)
    payload = {"title": "DocVerse"}
    response = api_client.post('/api/v1/documents/', payload, format='json')
    assert response.status_code == 201
    if response.data['status'] == 'draft':
        assert response.data['title'] == 'DocVerse'
    document.refresh_from_db()
    assert document.status == 'draft'
"""
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:python:test_function:9",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "python",
            "code_language": "python",
            "code_unit_kind": "test_function",
            "code_unit_name": "test_create_document_with_mock",
            "test_step_kind": "assertion",
            "line_start": 40,
            "line_end": 49,
        },
        tur="kod",
    )

    # Cagri: API testine ait nested assertion ve mock akislarini fallback'ten iste.
    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    # Dogrulama: Mock, POST cagrisi ve kosullu assertion katmanlari ayri ayri gorunmeli.
    assert any("Hazirlik" in item for item in out["steps"])
    assert any("Cagri" in item for item in out["steps"])
    assert any("Dogrulama" in item for item in out["steps"])
    assert any("mock" in item.lower() for item in out["block_comments"])
    assert any("POST" in item for item in out["line_comments"])
    assert any("deterministik" in item.lower() for item in out["line_comments"])
    assert any("hangi kosul saglandiginda" in item.lower() for item in out["line_comments"])
    assert any("HTTP 201" in item for item in out["line_comments"])
    assert any("'title'" in item or "title" in item.lower() for item in out["line_comments"])
    assert any("DRAFT" in item for item in out["line_comments"])
    assert "assertion zinciri" in out["very_simple"].lower()
    assert "satir 40-49" in out["flow_summary"].lower()
    assert "assertion" in out["flow_summary"].lower()


def test_code_fallback_for_python_function_tracks_input_flow_and_return():
    text = """def normalize_username(raw_name):
    cleaned = raw_name.strip().lower()
    if not cleaned:
        return "anonymous"
    return cleaned.replace(" ", "_")
"""
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:python:code_block:3",
        meta={"format": "code", "chunk_kind": "code_block", "symbol": "normalize_username", "line_start": 40, "line_end": 44},
        tur="kod",
    )

    # Cagri: Kisa bir normalize helper'inda girdi, kosul ve return akislarini uret.
    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    # Dogrulama: Veri akisi ve sonuc yorumu function explanation yuzeyine tasinmali.
    assert "fonksiyon" in out["one_liner"].lower() or "normalize_username" in out["one_liner"]
    assert "veri akisi" in out["very_simple"].lower()
    assert any("Girdi" in item for item in out["steps"])
    assert any("Beklenen sonuc" in item for item in out["steps"])
    assert any("return" in item.lower() for item in out["examples"])
    assert "normalize_username" in out["function_purpose"]
    assert "girdi" in out["flow_summary"].lower()
    assert any("temel akis" in item.lower() or "kosul" in item.lower() for item in out["block_comments"])
    assert any("dondurur" in item.lower() for item in out["line_comments"])


def test_code_fallback_for_python_function_mentions_nested_loop_and_condition_blocks():
    text = """def collect_active_ids(users):
    active_ids = []
    for user in users:
        if user["active"]:
            active_ids.append(user["id"])
    return active_ids
"""
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:python:code_block:11",
        meta={"format": "code", "chunk_kind": "code_block", "symbol": "collect_active_ids", "line_start": 90, "line_end": 95},
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "iterasyon" in out["flow_summary"].lower()
    assert any("iterasyon" in item.lower() for item in out["block_comments"])
    assert any("hangi dalin calisacagini" in item.lower() for item in out["line_comments"])
    assert any("iterasyonu baslatir" in item.lower() for item in out["line_comments"])


def test_code_fallback_for_python_function_mentions_helper_flow_and_conditional_return():
    text = """def build_username(raw_name, default_factory):
    cleaned = normalize_username(raw_name)
    if not cleaned:
        return default_factory()
    return cleaned
"""
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:python:code_block:12",
        meta={"format": "code", "chunk_kind": "code_block", "symbol": "build_username", "line_start": 96, "line_end": 100},
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "helper/ara islem" in out["flow_summary"].lower()
    assert any("helper" in item.lower() for item in out["block_comments"] + out["line_comments"])
    assert any("default_factory" in item.lower() or "cagrisi ile uretilen sonucu" in item.lower() for item in out["line_comments"])
    assert any("return" in item.lower() for item in out["examples"])


def test_code_fallback_for_class_separates_setup_state_and_methods():
    text = """class Cart:
    def __init__(self, items):
        self.items = items

    def total(self):
        return sum(item["price"] for item in self.items)
"""
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:python:code_block:4",
        meta={"format": "code", "chunk_kind": "code_block", "symbol": "Cart", "line_start": 60, "line_end": 65},
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "sinif" in out["very_simple"].lower()
    assert any("Kurulum" in item for item in out["steps"])
    assert any("Metotlar" in item for item in out["steps"])
    assert any("Durum kullanimi" in item for item in out["steps"])
    assert any("self" in item.lower() for item in out["examples"])
    assert "sinif" in out["function_purpose"].lower()
    assert "ilk durum" in out["flow_summary"].lower() or "kurulumu" in out["flow_summary"].lower()
    assert any("davranis" in item.lower() for item in out["block_comments"])
    assert any("self" in item.lower() or "__init__" in item.lower() for item in out["line_comments"])


def test_code_fallback_for_class_distinguishes_initial_state_and_state_update():
    text = """class Cart:
    def __init__(self, items):
        self.items = items

    def add_item(self, item):
        self.items = self.items + [item]
        return len(self.items)
"""
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:python:code_block:13",
        meta={"format": "code", "chunk_kind": "code_block", "symbol": "Cart", "line_start": 66, "line_end": 72},
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert any("ilk durumu olarak saklar" in item.lower() for item in out["line_comments"])
    assert any("yeni veri ekleyerek" in item.lower() or "mevcut deger uzerinden" in item.lower() for item in out["line_comments"])
    assert any("state degisimi" in item.lower() for item in out["block_comments"])


def test_code_fallback_for_python_method_explains_state_change_and_branch():
    text = """class Cart:
    def add_item(self, item):
        if not item:
            return None
        self.items = self.items + [item]
        return len(self.items)
"""
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:python:code_block:4",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "symbol": "add_item",
            "code_language": "python",
            "code_unit_kind": "method",
            "parent_unit": "Cart",
            "line_start": 70,
            "line_end": 75,
        },
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "state" in out["function_purpose"].lower() or "method" in out["function_purpose"].lower()
    assert "kosul" in out["flow_summary"].lower()
    assert any("state" in item.lower() or "items" in item.lower() for item in out["line_comments"])
    assert any("hangi durumda" in item.lower() or "hangi kosul" in item.lower() for item in out["line_comments"])
    assert any("davranis" in item.lower() or "kosul" in item.lower() for item in out["block_comments"])


def test_code_fallback_for_sql_query_explains_select_from_where():
    # Hazirlik: SELECT/FROM/WHERE akisini tasiyan SQL chunk baglami kur.
    text = """SELECT id, status, total_amount
FROM orders
WHERE status = 'APPROVED'
ORDER BY created_at DESC;"""
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:sql:code_block:1",
        meta={"format": "code", "chunk_kind": "code_block", "symbol": "approved_orders", "language": "sql", "line_start": 5, "line_end": 8},
        tur="kod",
    )

    # Cagri: SQL aciklamasinin clause akisini ve tablo rolunu ayirmasini iste.
    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    # Dogrulama: SELECT/FROM/WHERE mantigi hem adimlarda hem de line comments'te gorunmeli.
    assert "sql sorgusu" in out["one_liner"].lower() or "sorgu" in out["one_liner"].lower()
    assert any("Secim" in item for item in out["steps"])
    assert any("Kaynak" in item for item in out["steps"])
    assert any("Filtre" in item for item in out["steps"])
    assert any(item["terim"] == "SELECT" for item in out["glossary"])
    assert any("WHERE" in item or "where" in item.lower() for item in out["examples"])
    assert "sql sorgusu" in out["function_purpose"].lower()
    assert "select" in out["flow_summary"].lower()
    assert any("tablo" in item.lower() for item in out["block_comments"])
    assert any("kolon" in item.lower() for item in out["line_comments"])
    assert any("filtreler" in item.lower() for item in out["line_comments"])


def test_code_fallback_for_frontend_function_explains_event_state_and_render():
    # Hazirlik: Event, fetch ve render iceren frontend function chunk'i kur.
    text = """async function handleSubmit(event) {
  event.preventDefault();
  const response = await fetch('/api/save', { method: 'POST' });
  setSaved(true);
  return <SuccessBanner saved={saved} />;
}"""
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:javascript:code_block:5",
        meta={"format": "code", "chunk_kind": "code_block", "symbol": "handleSubmit", "language": "javascript", "line_start": 70, "line_end": 74},
        tur="kod",
    )

    # Cagri: Frontend fallback state degisimi ve UI sonucunu aciklasin.
    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    # Dogrulama: Event isleme, API cagrisi ve render etkisi ayni explanation setinde secilmeli.
    assert "frontend" in out["one_liner"].lower() or "arayuz" in out["one_liner"].lower()
    assert any("Girdi" in item for item in out["steps"])
    assert any("Islem" in item for item in out["steps"])
    assert any("Beklenen sonuc" in item for item in out["steps"])
    assert any("frontend/script" in item.lower() or "gorunen sonuc" in item.lower() for item in out["examples"])
    assert "ui sonucuna" in out["function_purpose"].lower() or "arayuz" in out["function_purpose"].lower()
    assert "render" in out["flow_summary"].lower()
    assert any("state" in item.lower() or "api" in item.lower() for item in out["block_comments"])
    assert any("arayuz durumunu gunceller" in item.lower() or "api cagrisi" in item.lower() for item in out["line_comments"])


def test_code_fallback_for_config_block_explains_section_and_key_purpose():
    text = '"api": {\n  "base": "/v1",\n  "token": "secret"\n}'
    # Hazirlik: config section'i olarak etiketlenmis guvenli bir chunk baglami kur.
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:json:section:1",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "json",
            "code_language": "json",
            "code_unit_kind": "section",
            "code_unit_name": "api",
            "code_purpose_hints": ["config", "network"],
            "line_start": 1,
            "line_end": 4,
        },
        tur="kod",
    )

    # Dogrulama: section ve key-value amaci uydurma yapmadan aciklanmali.
    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "config" in out["one_liner"].lower() or "ayar" in out["one_liner"].lower()
    assert any("Group/section" in item for item in out["steps"])
    assert any("key-value" in item.lower() for item in out["examples"])
    assert any(item["terim"] in {"section", "network"} for item in out["glossary"])
    assert "anahtar-deger" in out["function_purpose"].lower()
    assert "config anahtari" in out["flow_summary"].lower()
    assert any("config grubu" in item.lower() for item in out["block_comments"])
    assert any("config anahtari" in item.lower() for item in out["line_comments"])


def test_code_fallback_for_config_block_mentions_environment_override_without_overclaiming():
    text = "profiles:\n  environment: prod\n  api_base: ${API_BASE}\n"
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:yaml:section:11",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "yaml",
            "code_language": "yaml",
            "code_unit_kind": "section",
            "code_unit_name": "profiles",
            "code_purpose_hints": ["config", "environment_override"],
            "line_start": 1,
            "line_end": 3,
        },
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "config" in out["one_liner"].lower()
    assert any("environment override" in item.lower() for item in out["line_comments"])
    assert any("profiles" in item.lower() for item in out["line_comments"])
    assert "ayar amaci" in out["function_purpose"].lower()
    assert "gorunen deger" in out["flow_summary"].lower()


def test_code_fallback_for_config_block_highlights_section_flag_path_and_threshold_types():
    text = "routes:\n  api: /v1\nflags:\n  beta: true\nlimits:\n  timeout: 30\n"
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:yaml:section:15",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "yaml",
            "code_language": "yaml",
            "code_unit_kind": "section",
            "code_unit_name": "routes",
            "code_purpose_hints": ["config", "network"],
            "line_start": 1,
            "line_end": 6,
        },
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "route/path" in out["one_liner"].lower() or "boolean flag" in out["one_liner"].lower()
    assert any("deger tipi" in item.lower() for item in out["steps"])
    assert any("section/group" in item.lower() for item in out["line_comments"])
    assert any("boolean flag" in item.lower() for item in out["line_comments"])
    assert any("route/path" in item.lower() for item in out["line_comments"])
    assert any("esik/deger" in item.lower() for item in out["line_comments"])


def test_code_fallback_for_shell_assignment_api_and_pipeline_explains_visible_flow():
    text = """function Invoke-Test {
  $endpoint = "https://example.test"
  $response = Invoke-RestMethod -Uri $endpoint
  curl $endpoint | jq '.items'
  if ($response.ok) { Write-Host "ok" }
}"""
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:powershell:function:11",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "powershell",
            "code_language": "powershell",
            "code_unit_kind": "function",
            "code_unit_name": "Invoke-Test",
            "code_purpose_hints": ["shell", "api_call"],
            "line_start": 20,
            "line_end": 25,
        },
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "shell" in out["one_liner"].lower()
    assert any("response degiskeninde toplar" in item.lower() for item in out["line_comments"])
    assert any("pipeline" in item.lower() and "aktarir" in item.lower() for item in out["line_comments"])
    assert "command/api" in out["flow_summary"].lower()
    assert any("dis cagrilar" in item.lower() for item in out["block_comments"])


def test_code_fallback_for_powershell_env_and_process_mentions_specific_side_effects():
    text = """function Invoke-Deploy {
  $env:API_BASE = "https://example.test"
  $response = Invoke-RestMethod -Uri $env:API_BASE
  if ($response.ok) { Start-Process notepad.exe }
}"""
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:powershell:function:12",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "powershell",
            "code_language": "powershell",
            "code_unit_kind": "function",
            "code_unit_name": "Invoke-Deploy",
            "code_purpose_hints": ["shell", "api_call"],
            "line_start": 1,
            "line_end": 4,
        },
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "powershell" in out["one_liner"].lower()
    assert "environment" in out["flow_summary"].lower()
    assert any("environment degiskenini ayarlar" in item.lower() for item in out["line_comments"])
    assert any("start-process" in item.lower() for item in out["line_comments"])
    assert any("environment blogu" in item.lower() for item in out["block_comments"])


def test_code_fallback_for_markup_block_explains_structure_without_inventing_behavior():
    text = "<section>\n  <form>\n    <input />\n  </form>\n</section>"
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:html:markup_block:1",
        meta={"format": "code", "chunk_kind": "code_block", "language": "html", "code_language": "html", "code_unit_kind": "markup_block", "code_unit_name": "section", "line_start": 10, "line_end": 14},
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "markup" in out["one_liner"].lower() or "html" in out["very_simple"].lower()
    assert any("Markup block" in item for item in out["steps"])
    assert any("yapi" in item.lower() for item in out["examples"])
    assert "script davranisi" in out["trap"].lower()
    assert "sayfa iskeletini" in out["function_purpose"].lower()
    assert "tagler" in out["flow_summary"].lower() or "yapisal" in out["flow_summary"].lower()
    assert any("iskeleti" in item.lower() for item in out["block_comments"])
    assert any("form blogu" in item.lower() or "input alanini" in item.lower() for item in out["line_comments"])


def test_code_fallback_for_markup_block_mentions_semantic_roles():
    text = "<main>\n  <nav>\n    <a href='/home'>Home</a>\n  </nav>\n  <section>\n    <form>\n      <label>Email</label>\n      <input type='email' />\n    </form>\n  </section>\n</main>"
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:html:markup_block:11",
        meta={"format": "code", "chunk_kind": "code_block", "language": "html", "code_language": "html", "code_unit_kind": "markup_block", "code_unit_name": "main", "line_start": 1, "line_end": 10},
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "semantic" in out["flow_summary"].lower()
    assert any("semantic rol" in item.lower() for item in out["steps"])
    assert any("navigasyon" in item.lower() or "main" in item.lower() for item in out["line_comments"] + out["block_comments"])
    assert any("email input" in item.lower() or "etiketi" in item.lower() for item in out["line_comments"])


def test_code_fallback_for_css_rule_mentions_layout_and_spacing_roles():
    text = ".notice {\n  color: red;\n  display: flex;\n  gap: 8px;\n}"
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:css:style:11",
        meta={"format": "code", "chunk_kind": "code_block", "language": "css", "code_language": "css", "code_unit_kind": "style_rule", "code_unit_name": ".notice", "line_start": 1, "line_end": 4},
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "layout" in out["function_purpose"].lower()
    assert "spacing" in out["flow_summary"].lower()
    assert any("layout" in item.lower() for item in out["block_comments"] + out["line_comments"])
    assert any("spacing" in item.lower() or "gap" in item.lower() for item in out["line_comments"])


def test_code_fallback_for_html_block_mentions_script_and_style_separation():
    text = """<section>
  <style>
    .notice { color: red; }
  </style>
  <form>
    <input />
  </form>
  <script>
    fetch('/api/save')
  </script>
</section>"""
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:html:markup_block:9",
        meta={"format": "code", "chunk_kind": "code_block", "language": "html", "code_language": "html", "code_unit_kind": "markup_block", "code_unit_name": "section", "line_start": 1, "line_end": 10},
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert any("script/style" in item.lower() or "script" in item.lower() for item in out["steps"])
    assert any("script blogunu" in item.lower() for item in out["line_comments"])
    assert any("style blogunu" in item.lower() for item in out["line_comments"])
    assert "script davranisi" in out["trap"].lower()


def test_code_fallback_for_nested_js_callback_mentions_condition_and_avoids_fake_render():
    text = """function setupSave(button) {
  button.addEventListener("click", async () => {
    const response = await fetch("/api/save");
    if (response.ok) { setSaved(true); }
  });
}"""
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:javascript:code_block:14",
        meta={"format": "code", "chunk_kind": "code_block", "language": "javascript", "code_language": "javascript", "code_unit_kind": "function", "code_unit_name": "setupSave", "line_start": 1, "line_end": 5},
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "render" not in out["flow_summary"].lower()
    assert "kosul" in out["flow_summary"].lower()
    assert "state sonucuna" in out["function_purpose"].lower()
    assert any("click" in item.lower() for item in out["line_comments"])
    assert any("state guncellemesi" in item.lower() or "setsaved" in item.lower() for item in out["line_comments"])


def test_code_fallback_for_shell_block_explains_command_api_and_control_flow():
    text = """function Invoke-Test {
  $endpoint = 'https://example.test'
  $response = Invoke-RestMethod -Uri $endpoint
  if ($response.ok) { Write-Host 'ok' }
}"""
    # Hazirlik: shell fonksiyonu icin language ve purpose hint meta'larini ver.
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:powershell:function:1",
        meta={"format": "code", "chunk_kind": "code_block", "language": "powershell", "code_language": "powershell", "code_unit_kind": "function", "code_unit_name": "Invoke-Test", "code_purpose_hints": ["shell", "api_call"], "line_start": 20, "line_end": 24},
        tur="kod",
    )

    # Dogrulama: komut, API cagrisi ve kosul blogu ayni aciklama yuzeyinde secilebilmeli.
    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "komut" in out["one_liner"].lower() or "shell" in out["very_simple"].lower()
    assert any("Function" in item for item in out["steps"])
    assert any("Command/API" in item for item in out["steps"])
    assert any("Komut ornegi" in item or "komut, API ve kontrol akisinin" in item for item in out["examples"])
    assert "sirali sekilde calistirir" in out["function_purpose"].lower()
    assert "kontrol akisi" in out["flow_summary"].lower()
    assert any("degisken" in item.lower() for item in out["block_comments"])
    assert any("endpoint degiskenini hazirlar" in item.lower() or "kontrol akisini yonetir" in item.lower() for item in out["line_comments"])


def test_code_fallback_for_shell_pipeline_mentions_command_order_and_pipeline():
    text = """function Sync-Items {
  $endpoint = 'https://example.test/items'
  curl $endpoint | jq '.items'
  if ($LASTEXITCODE -ne 0) { Write-Host 'fail' }
}"""
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:powershell:function:9",
        meta={"format": "code", "chunk_kind": "code_block", "language": "powershell", "code_language": "powershell", "code_unit_kind": "function", "code_unit_name": "Sync-Items", "code_purpose_hints": ["shell", "api_call"], "line_start": 1, "line_end": 4},
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert any("Hazirlik" in item for item in out["steps"])
    assert any("Command/API" in item for item in out["steps"])
    assert "function" in out["flow_summary"].lower()
    assert "command/api" in out["flow_summary"].lower()
    assert any("pipeline" in item.lower() or "dis cagrilar" in item.lower() for item in out["block_comments"])
    assert any("curl" in item.lower() or "endpoint" in item.lower() for item in out["line_comments"])


def test_code_fallback_for_sql_update_explains_statement_purpose_and_filter():
    text = "UPDATE users SET active = 0 WHERE id = 9;"
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:sql:sql_update:2",
        meta={"format": "code", "chunk_kind": "code_block", "language": "sql", "code_language": "sql", "code_unit_kind": "sql_update", "code_unit_name": "update_users", "line_start": 30, "line_end": 30},
        tur="kod",
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic", chunk_context=context)

    assert "update" in out["one_liner"].lower() or "sql" in out["one_liner"].lower()
    assert any("statement purpose" in item.lower() for item in out["steps"])
    assert "hedef tabloya uygular" in out["function_purpose"].lower() or "yazma" in out["flow_summary"].lower()
    assert any("statement" in item.lower() or "tablo" in item.lower() for item in out["line_comments"] + out["block_comments"])


def test_code_prompt_mentions_test_phases_and_assertion_reasoning():
    # Hazirlik: Python API testine ait profile ve chunk metnini prompt katmanina ver.
    profile = {
        "tema": "genel",
        "tarz": "adim_adim",
        "seviye": "orta",
        "mesaj": "Bu testi acikla.",
        "chunk_kind": "code",
        "chunk_title": "test_author_can_create_document_with_hash",
        "code_unit_kind": "test_function",
        "test_step_kind": "assertion",
        "code_subtype": "api_test",
        "language": "python",
        "line_start": 18,
        "line_end": 25,
    }

    chunk = """def test_author(...):
    self.client.force_authenticate(user=self.author_user)
    response = self.client.post('/api/documents/', data)
"""
    # Cagri: Kod-aciklama prompt'unu olusturup tum sistem/user mesajlarini birlestir.
    messages = build_anlamadim_prompt("code:python:code_block:2", chunk, 12, profile)
    prompt_text = "\n".join(item["content"] for item in messages)

    # Dogrulama: Prompt test fazlari, assertion gerekcesi ve line-aware alanlari acikca istemeli.
    assert "hazirlik, input, cagri, dogrulama ve beklenen sonucu ayir" in prompt_text.lower()
    assert "assertion varsa neden yapildigini acikla" in prompt_text.lower()
    assert "satir araligi 18-25" in prompt_text.lower()
    assert "code_unit_kind=test_function" in prompt_text.lower()
    assert "test_step_kind=assertion" in prompt_text.lower()
    assert "function_purpose" in prompt_text
    assert "function_purpose ana amaci" in prompt_text.lower()
    assert "block_comments" in prompt_text
    assert "line_comments" in prompt_text
    assert "METIN:\ndef test_author(...):\n    self.client.force_authenticate" in prompt_text


def test_code_prompt_mentions_method_state_and_helper_guidance():
    profile = {
        "tema": "genel",
        "tarz": "adim_adim",
        "seviye": "orta",
        "mesaj": "Bu methodu acikla.",
        "chunk_kind": "code",
        "chunk_title": "Cart.add_item",
        "code_unit_kind": "method",
        "code_subtype": "method",
        "language": "python",
        "line_start": 70,
        "line_end": 75,
    }

    chunk = """def add_item(self, item):
    prepared = normalize_item(item)
    self.items = self.items + [prepared]
    return len(self.items)
"""
    messages = build_anlamadim_prompt("code:python:code_block:14", chunk, 14, profile)
    prompt_text = "\n".join(item["content"] for item in messages)

    assert "code_unit_kind=method" in prompt_text.lower()
    assert "helper call varsa" in prompt_text.lower()
    assert "state'ini okuma/guncelleme" in prompt_text.lower()
    assert "self.x = y" in prompt_text.lower()
    assert "satir araligi 70-75" in prompt_text.lower()


def test_code_prompt_mentions_sql_clause_flow():
    # Hazirlik: SQL chunk'i icin clause akisini aciklatacak yalın bir profil kur.
    profile = {
        "tema": "genel",
        "tarz": "adim_adim",
        "seviye": "orta",
        "mesaj": "Bu sorguyu acikla.",
        "chunk_kind": "code",
        "chunk_title": "approved_orders",
        "code_subtype": "sql",
        "language": "sql",
        "line_start": 5,
        "line_end": 8,
    }

    # Cagri: SQL parcasi icin prompt metnini olustur.
    messages = build_anlamadim_prompt("code:sql:code_block:1", "SELECT id FROM orders WHERE status='APPROVED'", 14, profile)
    prompt_text = "\n".join(item["content"] for item in messages)

    # Dogrulama: Prompt SELECT/FROM-WHERE akisina ve dil bilgisini korumaya vurgu yapmali.
    assert "select, from/join, where, group by ve order by akislarini ayir" in prompt_text.lower()
    assert "dil/format sql" in prompt_text.lower()


def test_code_prompt_mentions_config_and_shell_guidance():
    # Hazirlik: Biri config biri shell olan iki farkli kod profili kur.
    config_profile = {
        "tema": "genel",
        "tarz": "adim_adim",
        "seviye": "orta",
        "mesaj": "Bu configi acikla.",
        "chunk_kind": "code",
        "chunk_title": "api",
        "code_unit_kind": "section",
        "code_subtype": "config",
        "code_purpose_hints": ["config", "network"],
        "language": "json",
        "line_start": 1,
        "line_end": 4,
    }
    shell_profile = {
        "tema": "genel",
        "tarz": "adim_adim",
        "seviye": "orta",
        "mesaj": "Bu komutu acikla.",
        "chunk_kind": "code",
        "chunk_title": "Invoke-Test",
        "code_unit_kind": "function",
        "code_subtype": "shell",
        "code_purpose_hints": ["shell", "api_call"],
        "language": "powershell",
        "line_start": 20,
        "line_end": 24,
    }

    # Cagri: Iki profile gore prompt'lari ayri ayri uret.
    config_messages = build_anlamadim_prompt("code:json:section:1", '{"api":{"base":"/v1"}}', 22, config_profile)
    shell_messages = build_anlamadim_prompt("code:powershell:function:1", "function Invoke-Test { Invoke-RestMethod ... }", 23, shell_profile)
    config_prompt = "\n".join(item["content"] for item in config_messages)
    shell_prompt = "\n".join(item["content"] for item in shell_messages)

    # Dogrulama: Her prompt kendi alt turune uygun rehberlik tasimali.
    assert "json/yaml/config ise section/group ile key-value satirlarini ayir" in config_prompt.lower()
    assert "purpose_hints=config, network" in config_prompt.lower()
    assert "shell/ps1 ise function, variable, command, api_call ve control_flow adimlarini ayir" in shell_prompt.lower()
    assert "komut adlarini bos birakma" in shell_prompt.lower()


def test_code_endpoint_generates_special_chunk_fallback_themed_examples_and_safe_metrics(
    db,
    test_kullanicisi,
    monkeypatch,
):
    # Hazirlik: Kod parcasi, zayif AI JSON'u ve metric yuzeylerini gozlemek icin kontrollu dokuman kur.
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Kod Aciklama",
        mime="text/x-python",
        durum="parcalandi",
    )
    doc.dosya.save("kod.py", ContentFile(b"ornek"), save=True)
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="kod",
        adres="code:python:code_block:1",
        metin="def dogrula(token):\n    if not token:\n        return False\n    return True",
        meta={"format": "code", "chunk_kind": "code_block", "symbol": "dogrula", "quality_score": 0.51, "difficulty_score": 0.73},
    )

    weak_json = {
        "one_liner": "",
        "very_simple": "",
        "glossary": [],
        "steps": [],
        "examples": [],
        "trap": "",
        "mini_quiz": [],
    }
    monkeypatch.setattr("dokuman.views.chat", lambda messages, max_tokens=256: json.dumps(weak_json))

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    # Cagri: Endpoint'i zayif AI cevabi ile calistirip fallback + themed example zincirini tetikle.
    response = client.post(
        f"/api/dokuman-asistani/parcalar/{parca.id}/anlamadim-v2/",
        {"mesaj": "Bunu anlamadim", "tema": "oyun", "debug_ai2": True},
        format="json",
    )

    # Dogrulama: Response shape'i fallback alanlariyla dolmali, metric store ise ham kodu sizdirmamali.
    assert response.status_code == 200
    data = response.data
    assert "girdiyi" in data["very_simple"].lower() or "girdi" in data["very_simple"].lower()
    assert "veri akisi" in data["very_simple"].lower()
    assert "kritik isimler" in data["very_simple"].lower()
    assert any("Girdi" in item for item in data["steps"])
    assert any("Beklenen sonuc" in item for item in data["steps"])
    assert any("return" in item.lower() or "sonuc" in item.lower() for item in data["examples"])
    assert data["tema_bazli_ornek"]
    assert data["alternatif_ornek"]
    assert {"one_liner", "very_simple", "glossary", "steps", "examples", "trap", "mini_quiz", "tema_bazli_ornek", "alternatif_ornek", "function_purpose", "flow_summary", "block_comments", "line_comments"} <= set(data)
    assert data["function_purpose"]
    assert data["flow_summary"]
    assert data["block_comments"]
    assert data["line_comments"]

    special_metric = MetrikKaydi.objects.filter(dokuman=doc, olay_turu="special_chunk_fallback_used").latest("id")
    themed_metric = MetrikKaydi.objects.filter(dokuman=doc, olay_turu="themed_example_generated").latest("id")
    assert special_metric.skor_ozeti["chunk_kind"] == "code"
    assert themed_metric.skor_ozeti["tema"] == "oyun"
    assert "def dogrula" not in str(special_metric.skor_ozeti)
    assert "def dogrula" not in str(themed_metric.skor_ozeti)


def test_special_and_themed_flags_off_preserve_controlled_basic_fallback(settings):
    # Hazirlik: Ozel fallback ve tema flag'lerini kapatip temel fallback hattini izole et.
    settings.DOCVERSE_SPECIAL_CHUNK_FALLBACKS_ENABLED = False
    settings.DOCVERSE_THEMED_EXAMPLES_ENABLED = False
    text = "def hesapla(x): return x + 1"
    context = _anlamadim_chunk_context(
        text=text,
        adres="code:python:block:1",
        meta={"format": "code", "chunk_kind": "code_block", "symbol": "hesapla"},
        tur="kod",
    )

    # Cagri: Ayni kod parcasi icin bu kez yalnizca kontrollu temel fallback'i uret.
    out = _fallback_sections_v2(text, "oyun", "adim_adim", "baslangic", chunk_context=context)

    # Dogrulama: Flag'ler kapaliyken tema ve special chunk alanlari bos kalmali.
    assert "giris mantigi" not in out["very_simple"].lower()
    assert out.get("tema_bazli_ornek", "") == ""
    assert out.get("alternatif_ornek", "") == ""


def test_code_explanation_benchmark_matrix_has_required_coverage():
    required_axes = set(CODE_EXPLANATION_AXIS_MATRIX)
    case_axes = {case["axis"] for case in CODE_EXPLANATION_BENCHMARK_CASES}
    case_slugs = {case["slug"] for case in CODE_EXPLANATION_BENCHMARK_CASES}

    assert len(CODE_EXPLANATION_BENCHMARK_CASES) >= 22
    assert case_axes == required_axes
    assert {
        "python_drf_api_test",
        "python_mock_monkeypatch_test",
        "python_helper_assert_chain",
        "python_transform_function",
        "python_state_mutation_method",
        "sql_select_join_filter",
        "sql_update_filter",
        "sql_cte_rank_filter",
        "js_event_handler",
        "js_api_state_change",
        "js_nested_callback_handler",
        "html_markup_block",
        "html_markup_script_style_split",
        "css_style_rule",
        "yaml_config_section",
        "yaml_anchor_alias_section",
        "json_config_entry",
        "json_feature_flags_section",
        "powershell_external_call",
        "shell_pipeline_external_call",
    } <= case_slugs


def test_code_explanation_benchmark_case_docs_and_contract_fields_are_complete():
    for case in CODE_EXPLANATION_BENCHMARK_CASES:
        assert case["minimum_explanation"], case["slug"]
        assert case["good_output"], case["slug"]
        assert case["bad_output"], case["slug"]
        assert case["unacceptable_errors"], case["slug"]
        assert case["coverage_tags"], case["slug"]
        assert case["required_keywords"], case["slug"]
        assert case["specific_terms"], case["slug"]
        assert case["min_counts"]["block_comments"] >= 1, case["slug"]
        assert case["min_counts"]["line_comments"] >= 1, case["slug"]


def test_code_explanation_benchmark_coverage_tags_capture_required_risks():
    tags = {
        tag
        for case in CODE_EXPLANATION_BENCHMARK_CASES
        for tag in (case.get("coverage_tags") or [])
    }

    assert CODE_EXPLANATION_REQUIRED_COVERAGE_TAGS <= tags


def test_code_explanation_benchmark_penalizes_short_generic_kontrol_eder_output():
    case = next(item for item in CODE_EXPLANATION_BENCHMARK_CASES if item["slug"] == "python_transform_function")
    weak_payload = {
        "one_liner": "Bu fonksiyon bir sey yapar.",
        "very_simple": "Bu kod veriyi isler.",
        "glossary": [{"terim": "girdi", "tanim": "Bir deger gelir."}],
        "steps": ["Girdi alir.", "Bir sey yapar.", "Sonuc verir."],
        "examples": ["Bu fonksiyon sonucu verir."],
        "trap": "Tuzak, kodu yanlis anlamaktir.",
        "function_purpose": "Bu fonksiyon kontrol eder.",
        "flow_summary": "Girdi -> kontrol eder -> sonuc",
        "block_comments": ["Temel akis bir sey yapar."],
        "line_comments": [
            "Bu satir kontrol eder.",
            "Bu satir bir sey yapar.",
            "Bu satir sonucu verir.",
        ],
    }

    score = evaluate_code_explanation_case(case, weak_payload)

    assert score["scores"]["anti_generic"] == 0
    assert score["weak_generic_hits"] >= 2
    assert score["passed"] is False


@pytest.mark.parametrize("case", CODE_EXPLANATION_BENCHMARK_CASES, ids=[case["slug"] for case in CODE_EXPLANATION_BENCHMARK_CASES])
def test_code_explanation_benchmark_cases_meet_threshold(case):
    segments = build_code_segments(case["text"], case["segment_language"])
    segment_kinds = {item["unit_kind"] for item in segments}
    segment_names = {item["unit_name"] for item in segments if item.get("unit_name")}

    assert set(case["expected_segment_kinds"]) <= segment_kinds, case["slug"]
    if case["expected_segment_names"]:
        assert any(name in segment_names for name in case["expected_segment_names"]), case["slug"]

    context = _anlamadim_chunk_context(
        text=case["text"],
        adres=case["adres"],
        meta=case["meta"],
        tur="kod",
    )
    out = _fallback_sections_v2(case["text"], "genel", "adim_adim", "baslangic", chunk_context=context)
    score = evaluate_code_explanation_case(case, out)

    assert score["passed"], format_code_explanation_result(score)


def test_code_explanation_benchmark_summary_has_no_failed_axis():
    results = []
    for case in CODE_EXPLANATION_BENCHMARK_CASES:
        context = _anlamadim_chunk_context(
            text=case["text"],
            adres=case["adres"],
            meta=case["meta"],
            tur="kod",
        )
        out = _fallback_sections_v2(case["text"], "genel", "adim_adim", "baslangic", chunk_context=context)
        results.append(evaluate_code_explanation_case(case, out))

    summary = summarize_code_explanation_results(results)

    assert summary["case_count"] == len(CODE_EXPLANATION_BENCHMARK_CASES)
    assert summary["failed_cases"] == []
    assert set(summary["axis_summary"]) == set(CODE_EXPLANATION_AXIS_MATRIX)
