from __future__ import annotations

import re
from collections import Counter

from dokuman.models import AnlamadimKaydi, DokumanNotu, Not

_STOPWORDS = {
    "ve",
    "veya",
    "ile",
    "icin",
    "gibi",
    "ama",
    "fakat",
    "olan",
    "olarak",
    "bir",
    "bu",
    "su",
    "da",
    "de",
    "mi",
    "mu",
    "mı",
    "mü",
    "ise",
    "ile",
    "icin",
    "gore",
    "gorev",
    "kadar",
    "then",
    "that",
    "this",
    "from",
    "with",
    "into",
    "were",
    "have",
    "has",
    "been",
}
_WORD_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9_%-]{2,}")
_TITLE_RE = re.compile(r"\b(?:[A-ZÇĞİÖŞÜ][a-zçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+){0,2})\b")
_ACRONYM_RE = re.compile(r"\b[A-ZÇĞİÖŞÜ0-9_]{2,}\b")


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_key(value: str) -> str:
    return _clean_text(value).lower()


def _term_tokens(value: str) -> list[str]:
    return [token.lower() for token in _WORD_RE.findall(_clean_text(value))]


def _valid_term(value: str) -> bool:
    clean = _clean_text(value)
    if len(clean) < 2:
        return False
    lowered = clean.lower()
    if "secret" in lowered or clean.startswith("HAM_"):
        return False
    if "_" in clean and len(clean) > 10:
        return False
    tokens = _term_tokens(clean)
    if not tokens:
        return False
    if len(tokens) == 1 and tokens[0] in _STOPWORDS:
        return False
    if len(tokens) == 1 and len(tokens[0]) < 3:
        return False
    return True


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


def _generic_definition(term: str) -> str:
    clean = _clean_text(term)
    if clean.isupper():
        return f"{clean} dokumanda teknik kisaltma olarak izlenen bir kavramdir."
    if len(clean.split()) >= 2:
        return f"{clean}, dokumanda tekrar eden yapisal veya teknik bir kavramdir."
    return f"{clean}, dokumandaki temel kavramlardan biridir."


def _note_definition(*, doc, user, term: str) -> str:
    token = _clean_text(term)
    if not token:
        return ""

    note = Not.objects.filter(owner=user, dokuman=doc, baslik__icontains=token).order_by("-updated_at", "-id").first()
    if note and _clean_text(note.baslik):
        return f"{_clean_text(note.baslik)} notunda one cikan kavram."

    portal = DokumanNotu.objects.filter(owner=user, dokuman=doc, baslik__icontains=token).order_by("-updated_at", "-id").first()
    if portal and _clean_text(portal.baslik):
        return f"{_clean_text(portal.baslik)} portal notunda vurgulanan kavram."
    return ""


def _glossary_items(*, user, doc, parca=None) -> list[dict]:
    qs = AnlamadimKaydi.objects.filter(kullanici=user, dokuman=doc).order_by("-olusturuldu")
    if parca is not None:
        qs = qs.filter(parca=parca)

    items = []
    for kayit in qs[:24]:
        payload = kayit.cikti_json or {}
        raw_items = payload.get("terimler") or payload.get("glossary") or []
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            term = _clean_text(item.get("terim") or item.get("term"))
            tanim = _clean_text(item.get("tanim") or item.get("definition") or item.get("aciklama"))
            if not _valid_term(term):
                continue
            items.append(
                {
                    "terim": term,
                    "tanim": tanim[:180],
                    "parca_id": getattr(kayit, "parca_id", None),
                }
            )
    return items


def _meaningful_tokens(text: str) -> list[str]:
    out = []
    for raw in _WORD_RE.findall(_clean_text(text)):
        token = raw.lower()
        if token in _STOPWORDS or len(token) < 4:
            continue
        if token.isdigit():
            continue
        out.append(token)
    return out


def _iter_candidates(text: str) -> list[str]:
    clean = _clean_text(text)
    candidates = []
    candidates.extend(
        item for item in _ACRONYM_RE.findall(clean)
        if "_" not in item and len(item) <= 10
    )
    candidates.extend(_TITLE_RE.findall(clean))
    return [_clean_text(item) for item in candidates if _valid_term(item)]


def _register_candidate(index: dict, *, term: str, parca_id: int | None, tanim: str = "", weight: float = 1.0, count: int = 1):
    clean = _clean_text(term)
    key = _normalize_key(clean)
    if not _valid_term(clean):
        return

    row = index.setdefault(
        key,
        {
            "kavram": clean,
            "kaynak_parca_idleri": set(),
            "gecme_sayisi": 0,
            "score": 0.0,
            "kisa_tanim": "",
        },
    )
    if len(clean) > len(row["kavram"]):
        row["kavram"] = clean
    if parca_id:
        row["kaynak_parca_idleri"].add(int(parca_id))
    row["gecme_sayisi"] += max(int(count or 1), 1)
    row["score"] += float(weight or 0.0)
    if tanim and not row["kisa_tanim"]:
        row["kisa_tanim"] = _clean_text(tanim)[:180]


def compute_concept_candidates(*, doc, user, parca=None, limit: int = 12) -> list[dict]:
    parcalar = list((doc.parcalar.filter(id=getattr(parca, "id", None)) if parca is not None else doc.parcalar.all()).order_by("id"))
    concept_index: dict[str, dict] = {}
    concept_strong_sources: dict[str, set[int]] = {}
    token_counts: Counter[str] = Counter()
    token_scores: Counter[str] = Counter()
    token_sources: dict[str, set[int]] = {}
    token_strong_sources: dict[str, set[int]] = {}
    token_display: dict[str, str] = {}

    for item in _glossary_items(user=user, doc=doc, parca=parca):
        _register_candidate(
            concept_index,
            term=item["terim"],
            parca_id=item.get("parca_id"),
            tanim=item.get("tanim") or _note_definition(doc=doc, user=user, term=item["terim"]),
            weight=3.0,
            count=2,
        )
        if item.get("parca_id"):
            concept_strong_sources.setdefault(_normalize_key(item["terim"]), set()).add(int(item["parca_id"]))

    for parca_obj in parcalar:
        meta = dict(getattr(parca_obj, "meta", {}) or {})
        is_weak_content = bool(meta.get("weak_content"))
        weak_multiplier = 0.35 if is_weak_content else 1.0
        text = getattr(parca_obj, "metin", "") or ""

        for term in dict.fromkeys(_iter_candidates(text)):
            _register_candidate(
                concept_index,
                term=term,
                parca_id=parca_obj.id,
                tanim=_note_definition(doc=doc, user=user, term=term),
                weight=1.6 * weak_multiplier,
            )
            if not is_weak_content:
                concept_strong_sources.setdefault(_normalize_key(term), set()).add(int(parca_obj.id))

        for token in _meaningful_tokens(text):
            token_counts[token] += 1
            token_scores[token] += weak_multiplier
            token_sources.setdefault(token, set()).add(parca_obj.id)
            if not is_weak_content:
                token_strong_sources.setdefault(token, set()).add(parca_obj.id)
            token_display.setdefault(token, token.upper() if token.isupper() else token)

    for token, count in token_counts.items():
        if count < 2:
            continue
        weighted_score = float(token_scores[token])
        source_ids = sorted(token_sources[token])
        strong_source_ids = sorted(token_strong_sources.get(token) or [])
        if not strong_source_ids and weighted_score < 2.5:
            continue
        _register_candidate(
            concept_index,
            term=token_display[token],
            parca_id=(strong_source_ids or source_ids or [None])[0],
            tanim=_note_definition(doc=doc, user=user, term=token_display[token]),
            weight=min(2.2, 0.75 * weighted_score),
            count=count,
        )
        concept_index[_normalize_key(token_display[token])]["kaynak_parca_idleri"].update(source_ids)
        if strong_source_ids:
            concept_strong_sources.setdefault(_normalize_key(token_display[token]), set()).update(strong_source_ids)

    results = []
    for row in concept_index.values():
        source_ids = _dedupe_ints(sorted(row["kaynak_parca_idleri"]), limit=12)
        has_definition = bool(row["kisa_tanim"])
        has_strong_source = bool(concept_strong_sources.get(_normalize_key(row["kavram"])))
        if not has_definition and not has_strong_source and row["score"] < 1.35:
            continue
        if not has_definition and row["score"] < 1.35 and len(source_ids) < 2 and row["gecme_sayisi"] < 2:
            continue
        results.append(
            {
                "kavram": row["kavram"],
                "kaynak_parca_idleri": source_ids,
                "gecme_sayisi": int(row["gecme_sayisi"]),
                "kisa_tanim": row["kisa_tanim"] or _generic_definition(row["kavram"]),
                "_score": round(float(row["score"]), 4),
            }
        )

    results.sort(key=lambda item: (-item["_score"], -len(item["kaynak_parca_idleri"]), -item["gecme_sayisi"], item["kavram"].lower()))
    cleaned = []
    for item in results[: max(1, int(limit or 12))]:
        cleaned.append({key: value for key, value in item.items() if not key.startswith("_")})
    return cleaned


def build_concept_surface_payload(*, doc, user, limit: int = 12) -> dict:
    kavramlar = compute_concept_candidates(doc=doc, user=user, limit=limit)
    return {
        "dokuman_id": doc.id,
        "toplam_kavram": len(kavramlar),
        "kavramlar": kavramlar,
    }


def build_concept_detail_payload(*, doc, user, kavram: str) -> dict:
    concept = _clean_text(kavram)
    if not concept:
        return {
            "dokuman_id": doc.id,
            "kavram": "",
            "kisa_tanim": "",
            "bagli_parca_idleri": [],
            "ornek_gecis_sayisi": 0,
        }

    key = _normalize_key(concept)
    for item in compute_concept_candidates(doc=doc, user=user, limit=24):
        if _normalize_key(item.get("kavram")) == key:
            return {
                "dokuman_id": doc.id,
                "kavram": item["kavram"],
                "kisa_tanim": item.get("kisa_tanim") or _generic_definition(item["kavram"]),
                "bagli_parca_idleri": list(item.get("kaynak_parca_idleri") or [])[:12],
                "ornek_gecis_sayisi": int(item.get("gecme_sayisi") or 0),
            }

    parca_ids = []
    gecis_sayisi = 0
    tokens = set(_term_tokens(concept))
    for parca in doc.parcalar.all().order_by("id"):
        text_tokens = _meaningful_tokens(getattr(parca, "metin", "") or "")
        if tokens and tokens.intersection(text_tokens):
            parca_ids.append(parca.id)
            gecis_sayisi += sum(1 for token in tokens if token in text_tokens)

    kisa_tanim = _note_definition(doc=doc, user=user, term=concept) or _generic_definition(concept)
    return {
        "dokuman_id": doc.id,
        "kavram": concept,
        "kisa_tanim": kisa_tanim,
        "bagli_parca_idleri": _dedupe_ints(parca_ids, limit=12),
        "ornek_gecis_sayisi": int(gecis_sayisi),
    }
