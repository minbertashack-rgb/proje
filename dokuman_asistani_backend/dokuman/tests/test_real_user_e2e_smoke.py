from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from dokuman.models import Parca


_REPO_ROOT = Path(__file__).resolve().parents[2]


REAL_USER_E2E_SCENARIOS = [
    {
        "id": "auth_upload_part_list_baseline",
        "input_type": "Any supported upload",
        "flow": "auth -> upload -> parca listesi",
        "minimum_success": "Token alinir, upload 201 doner, parca listesi 200 ve en az bir parca vardir.",
        "minimum_quality": "Upload durum/parca_sayisi sinyalleri ve parca secimi tutarli kalir.",
        "unacceptable_failure": "Auth temizken upload veya parca listesi akisinin 4xx/5xx ile kirilmasi.",
        "automation": "manual/tools/smoke_docverse_e2e.ps1",
    },
    {
        "id": "docx_chunk_explanation_export",
        "input_type": "DOCX",
        "flow": "upload -> chunks -> anlamadim-v2 -> concepts -> readme-export -> real-export",
        "minimum_success": "Upload 201 doner, en az 1 parca olusur, explanation ve export zinciri 200 doner.",
        "minimum_quality": "Aciklama parcaya bagli kalir, concept yuzeyi bos kalmaz, export JSON shape sabit kalir.",
        "unacceptable_failure": "Upload tamamlanip downstream yuzeylerin bos veya 5xx donmesi.",
        "automation": "pytest:test_real_user_docx_upload_chain_keeps_explanation_concept_and_export_usable",
    },
    {
        "id": "pptx_summary_concept_anlamadim",
        "input_type": "PPTX",
        "flow": "upload -> chunks -> calisma-ozeti -> concepts -> concept-detail -> anlamadim-v2",
        "minimum_success": "Slide chunklari olusur, summary ve concept endpointleri 200 doner.",
        "minimum_quality": "Summary ana madde uretir, concept detail kavrami bagli parcalarla dondurur.",
        "unacceptable_failure": "Slayt parse olup summary veya concept katmaninin bos kalmasi.",
        "automation": "pytest:test_real_user_pptx_upload_chain_keeps_summary_concept_and_explanation_usable",
    },
    {
        "id": "xlsx_table_logic_and_analytics",
        "input_type": "XLSX",
        "flow": "upload -> chunks -> anlamadim-v2 -> excel-modes -> export-readiness",
        "minimum_success": "Table summary/table rows chunklari olusur, analytics paneli 200 doner.",
        "minimum_quality": "Aciklama tablo/sheet mantigina bakar, analytics bos kalmaz.",
        "unacceptable_failure": "Tablo parse olup explanation veya analytics tarafinin anlamsiz sekilde bos kalmasi.",
        "automation": "pytest:test_real_user_xlsx_upload_chain_keeps_table_logic_and_analytics_usable",
    },
    {
        "id": "text_pdf_summary_and_export",
        "input_type": "PDF (text)",
        "flow": "upload -> chunks -> calisma-ozeti -> readme-export",
        "minimum_success": "Text PDF normal chunk ureterek summary ve export yuzeyine akar.",
        "minimum_quality": "Summary kullanisli ana madde cikarir, export okunabilir shape tutar.",
        "unacceptable_failure": "PDF parse olmasina ragmen downstream tamamen bos kalmasi.",
        "automation": "manual/regression existing suites",
    },
    {
        "id": "scanned_pdf_ocr_retrieval",
        "input_type": "PDF (image-only/scanned)",
        "flow": "upload -> OCR fallback -> chunks -> concepts -> ai2 kanitli-cevap",
        "minimum_success": "OCR fallback ile parca olusur, upload response OCR kullanimini yansitir, retrieval 200 doner.",
        "minimum_quality": "Chunklar visual_ocr olarak etiketlenir, retrieval citation ile kanita bagli kalir.",
        "unacceptable_failure": "Scanned PDF sessizce bos chunk uretmesi veya OCR kullandigi halde bunu gizlemesi.",
        "automation": "pytest:test_real_user_scanned_pdf_upload_reports_ocr_and_supports_retrieval",
    },
    {
        "id": "ocr_image_direct_upload",
        "input_type": "PNG/JPG OCR image",
        "flow": "upload",
        "minimum_success": "Image upload ya acik bicimde kabul edilir ya da durustce reddedilir.",
        "minimum_quality": "Hata mesaji yonlendirici olur, sahte basari uretmez.",
        "unacceptable_failure": "Image upload'un sahte parcalandi yazmasi veya belirsiz hata vermesi.",
        "automation": "pytest:test_real_user_failure_surfaces_stay_honest_for_direct_image_and_bad_scan",
    },
    {
        "id": "txt_md_summary_readme",
        "input_type": "TXT/MD",
        "flow": "upload -> chunks -> calisma-ozeti -> readme-export -> panels-kpi",
        "minimum_success": "Heading-aware text chunklari ve aggregate paneller 200 doner.",
        "minimum_quality": "Summary dolu olur, panel aggregate cevabi ham metin tasimaz.",
        "unacceptable_failure": "Kisa metinlerde teknik olarak gecip kullaniciya bos cevap donmesi.",
        "automation": "pytest:test_real_user_panel_aggregates_stay_stable_after_multi_doc_usage",
    },
    {
        "id": "python_code_explanation",
        "input_type": "Python code",
        "flow": "upload -> chunks -> anlamadim-v2",
        "minimum_success": "Function/method/test chunklari olusur, explanation 200 doner.",
        "minimum_quality": "Function purpose, flow summary ve line/block comments dolu olur.",
        "unacceptable_failure": "Kod chunki varken explanation'in bos veya asiri genel kalmasi.",
        "automation": "pytest:test_real_user_python_code_upload_keeps_structured_explanations_connected",
    },
    {
        "id": "non_python_js_safe_explanation",
        "input_type": "JavaScript code",
        "flow": "upload -> chunks -> anlamadim-v2",
        "minimum_success": "Function/api_call/control_flow sinyalleri korunur, explanation 200 doner.",
        "minimum_quality": "Event -> api -> state akisi gorunur, parser gucu abartilmaz.",
        "unacceptable_failure": "JS event handler'in duz genel metne donmesi veya Python gibi aciklanmasi.",
        "automation": "pytest:test_real_user_non_python_code_upload_stays_safe_and_visible",
    },
    {
        "id": "non_python_ps1_safe_explanation",
        "input_type": "PowerShell code",
        "flow": "upload -> chunks -> anlamadim-v2",
        "minimum_success": "Komut ve pipeline sinyalleri korunur.",
        "minimum_quality": "Dis cagrilar ve pipeline varligi gorunur, parser derinligi abartilmaz.",
        "unacceptable_failure": "PowerShell yuzeyinin duz metin gibi anlatilmasi.",
        "automation": "manual/smoke_docverse_e2e.ps1",
    },
    {
        "id": "concept_surface_detail_chain",
        "input_type": "Any structured doc",
        "flow": "upload -> concepts -> concepts/detail",
        "minimum_success": "Surface ve detail birlikte 200 doner.",
        "minimum_quality": "Kavram detail cevabi parca baglariyla gelir.",
        "unacceptable_failure": "Surface dolu olup detail tarafinin bos veya tutarsiz kalmasi.",
        "automation": "pytest:test_real_user_pptx_upload_chain_keeps_summary_concept_and_explanation_usable",
    },
    {
        "id": "retrieval_rag_answer_chain",
        "input_type": "Scanned or text doc",
        "flow": "upload -> chunks -> ai2 kanitli-cevap",
        "minimum_success": "Supported cevap citation ile doner.",
        "minimum_quality": "Kullanilan kanit sayisi ve citation listesi tutarli olur.",
        "unacceptable_failure": "Citation disi uydurma veya unsupported durumda sahte destekli cevap.",
        "automation": "pytest:test_real_user_scanned_pdf_upload_reports_ocr_and_supports_retrieval",
    },
    {
        "id": "notes_create_update_chain",
        "input_type": "Uploaded doc + part",
        "flow": "upload -> parca -> note create -> note update",
        "minimum_success": "Not create 201 ve update 200 doner.",
        "minimum_quality": "Not yanitlari status_text ile kararlidir ve owner baglamini korur.",
        "unacceptable_failure": "Note create/update zincirinin sessizce bos veya tutarsiz payload donmesi.",
        "automation": "manual/tools/smoke_docverse_e2e.ps1 -ProbeNotes",
    },
    {
        "id": "foreign_object_safe_reject",
        "input_type": "Two authenticated users",
        "flow": "secondary note create -> primary foreign access deny",
        "minimum_success": "Primary user foreign note icin 404/resource_not_found alir.",
        "minimum_quality": "Var ama sana ait degil bilgisi sizmaz.",
        "unacceptable_failure": "Foreign object erisiminin veri sizdirmasi veya 200 ile donmesi.",
        "automation": "manual/tools/smoke_docverse_e2e.ps1 -ProbeForeignAccess",
    },
    {
        "id": "throttle_safe_429_probe",
        "input_type": "Low-rate staging or test env",
        "flow": "repeated note writes -> 429",
        "minimum_success": "Rate limit tetiklenirse 429 ve rate_limited payload doner.",
        "minimum_quality": "detail/status_text/retry_after istemci-dostu kalir.",
        "unacceptable_failure": "429 body shape'in bozulmasi veya ham framework detayi donmesi.",
        "automation": "manual/tools/smoke_docverse_e2e.ps1 -ProbeThrottle -RequireThrottleHit",
    },
    {
        "id": "export_and_readme_consistency",
        "input_type": "DOCX/MD/PDF",
        "flow": "upload -> readme-export -> real-export/export-manifest",
        "minimum_success": "Readme ve export JSON payload shape'i bozulmaz.",
        "minimum_quality": "Manifest/output_meta alanlari tutarli kalir.",
        "unacceptable_failure": "Export hazir gorunup download/meta tarafinin bos donmesi.",
        "automation": "pytest:test_real_user_docx_upload_chain_keeps_explanation_concept_and_export_usable",
    },
    {
        "id": "panel_kpi_aggregate_no_leak",
        "input_type": "Mixed docs",
        "flow": "upload -> product surfaces -> analytics/kpi -> panels-kpi",
        "minimum_success": "KPI endpointleri 200 ve numerik aggregate cevap dondurur.",
        "minimum_quality": "Ham metin, ham kod, benchmark veya debug alanlari sizmaz.",
        "unacceptable_failure": "Aggregate endpoint'in ham icerik veya ic teknik alan dondurmesi.",
        "automation": "pytest:test_real_user_panel_aggregates_stay_stable_after_multi_doc_usage",
    },
]


def _client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _repo_fixture(name: str) -> Path:
    return _REPO_ROOT / name


def _upload_file(
    client: APIClient,
    path: Path,
    *,
    content_type: str,
    title: str | None = None,
):
    return client.post(
        "/api/dokuman-asistani/dokumanlar/yukle/",
        {
            "baslik": title or path.stem,
            "dosya": SimpleUploadedFile(path.name, path.read_bytes(), content_type=content_type),
        },
        format="multipart",
    )


def _get_parts(client: APIClient, doc_id: int) -> dict:
    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc_id}/parcalar/")
    assert response.status_code == 200
    assert response.data["doc_id"] == doc_id
    assert response.data["parca_sayisi"] >= 1
    return response.data


def _post_explanation(client: APIClient, part_id: int, *, mesaj: str = "Bu parcayi sade anlat."):
    response = client.post(
        f"/api/dokuman-asistani/parcalar/{part_id}/anlamadim-v2/",
        {"mesaj": mesaj},
        format="json",
    )
    assert response.status_code == 200
    return response.data


def _meaningful_words(text: str) -> set[str]:
    stopwords = {
        "ve",
        "veya",
        "ile",
        "icin",
        "gibi",
        "olan",
        "bu",
        "bir",
        "the",
        "and",
        "for",
        "that",
        "from",
    }
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9_]{4,}", text or "")
        if token.lower() not in stopwords
    }


def _assert_overlap(surface_text: str, source_text: str, *, min_hits: int = 1) -> None:
    overlap = _meaningful_words(surface_text) & _meaningful_words(source_text)
    assert len(overlap) >= min_hits


def _assert_nonempty_explanation(payload: dict) -> None:
    assert payload["dokumanda_yok"] is False
    assert payload["one_liner"].strip()
    assert payload["very_simple"].strip()
    assert len(payload["steps"]) >= 2
    assert len(payload["examples"]) >= 1
    rendered = json.dumps(payload, ensure_ascii=False).lower()
    assert "bir sey yapar" not in rendered
    assert "bir is yapar" not in rendered


def _assert_safe_aggregate_payload(payload: dict) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, default=str).lower()
    for forbidden in (
        "benchmark",
        "debug_ozeti",
        "prompt_debug",
        "raw_text",
        "retrieval_ozeti",
        "portal note",
    ):
        assert forbidden not in rendered


def _write_image_only_pdf(path: Path, text: str) -> Path:
    image = Image.new("RGB", (1200, 700), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((70, 130), text, fill="black")
    image.save(path, "PDF")
    return path


def _write_png(path: Path, text: str) -> Path:
    image = Image.new("RGB", (500, 220), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 90), text, fill="black")
    image.save(path, "PNG")
    return path


def _write_python_code(path: Path) -> Path:
    path.write_text(
        "class SessionStore:\n"
        "    def update(self, state, payload):\n"
        "        state['token'] = payload.get('token')\n"
        "        state['refreshed'] = True\n"
        "        return state\n\n"
        "def build_payload(raw):\n"
        "    token = raw.strip().lower()\n"
        "    return {'token': token}\n\n"
        "def test_update_flow(client):\n"
        "    payload = build_payload(' JWT ')\n"
        "    response = client.post('/session', payload, format='json')\n"
        "    assert response.status_code == 200\n"
        "    assert response.json()['token'] == 'jwt'\n",
        encoding="utf-8",
    )
    return path


def _write_javascript_code(path: Path) -> Path:
    path.write_text(
        "export async function handleSave(event) {\n"
        "  event.preventDefault();\n"
        "  const response = await fetch('/api/save', { method: 'POST' });\n"
        "  if (response.ok) {\n"
        "    setSaved(true);\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    return path


def _write_markdown(path: Path) -> Path:
    path.write_text(
        "# KPI Signal\n\n"
        "HAM_PANEL_SECRET should stay inside source chunks and not appear in aggregate analytics.\n\n"
        "## Akis\n\n"
        "- Study summary kullanilir\n"
        "- Readme export kullanilir\n"
        "- Panel KPI aggregate cevap doner\n",
        encoding="utf-8",
    )
    return path


def test_real_user_docx_upload_chain_keeps_explanation_concept_and_export_usable(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
    monkeypatch,
):
    settings.DOCVERSE_CONCEPTS_ENABLED = True
    settings.DOCVERSE_STUDY_SUMMARY_ENABLED = True
    settings.DOCVERSE_README_EXPORT_ENABLED = True
    settings.DOCVERSE_EXPORT_PLAN_ENABLED = True
    settings.DOCVERSE_REAL_EXPORTS_ENABLED = True
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})
    client = _client(test_kullanicisi)

    upload = _upload_file(
        client,
        _repo_fixture("test_ingest.docx"),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        title="Real User DOCX",
    )

    assert upload.status_code == 201
    assert upload.data["durum"] == "parcalandi"
    assert upload.data["parca_sayisi"] >= 1

    doc_id = upload.data["id"]
    parcalar = _get_parts(client, doc_id)
    first = parcalar["parcalar"][0]
    explanation = _post_explanation(client, first["id"])
    concepts = client.get(f"/api/dokuman-asistani/dokumanlar/{doc_id}/concepts/")
    readme = client.get(f"/api/dokuman-asistani/dokumanlar/{doc_id}/readme-export/", {"out": "json"})
    real_export = client.get(
        f"/api/dokuman-asistani/dokumanlar/{doc_id}/real-export/",
        {"format": "pptx", "out": "json"},
    )

    _assert_nonempty_explanation(explanation)
    _assert_overlap(
        " ".join(
            [
                explanation["one_liner"],
                explanation["very_simple"],
                " ".join(explanation["steps"]),
            ]
        ),
        first["metin"],
    )
    assert concepts.status_code == 200
    assert concepts.data["dokuman_id"] == doc_id
    assert concepts.data["toplam_kavram"] >= 1
    assert readme.status_code == 200
    assert set(readme.data.keys()) == {
        "dokuman_id",
        "baslik",
        "proje_ozeti",
        "kurulum",
        "kullanim",
        "kritik_bilesenler",
        "kaynak_parca_idleri",
        "manifest",
        "output_meta",
    }
    assert real_export.status_code == 200
    assert set(real_export.data.keys()) == {
        "dokuman_id",
        "baslik",
        "hedef_format",
        "durum",
        "readiness",
        "download_ready",
        "manifest",
        "output_meta",
    }
    assert real_export.data["hedef_format"] == "pptx"
    _assert_safe_aggregate_payload(concepts.data)
    _assert_safe_aggregate_payload(readme.data)
    _assert_safe_aggregate_payload(real_export.data)


def test_real_user_pptx_upload_chain_keeps_summary_concept_and_explanation_usable(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
    monkeypatch,
):
    settings.DOCVERSE_CONCEPTS_ENABLED = True
    settings.DOCVERSE_STUDY_SUMMARY_ENABLED = True
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})
    client = _client(test_kullanicisi)

    upload = _upload_file(
        client,
        _repo_fixture("test_ingest.pptx"),
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        title="Real User PPTX",
    )

    assert upload.status_code == 201
    doc_id = upload.data["id"]
    parcalar = _get_parts(client, doc_id)["parcalar"]
    slide_summary = next(
        (item for item in parcalar if (item.get("meta") or {}).get("chunk_kind") == "slide_summary"),
        parcalar[0],
    )
    explanation = _post_explanation(client, slide_summary["id"], mesaj="Bu slayti sade anlat.")
    summary = client.get(f"/api/dokuman-asistani/dokumanlar/{doc_id}/calisma-ozeti/")
    concepts = client.get(f"/api/dokuman-asistani/dokumanlar/{doc_id}/concepts/")

    _assert_nonempty_explanation(explanation)
    _assert_overlap(
        f"{explanation['one_liner']} {explanation['very_simple']}",
        slide_summary["metin"],
    )
    assert summary.status_code == 200
    assert summary.data["calisma_ozeti"]["dokuman_id"] == doc_id
    assert summary.data["calisma_ozeti"]["ana_maddeler"]
    assert concepts.status_code == 200
    assert concepts.data["toplam_kavram"] >= 1

    first_concept = concepts.data["kavramlar"][0]["kavram"]
    detail = client.get(
        f"/api/dokuman-asistani/dokumanlar/{doc_id}/concepts/detail/",
        {"kavram": first_concept},
    )
    assert detail.status_code == 200
    assert detail.data["kavram"] == first_concept
    assert detail.data["bagli_parca_idleri"]
    _assert_safe_aggregate_payload(summary.data)
    _assert_safe_aggregate_payload(concepts.data)
    _assert_safe_aggregate_payload(detail.data)


def test_real_user_xlsx_upload_chain_keeps_table_logic_and_analytics_usable(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
    monkeypatch,
):
    settings.DOCVERSE_EXPORT_PLAN_ENABLED = True
    settings.DOCVERSE_EXPORT_READINESS_ENABLED = True
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})
    client = _client(test_kullanicisi)

    upload = _upload_file(
        client,
        _repo_fixture("test_ingest.xlsx"),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        title="Real User XLSX",
    )

    assert upload.status_code == 201
    doc_id = upload.data["id"]
    parcalar = _get_parts(client, doc_id)["parcalar"]
    assert any((item.get("meta") or {}).get("chunk_kind") == "table_summary" for item in parcalar)
    assert any((item.get("meta") or {}).get("chunk_kind") == "table_rows" for item in parcalar)
    summary_part = next(
        item for item in parcalar if (item.get("meta") or {}).get("chunk_kind") == "table_summary"
    )

    explanation = _post_explanation(client, summary_part["id"], mesaj="Bu tablo ne yapiyor?")
    excel_modes = client.get(f"/api/dokuman-asistani/dokumanlar/{doc_id}/excel-modes/")
    export_readiness = client.get(f"/api/dokuman-asistani/dokumanlar/{doc_id}/export-readiness/")

    _assert_nonempty_explanation(explanation)
    _assert_overlap(
        f"{explanation['one_liner']} {explanation['very_simple']}",
        summary_part["metin"],
    )
    assert excel_modes.status_code == 200
    assert set(excel_modes.data.keys()) == {
        "dokuman_id",
        "portal_not_id",
        "mod",
        "baslik",
        "kartlar",
        "oneriler",
        "kaynak_parca_idleri",
    }
    assert export_readiness.status_code == 200
    assert set(export_readiness.data.keys()) == {
        "pdf_hazirlik",
        "docx_hazirlik",
        "pptx_hazirlik",
        "readme_hazirlik",
        "export_readiness_score",
        "onerilen_format",
        "eksik_bilesenler",
    }
    _assert_safe_aggregate_payload(excel_modes.data)
    _assert_safe_aggregate_payload(export_readiness.data)


def test_real_user_scanned_pdf_upload_reports_ocr_and_supports_retrieval(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
    tmp_path,
    monkeypatch,
):
    settings.DOCVERSE_CONCEPTS_ENABLED = True
    settings.OCR_ENABLED = True
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})
    monkeypatch.setattr(
        "dokuman.services.ingestion.parse_document_structure",
        lambda path: {"section_count": 0, "sections": []},
    )
    monkeypatch.setattr(
        "dokuman.services.ocr.extract_text_from_pdf_pages",
        lambda path: [
            {
                "page": 1,
                "text": "JWT OCR akisi giris sayfasi.\n\nRefresh token ve retry adimlari burada anlatilir.",
                "image_width": 1000,
                "image_height": 1400,
            },
            {
                "page": 2,
                "text": "Yetkilendirme kontrolu ikinci sayfada devam eder.\n\nStatus assertion ve field assertion birlikte okunur.",
                "image_width": 1000,
                "image_height": 1400,
            },
        ],
    )
    client = _client(test_kullanicisi)
    file_path = _write_image_only_pdf(tmp_path / "scan.pdf", "JWT OCR scan document")

    upload = _upload_file(client, file_path, content_type="application/pdf", title="Scanned PDF")

    assert upload.status_code == 201
    assert upload.data["durum"] == "parcalandi"
    assert upload.data["parca_sayisi"] == 2
    assert upload.data["ocr"] is True

    doc_id = upload.data["id"]
    parcalar = _get_parts(client, doc_id)["parcalar"]
    assert all((item.get("meta") or {}).get("chunk_kind") == "visual_ocr" for item in parcalar)
    assert all((item.get("meta") or {}).get("format") == "pdf" for item in parcalar)
    parca_meta = list(Parca.objects.filter(dokuman_id=doc_id).order_by("sira").values_list("meta", flat=True))
    assert all((meta or {}).get("ocr") is True for meta in parca_meta)
    assert all((meta or {}).get("ocr_fallback") is True for meta in parca_meta)

    concepts = client.get(f"/api/dokuman-asistani/dokumanlar/{doc_id}/concepts/")
    assert concepts.status_code == 200
    assert concepts.data["toplam_kavram"] >= 1

    first_part_id = parcalar[0]["id"]
    monkeypatch.setattr("dokuman.views_ai2._should_abstain_for_low_evidence", lambda kanit_meta: False)
    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: json.dumps(
            {
                "answer": "JWT OCR akisinda refresh token ve retry adimlari kaynak parcayla dogrulaniyor.",
                "supported": True,
                "citations": [first_part_id],
                "missing": [],
                "followups": [],
            },
            ensure_ascii=False,
        ),
    )

    retrieval = client.post(
        "/api/dokuman-asistani/ai2/kanitli-cevap/",
        {"question": "JWT OCR akisinda ne dogrulaniyor?", "doc_id": doc_id, "top_k": 2},
        format="json",
    )

    assert retrieval.status_code == 200
    assert retrieval.data["supported"] is True
    assert retrieval.data["citations"] == [first_part_id]
    assert retrieval.data["kullanilan_kanit_sayisi"] == 1
    _assert_safe_aggregate_payload(concepts.data)


def test_real_user_failure_surfaces_stay_honest_for_direct_image_and_bad_scan(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
    tmp_path,
    monkeypatch,
):
    settings.DOCVERSE_UPLOAD_EXTENSIONS = [".pdf", ".docx", ".png"]
    settings.DOCVERSE_IMAGE_UPLOAD_ENABLED = False
    client = _client(test_kullanicisi)

    png_path = _write_png(tmp_path / "ocr.png", "JWT image upload")
    image_upload = _upload_file(client, png_path, content_type="image/png", title="Disabled Image")

    assert image_upload.status_code == 400
    assert ".png" not in image_upload.data["allowed"]
    assert "parcalandi" not in json.dumps(image_upload.data, ensure_ascii=False).lower()

    monkeypatch.setattr(
        "dokuman.services.ingestion.parse_document_structure",
        lambda path: {"section_count": 0, "sections": []},
    )
    monkeypatch.setattr("dokuman.services.ocr.extract_text_from_pdf_pages", lambda path: [])
    bad_scan = _write_image_only_pdf(tmp_path / "bad-scan.pdf", "unreadable scan")
    bad_upload = _upload_file(client, bad_scan, content_type="application/pdf", title="Bad Scan")

    assert bad_upload.status_code == 422
    assert bad_upload.data["durum"] == "hata"
    assert bad_upload.data["parca_sayisi"] == 0
    assert "ocr" in (bad_upload.data["mesaj"] or "").lower()


def test_real_user_python_code_upload_keeps_structured_explanations_connected(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})
    client = _client(test_kullanicisi)
    file_path = _write_python_code(tmp_path / "session_flow.py")

    upload = _upload_file(client, file_path, content_type="text/x-python", title="Python Code")

    assert upload.status_code == 201
    doc_id = upload.data["id"]
    parcalar = _get_parts(client, doc_id)["parcalar"]
    unit_kinds = {(item.get("meta") or {}).get("code_unit_kind") for item in parcalar}
    assert {"function", "method", "test_function", "test_step", "api_call", "assertion"} <= unit_kinds

    target = next(item for item in parcalar if (item.get("meta") or {}).get("code_unit_kind") == "method")
    explanation = _post_explanation(client, target["id"], mesaj="Bu method state'i nasil etkiliyor?")

    assert explanation["function_purpose"].strip()
    assert explanation["flow_summary"].strip()
    assert len(explanation["block_comments"]) >= 1
    assert len(explanation["line_comments"]) >= 1
    assert "update" in explanation["function_purpose"].lower()
    assert "state" in explanation["function_purpose"].lower()
    assert "girdi" in explanation["flow_summary"].lower()


def test_real_user_non_python_code_upload_stays_safe_and_visible(
    db,
    test_kullanicisi,
    gecici_media_root,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})
    client = _client(test_kullanicisi)
    file_path = _write_javascript_code(tmp_path / "ui.js")

    upload = _upload_file(client, file_path, content_type="application/javascript", title="JS Code")

    assert upload.status_code == 201
    doc_id = upload.data["id"]
    parcalar = _get_parts(client, doc_id)["parcalar"]
    unit_kinds = {(item.get("meta") or {}).get("code_unit_kind") for item in parcalar}
    assert {"function", "api_call", "control_flow"} <= unit_kinds

    target = next(item for item in parcalar if (item.get("meta") or {}).get("code_unit_kind") == "function")
    explanation = _post_explanation(client, target["id"], mesaj="Bu frontend fonksiyonu hangi etkilesimi yonetiyor?")
    lowered = json.dumps(
        {
            "function_purpose": explanation["function_purpose"],
            "flow_summary": explanation["flow_summary"],
            "line_comments": explanation["line_comments"],
        },
        ensure_ascii=False,
    ).lower()

    assert "event" in lowered or "callback" in lowered
    assert "api" in lowered
    assert "state" in lowered or "arayuz" in lowered
    assert "python" not in lowered


def test_real_user_panel_aggregates_stay_stable_after_multi_doc_usage(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
    tmp_path,
    monkeypatch,
):
    settings.DOCVERSE_METRIC_STORE_ENABLED = True
    settings.DOCVERSE_BOSS_ENABLED = True
    settings.DOCVERSE_BOSS_RUSH_PANEL_ENABLED = True
    settings.DOCVERSE_EXPORT_PLAN_ENABLED = True
    settings.DOCVERSE_EXPORT_READINESS_ENABLED = True
    settings.DOCVERSE_PERSONALIZATION_ENABLED = True
    settings.DOCVERSE_STUDY_SUMMARY_ENABLED = True
    settings.DOCVERSE_README_EXPORT_ENABLED = True
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"ok": True})
    client = _client(test_kullanicisi)

    md_upload = _upload_file(
        client,
        _write_markdown(tmp_path / "notes.md"),
        content_type="text/markdown",
        title="Panel Markdown",
    )
    xlsx_upload = _upload_file(
        client,
        _repo_fixture("test_ingest.xlsx"),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        title="Panel XLSX",
    )

    assert md_upload.status_code == 201
    assert xlsx_upload.status_code == 201

    md_doc_id = md_upload.data["id"]
    xlsx_doc_id = xlsx_upload.data["id"]

    summary = client.get(f"/api/dokuman-asistani/dokumanlar/{md_doc_id}/calisma-ozeti/")
    readme = client.get(f"/api/dokuman-asistani/dokumanlar/{md_doc_id}/readme-export/", {"out": "json"})
    export_readiness = client.get(f"/api/dokuman-asistani/dokumanlar/{xlsx_doc_id}/export-readiness/")
    panels = client.get("/api/dokuman-asistani/analytics/panels-kpi/")
    analytics = client.get("/api/dokuman-asistani/analytics/kpi/")

    assert summary.status_code == 200
    assert readme.status_code == 200
    assert export_readiness.status_code == 200
    assert panels.status_code == 200
    assert analytics.status_code == 200
    assert set(panels.data.keys()) == {
        "boss_rush_ready_ratio",
        "weekly_goal_completion_avg",
        "achievement_progress_avg",
        "export_readiness_avg",
        "personalization_confidence_avg",
    }
    assert set(analytics.data.keys()) == {
        "net_usefulness_score",
        "global_confusion_index",
        "feedback_trust_ratio",
        "cheatsheet_yield",
    }
    assert "HAM_PANEL_SECRET" not in json.dumps(panels.data, ensure_ascii=False)
    assert "HAM_PANEL_SECRET" not in json.dumps(analytics.data, ensure_ascii=False)
    _assert_safe_aggregate_payload(summary.data)
    _assert_safe_aggregate_payload(readme.data)
    _assert_safe_aggregate_payload(export_readiness.data)
    _assert_safe_aggregate_payload(panels.data)
    _assert_safe_aggregate_payload(analytics.data)
