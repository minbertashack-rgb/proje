from __future__ import annotations

from dokuman.models import AnlamadimKaydi, DokumanNotu, Not, Parca
from dokuman.services.metric_store import (
    compute_confusion_map_score,
    compute_study_summary_importance_score,
)


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _short_text(value: str, limit: int = 180) -> str:
    clean = _clean_text(value)
    if len(clean) <= limit:
        return clean
    short = clean[:limit].rsplit(" ", 1)[0].strip()
    return f"{short or clean[:limit].strip()}..."


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


def _study_summary_sort_key(score: float, *, pinned: bool = False, updated_at=None, pk: int = 0):
    timestamp = 0.0
    if updated_at is not None:
        try:
            timestamp = float(updated_at.timestamp())
        except Exception:
            timestamp = 0.0
    return (-round(float(score or 0.0), 4), -int(bool(pinned)), -timestamp, -int(pk or 0))


def _study_summary_odak_parcalari(doc, user, *, limit: int = 4) -> tuple[list[Parca], float]:
    scored = []
    for parca in doc.parcalar.all().order_by("id"):
        confusion_meta = compute_confusion_map_score(user=user, dokuman=doc, parca=parca)
        importance = compute_study_summary_importance_score(
            user=user,
            dokuman=doc,
            parca=parca,
            confusion_map_score=confusion_meta["confusion_map_score"],
        )
        scored.append(
            (
                importance["study_summary_importance_score"],
                int(getattr(parca, "id", 0) or 0),
                parca,
            )
        )

    scored.sort(key=lambda item: (-item[0], item[1]))
    top = scored[:limit]
    avg_score = sum(item[0] for item in top) / len(top) if top else 0.0
    return [item[2] for item in top], round(avg_score, 4)


def _collect_glossary(doc, user, *, parca_idleri: list[int]) -> list[dict]:
    qs = AnlamadimKaydi.objects.filter(kullanici=user, dokuman=doc).order_by("-olusturuldu")
    if parca_idleri:
        qs = qs.filter(parca_id__in=parca_idleri)

    glossary = []
    seen = set()
    for kayit in qs[:8]:
        payload = kayit.cikti_json or {}
        items = payload.get("terimler") or payload.get("glossary") or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            terim = _clean_text(item.get("terim") or item.get("term"))
            tanim = _short_text(item.get("tanim") or item.get("definition") or item.get("aciklama"), 120)
            if len(terim) < 2 or len(tanim) < 12:
                continue
            key = terim.lower()
            if key in seen:
                continue
            seen.add(key)
            glossary.append({"terim": terim, "tanim": tanim})
            if len(glossary) >= 5:
                return glossary
    return glossary


def build_study_summary_payload(
    *,
    doc,
    user,
    portal_not: DokumanNotu | None = None,
    include_internal: bool = False,
) -> dict:
    portal_notlar_qs = DokumanNotu.objects.filter(owner=user, dokuman=doc, arsivli=False).order_by("-pinned", "-updated_at")
    notlar_qs = Not.objects.filter(owner=user, dokuman=doc, arsivli=False).order_by("-pinned", "-updated_at", "-id")
    anlamadim_qs = AnlamadimKaydi.objects.filter(kullanici=user, dokuman=doc).order_by("-olusturuldu")

    secili_portal_not = portal_not
    if secili_portal_not is None:
        secili_portal_not = portal_notlar_qs.first()

    study_summary_importance_score = 0.0
    study_summary_importance_reason = "no_priority_signal"

    if secili_portal_not is not None:
        raw_bagli_notlar = list(secili_portal_not.bagli_notlar.order_by("-pinned", "-updated_at", "-id")[:8])
        bagli_notlar_scored = []
        for item in raw_bagli_notlar:
            confusion_meta = compute_confusion_map_score(
                user=user,
                dokuman=doc,
                parca=item.parca,
            )
            importance = compute_study_summary_importance_score(
                user=user,
                dokuman=doc,
                not_obj=item,
                confusion_map_score=confusion_meta["confusion_map_score"],
            )
            bagli_notlar_scored.append(
                (
                    importance["study_summary_importance_score"],
                    item,
                    importance["study_summary_importance_reason"],
                )
            )
        bagli_notlar_scored.sort(
            key=lambda item: _study_summary_sort_key(
                item[0],
                pinned=getattr(item[1], "pinned", False),
                updated_at=getattr(item[1], "updated_at", None),
                pk=getattr(item[1], "id", 0),
            )
        )
        bagli_notlar = [item[1] for item in bagli_notlar_scored[:6]]
        if bagli_notlar_scored:
            study_summary_importance_score = round(
                sum(item[0] for item in bagli_notlar_scored[:4]) / min(len(bagli_notlar_scored), 4),
                4,
            )
            study_summary_importance_reason = bagli_notlar_scored[0][2]

        kaynak_parcalar_raw = list(secili_portal_not.kaynak_parcalar.order_by("id"))
        kaynak_parca_sirali = []
        for parca in kaynak_parcalar_raw:
            confusion_meta = compute_confusion_map_score(user=user, dokuman=doc, parca=parca)
            importance = compute_study_summary_importance_score(
                user=user,
                dokuman=doc,
                parca=parca,
                confusion_map_score=confusion_meta["confusion_map_score"],
            )
            kaynak_parca_sirali.append((importance["study_summary_importance_score"], parca))
        kaynak_parca_sirali.sort(key=lambda item: (-item[0], item[1].id))
        kaynak_parca_idleri = [item[1].id for item in kaynak_parca_sirali[:10]]
        baslik = secili_portal_not.baslik or f"{doc.baslik or f'Dokuman {doc.id}'} Calisma Ozeti"
        kisa_ozet = _short_text(secili_portal_not.icerik or "Portal not merkezli calisma ozeti.", 220)
        ana_maddeler = _dedupe_strings(
            [
                item.baslik or _short_text(item.metin, 110)
                for item in bagli_notlar
            ]
            + [
                _short_text(item.kullanici_mesaj or item.cikti_text, 110)
                for item in anlamadim_qs.filter(parca_id__in=kaynak_parca_idleri)[:4]
            ],
            limit=6,
        )
        kritik_notlar = _dedupe_strings(
            [f"Portal odak: {_short_text(secili_portal_not.icerik, 120)}"]
            + [f"Not: {_short_text(item.metin, 120)}" for item in bagli_notlar if item.pinned][:3],
            limit=4,
        )
    else:
        raw_notlar = list(notlar_qs[:8])
        son_notlar_scored = []
        for item in raw_notlar:
            confusion_meta = compute_confusion_map_score(
                user=user,
                dokuman=doc,
                parca=item.parca,
            )
            importance = compute_study_summary_importance_score(
                user=user,
                dokuman=doc,
                not_obj=item,
                confusion_map_score=confusion_meta["confusion_map_score"],
            )
            son_notlar_scored.append((importance["study_summary_importance_score"], item))
        son_notlar_scored.sort(
            key=lambda item: _study_summary_sort_key(
                item[0],
                pinned=getattr(item[1], "pinned", False),
                updated_at=getattr(item[1], "updated_at", None),
                pk=getattr(item[1], "id", 0),
            )
        )
        son_notlar = [item[1] for item in son_notlar_scored[:6]]
        zor_parcalar, study_summary_importance_score = _study_summary_odak_parcalari(doc, user, limit=4)
        if son_notlar_scored:
            study_summary_importance_score = round(
                max(study_summary_importance_score, son_notlar_scored[0][0]),
                4,
            )
            study_summary_importance_reason = "note_priority"
        elif zor_parcalar:
            study_summary_importance_reason = "parca_priority"
        kaynak_parca_idleri = _dedupe_ints(
            [parca.id for parca in zor_parcalar]
            + [parca_id for item in son_notlar for parca_id in (item.kaynak_parca_idleri or [])],
            limit=10,
        )
        baslik = f"{doc.baslik or f'Dokuman {doc.id}'} Calisma Ozeti"
        kisa_ozet = _short_text(
            (son_notlar[0].metin if son_notlar else "") or (zor_parcalar[0].metin if zor_parcalar else ""),
            220,
        ) or "Bu dokuman icin kisa bir calisma ozeti hazirlandi."
        ana_maddeler = _dedupe_strings(
            [item.baslik or _short_text(item.metin, 110) for item in son_notlar]
            + [f"{parca.adres}: {_short_text(parca.metin, 100)}" for parca in zor_parcalar],
            limit=6,
        )
        kritik_notlar = _dedupe_strings(
            [f"Pinned not: {_short_text(item.metin, 110)}" for item in son_notlar if item.pinned]
            + [f"Zor parca: {parca.adres}" for parca in zor_parcalar[:2]],
            limit=4,
        )

    glossary = _collect_glossary(doc, user, parca_idleri=_dedupe_ints(kaynak_parca_idleri))

    if not ana_maddeler:
        ana_maddeler = ["Bu dokuman icin ana maddeler henuz notlar uzerinden olusmadi."]
    if not kritik_notlar:
        kritik_notlar = ["Kritik not bulunmadi; once not veya portal not ekleyebilirsin."]

    payload = {
        "baslik": baslik,
        "kisa_ozet": kisa_ozet,
        "ana_maddeler": ana_maddeler[:6],
        "kritik_notlar": kritik_notlar[:4],
        "glossary": glossary[:5],
        "bagli_parca_idleri": _dedupe_ints(kaynak_parca_idleri, limit=12),
        "portal_not_id": getattr(secili_portal_not, "id", None),
        "dokuman_id": doc.id,
    }
    if include_internal:
        payload["_internal_scores"] = {
            "study_summary_importance_score": round(float(study_summary_importance_score or 0.0), 4),
            "study_summary_importance_reason": study_summary_importance_reason,
        }
    return payload
