from __future__ import annotations

import json
from collections.abc import Mapping

from dokuman.ai2.validators import extract_json
from dokuman.i18n import language_instruction, normalize_lang
from dokuman.services.remix import clean_text, normalize_source, source_from_part_text

SUPPORTED_DIRECTORS_CUT_TYPES = {"quick", "story", "exam"}

CUT_TITLES = {
    "tr": {
        "quick": "Hızlı Cut",
        "story": "Story Cut",
        "exam": "Exam Cut",
    },
    "en": {
        "quick": "Quick Cut",
        "story": "Story Cut",
        "exam": "Exam Cut",
    },
}

CUT_INSTRUCTIONS = {
    "quick": "Critical sentences, two examples, and a quick summary.",
    "story": "Cause -> result -> lesson/story flow with smooth narration.",
    "exam": "Teacher question, trap points, and a mini test.",
}


def build_directors_cut_prompt(*, cut_type: str, source: dict, part_text: str, lang: str) -> list[dict]:
    lang = normalize_lang(lang)
    payload = {
        "one_liner": source.get("one_liner") or "",
        "very_simple": source.get("very_simple") or "",
        "steps": list(source.get("steps") or [])[:4],
        "examples": list(source.get("examples") or [])[:4],
        "glossary": list(source.get("glossary") or [])[:4],
        "mini_quiz": list(source.get("mini_quiz") or [])[:3],
        "part_text": clean_text(part_text, limit=1000),
    }
    system = (
        "You are DocVerse Director's Cut. Reframe only the given document part. "
        "Do not invent facts outside the source. Return compact JSON with keys: "
        "title, summary, sections, quiz. sections are [{title, items}], "
        "quiz is [{question, answer}]. "
        f"{language_instruction(lang)}"
    )
    user = (
        f"cut_type={cut_type}\n"
        f"instruction={CUT_INSTRUCTIONS.get(cut_type, '')}\n"
        f"source={json.dumps(payload, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def fallback_directors_cut_response(*, cut_type: str, source: dict, part_text: str, lang: str, warning: str = "") -> dict:
    lang = normalize_lang(lang)
    tr = lang == "tr"
    source = normalize_source(source) or source_from_part_text(part_text)
    one = clean_text(source.get("one_liner") or source.get("very_simple") or part_text, limit=220)
    simple = clean_text(source.get("very_simple") or one, limit=260)
    steps = _strings(source.get("steps"), limit=4)
    examples = _strings(source.get("examples"), limit=4)
    quiz_seed = _strings(source.get("mini_quiz"), limit=2)

    if cut_type == "quick":
        summary = (
            f"Bu bölümün ana fikri {one}" if tr else f"The main idea of this part is {one}"
        )
        sections = [
            {
                "title": "Kritik cümleler" if tr else "Critical sentences",
                "items": _pad([one] + steps, [simple], 3),
            },
            {
                "title": "Hızlı örnekler" if tr else "Quick examples",
                "items": _pad(examples, _generic_examples(tr, simple), 2),
            },
        ]
        quiz = []
    elif cut_type == "story":
        summary = (
            "Bu bölüm bir süreç gibi düşünülebilir."
            if tr
            else "This part can be read as a process."
        )
        sections = [
            {
                "title": "Sebep" if tr else "Cause",
                "items": [_first(steps, one)],
            },
            {
                "title": "Sonuç" if tr else "Result",
                "items": [simple],
            },
            {
                "title": "Ders" if tr else "Lesson",
                "items": [
                    "Ana fikri neden-sonuç ilişkisiyle bağla." if tr else "Connect the key idea through cause and result."
                ],
            },
        ]
        quiz = []
    else:
        summary = (
            "Bu bölüm sınavda kavram ve neden-sonuç ilişkisi olarak sorulabilir."
            if tr
            else "This part may appear as a concept and cause-result exam question."
        )
        question = quiz_seed[0] if quiz_seed else (f"Hoca bunu nasıl sorar: {one}?" if tr else f"How might a teacher ask this: {one}?")
        sections = [
            {
                "title": "Hoca ne sorar?" if tr else "What might the teacher ask?",
                "items": [question],
            },
            {
                "title": "Tuzak noktalar" if tr else "Trap points",
                "items": [
                    examples[0] if examples else (
                        "Ana kavramı örnekten kopuk ezberlemek." if tr else "Memorizing the concept without its example."
                    )
                ],
            },
        ]
        quiz = [
            {
                "question": question,
                "answer": simple,
            }
        ]

    return {
        "enabled": True,
        "cut_type": cut_type,
        "title": _title(cut_type, lang),
        "summary": clean_text(summary, limit=700),
        "sections": _sections(sections),
        "quiz": _quiz(quiz),
        "source": "fallback",
        "warning": warning,
    }


def parse_ai_directors_cut_response(raw, *, cut_type: str, lang: str) -> dict:
    if isinstance(raw, Mapping):
        obj = dict(raw)
    else:
        text = str(raw or "").strip()
        obj = extract_json(text) or {}
        if not obj and text:
            obj = {"summary": text}
    if not isinstance(obj, Mapping):
        obj = {}

    summary = clean_text(obj.get("summary") or obj.get("content") or obj.get("text"), limit=900)
    sections = _sections(obj.get("sections") or obj.get("bolumler") or [])
    quiz = _quiz(obj.get("quiz") or obj.get("mini_quiz") or [])
    if not summary and not sections and not quiz:
        return {}
    return {
        "enabled": True,
        "cut_type": cut_type,
        "title": clean_text(obj.get("title") or _title(cut_type, lang), limit=90),
        "summary": summary,
        "sections": sections,
        "quiz": quiz,
        "source": "ai",
        "warning": "",
    }


def _title(cut_type: str, lang: str) -> str:
    catalog = CUT_TITLES.get(normalize_lang(lang)) or CUT_TITLES["en"]
    return catalog.get(cut_type) or CUT_TITLES["en"].get(cut_type) or cut_type


def _strings(value, *, limit: int = 4) -> list[str]:
    raw = value if isinstance(value, list) else ([] if value in (None, "") else [value])
    out = []
    for item in raw:
        if isinstance(item, Mapping):
            text = item.get("text") or item.get("question") or item.get("title") or item.get("answer")
            if not text:
                text = " - ".join(clean_text(v) for v in item.values() if clean_text(v))
        else:
            text = item
        clean = clean_text(text, limit=220)
        if clean and clean not in out:
            out.append(clean)
        if len(out) >= limit:
            break
    return out


def _sections(value) -> list[dict]:
    raw = value if isinstance(value, list) else []
    out = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        title = clean_text(item.get("title") or item.get("baslik"), limit=90)
        items = _strings(item.get("items") or item.get("maddeler"), limit=5)
        if title or items:
            out.append({"title": title, "items": items})
        if len(out) >= 5:
            break
    return out


def _quiz(value) -> list[dict]:
    raw = value if isinstance(value, list) else []
    out = []
    for item in raw:
        if isinstance(item, Mapping):
            question = clean_text(item.get("question") or item.get("soru"), limit=220)
            answer = clean_text(item.get("answer") or item.get("cevap"), limit=260)
        else:
            question = clean_text(item, limit=220)
            answer = ""
        if question or answer:
            out.append({"question": question, "answer": answer})
        if len(out) >= 4:
            break
    return out


def _pad(items: list[str], fallback: list[str], count: int) -> list[str]:
    out = []
    for item in list(items or []) + list(fallback or []):
        clean = clean_text(item, limit=220)
        if clean and clean not in out:
            out.append(clean)
        if len(out) >= count:
            return out
    return out


def _first(items: list[str], fallback: str) -> str:
    return clean_text(items[0] if items else fallback, limit=220)


def _generic_examples(tr: bool, simple: str) -> list[str]:
    if tr:
        return [
            f"Örnek: {simple}",
            "Mini örnek: ana fikri tek cümleyle not kartına çevir.",
        ]
    return [
        f"Example: {simple}",
        "Mini example: turn the main idea into one note-card sentence.",
    ]
