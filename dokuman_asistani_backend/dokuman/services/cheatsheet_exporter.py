from __future__ import annotations

from dokuman.services.cheatsheet_builder import build_cheatsheet_payload
from dokuman.services.export_manifest_v2 import build_export_manifest_v2_payload
from dokuman.services.export_writer import (
    build_attachment_filename,
    build_markdown_document,
    build_output_meta,
    markdown_to_txt,
    write_docx_bytes,
    write_pdf_bytes,
)
from dokuman.services.study_summary import build_study_summary_payload


def _glossary_lines(payload: dict) -> list[str]:
    out = []
    for item in payload.get("glossary") or []:
        terim = str(item.get("terim") or "").strip()
        tanim = str(item.get("tanim") or "").strip()
        if terim and tanim:
            out.append(f"{terim}: {tanim}")
    return out[:5]


def _merge_source_ids(primary_ids, secondary_ids) -> list[int]:
    seen = set()
    merged = []
    for raw in list(primary_ids or []) + list(secondary_ids or []):
        try:
            value = int(raw)
        except Exception:
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        merged.append(value)
    return merged


def _manifest_for_cheatsheet(*, doc, payload: dict, output_format: str, manifest_v2: dict) -> dict:
    kaynak_ids = _merge_source_ids(
        payload.get("bagli_parca_idleri"),
        manifest_v2.get("kaynak_parca_idleri"),
    )
    return {
        "format": output_format,
        "dokuman_id": doc.id,
        "portal_not_id": payload.get("portal_not_id"),
        "kullanilan_parca_sayisi": len(payload.get("bagli_parca_idleri") or []),
        "ana_madde_sayisi": len(payload.get("ana_maddeler") or []),
        "kritik_not_sayisi": len(payload.get("kritik_notlar") or []),
        "kaynak_parca_idleri": kaynak_ids,
        "source_manifest_version": "v2",
    }


def _cheatsheet_sections(payload: dict, output_meta: dict) -> list[dict]:
    return [
        {"heading": "Kisa Ozet", "body": payload.get("kisa_ozet", ""), "bullets": []},
        {"heading": "Ana Maddeler", "body": "", "bullets": list(payload.get("ana_maddeler") or [])[:6]},
        {"heading": "Kritik Notlar", "body": "", "bullets": list(payload.get("kritik_notlar") or [])[:4]},
        {"heading": "Kisa Glossary", "body": "", "bullets": _glossary_lines(payload)},
        {
            "heading": "Kaynak Parcalar",
            "body": ", ".join(str(item) for item in payload.get("bagli_parca_idleri") or []),
            "bullets": [],
        },
        {
            "heading": "Manifest",
            "body": "",
            "bullets": [
                f"output_format: {output_meta['output_format']}",
                f"source_manifest_version: {output_meta['source_manifest_version']}",
                f"section_count: {output_meta['section_count']}",
            ],
        },
    ]


def build_cheatsheet_export_result(*, doc, user, portal_not=None, output_format: str = "md") -> dict:
    payload = build_cheatsheet_payload(doc=doc, user=user, portal_not=portal_not, include_internal=True)
    internal_scores = dict(payload.pop("_internal_scores", {}) or {})
    study_summary = build_study_summary_payload(doc=doc, user=user, portal_not=portal_not)
    manifest_format = "txt" if output_format == "txt" else "markdown"
    manifest_v2 = build_export_manifest_v2_payload(
        doc=doc,
        user=user,
        portal_not=portal_not,
        hedef_format=manifest_format,
        cheatsheet_enabled=True,
        concepts_enabled=True,
    )
    manifest = _manifest_for_cheatsheet(doc=doc, payload=payload, output_format=output_format, manifest_v2=manifest_v2)
    payload["bagli_parca_idleri"] = list(manifest.get("kaynak_parca_idleri") or payload.get("bagli_parca_idleri") or [])
    sections = _cheatsheet_sections(
        payload={
            **payload,
            "kritik_notlar": list(payload.get("kritik_notlar") or [])[:4] + [
                item for item in (study_summary.get("kritik_notlar") or []) if item not in (payload.get("kritik_notlar") or [])
            ][:2],
        },
        output_meta=build_output_meta(manifest=manifest, output_format=output_format, output_created=True, section_count=6),
    )
    output_meta = build_output_meta(
        manifest=manifest,
        output_format=output_format,
        output_created=True,
        section_count=len(sections),
    )
    markdown = build_markdown_document(title=payload.get("baslik") or "Cheatsheet", sections=sections, output_meta=output_meta)
    txt = markdown_to_txt(markdown)

    result = {
        "payload": payload,
        "internal_scores": internal_scores,
        "manifest": manifest,
        "output_meta": output_meta,
        "content": None,
        "content_type": "",
        "filename": "",
        "durum": "ok",
        "readiness": "ready",
    }

    if output_format in {"json"}:
        return result
    if output_format in {"md", "markdown"}:
        result["content"] = markdown.encode("utf-8")
        result["content_type"] = "text/markdown; charset=utf-8"
        result["filename"] = build_attachment_filename(title=payload.get("baslik") or "cheatsheet", prefix="cheatsheet", ext="md")
        return result
    if output_format == "txt":
        result["content"] = txt.encode("utf-8")
        result["content_type"] = "text/plain; charset=utf-8"
        result["filename"] = build_attachment_filename(title=payload.get("baslik") or "cheatsheet", prefix="cheatsheet", ext="txt")
        return result
    if output_format == "docx":
        content, reason = write_docx_bytes(title=payload.get("baslik") or "Cheatsheet", sections=sections)
        if content is None:
            result["durum"] = "fallback"
            result["readiness"] = reason
            result["output_meta"]["output_created"] = False
            return result
        result["content"] = content
        result["content_type"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        result["filename"] = build_attachment_filename(title=payload.get("baslik") or "cheatsheet", prefix="cheatsheet", ext="docx")
        return result
    if output_format == "pdf":
        content, reason = write_pdf_bytes(title=payload.get("baslik") or "Cheatsheet", sections=sections)
        if content is None:
            result["durum"] = "fallback"
            result["readiness"] = reason
            result["output_meta"]["output_created"] = False
            return result
        result["content"] = content
        result["content_type"] = "application/pdf"
        result["filename"] = build_attachment_filename(title=payload.get("baslik") or "cheatsheet", prefix="cheatsheet", ext="pdf")
        return result

    result["durum"] = "fallback"
    result["readiness"] = "unsupported_format"
    result["output_meta"]["output_created"] = False
    return result
