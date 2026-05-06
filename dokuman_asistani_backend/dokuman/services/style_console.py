from __future__ import annotations

from dokuman.services.cheatsheet_builder import build_cheatsheet_payload
from dokuman.services.study_summary import build_study_summary_payload

ALLOWED_STILLER = {"kisa", "derin", "ornekli", "tablo", "akis"}
ALLOWED_TONLAR = {"kanka", "hoca", "teknik", "sunum"}


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


def _normalize_choice(value: str, *, allowed: set[str], default: str) -> str:
    clean = _clean_text(value).lower()
    return clean if clean in allowed else default


def _tone_intro(ton: str) -> str:
    return {
        "kanka": "Kisa ve rahat akista, hizli kavrama odagi.",
        "hoca": "Ogretici ve duzenli akista, kavramlari sirali vurgular.",
        "teknik": "Terminoloji ve baglam netligi onceliklidir.",
        "sunum": "Baslik, vurgu ve akista sahne mantigi korunur.",
    }.get(ton, "Net ve sade bir akista sunulur.")


def build_style_console_payload(
    *,
    doc,
    user,
    stil: str = "kisa",
    ton: str = "teknik",
    portal_not=None,
    cheatsheet_enabled: bool = True,
) -> dict:
    stil = _normalize_choice(stil, allowed=ALLOWED_STILLER, default="kisa")
    ton = _normalize_choice(ton, allowed=ALLOWED_TONLAR, default="teknik")

    summary = build_study_summary_payload(doc=doc, user=user, portal_not=portal_not)
    cheatsheet = build_cheatsheet_payload(doc=doc, user=user, portal_not=portal_not) if cheatsheet_enabled else {}

    base_maddeler = _dedupe_strings(
        list(summary.get("ana_maddeler") or []) + list(cheatsheet.get("ana_maddeler") or []),
        limit=8,
    )
    vurgular = _dedupe_strings(
        list(summary.get("kritik_notlar") or []) + list(cheatsheet.get("kritik_notlar") or []),
        limit=6,
    )

    if stil == "kisa":
        maddeler = base_maddeler[:3]
    elif stil == "derin":
        glossary_lines = [
            f"{item.get('terim')}: {item.get('tanim')}"
            for item in list(cheatsheet.get("glossary") or [])[:3]
        ]
        maddeler = _dedupe_strings(base_maddeler + glossary_lines, limit=6)
    elif stil == "ornekli":
        ornekler = [f"Ornek odak: {item}" for item in base_maddeler[:2]]
        maddeler = _dedupe_strings(ornekler + vurgular + base_maddeler[:2], limit=5)
    elif stil == "tablo":
        maddeler = _dedupe_strings(
            [f"Konu | {item}" for item in base_maddeler[:3]]
            + [f"Risk | {item}" for item in vurgular[:2]],
            limit=5,
        )
    else:
        maddeler = _dedupe_strings(
            [f"Adim {idx}. {item}" for idx, item in enumerate(base_maddeler[:5], start=1)],
            limit=5,
        )

    return {
        "dokuman_id": doc.id,
        "portal_not_id": getattr(portal_not, "id", None),
        "stil": stil,
        "ton": ton,
        "baslik": summary.get("baslik") or cheatsheet.get("baslik") or f"Dokuman {doc.id} Stil Konsolu",
        "acilis": _dedupe_strings(
            [_tone_intro(ton), base_maddeler[0] if base_maddeler else "", summary.get("baslik")],
            limit=2,
        )[0],
        "maddeler": maddeler,
        "vurgular": vurgular[:4],
        "kaynak_parca_idleri": list(summary.get("bagli_parca_idleri") or cheatsheet.get("bagli_parca_idleri") or [])[:12],
    }
