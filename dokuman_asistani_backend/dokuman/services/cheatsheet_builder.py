from __future__ import annotations

from dokuman.services.metric_store import compute_cheatsheet_priority_score
from dokuman.services.study_summary import build_study_summary_payload


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _short_text(value: str, limit: int = 96) -> str:
    clean = _clean_text(value)
    if len(clean) <= limit:
        return clean
    short = clean[:limit].rsplit(" ", 1)[0].strip()
    return f"{short or clean[:limit].strip()}..."


def _cheatsheet_candidate_parcalar(doc, preferred_ids: list[int]) -> list:
    preferred = []
    seen = set()
    if preferred_ids:
        for parca in doc.parcalar.filter(id__in=preferred_ids).order_by("id"):
            if parca.id in seen:
                continue
            seen.add(parca.id)
            preferred.append(parca)

    kalanlar = []
    for parca in doc.parcalar.order_by("id"):
        if parca.id in seen:
            continue
        seen.add(parca.id)
        kalanlar.append(parca)
    return preferred + kalanlar


def build_cheatsheet_payload(*, doc, user, portal_not=None, include_internal: bool = False) -> dict:
    summary = build_study_summary_payload(
        doc=doc,
        user=user,
        portal_not=portal_not,
        include_internal=True,
    )
    internal_scores = dict(summary.pop("_internal_scores", {}) or {})
    bagli_parca_idleri = list(summary.get("bagli_parca_idleri") or [])
    candidate_parcalar = _cheatsheet_candidate_parcalar(doc, bagli_parca_idleri)

    scored_parcalar = []
    for parca in candidate_parcalar:
        priority = compute_cheatsheet_priority_score(parca=parca)
        scored_parcalar.append(
            (
                priority["cheatsheet_priority_score"],
                parca,
                priority["cheatsheet_priority_reason"],
            )
        )
    scored_parcalar.sort(key=lambda item: (-item[0], item[1].id))

    top_parca_bullets = [
        f"{item[1].adres}: {_short_text(item[1].metin, 92)}"
        for item in scored_parcalar[:3]
    ]
    ana_maddeler = []
    seen = set()
    for raw in top_parca_bullets + list(summary.get("ana_maddeler") or []):
        clean = _clean_text(raw)
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        ana_maddeler.append(clean)
        if len(ana_maddeler) >= 6:
            break

    baslik = summary.get("baslik") or f"{doc.baslik or f'Dokuman {doc.id}'} Cheatsheet"
    payload = {
        "baslik": baslik,
        "kisa_ozet": summary.get("kisa_ozet") or "Kisa cheatsheet hazirlandi.",
        "ana_maddeler": ana_maddeler[:6],
        "kritik_notlar": list(summary.get("kritik_notlar") or [])[:4],
        "glossary": list(summary.get("glossary") or [])[:5],
        "bagli_parca_idleri": [item[1].id for item in scored_parcalar[:12]],
        "portal_not_id": summary.get("portal_not_id"),
        "dokuman_id": doc.id,
    }
    if include_internal:
        avg_priority = (
            sum(item[0] for item in scored_parcalar[:4]) / min(len(scored_parcalar), 4)
            if scored_parcalar
            else 0.0
        )
        payload["_internal_scores"] = {
            **internal_scores,
            "cheatsheet_priority_score": round(avg_priority, 4),
            "cheatsheet_priority_reason": scored_parcalar[0][2] if scored_parcalar else "no_priority_signal",
        }
    return payload


def render_cheatsheet_markdown(payload: dict) -> str:
    lines = [
        f"# {payload.get('baslik') or 'Cheatsheet'}",
        "",
        "## Kisa Ozet",
        str(payload.get("kisa_ozet") or "-"),
        "",
        "## Ana Maddeler",
    ]

    ana_maddeler = payload.get("ana_maddeler") or []
    if ana_maddeler:
        for item in ana_maddeler:
            lines.append(f"- {item}")
    else:
        lines.append("- Ana madde bulunmadi.")
    lines.append("")

    lines.append("## Kritik Notlar")
    kritik_notlar = payload.get("kritik_notlar") or []
    if kritik_notlar:
        for item in kritik_notlar:
            lines.append(f"- {item}")
    else:
        lines.append("- Kritik not bulunmadi.")
    lines.append("")

    lines.append("## Kisa Glossary")
    glossary = payload.get("glossary") or []
    if glossary:
        for item in glossary:
            terim = str(item.get("terim") or "").strip()
            tanim = str(item.get("tanim") or "").strip()
            if terim and tanim:
                lines.append(f"- **{terim}**: {tanim}")
    else:
        lines.append("- Glossary bulunmadi.")
    lines.append("")

    bagli_parcalar = payload.get("bagli_parca_idleri") or []
    if bagli_parcalar:
        lines.append("## Kaynak Parcalar")
        lines.append("- " + ", ".join(str(item) for item in bagli_parcalar))
        lines.append("")

    return "\n".join(lines).strip() + "\n"
