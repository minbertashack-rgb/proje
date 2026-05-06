from __future__ import annotations

from dokuman.services.cheatsheet_builder import build_cheatsheet_payload
from dokuman.services.study_summary import build_study_summary_payload

ALLOWED_MODLAR = {"hizli_cut", "story_cut", "exam_cut"}


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _dedupe_strings(values, *, limit: int = 8) -> list[str]:
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


def _normalize_mod(value: str) -> str:
    clean = _clean_text(value).lower()
    return clean if clean in ALLOWED_MODLAR else "hizli_cut"


def _questionize(item: str) -> str:
    clean = _clean_text(item)
    if not clean:
        return ""
    return f"{clean} neden kritik?"


def build_directors_cut_payload(*, doc, user, mod: str = "hizli_cut", portal_not=None, cheatsheet_enabled: bool = True) -> dict:
    mod = _normalize_mod(mod)
    summary = build_study_summary_payload(doc=doc, user=user, portal_not=portal_not)
    cheatsheet = build_cheatsheet_payload(doc=doc, user=user, portal_not=portal_not) if cheatsheet_enabled else {}

    ana = _dedupe_strings(
        list(summary.get("ana_maddeler") or []) + list(cheatsheet.get("ana_maddeler") or []),
        limit=8,
    )
    kritik = _dedupe_strings(
        list(summary.get("kritik_notlar") or []) + list(cheatsheet.get("kritik_notlar") or []),
        limit=6,
    )
    glossary = [
        f"{item.get('terim')}: {item.get('tanim')}"
        for item in list(cheatsheet.get("glossary") or [])[:3]
    ]
    olasi_sorular = _dedupe_strings([_questionize(item) for item in ana + kritik], limit=5)

    if mod == "hizli_cut":
        ana_maddeler = ana[:3]
        kritik_noktalar = kritik[:2]
        tuzaklar = _dedupe_strings(glossary + kritik[:2], limit=3)
    elif mod == "story_cut":
        ana_maddeler = _dedupe_strings(
            [summary.get("baslik")] + ana[:4],
            limit=5,
        )
        kritik_noktalar = _dedupe_strings(kritik[:3] + glossary[:2], limit=4)
        tuzaklar = _dedupe_strings(
            [f"Akis kopmasi: {item}" for item in kritik[:2]] + glossary[:1],
            limit=3,
        )
    else:
        ana_maddeler = _dedupe_strings(ana[:4] + glossary[:2], limit=5)
        kritik_noktalar = _dedupe_strings(kritik[:3], limit=3)
        tuzaklar = _dedupe_strings(
            [f"Sinav tuzagi: {item}" for item in kritik[:2]]
            + [f"Kavram karisabilir: {item}" for item in glossary[:2]],
            limit=4,
        )

    return {
        "dokuman_id": doc.id,
        "portal_not_id": getattr(portal_not, "id", None),
        "mod": mod,
        "baslik": summary.get("baslik") or cheatsheet.get("baslik") or f"Dokuman {doc.id} Director's Cut",
        "ana_maddeler": ana_maddeler,
        "kritik_noktalar": kritik_noktalar,
        "tuzaklar": tuzaklar,
        "sorulabilecekler": olasi_sorular,
        "kaynak_parca_idleri": list(cheatsheet.get("bagli_parca_idleri") or summary.get("bagli_parca_idleri") or [])[:12],
    }
