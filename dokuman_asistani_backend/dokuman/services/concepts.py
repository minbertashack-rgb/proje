from __future__ import annotations

import re
import unicodedata
from collections import Counter


_WORD_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9][A-Za-zÇĞİÖŞÜçğıöşü0-9_%-]*")
_ACRONYM_RE = re.compile(r"\b[A-Z0-9ÇĞİÖŞÜ]{2,10}\b")
_PHRASE_RE = re.compile(
    r"\b[A-Za-zÇĞİÖŞÜçğıöşü]{3,}(?:\s+[A-Za-zÇĞİÖŞÜçğıöşü]{3,}){1,3}\b"
)

_STOPWORDS = {
    "acaba",
    "ama",
    "ancak",
    "bana",
    "bazı",
    "belki",
    "ben",
    "bile",
    "bir",
    "biri",
    "bunu",
    "cok",
    "çok",
    "daha",
    "de",
    "da",
    "diye",
    "gibi",
    "gore",
    "göre",
    "hem",
    "icin",
    "için",
    "ile",
    "ise",
    "mi",
    "mu",
    "mı",
    "mü",
    "olan",
    "olarak",
    "sonra",
    "su",
    "şu",
    "ve",
    "veya",
    "ya",
    "the",
    "and",
    "for",
    "from",
    "into",
    "that",
    "this",
    "with",
    "are",
    "was",
    "were",
    "has",
    "have",
}

_KNOWN_DEFINITIONS = {
    "atp": {
        "tr": "Hücrede enerji taşıyan molekül.",
        "en": "A molecule that carries energy in the cell.",
    },
    "dna": {
        "tr": "Canlıların kalıtsal bilgisini taşıyan molekül.",
        "en": "A molecule that carries hereditary information.",
    },
    "rna": {
        "tr": "Genetik bilginin okunması ve protein üretiminde görev alan molekül.",
        "en": "A molecule involved in reading genetic information and making proteins.",
    },
}


def _clean(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    return " ".join(text.split()).strip(" \t\r\n.,;:!?()[]{}\"'")


def normalize_concept(value: str) -> str:
    clean = _clean(value).lower()
    clean = clean.translate(str.maketrans({"ı": "i", "İ": "i"}))
    clean = re.sub(r"[^a-z0-9çğöşü\s_-]+", "", clean)
    return re.sub(r"\s+", "-", clean).strip("-_")


def _display_term(value: str) -> str:
    clean = _clean(value)
    if clean.isupper():
        return clean
    words = clean.split()
    if len(words) > 1:
        return " ".join(word.lower() for word in words)
    return clean


def _is_valid_candidate(value: str) -> bool:
    clean = _clean(value)
    if len(clean) < 3 or len(clean) > 72:
        return False
    if clean.isdigit() or normalize_concept(clean) in _STOPWORDS:
        return False
    tokens = [token.lower() for token in _WORD_RE.findall(clean)]
    if not tokens or all(token in _STOPWORDS or len(token) < 3 for token in tokens):
        return False
    if len(tokens) > 4:
        return False
    return True


def concept_definition_fallback(concept: str, context: str, lang: str) -> str:
    key = normalize_concept(concept)
    language = "en" if str(lang or "").lower().startswith("en") else "tr"
    known = _KNOWN_DEFINITIONS.get(key)
    if known:
        return known.get(language) or known["tr"]
    clean = _display_term(concept)
    if language == "en":
        return f"{clean} is an important concept in the selected text."
    return f"{clean}, seçili metinde geçen önemli bir kavramdır."


def _example_for(concept: str, lang: str) -> str:
    key = normalize_concept(concept)
    if key == "atp":
        return (
            "Think of ATP like an energy bar in a game."
            if str(lang or "").lower().startswith("en")
            else "ATP'yi oyundaki enerji barı gibi düşünebilirsin."
        )
    if str(lang or "").lower().startswith("en"):
        return f"You can treat {concept} as a keyword that unlocks this part."
    return f"{concept} bu parçayı anlamak için anahtar kelime gibi düşünülebilir."


def extract_concepts_from_text(text: str, lang: str = "tr") -> list[dict]:
    clean_text = _clean(text)
    scores: dict[str, float] = {}
    display: dict[str, str] = {}

    def add(term: str, weight: float) -> None:
        if not _is_valid_candidate(term):
            return
        key = normalize_concept(term)
        scores[key] = scores.get(key, 0.0) + weight
        candidate = _display_term(term)
        current = display.get(key, "")
        if not current or candidate.isupper() or len(candidate) > len(current):
            display[key] = candidate

    for term in _ACRONYM_RE.findall(clean_text):
        add(term, 4.0)

    for phrase in _PHRASE_RE.findall(clean_text):
        tokens = [token for token in phrase.split() if token.lower() not in _STOPWORDS]
        if 2 <= len(tokens) <= 4:
            add(" ".join(tokens), 2.0)

    token_counter: Counter[str] = Counter()
    token_original: dict[str, str] = {}
    for raw in _WORD_RE.findall(clean_text):
        token = raw.lower()
        if token in _STOPWORDS or token.isdigit() or len(token) < 4:
            continue
        token_counter[token] += 1
        token_original.setdefault(token, raw.upper() if raw.isupper() else raw.lower())

    for token, count in token_counter.items():
        if count >= 2:
            add(token_original[token], min(3.0, 1.0 + count * 0.45))

    concepts = []
    for key, score in scores.items():
        term = display[key]
        concepts.append(
            {
                "id": key,
                "term": term,
                "definition": concept_definition_fallback(term, clean_text, lang),
                "example": _example_for(term, lang),
                "source_part_id": None,
                "path": "",
                "confidence": round(min(0.95, 0.45 + score / 10), 2),
            }
        )
    concepts.sort(key=lambda item: (-item["confidence"], item["term"].lower()))
    return concepts[:16]


def build_concept_relations(concepts: list, text: str) -> list[dict]:
    clean_text = _clean(text).lower()
    normalized = []
    for item in concepts or []:
        term = _clean(item.get("term") if isinstance(item, dict) else item)
        if term:
            normalized.append(term)

    relations = []
    for index, source in enumerate(normalized[:10]):
        source_key = normalize_concept(source)
        for target in normalized[index + 1 : index + 4]:
            target_key = normalize_concept(target)
            if source_key == target_key:
                continue
            source_pos = clean_text.find(source.lower())
            target_pos = clean_text.find(target.lower())
            close = source_pos >= 0 and target_pos >= 0 and abs(source_pos - target_pos) <= 360
            if not close and index > 1:
                continue
            relations.append(
                {
                    "source": source,
                    "target": target,
                    "relation": "ilişkili",
                    "reason": f"{source} ve {target} seçili metinde yakın bağlamda geçiyor.",
                }
            )
            if len(relations) >= 12:
                return relations
    return relations


def find_concept_mentions(document, concept: str) -> list[dict]:
    query = _clean(concept)
    if not query or len(query) < 2:
        return []
    query_lower = query.lower()
    mentions = []
    for part in document.parcalar.all().order_by("sira", "id"):
        text = _clean(getattr(part, "metin", "") or "")
        pos = text.lower().find(query_lower)
        if pos < 0:
            continue
        start = max(0, pos - 70)
        end = min(len(text), pos + len(query) + 110)
        snippet = text[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        meta = getattr(part, "meta", {}) or {}
        title = meta.get("baslik") or meta.get("title") or getattr(part, "adres", "") or f"Parça {part.sira}"
        mentions.append(
            {
                "part_id": part.id,
                "title": str(title),
                "path": getattr(part, "adres", "") or str(title),
                "snippet": snippet,
            }
        )
    return mentions[:20]
