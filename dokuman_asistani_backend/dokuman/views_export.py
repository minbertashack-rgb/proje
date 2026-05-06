from __future__ import annotations

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from dokuman.models import Dokuman, DokumanNotu
from dokuman.serializers import ReadmeExportSerializer, RealExportSerializer
from dokuman.services.cheatsheet_exporter import build_cheatsheet_export_result
from dokuman.services.export_manifest_v2 import build_export_manifest_v2_payload
from dokuman.services.export_writer import (
    apply_output_meta_headers,
    build_attachment_filename,
    build_output_meta,
    write_docx_bytes,
    write_pdf_bytes,
    write_pptx_bytes,
)
from dokuman.services.feature_flags import modul_acik_mi
from dokuman.services.metric_store import (
    compute_confusion_map_score,
    compute_mastery_score,
    guvenli_metrik_kaydi_olustur,
)
from dokuman.services.presentation_builder import build_presentation_payload
from dokuman.services.readme_builder import build_readme_export_result
from dokuman.services.study_summary import build_study_summary_payload


def _modul_kapali_response(detay: str):
    return Response({"detail": detay}, status=404)


def _get_owned_doc(request, doc_id: int):
    return Dokuman.objects.filter(id=doc_id, owner=request.user).first()


def _get_owned_portal_not(request, *, doc, portal_not_id):
    if not portal_not_id:
        return None
    return DokumanNotu.objects.filter(id=portal_not_id, owner=request.user, dokuman=doc).first()


def _export_json_response(result: dict, *, serializer_class=None):
    payload = {
        key: value
        for key, value in result.items()
        if key not in {"content", "content_type", "filename"}
    }
    if serializer_class is None:
        return Response(payload)
    return Response(serializer_class(payload).data)


def _export_file_response(result: dict):
    response = HttpResponse(result["content"], content_type=result["content_type"])
    response["Content-Disposition"] = f'attachment; filename="{result["filename"]}"'
    apply_output_meta_headers(response, result["output_meta"])
    return response


def _record_export_metric(
    *,
    user,
    doc,
    event_name: str,
    source_module: str,
    output_meta: dict,
    manifest: dict,
    portal_not_id=None,
    extra_scores: dict | None = None,
):
    score_map = {
        "output_format": output_meta.get("output_format"),
        "source_manifest_version": output_meta.get("source_manifest_version"),
        "section_count": output_meta.get("section_count"),
        "slide_count": output_meta.get("slide_count"),
        "output_created": output_meta.get("output_created"),
        "kaynak_parca_sayisi": len(output_meta.get("source_parca_idleri") or []),
        **dict(extra_scores or {}),
    }
    guvenli_metrik_kaydi_olustur(
        kullanici=user,
        olay_turu=event_name,
        kaynak_modul=source_module,
        dokuman=doc,
        ilgili_portal_not_id=portal_not_id,
        skor_ozeti=score_map,
        durum="ok" if output_meta.get("output_created") else "hata",
    )


def _manifest_sections_for_report(manifest: dict, summary: dict) -> list[dict]:
    sections = [
        {"heading": "Kisa Ozet", "body": summary.get("kisa_ozet") or "Ozet bulunamadi.", "bullets": []},
        {"heading": "Ana Maddeler", "body": "", "bullets": list(summary.get("ana_maddeler") or [])[:5]},
    ]
    for section in manifest.get("bolumler") or []:
        sections.append(
            {
                "heading": section.get("baslik") or "Bolum",
                "body": section.get("amaci") or "",
                "bullets": [section.get("konusma_notu") or ""],
            }
        )
    sections.append(
        {
            "heading": "Kaynak Parcalar",
            "body": ", ".join(str(item) for item in manifest.get("kaynak_parca_idleri") or []),
            "bullets": [],
        }
    )
    return sections


def _build_real_export_result(*, doc, user, portal_not=None, hedef_format: str) -> dict:
    manifest = build_export_manifest_v2_payload(
        doc=doc,
        user=user,
        portal_not=portal_not,
        hedef_format=hedef_format,
        cheatsheet_enabled=modul_acik_mi("DOCVERSE_CHEATSHEET_EXPORT_ENABLED", True),
        concepts_enabled=modul_acik_mi("DOCVERSE_CONCEPTS_ENABLED", True),
    )
    summary = build_study_summary_payload(doc=doc, user=user, portal_not=portal_not)
    title = doc.baslik or f"Dokuman {doc.id}"
    sections = _manifest_sections_for_report(manifest, summary)
    section_count = len(sections)
    output_meta = build_output_meta(
        manifest=manifest,
        output_format=hedef_format,
        output_created=True,
        section_count=section_count,
        slide_count=0,
    )
    result = {
        "dokuman_id": doc.id,
        "baslik": title,
        "hedef_format": hedef_format,
        "durum": "ok",
        "readiness": "ready",
        "download_ready": True,
        "manifest": manifest,
        "output_meta": output_meta,
        "content": None,
        "content_type": "",
        "filename": "",
    }

    if hedef_format == "pdf":
        content, reason = write_pdf_bytes(title=title, sections=sections)
        if content is None:
            result["durum"] = "fallback"
            result["readiness"] = reason
            result["download_ready"] = False
            result["output_meta"]["output_created"] = False
            return result
        result["content"] = content
        result["content_type"] = "application/pdf"
        result["filename"] = build_attachment_filename(title=title, prefix="export", ext="pdf")
        return result

    if hedef_format == "docx":
        content, reason = write_docx_bytes(title=title, sections=sections)
        if content is None:
            result["durum"] = "fallback"
            result["readiness"] = reason
            result["download_ready"] = False
            result["output_meta"]["output_created"] = False
            return result
        result["content"] = content
        result["content_type"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        result["filename"] = build_attachment_filename(title=title, prefix="export", ext="docx")
        return result

    if hedef_format == "pptx":
        presentation = build_presentation_payload(doc=doc, user=user, manifest=manifest)
        slides = list(presentation.get("slaytlar") or [])
        result["output_meta"]["slide_count"] = len(slides)
        content, reason = write_pptx_bytes(title=title, slides=slides)
        if content is None:
            result["durum"] = "fallback"
            result["readiness"] = reason
            result["download_ready"] = False
            result["output_meta"]["output_created"] = False
            return result
        result["content"] = content
        result["content_type"] = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        result["filename"] = build_attachment_filename(title=title, prefix="export", ext="pptx")
        return result

    result["durum"] = "fallback"
    result["readiness"] = "unsupported_format"
    result["download_ready"] = False
    result["output_meta"]["output_created"] = False
    return result


class CheatSheetExport(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int, *args, **kwargs):
        if not modul_acik_mi("DOCVERSE_CHEATSHEET_EXPORT_ENABLED", True):
            return _modul_kapali_response("Cheatsheet export modulu devre disi.")

        fmt = (request.query_params.get("out") or request.query_params.get("format") or "pdf").lower()
        doc = _get_owned_doc(request, doc_id)
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        portal_not = _get_owned_portal_not(request, doc=doc, portal_not_id=request.query_params.get("portal_not_id"))
        if request.query_params.get("portal_not_id") and portal_not is None:
            return Response({"detail": "Portal not yok"}, status=404)

        result = build_cheatsheet_export_result(doc=doc, user=request.user, portal_not=portal_not, output_format=fmt)
        internal_scores = dict(result.get("internal_scores") or {})
        confusion_meta = compute_confusion_map_score(user=request.user, dokuman=doc)
        mastery_meta = compute_mastery_score(user=request.user, dokuman=doc)
        _record_export_metric(
            user=request.user,
            doc=doc,
            event_name="cheatsheet_export_generated",
            source_module="cheatsheet_export.api",
            output_meta=result["output_meta"],
            manifest=result["manifest"],
            portal_not_id=getattr(portal_not, "id", None),
            extra_scores={
                "ana_madde_sayisi": len(result["payload"].get("ana_maddeler") or []),
                "kritik_not_sayisi": len(result["payload"].get("kritik_notlar") or []),
                "glossary_sayisi": len(result["payload"].get("glossary") or []),
                "cheatsheet_priority_score": internal_scores.get("cheatsheet_priority_score", 0.0),
                "confusion_map_score": confusion_meta["confusion_map_score"],
                "mastery_score": mastery_meta["mastery_score"],
            },
        )
        guvenli_metrik_kaydi_olustur(
            kullanici=request.user,
            olay_turu="cheatsheet_export_uretildi",
            kaynak_modul="cheatsheet_export.api",
            dokuman=doc,
            ilgili_portal_not_id=getattr(portal_not, "id", None),
            skor_ozeti={
                "format": fmt,
                "ana_madde_sayisi": len(result["payload"].get("ana_maddeler") or []),
                "kritik_not_sayisi": len(result["payload"].get("kritik_notlar") or []),
                "glossary_sayisi": len(result["payload"].get("glossary") or []),
                "bagli_parca_sayisi": len(result["payload"].get("bagli_parca_idleri") or []),
                "cheatsheet_priority_score": internal_scores.get("cheatsheet_priority_score", 0.0),
                "cheatsheet_priority_reason": internal_scores.get("cheatsheet_priority_reason", "no_priority_signal"),
                "portal_not_var_mi": bool(result["payload"].get("portal_not_id")),
                "confusion_map_score": confusion_meta["confusion_map_score"],
                "mastery_score": mastery_meta["mastery_score"],
                "output_created": result["output_meta"]["output_created"],
            },
            durum="ok" if result["output_meta"]["output_created"] else "hata",
        )

        if fmt == "json":
            return Response({**result["payload"], "manifest": result["manifest"], "output_meta": result["output_meta"]})
        if not result["output_meta"]["output_created"]:
            return Response({**result["payload"], "manifest": result["manifest"], "output_meta": result["output_meta"], "durum": result["durum"], "readiness": result["readiness"]})
        return _export_file_response(result)


class ReadmeExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int, *args, **kwargs):
        if not modul_acik_mi("DOCVERSE_README_EXPORT_ENABLED", True):
            return _modul_kapali_response("README export modulu devre disi.")
        if not modul_acik_mi("DOCVERSE_STUDY_SUMMARY_ENABLED", True):
            return _modul_kapali_response("README export icin study summary gerekli.")

        fmt = (request.query_params.get("out") or request.query_params.get("format") or "json").lower()
        doc = _get_owned_doc(request, doc_id)
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        portal_not = _get_owned_portal_not(request, doc=doc, portal_not_id=request.query_params.get("portal_not_id"))
        if request.query_params.get("portal_not_id") and portal_not is None:
            return Response({"detail": "Portal not yok"}, status=404)

        result = build_readme_export_result(doc=doc, user=request.user, portal_not=portal_not, output_format=fmt)
        _record_export_metric(
            user=request.user,
            doc=doc,
            event_name="readme_generated",
            source_module="readme_export.api",
            output_meta=result["output_meta"],
            manifest=result["manifest"],
            portal_not_id=getattr(portal_not, "id", None),
            extra_scores={"ana_madde_sayisi": len(result.get("kritik_bilesenler") or [])},
        )

        if fmt == "json" or not result["output_meta"]["output_created"]:
            return _export_json_response(result, serializer_class=ReadmeExportSerializer)
        return _export_file_response(result)


class RealExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int, *args, **kwargs):
        if not modul_acik_mi("DOCVERSE_EXPORT_PLAN_ENABLED", True):
            return _modul_kapali_response("Export plan modulu devre disi.")
        if not modul_acik_mi("DOCVERSE_REAL_EXPORTS_ENABLED", True):
            return _modul_kapali_response("Real export modulu devre disi.")
        if not modul_acik_mi("DOCVERSE_STUDY_SUMMARY_ENABLED", True):
            return _modul_kapali_response("Real export icin study summary gerekli.")

        hedef_format = (request.query_params.get("format") or request.query_params.get("hedef_format") or "pdf").lower()
        out = (request.query_params.get("out") or hedef_format).lower()
        doc = _get_owned_doc(request, doc_id)
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        portal_not = _get_owned_portal_not(request, doc=doc, portal_not_id=request.query_params.get("portal_not_id"))
        if request.query_params.get("portal_not_id") and portal_not is None:
            return Response({"detail": "Portal not yok"}, status=404)

        result = _build_real_export_result(doc=doc, user=request.user, portal_not=portal_not, hedef_format=hedef_format)
        _record_export_metric(
            user=request.user,
            doc=doc,
            event_name="export_generated",
            source_module="real_export.api",
            output_meta=result["output_meta"],
            manifest=result["manifest"],
            portal_not_id=getattr(portal_not, "id", None),
            extra_scores={"format": hedef_format},
        )
        if hedef_format == "pptx":
            _record_export_metric(
                user=request.user,
                doc=doc,
                event_name="presentation_generated",
                source_module="real_export.api",
                output_meta=result["output_meta"],
                manifest=result["manifest"],
                portal_not_id=getattr(portal_not, "id", None),
                extra_scores={"format": hedef_format},
            )

        if out == "json" or not result["download_ready"]:
            return _export_json_response(result, serializer_class=RealExportSerializer)
        return _export_file_response(result)


CheatSheetExportView = CheatSheetExport
