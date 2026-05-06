"""Multiformat ingestion hattinin chunk, meta ve downstream yuzeylerle uyumunu dogrulayan testler."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from dokuman.models import MetrikKaydi, Parca
from dokuman.services.concept_runtime import build_concept_surface_payload
from dokuman.services import ingestion
from dokuman.services.code_structure import build_code_segments
from dokuman.services.ingestion import dokumani_parcala_ve_kaydet
from dokuman.services.ocr import gorseli_ocr_ile_parcala_ve_kaydet
from dokuman.services.readme_builder import build_readme_export_result
from dokuman.services.study_summary import build_study_summary_payload
from dokuman.tests.yardimcilar import dokuman_kaydi_olustur

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _xlsx_fixture(path: Path) -> Path:
    path.write_bytes((_REPO_ROOT / "test_ingest.xlsx").read_bytes())
    return path


def _pptx_fixture(path: Path) -> Path:
    path.write_bytes((_REPO_ROOT / "test_ingest.pptx").read_bytes())
    return path


def _code_fixture(path: Path) -> Path:
    path.write_text(
        "# Kimlik akisi\n"
        "# Token kontrolu\n\n"
        "def dogrula(token, cache):\n"
        "    if not token:\n"
        "        return False\n"
        "    return cache.get(token) is not None\n",
        encoding="utf-8",
    )
    return path


def _structured_python_code_fixture(path: Path) -> Path:
    path.write_text(
        '"""Authentication helpers."""\n'
        "import requests\n"
        "from rest_framework import status\n\n"
        'API_ROOT = "/health"\n\n'
        "class ApiClient:\n"
        '    """Wraps endpoint calls."""\n'
        "    def fetch(self, client):\n"
        "        response = client.get(API_ROOT)\n"
        "        if response.status_code != status.HTTP_200_OK:\n"
        "            return None\n"
        "        return response.json()\n\n"
        "def build_payload(token):\n"
        '    data = {"token": token}\n'
        "    return data\n\n"
        "def test_fetch_health(client):\n"
        '    payload = build_payload("abc")\n'
        '    response = client.get(API_ROOT, headers={"Authorization": payload["token"]})\n'
        "    assert response.status_code == status.HTTP_200_OK\n"
        "    assert response.json() is not None\n",
        encoding="utf-8",
    )
    return path


def _markdown_fixture(path: Path) -> Path:
    path.write_text(
        "# JWT Akisi\n\n"
        "JWT token uretimi ve dogrulama akisinda imza, payload ve refresh token birlikte kullanilir.\n\n"
        "- Token kontrolu cache ile hizlanir\n"
        "- Refresh token oturum yeniler\n"
        "- Signature degisikligi yakalar\n\n"
        "## Riskler\n\n"
        "Yanlis anahtar yonetimi tum akisi zayiflatabilir.",
        encoding="utf-8",
    )
    return path


def _csv_fixture(path: Path) -> Path:
    path.write_text(
        "Kavram,Aciklama,Skor\n"
        "JWT,Kimlik dogrulama tokeni,0.91\n"
        "Refresh Token,Oturum yenileme araci,0.77\n"
        "Cache,Performans katmani,0.62\n",
        encoding="utf-8",
    )
    return path


def _legacy_binary_fixture(path: Path, *texts: str) -> Path:
    payload = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    for text in texts:
        payload += str(text).encode("utf-16-le") + b"\x00\x00"
    path.write_bytes(payload)
    return path


def _legacy_doc_fixture(path: Path) -> Path:
    return _legacy_binary_fixture(
        path,
        "Sistem Tasarimi",
        "JWT dogrulama akisi ve refresh token yonetimi",
        "Cache invalidation adimlari ve hata senaryolari",
    )


def _legacy_xls_fixture(path: Path) -> Path:
    return _legacy_binary_fixture(
        path,
        "Siparis Ozeti",
        "Musteri kodu, toplam tutar ve teslim tarihi alanlari birlikte raporlanir",
        "Onay bekleyen islemler ve geciken siparisler ayri bir satir grubunda izlenir",
        "Finans ekibi toplam tutar degisikliklerini haftalik olarak kontrol eder",
    )


def _legacy_ppt_fixture(path: Path) -> Path:
    return _legacy_binary_fixture(
        path,
        "Q2 Sunum Ozeti",
        "Kimlik dogrulama hizi artti ve kullanici bekleme suresi anlamli bicimde azaldi",
        "Risk maddeleri ve aksiyon plani son slaytta ekip bazli sorumluluklarla listelenir",
        "Yonetim ozeti sonraki ceyrek icin oncelikli iyilestirme alanlarini vurgular",
    )


def _pdf_placeholder_fixture(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.4\n%fake pdf for ocr fallback\n")
    return path


def _image_fixture(path: Path) -> Path:
    Image.new("RGB", (220, 90), color="white").save(path)
    return path


def test_xlsx_ingestion_creates_table_meta_and_rows_chunks(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    # Hazırlık: İçinde tablo olan geçici bir Excel (xlsx) dosyası ve sistem kaydı oluştur.
    file_path = _xlsx_fixture(tmp_path / "siparis.xlsx")
    doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik="XLSX")
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})

    # Çağrı: Yüklenen excel belgesini RAG sistemine uygun parçalara (chunk) ayır.
    dokumani_parcala_ve_kaydet(doc)
    doc.refresh_from_db()
    parcalar = list(Parca.objects.filter(dokuman=doc).order_by("sira"))

    # Doğrulama: İşlemin başarılı olduğu ve `table_summary` ile `table_rows` türünde parçaların oluştuğu teyit edilir.
    assert doc.durum == "parcalandi"
    assert any(parca.tur == "tablo_meta" for parca in parcalar)
    assert any((parca.meta or {}).get("chunk_kind") == "table_summary" for parca in parcalar)
    assert any((parca.meta or {}).get("chunk_kind") == "table_rows" for parca in parcalar)
    assert all(parca.adres.startswith("xlsx:") for parca in parcalar)
    summary_parca = next(parca for parca in parcalar if (parca.meta or {}).get("chunk_kind") == "table_summary")
    assert summary_parca.meta["office_document_type"] == "excel"
    assert summary_parca.meta["office_unit_kind"] == "sheet"
    assert "header_value_pairs" in summary_parca.meta
    metric = MetrikKaydi.objects.filter(dokuman=doc, olay_turu="multiformat_chunk_created").latest("id")
    assert metric.skor_ozeti["format"] == "xlsx"
    assert "Elma" not in str(metric.skor_ozeti)


def test_pptx_ingestion_creates_slide_title_and_bullet_chunks(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    # Hazirlik: Slayt fixture'i ve deterministic RAG sync mock'u ile pptx ingestion kosulu kur.
    file_path = _pptx_fixture(tmp_path / "akis.pptx")
    doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik="PPTX")
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})

    # Cagri: PPTX belgesini slayt basligi, ozet ve bullet chunk'larina ayir.
    dokumani_parcala_ve_kaydet(doc)
    parcalar = list(Parca.objects.filter(dokuman=doc).order_by("sira"))

    # Dogrulama: Slayt yuzeyi korunmali ve metadata office/presentation baglamini tasimali.
    assert doc.parcalar.count() >= 2
    assert any((parca.meta or {}).get("chunk_kind") == "slide_title" for parca in parcalar)
    assert any((parca.meta or {}).get("chunk_kind") == "slide_summary" for parca in parcalar)
    assert any((parca.meta or {}).get("chunk_kind") == "slide_bullets" for parca in parcalar)
    assert all(parca.adres.startswith("pptx:") for parca in parcalar)
    summary_parca = next(parca for parca in parcalar if (parca.meta or {}).get("chunk_kind") == "slide_summary")
    assert summary_parca.meta["office_document_type"] == "powerpoint"
    assert summary_parca.meta["office_unit_kind"] == "slide"
    assert "Slayt" in summary_parca.metin


def test_pptx_title_fallback_skips_placeholder_and_uses_first_meaningful_line():
    # Hazirlik + cagri: Placeholder title ile resolve helper'ini direkt calistir.
    title, bullet_lines, other_lines = ingestion._resolve_pptx_slide_content(
        title_text="Click to add title",
        bullet_lines=["JWT Akisi", "Token uretilir", "Imza dogrulanir"],
        other_lines=[],
    )

    # Dogrulama: Placeholder atilmali, ilk anlamli satir gercek baslik olarak secilmeli.
    assert title == "JWT Akisi"
    assert bullet_lines == ["Token uretilir", "Imza dogrulanir"]
    assert other_lines == []


def test_pptx_xml_fallback_orders_slide_files_numerically(tmp_path):
    # Hazirlik: Slide dosyalari dogal siralama yerine metinsel olarak karisabilecek isimlerle uretilir.
    slide1 = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Slide 1</a:t></a:r></a:p></p:txBody></p:sp>'
        '</p:spTree></p:cSld></p:sld>'
    )
    slide2 = slide1.replace("Slide 1", "Slide 2")
    slide10 = slide1.replace("Slide 1", "Slide 10")
    pptx_path = tmp_path / "order-check.pptx"

    import zipfile

    with zipfile.ZipFile(pptx_path, "w") as zf:
        zf.writestr("ppt/slides/slide1.xml", slide1)
        zf.writestr("ppt/slides/slide10.xml", slide10)
        zf.writestr("ppt/slides/slide2.xml", slide2)

    # Cagri: python-pptx fallback'i slide sirasini XML adlarindan cozsun.
    slides = ingestion._pptx_slides_without_pptx(str(pptx_path))

    # Dogrulama: 1-2-10 sirasi korunarak acceptance'taki slayt akisi bozulmamali.
    assert [title for _, title, _ in slides] == ["Slide 1", "Slide 2", "Slide 10"]


def test_code_ingestion_creates_comment_and_function_centered_chunks(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    # Hazirlik: Yorum ve fonksiyon iceren kisa kod fixture'i ile ingestion tetiklenir.
    file_path = _code_fixture(tmp_path / "kimlik.py")
    doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik="Kod")
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})

    # Cagri: Kod dosyasini comment ve function merkezli chunk'lara ayir.
    dokumani_parcala_ve_kaydet(doc)
    parcalar = list(Parca.objects.filter(dokuman=doc).order_by("sira"))

    # Dogrulama: Comment/code ayrimi ve sembol metasi downstream explain yuzeyi icin korunmali.
    assert doc.durum == "parcalandi"
    assert any((parca.meta or {}).get("chunk_kind") == "code_comment" for parca in parcalar)
    assert any((parca.meta or {}).get("chunk_kind") == "code_block" for parca in parcalar)
    assert any((parca.meta or {}).get("symbol") == "dogrula" for parca in parcalar)
    assert all(parca.adres.startswith("code:") for parca in parcalar)


def test_code_ingestion_extracts_python_structured_units_and_test_steps(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    # Hazirlik: Test fonksiyonu, API cagrisi ve assertion iceren daha zengin python fixture'i kur.
    file_path = _structured_python_code_fixture(tmp_path / "api_test.py")
    doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik="Structured Python")
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})

    # Cagri: Ingestion sonrasi code_structure metasi parcalara yansitilsin.
    dokumani_parcala_ve_kaydet(doc)
    parcalar = list(Parca.objects.filter(dokuman=doc).order_by("sira"))

    unit_kinds = {(parca.meta or {}).get("code_unit_kind") for parca in parcalar}
    step_kinds = {(parca.meta or {}).get("code_step_kind") for parca in parcalar if (parca.meta or {}).get("code_unit_kind") == "test_step"}

    # Dogrulama: Arrange/act/assert dahil yapisal sinyaller ve line bilgisi korunmali.
    assert doc.durum == "parcalandi"
    assert {"import", "constant", "class", "method", "function", "test_function", "test_step", "assertion", "api_call", "control_flow"} <= unit_kinds
    assert {"arrange", "act", "assert"} <= step_kinds
    assert any((parca.meta or {}).get("parent_unit") == "test_fetch_health" for parca in parcalar if (parca.meta or {}).get("code_unit_kind") in {"assertion", "test_step", "api_call"})
    assert any((parca.meta or {}).get("code_unit_name") == "test_fetch_health" for parca in parcalar if (parca.meta or {}).get("code_unit_kind") == "test_function")
    assert all((parca.meta or {}).get("code_language") == "python" for parca in parcalar)
    assert all((parca.meta or {}).get("line_start") for parca in parcalar)
    assert all((parca.meta or {}).get("line_end") for parca in parcalar)


def test_code_structure_supports_basic_non_python_units():
    # Hazirlik: Farkli dillerden kisa ornekler verip code_structure segmentleyicisini calistir.
    js_segments = build_code_segments(
        "import api from './api';\n"
        "const token = getToken();\n"
        "async function loadData() {\n"
        "  const response = await fetch('/items');\n"
        "  expect(response.ok).toBe(true);\n"
        "}\n",
        "javascript",
    )
    html_segments = build_code_segments("<section>\n  <form>\n    <input />\n  </form>\n</section>\n", "html")
    css_segments = build_code_segments(".card {\n  color: red;\n}\n", "css")
    json_segments = build_code_segments('{"api": {"base": "/v1"}, "retry": 3}', "json")
    yaml_segments = build_code_segments("service:\n  url: https://x\nlogging:\n  level: info\n", "yaml")
    sql_segments = build_code_segments("SELECT id, name FROM users WHERE active = 1;\n", "sql")
    ps_segments = build_code_segments(
        "function Invoke-Test {\n"
        "  $response = Invoke-RestMethod -Uri https://example.test\n"
        "  if ($response.ok) { Write-Host 'ok' }\n"
        "}\n",
        "powershell",
    )

    # Dogrulama: Her dilin kendine ozgu unit_kind sinyallerinin korundugunu teyit et.
    assert {"import", "function", "api_call", "assertion"} <= {item["unit_kind"] for item in js_segments}
    assert "markup_block" in {item["unit_kind"] for item in html_segments}
    assert "style_rule" in {item["unit_kind"] for item in css_segments}
    assert "config_entry" in {item["unit_kind"] for item in json_segments}
    assert "config_entry" in {item["unit_kind"] for item in yaml_segments}
    assert "sql_select" in {item["unit_kind"] for item in sql_segments}
    assert {"function", "api_call", "control_flow"} <= {item["unit_kind"] for item in ps_segments}


def test_code_structure_separates_html_markup_script_and_style_units():
    # Hazirlik: Tek HTML belge icinde markup, style ve script katmanlari birlikte verilir.
    html = (
        "<section>\n"
        "  <style>\n"
        "    .notice { color: red; }\n"
        "  </style>\n"
        "  <form>\n"
        "    <input />\n"
        "  </form>\n"
        "  <script>\n"
        "    fetch('/api/save')\n"
        "  </script>\n"
        "</section>\n"
    )

    # Cagri: Segmentleyici farkli unit turlerini ayni dokuda ayirmali.
    segments = build_code_segments(html, "html")
    unit_kinds = {item["unit_kind"] for item in segments}

    # Dogrulama: Markup/style/script ve API call sinyalleri ayni cikti setinde gorunmeli.
    assert {"markup_block", "style_block", "script_block", "api_call"} <= unit_kinds


def test_code_structure_names_nested_js_callback_and_shell_pipeline_units():
    js = (
        "button.addEventListener('click', async (event) => {\n"
        "  event.preventDefault();\n"
        "  const response = await fetch('/api/save');\n"
        "});\n"
    )
    ps = (
        "function Sync-Items {\n"
        "  $endpoint = 'https://example.test/items'\n"
        "  curl $endpoint | jq '.items'\n"
        "}\n"
    )

    js_segments = build_code_segments(js, "javascript")
    ps_segments = build_code_segments(ps, "powershell")

    assert any(item["unit_kind"] == "function" and item["unit_name"] == "click_handler" for item in js_segments)
    assert any(item["unit_kind"] == "api_call" and item["parent_unit"] == "click_handler" for item in js_segments)
    assert any(item["unit_kind"] == "api_call" and item["unit_name"] == "curl" for item in ps_segments)
    assert any("pipeline" in (item.get("purpose_hints") or []) for item in ps_segments if item["unit_kind"] == "api_call")


def test_code_structure_keeps_js_property_and_powershell_environment_hints_visible():
    js = (
        "function saveCard() {\n"
        "  return api.then((payload) => {\n"
        "    this.state = payload;\n"
        "  });\n"
        "}\n"
    )
    ps = (
        "function Invoke-Deploy {\n"
        "  $env:API_BASE = 'https://example.test'\n"
        "  Start-Process notepad.exe\n"
        "}\n"
    )

    js_segments = build_code_segments(js, "javascript")
    ps_segments = build_code_segments(ps, "powershell")

    assert any("promise_chain" in (item.get("purpose_hints") or []) for item in js_segments if item["unit_kind"] == "function")
    assert any("property_assignment" in (item.get("purpose_hints") or []) for item in js_segments if item["unit_kind"] in {"function", "variable", "command", "control_flow", "api_call"})
    assert any(item["unit_kind"] == "variable" and "environment_variable" in (item.get("purpose_hints") or []) for item in ps_segments)
    assert any("process_launch" in (item.get("purpose_hints") or []) for item in ps_segments if item["unit_kind"] == "command")


def test_code_structure_keeps_heuristic_boundary_units_visible_without_overclaiming_parse_depth():
    js_segments = build_code_segments(
        "function setupSave(button) {\n"
        "  button.addEventListener('click', async () => {\n"
        "    const response = await fetch('/api/save');\n"
        "    if (response.ok) { setSaved(true); }\n"
        "  });\n"
        "}\n",
        "javascript",
    )
    sql_segments = build_code_segments(
        "WITH ranked AS (\n"
        "  SELECT user_id, score, ROW_NUMBER() OVER (PARTITION BY team_id ORDER BY score DESC) AS rn\n"
        "  FROM scores\n"
        ")\n"
        "SELECT user_id, score FROM ranked WHERE rn = 1;\n",
        "sql",
    )
    yaml_segments = build_code_segments(
        "defaults: &defaults\n"
        "  timeout: 30\n"
        "service:\n"
        "  <<: *defaults\n"
        "  base_url: https://api.example.test\n",
        "yaml",
    )

    assert {"function", "api_call", "control_flow"} <= {item["unit_kind"] for item in js_segments}
    assert any(item["unit_name"] == "click_handler" for item in js_segments if item["unit_kind"] == "function")
    assert {"sql_with", "sql_select", "sql_from_join"} <= {item["unit_kind"] for item in sql_segments}
    assert {"section", "config_entry"} <= {item["unit_kind"] for item in yaml_segments}
    assert any(item["unit_name"] == "defaults" for item in yaml_segments)
    assert any(item["unit_name"] == "service" for item in yaml_segments)


def test_code_structure_extracts_inline_sql_clauses_without_confusing_window_order_by():
    sql = (
        "WITH ranked AS (\n"
        "  SELECT user_id, score, ROW_NUMBER() OVER (PARTITION BY team_id ORDER BY score DESC) AS rn\n"
        "  FROM scores\n"
        ")\n"
        "SELECT user_id, score FROM ranked WHERE rn = 1;\n"
    )

    segments = build_code_segments(sql, "sql")
    clause_map = {(item["unit_kind"], item["text"]) for item in segments}

    assert any(item["unit_kind"] == "sql_with" for item in segments)
    assert any(item["unit_kind"] == "sql_from_join" and "FROM scores" in item["text"] for item in segments)
    assert any(item["unit_kind"] == "sql_from_join" and "FROM ranked" in item["text"] for item in segments)
    assert any(item["unit_kind"] == "sql_where_group" and "WHERE rn = 1" in item["text"] for item in segments)
    assert not any(item["unit_kind"] == "sql_order_by" for item in segments)
    assert ("sql_select", "SELECT user_id, score") in clause_map


def test_image_ocr_ingestion_creates_visual_chunks_and_redacted_metric(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    # Hazirlik: OCR sonucu deterministik olsun diye gorsel parser ve chunker mock'lanir.
    file_path = _image_fixture(tmp_path / "gorsel.png")
    doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik="Gorsel")
    monkeypatch.setattr("dokuman.services.ocr.extract_text_from_image", lambda path: "OCR HAM SATIR\n\nTablo benzeri ana not")
    monkeypatch.setattr("dokuman.services.ocr.split_text_into_chunks", lambda text, max_chars=1200: ["OCR HAM SATIR", "Tablo benzeri ana not"])
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})

    # Cagri: Gorsel dosyasini OCR ingestion hattindan gecir.
    gorseli_ocr_ile_parcala_ve_kaydet(doc)
    parcalar = list(Parca.objects.filter(dokuman=doc).order_by("sira"))

    # Dogrulama: Chunk'lar visual_ocr olarak etiketlenmeli, metrikte ise ham OCR sizmamali.
    assert doc.durum == "parcalandi"
    assert all((parca.meta or {}).get("format") == "image" for parca in parcalar)
    assert all((parca.meta or {}).get("chunk_kind") == "visual_ocr" for parca in parcalar)
    metric = MetrikKaydi.objects.filter(dokuman=doc, olay_turu="multiformat_chunk_created").latest("id")
    assert metric.skor_ozeti["format"] == "image"
    assert "OCR HAM SATIR" not in str(metric.skor_ozeti)


def test_markdown_ingestion_creates_heading_aware_text_chunks(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    # Hazirlik: Baslik ve liste iceren markdown fixture'i ile sade ingestion kosulu kur.
    file_path = _markdown_fixture(tmp_path / "akis.md")
    doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik="Markdown")
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})

    # Cagri: Markdown dokumanini heading-aware text bulk'una cevir.
    dokumani_parcala_ve_kaydet(doc)
    parcalar = list(Parca.objects.filter(dokuman=doc).order_by("sira"))

    # Dogrulama: Baslik baglami ve list block ayriminin metadata'ya yansidigi gorunmeli.
    assert doc.parcalar.count() >= 2
    assert any((parca.meta or {}).get("heading_title") == "JWT Akisi" for parca in parcalar)
    assert any((parca.meta or {}).get("chunk_kind") == "list_block" for parca in parcalar)
    assert all(parca.adres.startswith("md:") for parca in parcalar)


def test_csv_ingestion_creates_table_chunks_and_safe_metric(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    # Hazirlik: Tablo agirlikli csv fixture'i ve RAG sync mock'u ile deterministik ortam kur.
    file_path = _csv_fixture(tmp_path / "kavramlar.csv")
    doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik="CSV")
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})

    # Cagri: CSV dosyasini tablo chunk'larina ayir.
    dokumani_parcala_ve_kaydet(doc)
    parcalar = list(Parca.objects.filter(dokuman=doc).order_by("sira"))

    # Dogrulama: table_meta/table_rows chunk'lari olusmali ve metrikte ham aciklama sizmamali.
    assert doc.durum == "parcalandi"
    assert any((parca.meta or {}).get("chunk_kind") == "table_meta" for parca in parcalar)
    assert any((parca.meta or {}).get("chunk_kind") == "table_rows" for parca in parcalar)
    metric = MetrikKaydi.objects.filter(dokuman=doc, olay_turu="multiformat_chunk_created").latest("id")
    assert metric.skor_ozeti["format"] == "csv"
    assert "Kimlik dogrulama tokeni" not in str(metric.skor_ozeti)


def test_legacy_office_formats_fail_honestly_and_suggest_conversion(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})
    fixtures = [
        (_legacy_doc_fixture(tmp_path / "tasarim.doc"), "Legacy DOC", ".DOCX"),
        (_legacy_xls_fixture(tmp_path / "rapor.xls"), "Legacy XLS", ".XLSX"),
        (_legacy_ppt_fixture(tmp_path / "sunum.ppt"), "Legacy PPT", ".PPTX"),
    ]

    for file_path, title, expected_target in fixtures:
        doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik=title)
        dokumani_parcala_ve_kaydet(doc)
        doc.refresh_from_db()

        assert doc.durum == "hata"
        assert doc.parcalar.count() == 0
        assert title.upper() in doc.hata.upper()
        assert expected_target in doc.hata.upper()


def test_legacy_office_failure_is_honest_and_suggests_conversion(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
):
    file_path = tmp_path / "kirik.xls"
    file_path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x01\x02")
    doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik="Bozuk XLS")

    dokumani_parcala_ve_kaydet(doc)
    doc.refresh_from_db()

    assert doc.durum == "hata"
    assert doc.parcalar.count() == 0
    assert ".XLSX" in doc.hata.upper()
    assert "LEGACY XLS" in doc.hata.upper()


def test_scanned_pdf_ingestion_uses_ocr_fallback_and_feeds_existing_surfaces(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    file_path = _pdf_placeholder_fixture(tmp_path / "taranmis.pdf")
    doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik="Scanned PDF")
    monkeypatch.setattr("dokuman.services.ingestion.parse_document_structure", lambda path: {"section_count": 0, "sections": []})
    monkeypatch.setattr(
        "dokuman.services.ocr.extract_text_from_pdf_pages",
        lambda path: [
            {"page": 1, "text": "Tarama sayfasi bir\n\nJWT token akisi ve oturum yenileme adimlari", "image_width": 1200, "image_height": 1600},
            {"page": 2, "text": "Tarama sayfasi iki\n\nRiskler ve dogrulama kontrolleri", "image_width": 1200, "image_height": 1600},
        ],
    )
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})

    dokumani_parcala_ve_kaydet(doc)
    doc.refresh_from_db()
    parcalar = list(Parca.objects.filter(dokuman=doc).order_by("sira"))
    summary = build_study_summary_payload(doc=doc, user=test_kullanicisi)
    concepts = build_concept_surface_payload(doc=doc, user=test_kullanicisi)
    readme = build_readme_export_result(doc=doc, user=test_kullanicisi, output_format="json")

    assert doc.durum == "parcalandi"
    assert parcalar
    assert all(parca.tur == "ocr" for parca in parcalar)
    assert [parca.adres for parca in parcalar] == ["pdf:page:1#ocr:1", "pdf:page:2#ocr:1"]
    assert all((parca.meta or {}).get("ocr") is True for parca in parcalar)
    assert all((parca.meta or {}).get("ocr_fallback") is True for parca in parcalar)
    assert all((parca.meta or {}).get("format") == "pdf" for parca in parcalar)
    assert all((parca.meta or {}).get("office_unit_kind") == "page" for parca in parcalar)
    assert all((parca.meta or {}).get("chunk_kind") == "visual_ocr" for parca in parcalar)
    assert summary["ana_maddeler"]
    assert concepts["toplam_kavram"] >= 1
    assert readme["readiness"] == "ready"
    metric = MetrikKaydi.objects.filter(dokuman=doc, olay_turu="multiformat_chunk_created").latest("id")
    assert metric.skor_ozeti["format"] == "pdf"
    assert "JWT token akisi" not in str(metric.skor_ozeti)


def test_pdf_text_layer_fallback_korur_ve_ocrya_gitmeden_parca_uretir(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    file_path = _pdf_placeholder_fixture(tmp_path / "text-layer.pdf")
    doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik="PDF Text Layer")
    monkeypatch.setattr("dokuman.services.ingestion.parse_document_structure", lambda path: {"section_count": 0, "sections": []})
    monkeypatch.setattr(
        "dokuman.services.ingestion._inspect_pdf_text_layer",
        lambda path: {
            "page_rows": [
                {
                    "page": 1,
                    "raw_text": "JWT Akisi\n\nJWT dogrulama ve refresh token adimlari aciklanir.",
                    "text": "JWT Akisi JWT dogrulama ve refresh token adimlari aciklanir.",
                    "char_count": 63,
                    "has_text": True,
                },
                {
                    "page": 2,
                    "raw_text": "Riskler\n\nAnahtar rotasyonu ve oturum sonlandirma kontrolleri.",
                    "text": "Riskler Anahtar rotasyonu ve oturum sonlandirma kontrolleri.",
                    "char_count": 65,
                    "has_text": True,
                },
            ],
            "page_count": 2,
            "contentful_pages": 2,
            "total_chars": 128,
            "avg_chars_per_contentful_page": 64.0,
            "text_layer_detected": True,
            "likely_scanned": False,
        },
    )
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})

    dokumani_parcala_ve_kaydet(doc)
    doc.refresh_from_db()
    parcalar = list(Parca.objects.filter(dokuman=doc).order_by("sira"))

    assert doc.durum == "parcalandi"
    assert parcalar
    assert all(parca.adres.startswith("pdf:page:") for parca in parcalar)
    assert all((parca.meta or {}).get("text_layer_used") is True for parca in parcalar)
    assert not any((parca.meta or {}).get("ocr") for parca in parcalar)
    assert any((parca.meta or {}).get("page") == 1 for parca in parcalar)


def test_weak_text_layer_pdf_falls_back_to_ocr_when_text_layer_is_not_trustworthy(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    file_path = _pdf_placeholder_fixture(tmp_path / "weak-text-layer.pdf")
    doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik="Weak Text Layer")
    monkeypatch.setattr("dokuman.services.ingestion.parse_document_structure", lambda path: {"section_count": 0, "sections": []})
    monkeypatch.setattr(
        "dokuman.services.ingestion._inspect_pdf_text_layer",
        lambda path: {
            "page_rows": [
                {
                    "page": 1,
                    "raw_text": "B U T U N A K I S",
                    "text": "B U T U N A K I S",
                    "char_count": 15,
                    "has_text": True,
                },
                {
                    "page": 2,
                    "raw_text": "A B C D E F G",
                    "text": "A B C D E F G",
                    "char_count": 13,
                    "has_text": True,
                },
            ],
            "page_count": 2,
            "contentful_pages": 2,
            "total_chars": 140,
            "avg_chars_per_contentful_page": 70.0,
            "text_layer_detected": True,
            "likely_scanned": False,
        },
    )
    monkeypatch.setattr(
        "dokuman.services.ocr.extract_text_from_pdf_pages",
        lambda path: [
            {"page": 1, "text": "JWT akisi ve refresh token adimlari burada anlatilir.", "image_width": 1200, "image_height": 1600},
            {"page": 2, "text": "Retry mantigi ve dogrulama kontrolleri ikinci sayfada surer.", "image_width": 1200, "image_height": 1600},
        ],
    )
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})

    dokumani_parcala_ve_kaydet(doc)
    doc.refresh_from_db()
    parcalar = list(Parca.objects.filter(dokuman=doc).order_by("sira"))

    assert doc.durum == "parcalandi"
    assert parcalar
    assert all(parca.tur == "ocr" for parca in parcalar)
    assert all((parca.meta or {}).get("ocr_fallback") is True for parca in parcalar)
    assert all((parca.meta or {}).get("ocr_kaynak_turu") == "pdf_ocr_fallback" for parca in parcalar)


def test_text_layer_broken_ocr_line_is_not_promoted_to_page_heading(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    file_path = _pdf_placeholder_fixture(tmp_path / "broken-text-layer.pdf")
    doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik="Broken Text Layer")
    monkeypatch.setattr("dokuman.services.ingestion.parse_document_structure", lambda path: {"section_count": 0, "sections": []})
    monkeypatch.setattr(
        "dokuman.services.ingestion._inspect_pdf_text_layer",
        lambda path: {
            "page_rows": [
                {
                    "page": 1,
                    "raw_text": "B U T U N A K I S\n\nJWT dogrulama ve refresh token adimlari aciklanir.",
                    "text": "B U T U N A K I S JWT dogrulama ve refresh token adimlari aciklanir.",
                    "char_count": 72,
                    "has_text": True,
                },
            ],
            "page_count": 1,
            "contentful_pages": 1,
            "total_chars": 120,
            "avg_chars_per_contentful_page": 120.0,
            "text_layer_detected": True,
            "likely_scanned": False,
        },
    )
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})

    dokumani_parcala_ve_kaydet(doc)
    doc.refresh_from_db()
    parcalar = list(Parca.objects.filter(dokuman=doc).order_by("sira"))

    assert doc.durum == "parcalandi"
    assert parcalar
    assert all((parca.meta or {}).get("text_layer_used") is True for parca in parcalar)
    assert not any((parca.meta or {}).get("chunk_kind") == "page_heading" for parca in parcalar)
    assert any((parca.meta or {}).get("chunk_kind") == "page_paragraph" for parca in parcalar)


def test_scanned_pdf_ocr_fallback_failure_does_not_fake_success(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    file_path = _pdf_placeholder_fixture(tmp_path / "bos-tarama.pdf")
    doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik="Bos Scanned PDF")
    monkeypatch.setattr("dokuman.services.ingestion.parse_document_structure", lambda path: {"section_count": 0, "sections": []})
    monkeypatch.setattr("dokuman.services.ocr.extract_text_from_pdf_pages", lambda path: [])

    dokumani_parcala_ve_kaydet(doc)
    doc.refresh_from_db()

    assert doc.durum == "hata"
    assert doc.parcalar.count() == 0
    assert "OCR FALLBACK" in doc.hata.upper()


def test_multiformat_common_metadata_floor_is_aligned_across_formats(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})
    monkeypatch.setattr("dokuman.services.ocr.extract_text_from_image", lambda path: "Gorsel OCR metni\n\nAksiyon maddeleri")
    fixtures = [
        (_markdown_fixture(tmp_path / "zemin.md"), "Markdown"),
        (_csv_fixture(tmp_path / "zemin.csv"), "CSV"),
        (_xlsx_fixture(tmp_path / "zemin.xlsx"), "XLSX"),
        (_pptx_fixture(tmp_path / "zemin.pptx"), "PPTX"),
        (_image_fixture(tmp_path / "zemin.png"), "Image OCR"),
    ]

    required_keys = {
        "path",
        "source_address",
        "format",
        "chunk_kind",
        "chunk_title",
        "quality_score",
        "difficulty_score",
    }

    for file_path, title in fixtures:
        doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik=title)
        dokumani_parcala_ve_kaydet(doc)
        first = Parca.objects.filter(dokuman=doc).order_by("sira").first()

        assert doc.durum == "parcalandi"
        assert first is not None
        assert required_keys <= set((first.meta or {}))
        assert (first.meta or {}).get("source_address") == first.adres


def test_text_csv_and_code_docs_existing_output_surfaces_can_still_produce_meaningful_output(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    # Hazirlik: Farkli formatlari ayni smoke dongusunde gezip mevcut urun yuzeylerini dogrula.
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})
    fixtures = [
        (_markdown_fixture(tmp_path / "ozet.md"), "Markdown"),
        (_csv_fixture(tmp_path / "veri.csv"), "CSV"),
        (_code_fixture(tmp_path / "akis.py"), "Kod"),
    ]

    for file_path, title in fixtures:
        doc = dokuman_kaydi_olustur(kullanici=test_kullanicisi, dosya_yolu=file_path, baslik=title)
        # Cagri: Ingestion tamamlaninca ozet, concept ve readme yuzeylerini arka arkaya uret.
        dokumani_parcala_ve_kaydet(doc)
        summary = build_study_summary_payload(doc=doc, user=test_kullanicisi)
        concepts = build_concept_surface_payload(doc=doc, user=test_kullanicisi)
        readme = build_readme_export_result(doc=doc, user=test_kullanicisi, output_format="json")

        # Dogrulama: Multiformat ingestion sonrasi mevcut downstream acceptance yuzeyleri calismaya devam etmeli.
        assert doc.durum == "parcalandi"
        assert summary["dokuman_id"] == doc.id
        assert summary["ana_maddeler"]
        assert concepts["dokuman_id"] == doc.id
        assert concepts["toplam_kavram"] >= 1
        assert readme["dokuman_id"] == doc.id
        assert readme["readiness"] == "ready"
        assert readme["kritik_bilesenler"]
