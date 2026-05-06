from __future__ import annotations

import re

from dokuman.services.concept_runtime import compute_concept_candidates

_WORD_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9_%-]{2,}")
_STOPWORDS = {
    "ve",
    "veya",
    "ile",
    "icin",
    "gibi",
    "ama",
    "fakat",
    "bir",
    "bu",
    "su",
    "the",
    "that",
    "this",
}


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def _tokens(text: str) -> list[str]:
    out = []
    for raw in _WORD_RE.findall(_clean_text(text)):
        token = raw.lower()
        if token in _STOPWORDS or len(token) < 3:
            continue
        out.append(token)
    return out


def _phrase_match(term: str, answer_tokens: set[str]) -> bool:
    parts = [item.lower() for item in _WORD_RE.findall(_clean_text(term))]
    if not parts:
        return False
    matches = sum(1 for item in parts if item in answer_tokens)
    return matches / max(len(parts), 1) >= 0.5


def _hallucinated_terms(answer: str, source_terms: set[str], source_tokens: set[str]) -> list[str]:
    candidates = []
    seen = set()
    for raw in _WORD_RE.findall(_clean_text(answer)):
        clean = _clean_text(raw)
        if not clean:
            continue
        if not (clean[0].isupper() or clean.isupper()):
            continue
        if "_" in clean or "secret" in clean.lower():
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        pieces = [item.lower() for item in _WORD_RE.findall(clean)]
        if set(pieces).intersection(source_tokens) or key in source_terms:
            continue
        if len(clean) < 3:
            continue
        candidates.append(clean)
    return candidates[:3]


def evaluate_self_check(*, user, parca, kullanici_aciklamasi: str) -> dict:
    text = _clean_text(kullanici_aciklamasi)
    source_text = _clean_text(getattr(parca, "metin", "") or "")
    answer_tokens = set(_tokens(text))
    source_tokens = _tokens(source_text)
    source_token_set = set(source_tokens)

    concepts = compute_concept_candidates(doc=parca.dokuman, user=user, parca=parca, limit=8)
    if not concepts:
        concepts = [
            {
                "kavram": token.upper() if token.isupper() else token,
                "kaynak_parca_idleri": [parca.id],
                "gecme_sayisi": 1,
                "kisa_tanim": "",
            }
            for token in list(dict.fromkeys(source_tokens))[:5]
        ]

    critical = concepts[:5]
    matched = [item for item in critical if _phrase_match(item["kavram"], answer_tokens)]
    missing = [item for item in critical if item not in matched]
    source_terms = {item["kavram"].lower() for item in critical}
    hallucinated = _hallucinated_terms(text, source_terms, source_token_set)

    lexical_overlap = len(answer_tokens.intersection(source_token_set)) / max(len(source_token_set), 1)
    concept_coverage = len(matched) / max(len(critical), 1)
    hallucination_ratio = len(hallucinated) / max(len(answer_tokens), 1)
    score = round(_clamp01((0.55 * concept_coverage) + (0.3 * lexical_overlap) + (0.15 * (1.0 - hallucination_ratio))), 4)

    dogru_noktalar = [f"'{item['kavram']}' kavramina dogru temas var." for item in matched[:3]]
    if lexical_overlap >= 0.35:
        dogru_noktalar.append("Kaynak parcadaki ana baglamin onemli bir kismi yakalanmis.")

    duzeltilecek_noktalar = [f"'{term}' kavrami bu parca baglaminda desteklenmiyor." for term in hallucinated]
    if lexical_overlap < 0.2:
        duzeltilecek_noktalar.append("Kaynak parcadaki ana iliski daha net kurulmalı.")

    eksik_noktalar = [f"'{item['kavram']}' kavrami veya iliskisi eksik kalmis." for item in missing[:3]]
    if len(answer_tokens) < 5:
        eksik_noktalar.append("Aciklama cok kisa; bir ek cumle daha kapsamayi guclendirir.")

    return {
        "dogru_noktalar": dogru_noktalar[:4],
        "duzeltilecek_noktalar": duzeltilecek_noktalar[:4],
        "eksik_noktalar": eksik_noktalar[:4],
        "self_check_score": score,
        "_meta": {
            "critical_concept_count": len(critical),
            "matched_concept_count": len(matched),
            "hallucinated_term_count": len(hallucinated),
            "concept_overlap_ratio": round(concept_coverage, 4),
            "sonuc_orani": score,
        },
    }
