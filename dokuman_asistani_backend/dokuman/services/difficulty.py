from __future__ import annotations

import re
from typing import Any

DOMAIN_TERMS = {
    "rls",
    "cdc",
    "oltp",
    "etl",
    "jwt",
    "rbac",
    "oauth",
    "api",
    "gateway",
    "telemetry",
    "observability",
    "latency",
    "throughput",
    "cache",
    "index",
    "sql",
    "select",
    "join",
    "where",
    "group",
    "xlookup",
    "vlookup",
    "if",
}

FORMULA_KEYWORDS = {
    "if(",
    "xlookup(",
    "vlookup(",
    "sum(",
    "avg(",
    "count(",
    "min(",
    "max(",
}

WORD_RE = re.compile(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü_]+", re.UNICODE)
SENT_SPLIT_RE = re.compile(r"[.!?…]+")
UPPER_ACRONYM_RE = re.compile(r"\b[A-ZÇĞİÖŞÜ]{2,}\b")
TABLE_LINE_RE = re.compile(r"\|")
MATH_SYMBOL_RE = re.compile(r"[=<>+\-/*^%(){}\[\];:]")
PUNCTUATION_RE = re.compile(r"[,;()]")
CODE_HINT_RE = re.compile(r"\b(def|class|import|select|from|where|return)\b|[{}]")

REASON_TEXT = {
    "long_text": {
        "tr": "Metin uzun",
        "en": "Text is long",
    },
    "long_sentences": {
        "tr": "Cümleler uzun",
        "en": "Sentences are long",
    },
    "term_density": {
        "tr": "Terim yoğunluğu yüksek",
        "en": "Term density is high",
    },
    "symbol_formula_density": {
        "tr": "Sembol veya formül yoğunluğu yüksek",
        "en": "Symbol or formula density is high",
    },
    "structured_content": {
        "tr": "Kod/tablo benzeri yapı içeriyor",
        "en": "Contains code/table-like structure",
    },
    "uppercase_acronyms": {
        "tr": "Kısaltma veya büyük harf yoğunluğu yüksek",
        "en": "Contains many abbreviations or uppercase terms",
    },
    "long_words": {
        "tr": "Uzun kelime oranı yüksek",
        "en": "Long-word ratio is high",
    },
    "technical_content": {
        "tr": "Teknik kavramlar içeriyor",
        "en": "Contains technical concepts",
    },
    "simple_text": {
        "tr": "Kısa ve sade metin",
        "en": "Short and plain text",
    },
}


def _clamp01(value: float) -> float:
    return 0.0 if value < 0 else 1.0 if value > 1 else value


def normalize_language(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "tr"
    code = raw.split(",", 1)[0].split(";", 1)[0].replace("_", "-").split("-", 1)[0]
    return code if code in {"tr", "en"} else "tr"


def difficulty_label_from_score(score: float | None) -> str:
    if score is None:
        return "orta"
    if score >= 0.70:
        return "zor"
    if score >= 0.40:
        return "orta"
    return "kolay"


def _reason_text(reason_key: str, *, language: str) -> str:
    entry = REASON_TEXT.get(reason_key) or {}
    return entry.get(normalize_language(language)) or entry.get("tr") or reason_key


def summarize_difficulty_reasons(metrics: dict[str, Any], *, language: str = "tr") -> list[str]:
    keys: list[str] = []
    if metrics.get("term_factor", 0.0) >= 0.45:
        keys.append("term_density")
    if metrics.get("long_factor", 0.0) >= 0.45:
        keys.append("long_sentences")
    if metrics.get("symbol_factor", 0.0) >= 0.35:
        keys.append("symbol_formula_density")
    if metrics.get("structure_factor", 0.0) >= 0.55:
        keys.append("structured_content")
    if metrics.get("length_factor", 0.0) >= 0.75:
        keys.append("long_text")
    if metrics.get("uppercase_acronym_count", 0) >= 2:
        keys.append("uppercase_acronyms")
    if metrics.get("long_word_factor", 0.0) >= 0.45:
        keys.append("long_words")
    if not keys and metrics.get("score", 0.0) >= 0.40:
        keys.append("technical_content")
    if not keys:
        keys.append("simple_text")
    return [_reason_text(key, language=language) for key in keys[:4]]


def calculate_part_difficulty(
    text: str,
    metadata: dict | None = None,
    *,
    language: str = "tr",
) -> dict[str, Any]:
    value = str(text or "").strip()
    meta = metadata if isinstance(metadata, dict) else {}
    if not value:
        return {
            "difficulty_score": 0.0,
            "difficulty_label": "kolay",
            "difficulty_reasons": [],
            "metrics": {"words": 0, "score": 0.0},
        }

    lower = value.lower()
    words = WORD_RE.findall(value)
    word_count = len(words)
    char_count = len(value)

    sentences = [item.strip() for item in SENT_SPLIT_RE.split(value) if item.strip()]
    sentence_lengths = [len(WORD_RE.findall(sentence)) for sentence in sentences] or [word_count]
    avg_sentence_len = sum(sentence_lengths) / max(len(sentence_lengths), 1)
    max_sentence_len = max(sentence_lengths)

    domain_hits = sum(
        len(re.findall(rf"\b{re.escape(term)}\b", lower))
        for term in DOMAIN_TERMS
    )
    uppercase_acronyms = len(UPPER_ACRONYM_RE.findall(value))
    term_density = (domain_hits + uppercase_acronyms) / max(word_count, 1)

    symbol_count = len(MATH_SYMBOL_RE.findall(value))
    formula_hits = sum(1 for keyword in FORMULA_KEYWORDS if keyword in lower)
    symbol_ratio = symbol_count / max(char_count, 1)

    punctuation_ratio = len(PUNCTUATION_RE.findall(value)) / max(char_count, 1)
    pipe_lines = sum(1 for line in value.splitlines() if TABLE_LINE_RE.search(line))
    code_hint = bool(CODE_HINT_RE.search(value))
    meta_kind = str(meta.get("chunk_kind") or meta.get("tur") or "").lower()
    meta_structured = any(token in meta_kind for token in ("table", "code", "formula", "rows"))

    long_words = [word for word in words if len(word) >= 10]
    long_word_ratio = len(long_words) / max(word_count, 1)

    length_factor = _clamp01(word_count / 60.0)
    sentence_factor = _clamp01(max(max_sentence_len / 60.0, avg_sentence_len / 35.0))
    term_factor = _clamp01(term_density * 12.0)
    symbol_factor = _clamp01(symbol_ratio * 8.0 + formula_hits * 0.08)
    punctuation_factor = _clamp01(punctuation_ratio * 18.0)
    structure_factor = 1.0 if pipe_lines or code_hint or meta_structured else 0.0
    long_word_factor = _clamp01(long_word_ratio * 5.0)

    score = 0.05 + (
        0.16 * length_factor
        + 0.16 * sentence_factor
        + 0.28 * term_factor
        + 0.20 * symbol_factor
        + 0.05 * punctuation_factor
        + 0.10 * structure_factor
        + 0.05 * long_word_factor
    )
    if structure_factor >= 1.0 and (symbol_factor >= 0.20 or term_factor >= 0.25):
        score = max(score, 0.72)
    if formula_hits >= 1 and symbol_factor >= 0.35:
        score = max(score, 0.70)
    score = round(_clamp01(score), 3)

    metrics = {
        "words": word_count,
        "chars": char_count,
        "length_factor": length_factor,
        "avg_sentence_len": avg_sentence_len,
        "max_sentence_len": max_sentence_len,
        "long_factor": sentence_factor,
        "domain_hits": domain_hits,
        "uppercase_acronym_count": uppercase_acronyms,
        "term_density": term_density,
        "term_factor": term_factor,
        "symbol_count": symbol_count,
        "formula_hits": formula_hits,
        "symbol_factor": symbol_factor,
        "punctuation_factor": punctuation_factor,
        "pipe_lines": pipe_lines,
        "structure_factor": structure_factor,
        "long_word_ratio": long_word_ratio,
        "long_word_factor": long_word_factor,
        "score": score,
    }
    return {
        "difficulty_score": score,
        "difficulty_label": difficulty_label_from_score(score),
        "difficulty_reasons": summarize_difficulty_reasons(metrics, language=language),
        "metrics": metrics,
    }
