from __future__ import annotations

import re
from collections import Counter

from dokuman.models import MetrikKaydi
from dokuman.services.concept_runtime import compute_concept_candidates


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


def _slugify(value: str, *, fallback: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", _clean_text(value).lower()).strip("-")
    return clean[:36] or fallback


def _fallback_concepts(*, limit: int) -> list[dict]:
    labels = ["Temel Kavram", "Baglam", "Uygulama"][: max(2, int(limit or 3))]
    return [
        {
            "id": f"concept_{idx + 1}",
            "label": label,
            "source_ids": [],
            "gecme_sayisi": 0,
            "fusion_hits": 0,
            "agirlik": round(max(0.32, 0.56 - (idx * 0.08)), 2),
        }
        for idx, label in enumerate(labels)
    ]


def _fusion_history_pairs(*, user, doc, enabled: bool) -> Counter[tuple[str, str]]:
    if not enabled:
        return Counter()

    pair_counter: Counter[tuple[str, str]] = Counter()
    kayitlar = MetrikKaydi.objects.filter(
        kullanici=user,
        dokuman=doc,
        olay_turu="concept_fusion_uretildi",
    ).order_by("-id")[:32]

    for kayit in kayitlar:
        skor_ozeti = dict(getattr(kayit, "skor_ozeti", {}) or {})
        concept_a = _clean_text(skor_ozeti.get("concept_a"))
        concept_b = _clean_text(skor_ozeti.get("concept_b"))
        if (not concept_a or not concept_b) and isinstance(skor_ozeti.get("concept_pair"), list):
            pair = list(skor_ozeti.get("concept_pair") or [])[:2]
            concept_a = concept_a or _clean_text(pair[0] if len(pair) >= 1 else "")
            concept_b = concept_b or _clean_text(pair[1] if len(pair) >= 2 else "")
        if not concept_a or not concept_b or concept_a.lower() == concept_b.lower():
            continue
        pair_counter[tuple(sorted((concept_a, concept_b), key=str.lower))] += 1
    return pair_counter


def _candidate_rows(*, doc, user, limit: int, fusion_pairs: Counter[tuple[str, str]]) -> list[dict]:
    rows = []
    candidates = compute_concept_candidates(doc=doc, user=user, limit=max(limit, 8))
    for idx, item in enumerate(candidates[: max(1, int(limit or 6))], start=1):
        label = _clean_text(item.get("kavram"))
        if not label:
            continue
        source_ids = _dedupe_ints(item.get("kaynak_parca_idleri"), limit=12)
        gecme_sayisi = max(int(item.get("gecme_sayisi") or 0), 0)
        fusion_hits = sum(
            count
            for pair, count in fusion_pairs.items()
            if any(part.lower() == label.lower() for part in pair)
        )
        agirlik = min(
            1.0,
            0.24
            + min(len(source_ids), 4) * 0.13
            + min(gecme_sayisi, 6) * 0.07
            + min(fusion_hits, 3) * 0.08,
        )
        rows.append(
            {
                "id": f"concept_{_slugify(label, fallback=str(idx))}",
                "label": label,
                "source_ids": source_ids,
                "gecme_sayisi": gecme_sayisi,
                "fusion_hits": fusion_hits,
                "agirlik": round(agirlik, 2),
            }
        )
    return rows or _fallback_concepts(limit=limit)


def _edge_strength(row_a: dict, row_b: dict, fusion_pairs: Counter[tuple[str, str]]) -> float:
    sources_a = set(row_a.get("source_ids") or [])
    sources_b = set(row_b.get("source_ids") or [])
    ortak = len(sources_a.intersection(sources_b))
    birlik = len(sources_a.union(sources_b))
    ortak_oran = (ortak / max(birlik, 1)) if birlik else 0.0
    fusion_hits = fusion_pairs.get(tuple(sorted((row_a["label"], row_b["label"]), key=str.lower)), 0)
    if ortak <= 0 and fusion_hits <= 0:
        return 0.0

    skor = min(
        1.0,
        0.16
        + min(ortak, 3) * 0.21
        + ortak_oran * 0.28
        + min(fusion_hits, 3) * 0.17
        + min(row_a.get("gecme_sayisi", 0) + row_b.get("gecme_sayisi", 0), 8) * 0.02,
    )
    return round(skor, 2)


def _priority_band(value: float) -> str:
    if value >= 0.72:
        return "yuksek"
    if value >= 0.46:
        return "orta"
    return "dusuk"


def _strength_band(value: float) -> str:
    if value >= 0.68:
        return "kuvvetli"
    if value >= 0.4:
        return "orta"
    return "zayif"


def build_concept_graph_payload(
    *,
    doc,
    user,
    fusion_enabled: bool = True,
    metric_store_enabled: bool = True,
    limit: int = 6,
) -> dict:
    fusion_pairs = _fusion_history_pairs(
        user=user,
        doc=doc,
        enabled=bool(fusion_enabled and metric_store_enabled),
    )
    rows = _candidate_rows(doc=doc, user=user, limit=limit, fusion_pairs=fusion_pairs)

    dugumler = [
        {
            "id": row["id"],
            "label": row["label"],
            "agirlik": row["agirlik"],
        }
        for row in rows
    ]

    baglar = []
    for idx, row_a in enumerate(rows):
        for row_b in rows[idx + 1:]:
            strength = _edge_strength(row_a, row_b, fusion_pairs)
            if strength <= 0:
                continue
            baglar.append(
                {
                    "source": row_a["id"],
                    "target": row_b["id"],
                    "strength": strength,
                }
            )

    baglar.sort(
        key=lambda item: (
            -float(item["strength"]),
            item["source"],
            item["target"],
        )
    )
    baglar = baglar[:8]

    ortalama_agirlik = (
        sum(float(item["agirlik"]) for item in dugumler) / len(dugumler)
        if dugumler
        else 0.0
    )
    ortalama_bag = (
        sum(float(item["strength"]) for item in baglar) / len(baglar)
        if baglar
        else 0.0
    )

    return {
        "dokuman_id": doc.id,
        "dugumler": dugumler,
        "baglar": baglar,
        "kavram_onceligi": _priority_band(ortalama_agirlik),
        "bag_gucu": _strength_band(ortalama_bag),
    }
