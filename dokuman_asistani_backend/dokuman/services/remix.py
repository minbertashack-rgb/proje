from __future__ import annotations

import json
import re
from collections.abc import Mapping

from dokuman.ai2.validators import extract_json
from dokuman.i18n import language_instruction, normalize_lang

SUPPORTED_REMIX_STYLES = {
    "short",
    "simpler",
    "more_examples",
    "table",
    "exam",
    "buddy",
    "teacher",
    "technical",
}

STYLE_TITLES = {
    "tr": {
        "short": "Kısa anlatım",
        "simpler": "Daha basit anlatım",
        "more_examples": "Örnekli anlatım",
        "table": "Tablolu anlatım",
        "exam": "Sinav dili",
        "buddy": "Kanka dili",
        "teacher": "Hoca dili",
        "technical": "Teknik anlatım",
    },
    "en": {
        "short": "Short version",
        "simpler": "Simpler explanation",
        "more_examples": "More examples",
        "table": "Table version",
        "exam": "Exam style",
        "buddy": "Buddy style",
        "teacher": "Teacher style",
        "technical": "Technical style",
    },
}

STYLE_INSTRUCTIONS = {
    "short": "3 short bullets. Keep only the core idea.",
    "simpler": "Explain for a beginner. Use plain words and two simple bullets.",
    "more_examples": "Add 2 or 3 concrete examples.",
    "table": "Return a concept / meaning / example table.",
    "exam": "Show how a teacher may ask it and one common trap.",
    "buddy": "Warm, casual, respectful tone. No slang overload.",
    "teacher": "Calm, structured teacher tone.",
    "technical": "More academic and precise wording.",
}


def clean_text(value, *, limit: int | None = None) -> str:
    text = " ".join(str(value or "").split()).strip()
    if limit is not None and len(text) > limit:
        return text[:limit].rsplit(" ", 1)[0].strip() + "..."
    return text


def normalize_source(source) -> dict:
    if not isinstance(source, Mapping):
        return {}
    return {
        "one_liner": clean_text(source.get("one_liner") or source.get("oneSentence") or source.get("summary")),
        "very_simple": clean_text(source.get("very_simple") or source.get("verySimple") or source.get("simpleExplanation")),
        "glossary": _string_items(source.get("glossary") or source.get("terms"), limit=5),
        "steps": _string_items(source.get("steps"), limit=5),
        "examples": _string_items(source.get("examples"), limit=5),
        "mini_quiz": _string_items(source.get("mini_quiz") or source.get("quiz"), limit=3),
    }


def source_from_part_text(text: str) -> dict:
    clean = clean_text(text, limit=900)
    sentences = _sentences(clean)
    one_liner = sentences[0] if sentences else clean
    return {
        "one_liner": clean_text(one_liner, limit=180),
        "very_simple": clean_text(one_liner or clean, limit=240),
        "glossary": [],
        "steps": sentences[:3],
        "examples": [],
        "mini_quiz": [],
    }


def build_remix_prompt(*, style: str, source: dict, part_text: str, lang: str) -> list[dict]:
    lang = normalize_lang(lang)
    base = {
        "one_liner": source.get("one_liner") or "",
        "very_simple": source.get("very_simple") or "",
        "steps": list(source.get("steps") or [])[:4],
        "examples": list(source.get("examples") or [])[:4],
        "glossary": list(source.get("glossary") or [])[:4],
        "part_text": clean_text(part_text, limit=900),
    }
    content = json.dumps(base, ensure_ascii=False)
    system = (
        "You are DocVerse Remix. Rework the given explanation only. "
        "Do not invent facts outside the source. Return compact JSON with keys: "
        "title, content, items, table. table rows use left, middle, right. "
        f"{language_instruction(lang)}"
    )
    user = (
        f"style={style}\n"
        f"instruction={STYLE_INSTRUCTIONS.get(style, '')}\n"
        f"source={content}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def fallback_remix_response(*, style: str, source: dict, part_text: str, lang: str, warning: str = "") -> dict:
    lang = normalize_lang(lang)
    tr = lang == "tr"
    title = _title(style, lang)
    source = normalize_source(source) or source_from_part_text(part_text)
    one = clean_text(source.get("one_liner") or source.get("very_simple") or part_text, limit=220)
    simple = clean_text(source.get("very_simple") or one, limit=260)
    steps = _string_items(source.get("steps"), limit=4)
    examples = _string_items(source.get("examples"), limit=4)
    glossary = _string_items(source.get("glossary"), limit=4)

    if style == "short":
        items = _pad_items([one] + steps, [simple], count=3)
        content = "Kisa ozet:" if tr else "Short summary:"
        table = []
    elif style == "simpler":
        content = f"Bu bolum basitce sunu anlatir: {simple}" if tr else f"In simple terms: {simple}"
        items = _pad_items(steps, [one, simple], count=2)
        table = []
    elif style == "more_examples":
        content = one
        seed = examples or [simple]
        generic = (
            ["Gunluk ornek: bir kavrami once adiyla, sonra ne ise yaradigiyla dusun.", "Mini ornek: metindeki ana fikir bir kontrol listesine cevrilebilir."]
            if tr
            else ["Everyday example: name the concept first, then say what it does.", "Mini example: turn the core idea into a quick checklist."]
        )
        items = _pad_items(seed, generic, count=3)
        table = []
    elif style == "table":
        content = "Kavramlari tablo gibi oku." if tr else "Read the concepts as a table."
        terms = glossary or [one]
        table = [
            {"left": clean_text(term.split(":", 1)[0], limit=70), "middle": clean_text(term, limit=120), "right": examples[idx] if idx < len(examples) else clean_text(simple, limit=90)}
            for idx, term in enumerate(terms[:3])
        ]
        if not table:
            table = [{"left": "Kavram" if tr else "Concept", "middle": simple, "right": one}]
        items = []
    elif style == "exam":
        content = f"Hoca bunu soyle sorabilir: {one}" if tr else f"A teacher may ask it like this: {one}"
        items = [
            f"Dikkat edilmesi gereken tuzak: {examples[0] if examples else simple}" if tr else f"Common trap: {examples[0] if examples else simple}",
            "Cevapta ana kavrami ve kaniti birlikte yaz." if tr else "Mention the key concept and its evidence together.",
        ]
        table = []
    elif style == "buddy":
        content = f"Kisaca soyle dusun: {simple}" if tr else f"Think of it this way: {simple}"
        items = _pad_items(examples + steps, [one], count=2)
        table = []
    elif style == "teacher":
        content = f"Bu parcanin ana fikri sudur: {one}" if tr else f"The main idea of this part is: {one}"
        items = _pad_items(steps, [simple], count=3)
        table = []
    else:
        content = f"Teknik ifade: {one}" if tr else f"Technical wording: {one}"
        items = _pad_items(glossary + steps, [simple], count=3)
        table = []

    return {
        "enabled": True,
        "style": style,
        "title": title,
        "content": clean_text(content, limit=700),
        "items": [clean_text(item, limit=220) for item in items if clean_text(item)][:5],
        "table": table[:5],
        "source": "fallback",
        "warning": warning,
    }


def parse_ai_remix_response(raw, *, style: str, lang: str) -> dict:
    if isinstance(raw, Mapping):
        obj = dict(raw)
    else:
        text = str(raw or "").strip()
        obj = extract_json(text) or {}
        if not obj and text:
            obj = {"content": text}
    if not isinstance(obj, Mapping):
        obj = {}
    content = clean_text(obj.get("content") or obj.get("text") or obj.get("answer"), limit=900)
    items = _string_items(obj.get("items") or obj.get("maddeler"), limit=5)
    table = _table_rows(obj.get("table") or obj.get("tablo"))
    if not content and not items and not table:
        return {}
    return {
        "enabled": True,
        "style": style,
        "title": clean_text(obj.get("title") or _title(style, lang), limit=80),
        "content": content,
        "items": items,
        "table": table,
        "source": "ai",
        "warning": "",
    }


def _title(style: str, lang: str) -> str:
    lang = normalize_lang(lang)
    catalog = STYLE_TITLES.get(lang) or STYLE_TITLES["en"]
    return catalog.get(style) or STYLE_TITLES["en"].get(style) or style


def _sentences(text: str) -> list[str]:
    return [clean_text(part) for part in re.split(r"(?<=[.!?])\s+|\n+", str(text or "")) if clean_text(part)]


def _string_items(value, *, limit: int = 5) -> list[str]:
    raw = value if isinstance(value, list) else ([] if value in (None, "") else [value])
    out = []
    for item in raw:
        if isinstance(item, Mapping):
            text = item.get("text") or item.get("metin") or item.get("title") or item.get("terim")
            if not text:
                vals = [clean_text(v) for v in item.values() if clean_text(v)]
                text = " - ".join(vals)
        else:
            text = item
        clean = clean_text(text)
        if clean and clean not in out:
            out.append(clean)
        if len(out) >= limit:
            break
    return out


def _table_rows(value) -> list[dict]:
    rows = value if isinstance(value, list) else []
    out = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        left = clean_text(row.get("left") or row.get("concept") or row.get("kavram"))
        middle = clean_text(row.get("middle") or row.get("meaning") or row.get("aciklama"))
        right = clean_text(row.get("right") or row.get("example") or row.get("ornek"))
        if left or middle or right:
            out.append({"left": left, "middle": middle, "right": right})
        if len(out) >= 5:
            break
    return out


def _pad_items(items: list[str], fallback: list[str], *, count: int) -> list[str]:
    out = []
    for item in list(items or []) + list(fallback or []):
        clean = clean_text(item)
        if clean and clean not in out:
            out.append(clean)
        if len(out) >= count:
            return out
    while len(out) < count:
        out.append("Ana fikri kisa ve net tekrar et." if count else "")
    return out
