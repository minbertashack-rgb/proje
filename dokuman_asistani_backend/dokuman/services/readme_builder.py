from __future__ import annotations

from dokuman.services.export_writer import (
    build_attachment_filename,
    build_markdown_document,
    build_output_meta,
    markdown_to_txt,
)
from dokuman.services.export_manifest_v2 import build_export_manifest_v2_payload
from dokuman.services.study_summary import build_study_summary_payload


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _dedupe_strings(values, *, limit: int = 6) -> list[str]:
    out = []
    seen = set()
    for value in values or []:
        clean = _clean_text(value)
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def build_readme_payload(*, doc, user, portal_not=None) -> dict:
    summary = build_study_summary_payload(doc=doc, user=user, portal_not=portal_not)
    baslik = f"{doc.baslik or f'Dokuman {doc.id}'} README"
    kritik_bilesenler = _dedupe_strings(
        list(summary.get("ana_maddeler") or []) + [item.get("terim") for item in summary.get("glossary") or []],
        limit=6,
    ) or ["Temel moduller", "Kurulum akisi", "Kullanim senaryosu"]
    kurulum = [
        "Gereksinimleri yukle ve ortam ayarlarini kontrol et.",
        "Temel giris noktalarini ve bagli bilesenleri dogrula.",
        "Ilk calistirma sonrasi ozet ve kritik notlari yeniden gozden gecir.",
    ]
    kullanim = _dedupe_strings(
        [summary.get("kisa_ozet")] + [f"Kullanim ipucu: {item}" for item in (summary.get("kritik_notlar") or [])],
        limit=4,
    ) or ["Projeyi baslat, ana akisi dogrula ve kritik notlari takip et."]
    return {
        "dokuman_id": doc.id,
        "baslik": baslik,
        "proje_ozeti": summary.get("kisa_ozet") or "Bu README dokuman ozetinden derlendi.",
        "kurulum": kurulum,
        "kullanim": kullanim,
        "kritik_bilesenler": kritik_bilesenler,
        "kaynak_parca_idleri": list(summary.get("bagli_parca_idleri") or []),
    }


def build_readme_export_result(*, doc, user, portal_not=None, output_format: str = "md") -> dict:
    payload = build_readme_payload(doc=doc, user=user, portal_not=portal_not)
    manifest_format = "txt" if output_format == "txt" else "markdown"
    manifest = build_export_manifest_v2_payload(
        doc=doc,
        user=user,
        portal_not=portal_not,
        hedef_format=manifest_format,
        cheatsheet_enabled=True,
        concepts_enabled=True,
    )
    if not payload["kaynak_parca_idleri"]:
        payload["kaynak_parca_idleri"] = list(manifest.get("kaynak_parca_idleri") or [])
    output_meta = build_output_meta(
        manifest=manifest,
        output_format=output_format,
        output_created=True,
        section_count=5,
    )
    sections = [
        {"heading": "Proje Ozeti", "body": payload["proje_ozeti"], "bullets": []},
        {"heading": "Kurulum", "body": "", "bullets": payload["kurulum"]},
        {"heading": "Kullanim", "body": "", "bullets": payload["kullanim"]},
        {"heading": "Kritik Bilesenler", "body": "", "bullets": payload["kritik_bilesenler"]},
        {
            "heading": "Kaynak Parcalar",
            "body": ", ".join(str(item) for item in payload["kaynak_parca_idleri"]),
            "bullets": [],
        },
    ]
    markdown = build_markdown_document(title=payload["baslik"], sections=sections, output_meta=output_meta)
    txt = markdown_to_txt(markdown)
    result = {
        **payload,
        "manifest": manifest,
        "output_meta": output_meta,
        "content": None,
        "content_type": "",
        "filename": "",
        "durum": "ok",
        "readiness": "ready",
    }
    if output_format == "json":
        return result
    if output_format in {"md", "markdown"}:
        result["content"] = markdown.encode("utf-8")
        result["content_type"] = "text/markdown; charset=utf-8"
        result["filename"] = build_attachment_filename(title=payload["baslik"], prefix="readme", ext="md")
        return result
    if output_format == "txt":
        result["content"] = txt.encode("utf-8")
        result["content_type"] = "text/plain; charset=utf-8"
        result["filename"] = build_attachment_filename(title=payload["baslik"], prefix="readme", ext="txt")
        return result
    result["durum"] = "fallback"
    result["readiness"] = "unsupported_format"
    result["output_meta"]["output_created"] = False
    return result
