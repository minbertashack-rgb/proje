from __future__ import annotations

from dokuman.services.export_manifest_v2 import (
    build_export_sections,
    build_export_source_bundle,
)


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_plan_turu(value: str) -> str:
    clean = _clean_text(value).lower()
    return "rapor" if clean == "rapor" else "slayt"


def build_export_plan_payload(
    *,
    doc,
    user,
    portal_not=None,
    plan_turu: str = "slayt",
    cheatsheet_enabled: bool = True,
    concepts_enabled: bool = True,
) -> dict:
    plan_turu = _normalize_plan_turu(plan_turu)
    hedef_format = "pptx" if plan_turu == "slayt" else "docx"
    bundle = build_export_source_bundle(
        doc=doc,
        user=user,
        portal_not=portal_not,
        cheatsheet_enabled=cheatsheet_enabled,
        concepts_enabled=concepts_enabled,
    )
    plan = build_export_sections(bundle=bundle, hedef_format=hedef_format)

    return {
        "dokuman_id": doc.id,
        "portal_not_id": bundle["portal_not_id"],
        "baslik": f"{doc.baslik or f'Dokuman {doc.id}'} Export Plani",
        "plan_turu": plan_turu,
        "slayt_plani": plan if plan_turu == "slayt" else [],
        "bolum_plani": plan if plan_turu == "rapor" else [],
        "_meta": {
            "export_plan_turu": plan_turu,
            "bagli_parca_sayisi": len(
                {
                    parca_id
                    for adim in plan
                    for parca_id in (adim.get("kaynak_parca_idleri") or [])
                }
            ),
            "portal_not_var_mi": bool(bundle["portal_not_id"]),
            "concept_count": len(bundle.get("concept_labels") or []),
        },
    }
