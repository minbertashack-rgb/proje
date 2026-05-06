from __future__ import annotations

from dokuman.services.concept_runtime import build_concept_detail_payload


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


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


def build_concept_fusion_payload(*, doc, user, kavram_a: str, kavram_b: str) -> dict:
    detail_a = build_concept_detail_payload(doc=doc, user=user, kavram=kavram_a)
    detail_b = build_concept_detail_payload(doc=doc, user=user, kavram=kavram_b)
    kaynak_a = set(detail_a.get("bagli_parca_idleri") or [])
    kaynak_b = set(detail_b.get("bagli_parca_idleri") or [])
    ortak = sorted(kaynak_a.intersection(kaynak_b))
    toplam = sorted(kaynak_a.union(kaynak_b))

    ortak_yonler = _dedupe_strings(
        [
            f"{detail_a['kavram']} ve {detail_b['kavram']} dokumandaki ana teknik akisla iliskilidir.",
            f"Bu iki kavram {len(ortak)} ortak parcada birlikte gorunur." if ortak else "",
            "Ikisi de tekil ham metin yerine yapisal kavram olarak izlenebilir.",
        ],
        limit=3,
    )
    farklar = _dedupe_strings(
        [
            f"{detail_a['kavram']} {len(kaynak_a)} parcada, {detail_b['kavram']} ise {len(kaynak_b)} parcada odak olur.",
            f"{detail_a['kavram']} icin tanim daha cok '{detail_a['kisa_tanim'][:42]}' eksenindedir." if detail_a.get("kisa_tanim") else "",
            f"{detail_b['kavram']} farkli bir rol tasir: '{detail_b['kisa_tanim'][:42]}'." if detail_b.get("kisa_tanim") else "",
        ],
        limit=3,
    )

    birlikte_ornek = (
        f"{detail_a['kavram']} ile {detail_b['kavram']}, {doc.baslik or 'bu dokuman'} icindeki ayni akisin farkli noktalarini birlikte aciklar."
    )
    mini_soru = f"{detail_a['kavram']} ile {detail_b['kavram']} birlikte dusunuldugunde hangi problem cozulur?"

    return {
        "dokuman_id": doc.id,
        "kavram_a": detail_a["kavram"],
        "kavram_b": detail_b["kavram"],
        "ortak_yonler": ortak_yonler,
        "farklar": farklar,
        "birlikte_kullanim_ornegi": birlikte_ornek,
        "mini_soru": mini_soru,
        "_meta": {
            "concept_count": 2,
            "bagli_parca_sayisi": len(toplam),
            "ortak_parca_sayisi": len(ortak),
            "concept_overlap_ratio": round(len(ortak) / max(len(toplam), 1), 4),
        },
    }
