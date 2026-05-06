from __future__ import annotations

from collections import defaultdict

from dokuman.models import AnlamadimKaydi, DokumanNotu, Not
from dokuman.services.cheatsheet_builder import build_cheatsheet_payload
from dokuman.services.concept_runtime import compute_concept_candidates
from dokuman.services.metric_store import (
    compute_cheatsheet_priority_score,
    compute_confusion_map_score,
    compute_study_summary_importance_score,
)
from dokuman.services.study_summary import build_study_summary_payload


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _shorten(value: str, limit: int = 120) -> str:
    clean = _clean_text(value)
    if len(clean) <= limit:
        return clean
    short = clean[:limit].rsplit(" ", 1)[0].strip()
    return f"{short or clean[:limit].strip()}..."


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


def _glossary_by_parca(*, doc, user) -> dict[int, list[dict]]:
    items = defaultdict(list)
    qs = AnlamadimKaydi.objects.filter(kullanici=user, dokuman=doc).order_by("-olusturuldu")
    for kayit in qs[:24]:
        payload = kayit.cikti_json or {}
        for item in (payload.get("glossary") or payload.get("terimler") or [])[:4]:
            if not isinstance(item, dict):
                continue
            term = _clean_text(item.get("terim") or item.get("term"))
            definition = _clean_text(item.get("tanim") or item.get("definition") or item.get("aciklama"))
            if not term or not definition or kayit.parca_id is None:
                continue
            items[int(kayit.parca_id)].append({"terim": term, "tanim": _shorten(definition, 120)})
    return items


def _notes_by_parca(*, doc, user) -> dict[int, list[str]]:
    out = defaultdict(list)
    for note in Not.objects.filter(owner=user, dokuman=doc, arsivli=False).order_by("-pinned", "-updated_at", "-id")[:24]:
        parca_id = note.parca_id
        if not parca_id:
            for kaynak_id in list(note.kaynak_parca_idleri or [])[:3]:
                try:
                    out[int(kaynak_id)].append(_shorten(note.baslik or note.metin, 100))
                except Exception:
                    continue
            continue
        out[int(parca_id)].append(_shorten(note.baslik or note.metin, 100))

    for portal_not in DokumanNotu.objects.filter(owner=user, dokuman=doc, arsivli=False).order_by("-pinned", "-updated_at", "-id")[:16]:
        if portal_not.parca_id:
            out[int(portal_not.parca_id)].append(_shorten(portal_not.baslik or portal_not.icerik, 100))
        for kaynak in portal_not.kaynak_parcalar.all().order_by("id")[:3]:
            out[int(kaynak.id)].append(_shorten(portal_not.baslik or portal_not.icerik, 100))
    return out


def _concepts_by_parca(*, doc, user) -> dict[int, list[dict]]:
    out = defaultdict(list)
    for item in compute_concept_candidates(doc=doc, user=user, limit=18):
        for parca_id in list(item.get("kaynak_parca_idleri") or [])[:4]:
            try:
                out[int(parca_id)].append(item)
            except Exception:
                continue
    return out


def _preferred_context_lines(summary: dict, cheatsheet: dict) -> list[str]:
    return _dedupe_strings(
        list(summary.get("kritik_notlar") or [])
        + list(cheatsheet.get("kritik_notlar") or [])
        + [summary.get("baslik") or "", cheatsheet.get("baslik") or ""]
        + [
            f"{item.get('terim')}: {item.get('tanim')}"
            for item in list((summary.get("glossary") or []) + (cheatsheet.get("glossary") or []))[:6]
            if _clean_text(item.get("terim")) and _clean_text(item.get("tanim"))
        ],
        limit=10,
    )


def _card_content(
    *,
    parca,
    glossary_items: list[dict],
    note_lines: list[str],
    concept_items: list[dict],
    context_lines: list[str],
) -> dict:
    glossary_item = glossary_items[0] if glossary_items else {}
    concept_item = concept_items[0] if concept_items else {}
    term = (
        _clean_text(glossary_item.get("terim"))
        or _clean_text(concept_item.get("kavram"))
        or _clean_text(getattr(parca, "adres", ""))
        or f"Parca {getattr(parca, 'id', 0)}"
    )
    definition = _clean_text(glossary_item.get("tanim") or concept_item.get("kisa_tanim"))
    note_line = _clean_text(note_lines[0] if note_lines else "")
    context_line = _clean_text(context_lines[0] if context_lines else "")

    ozet = definition or note_line or context_line or f"{term} bu turda tekrar odagi olarak secildi."
    if term and definition and not ozet.lower().startswith(term.lower()):
        ozet = f"{term}: {definition}"

    ornek = note_line or context_line or definition or f"{term} once kisa ozet ve glossary ile pekistirilir."
    if concept_item and _clean_text(concept_item.get("kisa_tanim")) and not note_line:
        ornek = concept_item["kisa_tanim"]

    mini_soru = f"{term} hangi iliski veya amac icin kritik gorunuyor?"
    if _clean_text(concept_item.get("kavram")) and _clean_text(concept_item.get("kisa_tanim")):
        mini_soru = f"{concept_item['kavram']} neyi aciklamak icin tekrar edilmeli?"

    return {
        "ozet": _shorten(ozet, 140),
        "ornek": _shorten(ornek, 140),
        "mini_soru": _shorten(mini_soru, 120),
    }


def build_reels_surface_payload(*, doc, user, portal_not=None, cheatsheet_enabled: bool = True) -> dict:
    summary = build_study_summary_payload(doc=doc, user=user, portal_not=portal_not)
    cheatsheet = build_cheatsheet_payload(doc=doc, user=user, portal_not=portal_not) if cheatsheet_enabled else {}
    preferred_ids = list(cheatsheet.get("bagli_parca_idleri") or summary.get("bagli_parca_idleri") or [])[:12]
    preferred_context = _preferred_context_lines(summary, cheatsheet)
    glossary_map = _glossary_by_parca(doc=doc, user=user)
    notes_map = _notes_by_parca(doc=doc, user=user)
    concept_map = _concepts_by_parca(doc=doc, user=user)

    scored_cards = []
    for parca in doc.parcalar.all().order_by("id"):
        meta = dict(getattr(parca, "meta", {}) or {})
        if bool(meta.get("weak_content")):
            continue

        confusion_meta = compute_confusion_map_score(user=user, dokuman=doc, parca=parca)
        importance_meta = compute_study_summary_importance_score(
            user=user,
            dokuman=doc,
            parca=parca,
            confusion_map_score=confusion_meta["confusion_map_score"],
        )
        cheatsheet_meta = compute_cheatsheet_priority_score(parca=parca)
        priority_score = min(
            1.0,
            (
                confusion_meta["confusion_map_score"] * 0.42
                + importance_meta["study_summary_importance_score"] * 0.34
                + cheatsheet_meta["cheatsheet_priority_score"] * 0.24
                + (0.04 if parca.id in preferred_ids else 0.0)
            ),
        )
        card = _card_content(
            parca=parca,
            glossary_items=list(glossary_map.get(parca.id) or []),
            note_lines=_dedupe_strings(notes_map.get(parca.id) or [], limit=3),
            concept_items=list(concept_map.get(parca.id) or []),
            context_lines=preferred_context,
        )
        scored_cards.append(
            {
                **card,
                "bagli_parca_id": parca.id,
                "_priority_score": round(priority_score, 4),
                "_confusion": round(confusion_meta["confusion_map_score"], 4),
                "_importance": round(importance_meta["study_summary_importance_score"], 4),
                "_cheatsheet": round(cheatsheet_meta["cheatsheet_priority_score"], 4),
            }
        )

    scored_cards.sort(
        key=lambda item: (
            -float(item["_priority_score"]),
            -float(item["_confusion"]),
            item["bagli_parca_id"],
        )
    )
    selected_cards = [
        {
            "ozet": item["ozet"],
            "ornek": item["ornek"],
            "mini_soru": item["mini_soru"],
            "bagli_parca_id": item["bagli_parca_id"],
        }
        for item in scored_cards[:3]
    ]

    avg_confusion = sum(item["_confusion"] for item in scored_cards[:3]) / len(scored_cards[:3]) if scored_cards[:3] else 0.0
    avg_importance = sum(item["_importance"] for item in scored_cards[:3]) / len(scored_cards[:3]) if scored_cards[:3] else 0.0
    avg_cheatsheet = sum(item["_cheatsheet"] for item in scored_cards[:3]) / len(scored_cards[:3]) if scored_cards[:3] else 0.0

    return {
        "dokuman_id": doc.id,
        "portal_not_id": getattr(portal_not, "id", None),
        "kartlar": selected_cards,
        "_meta": {
            "reels_selected_count": len(selected_cards),
            "confusion_map_score": round(avg_confusion, 4),
            "study_summary_importance_score": round(avg_importance, 4),
            "cheatsheet_priority_score": round(avg_cheatsheet, 4),
        },
    }
