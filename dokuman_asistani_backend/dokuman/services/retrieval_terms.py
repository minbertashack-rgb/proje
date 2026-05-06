from __future__ import annotations

import re


TOKEN_RE = re.compile(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü_]+", re.UNICODE)
STOPWORDS = {
    "ve", "ile", "bir", "bu", "şu", "icin", "için", "gibi", "ama", "fakat", "cunku", "çünkü",
    "da", "de", "the", "a", "an", "to", "of", "in", "on", "for", "is", "are",
}


def normalize_query_terms(text: str) -> list[str]:
    # Retrieval ve evidence selection ayni hafif token temizligini kullansin.
    toks = [tok.lower() for tok in TOKEN_RE.findall(str(text or ""))]
    return [tok for tok in toks if len(tok) >= 2 and tok not in STOPWORDS]


def normalize_text_terms(text: str) -> list[str]:
    return normalize_query_terms(text)
