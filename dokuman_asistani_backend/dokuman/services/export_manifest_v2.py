from __future__ import annotations

from dokuman.services.cheatsheet_builder import build_cheatsheet_payload
from dokuman.services.concept_runtime import compute_concept_candidates
from dokuman.services.study_summary import build_study_summary_payload

ALLOWED_FORMATS = {"pdf", "docx", "pptx", "markdown", "txt"}


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _dedupe_ints(values, *, limit: int = 12) -> list[int]:
    out = []
    seen = set()
    for value in values or []:
        try:
            clean = int(value)
        except Exception:
            continue
        if clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def _dedupe_strings(values, *, limit: int = 4) -> list[str]:
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


def _normalize_format(value: str) -> str:
    clean = _clean_text(value).lower()
    return clean if clean in ALLOWED_FORMATS else "pdf"


def build_export_source_bundle(
    *,
    doc,
    user,
    portal_not=None,
    cheatsheet_enabled: bool = True,
    concepts_enabled: bool = True,
) -> dict:
    summary = build_study_summary_payload(doc=doc, user=user, portal_not=portal_not)
    cheatsheet = build_cheatsheet_payload(doc=doc, user=user, portal_not=portal_not) if cheatsheet_enabled else {}

    portal_ids = []
    if portal_not is not None:
        portal_ids = list(portal_not.kaynak_parcalar.order_by("id").values_list("id", flat=True)[:12])

    concept_candidates = (
        compute_concept_candidates(doc=doc, user=user, limit=4)
        if concepts_enabled
        else []
    )
    concept_labels = _dedupe_strings(
        [item.get("kavram") for item in concept_candidates],
        limit=3,
    )
    concept_ids = _dedupe_ints(
        [
            parca_id
            for item in concept_candidates
            for parca_id in (item.get("kaynak_parca_idleri") or [])
        ],
        limit=12,
    )

    summary_ids = _dedupe_ints(summary.get("bagli_parca_idleri"), limit=12)
    cheatsheet_ids = _dedupe_ints(cheatsheet.get("bagli_parca_idleri"), limit=12)
    default_ids = _dedupe_ints(
        summary_ids + portal_ids + cheatsheet_ids + concept_ids,
        limit=12,
    ) or list(doc.parcalar.order_by("id").values_list("id", flat=True)[:8])

    return {
        "summary": summary,
        "cheatsheet": cheatsheet,
        "concept_labels": concept_labels,
        "summary_ids": summary_ids,
        "portal_ids": _dedupe_ints(portal_ids, limit=12),
        "cheatsheet_ids": cheatsheet_ids,
        "concept_ids": concept_ids,
        "default_ids": _dedupe_ints(default_ids, limit=12),
        "portal_not_id": getattr(portal_not, "id", None),
    }


def _fallback_ids(bundle: dict, *keys: str) -> list[int]:
    values = []
    for key in keys:
        values.extend(bundle.get(key) or [])
    values.extend(bundle.get("default_ids") or [])
    return _dedupe_ints(values, limit=4)[:3]


def _section_amaci(slot: str, bundle: dict) -> str:
    if slot == "summary":
        return f"{len(bundle.get('summary_ids') or []) or len(bundle.get('default_ids') or [])} kaynak parcadan calisma omurgasi kurar."
    if slot == "portal":
        return f"Portal nota bagli {len(bundle.get('portal_ids') or bundle.get('default_ids') or [])} parcayi odak akisa sabitler."
    if slot == "concept":
        concepts = ", ".join(bundle.get("concept_labels") or ["kavram"])
        return f"{concepts} ekseninde kavramsal baglari yapisal olarak toplar."
    if slot == "cheatsheet":
        return f"{len(bundle.get('cheatsheet_ids') or bundle.get('default_ids') or [])} oncelikli parcayi hizli tekrar katmanina tasir."
    return f"{len(bundle.get('default_ids') or [])} parcadan kapanis ve teslim akisina hazirlik yapar."


def _section_note(slot: str, bundle: dict) -> str:
    if slot == "concept":
        concepts = ", ".join((bundle.get("concept_labels") or [])[:2]) or "temel kavramlar"
        return f"Anlatimda ham chunk yerine {concepts} ve kaynak parcalar arasi gecisler korunur."
    if slot == "portal":
        return "Portal not baglami korunur; detay yerine karar ve takip akisi vurgulanir."
    if slot == "cheatsheet":
        return "Kisa tekrar ve sunuma hazir cekirdek maddeler one alinir."
    if slot == "summary":
        return "Bolum, toplu cikarim ve oncelikli parcalarla sinirli tutulur."
    return "Cikis bolumu yalnizca yapisal sonlandirma ve teslim sirasi tasir."


def _format_specs(hedef_format: str) -> list[tuple[str, str]]:
    if hedef_format == "pptx":
        return [
            ("summary", "Acilis Slaydi"),
            ("concept", "Kavram Akisi"),
            ("portal", "Calisma Notlari"),
            ("cheatsheet", "Kapanis"),
        ]
    if hedef_format == "docx":
        return [
            ("summary", "Kapak ve Ozet"),
            ("portal", "Calisma Girdileri"),
            ("concept", "Kavram Omurgasi"),
            ("cheatsheet", "Sonuc ve Tekrar"),
        ]
    if hedef_format == "markdown":
        return [
            ("summary", "Baslangic"),
            ("concept", "Kavramlar"),
            ("cheatsheet", "Kontrol Listesi"),
        ]
    if hedef_format == "txt":
        return [
            ("summary", "Kisa Ozet"),
            ("portal", "Takip Noktalari"),
            ("cheatsheet", "Kapanis Notu"),
        ]
    return [
        ("summary", "Yonetici Ozeti"),
        ("concept", "Kavram Akisi"),
        ("portal", "Kaynak Notlar"),
        ("cheatsheet", "Ek Notlar"),
    ]


def build_export_sections(*, bundle: dict, hedef_format: str) -> list[dict]:
    bolumler = []
    for idx, (slot, title) in enumerate(_format_specs(hedef_format), start=1):
        if slot == "summary":
            kaynak_ids = _fallback_ids(bundle, "summary_ids", "portal_ids", "cheatsheet_ids")
        elif slot == "portal":
            kaynak_ids = _fallback_ids(bundle, "portal_ids", "summary_ids", "cheatsheet_ids")
        elif slot == "concept":
            kaynak_ids = _fallback_ids(bundle, "concept_ids", "summary_ids", "cheatsheet_ids")
        else:
            kaynak_ids = _fallback_ids(bundle, "cheatsheet_ids", "summary_ids", "portal_ids")

        bolumler.append(
            {
                "sira": idx,
                "baslik": title,
                "amaci": _section_amaci(slot, bundle),
                "kaynak_parca_idleri": kaynak_ids,
                "konusma_notu": _section_note(slot, bundle),
            }
        )
    return bolumler


def build_export_manifest_v2_payload(
    *,
    doc,
    user,
    portal_not=None,
    hedef_format: str = "pdf",
    cheatsheet_enabled: bool = True,
    concepts_enabled: bool = True,
) -> dict:
    hedef_format = _normalize_format(hedef_format)
    bundle = build_export_source_bundle(
        doc=doc,
        user=user,
        portal_not=portal_not,
        cheatsheet_enabled=cheatsheet_enabled,
        concepts_enabled=concepts_enabled,
    )
    bolumler = build_export_sections(bundle=bundle, hedef_format=hedef_format)
    kaynak_ids = _dedupe_ints(
        [
            parca_id
            for bolum in bolumler
            for parca_id in (bolum.get("kaynak_parca_idleri") or [])
        ],
        limit=12,
    ) or list(doc.parcalar.order_by("id").values_list("id", flat=True)[:8])

    return {
        "dokuman_id": doc.id,
        "portal_not_id": bundle["portal_not_id"],
        "baslik": f"{doc.baslik or f'Dokuman {doc.id}'} Export Manifest",
        "hedef_format": hedef_format,
        "bolumler": bolumler,
        "kaynak_parca_idleri": kaynak_ids,
        "ozet_kaynaklari": {
            "study_summary": bool(bundle.get("summary_ids")),
            "cheatsheet": bool(cheatsheet_enabled and bundle.get("cheatsheet_ids")),
            "portal_not": bool(bundle.get("portal_ids")),
            "concept_surface": bool(concepts_enabled and bundle.get("concept_ids")),
            "kaynak_sayilari": {
                "study_summary": len(bundle.get("summary_ids") or []),
                "portal_not": len(bundle.get("portal_ids") or []),
                "cheatsheet": len(bundle.get("cheatsheet_ids") or []),
                "concept_surface": len(bundle.get("concept_ids") or []),
            },
        },
        "konusma_notu_var_mi": True,
        "tahmini_slayt_sayisi": len(bolumler) if hedef_format == "pptx" else min(len(bolumler), 4),
        "tahmini_bolum_sayisi": len(bolumler),
        "_meta": {
            "format": hedef_format,
            "bagli_parca_sayisi": len(kaynak_ids),
            "portal_not_var_mi": bool(bundle["portal_not_id"]),
            "concept_count": len(bundle.get("concept_labels") or []),
        },
    }
