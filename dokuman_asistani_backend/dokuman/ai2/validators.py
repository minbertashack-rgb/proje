"""AI ciktilarini parse eden, onaran ve guvenli response sekline sokan validator katmani."""

import ast
import json
import math
import re
from typing import Any

from dokuman.services.phase2_scores import apply_feedback_to_usefulness
from dokuman.services.retrieval_terms import normalize_query_terms


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_ANLAMADIM_FIELD_NAMES = (
    "one_liner",
    "very_simple",
    "glossary",
    "steps",
    "examples",
    "trap",
    "function_purpose",
    "flow_summary",
    "block_comments",
    "line_comments",
    "mini_quiz",
    "dokumanda_yok",
)


def _clamp01(value: float) -> float:
    """Skor hesaplarinda 0-1 araligini koruyan kucuk guard helper'i."""
    return max(0.0, min(1.0, float(value)))


def _safe_text(value: Any) -> str:
    """Validator icinde null ve tip farklarini tek string yuzeyine indirger."""
    return str(value or "").strip()


def _strip_code_fences(text: str) -> str:
    """LLM'in markdown code fence ile sarmaladigi JSON cevabi temizler."""
    return _CODE_FENCE_RE.sub("", str(text or "").strip()).strip()


def _balanced_json_slice(text: str) -> str:
    """Bozuk cevap icinden ilk dengeli dict/list blogunu ayiklamaya calisir."""
    start_positions = [idx for idx in (text.find("{"), text.find("[")) if idx != -1]
    if not start_positions:
        return text

    start = min(start_positions)
    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escaped = False

    for idx in range(start, len(text)):
        ch = text[idx]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]

    return text[start:]


def _repair_json_text(text: str) -> str:
    """Akilli tirnak ve eksik kapanis gibi yaygin JSON bozulmalarini onarir."""
    candidate = _strip_code_fences(text)
    candidate = candidate.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    candidate = _balanced_json_slice(candidate).strip()
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)

    open_curly = candidate.count("{")
    close_curly = candidate.count("}")
    open_square = candidate.count("[")
    close_square = candidate.count("]")

    if open_square > close_square:
        candidate += "]" * (open_square - close_square)
    if open_curly > close_curly:
        candidate += "}" * (open_curly - close_curly)

    return candidate.strip()


def _loads_candidates(text: str):
    """Ham ve onarilmis adaylari sirasiyla deneyip dict/list parse etmeye calisir."""
    candidates = []
    raw = _strip_code_fences(text)
    if raw:
        candidates.append(raw)

    repaired = _repair_json_text(raw)
    if repaired and repaired not in candidates:
        candidates.append(repaired)

    if raw:
        start = raw.find("{")
        if start != -1 and start < len(raw) - 1:
            tail = _repair_json_text(raw[start:])
            if tail and tail not in candidates:
                candidates.append(tail)

    for candidate in candidates:
        # json.loads basarisizsa literal_eval yalnizca salvage amacli son sans olarak kullaniliyor.
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, (dict, list)):
                return parsed
        except Exception:
            pass

        try:
            parsed = ast.literal_eval(candidate)
            if isinstance(parsed, (dict, list)):
                return parsed
        except Exception:
            pass

    return None


def _strip_json_wrappers(text: str) -> str:
    """Parca parca alan kurtarma modunda dis sarmallari kaldirir."""
    clean = _strip_code_fences(text).strip().strip(",")
    if clean.startswith("{"):
        clean = clean[1:]
    if clean.endswith("}"):
        clean = clean[:-1]
    return clean.strip()


def _extract_field_map(text: str) -> dict[str, str]:
    """Tam JSON gelmese bile satir bazli alan ciftlerini salvage etmek icin toplar."""
    clean = _strip_json_wrappers(text)
    if not clean:
        return {}

    field_pattern = re.compile(
        r'^(?:[*_`#>\-\s]*)?(?:"?(%s)"?)(?:[*_`#\s]*)?:\s*(.*)$'
        % "|".join(_ANLAMADIM_FIELD_NAMES),
        re.IGNORECASE,
    )
    out: dict[str, str] = {}
    current_key = ""
    buffer: list[str] = []

    def flush():
        """Toplanan satirlari aktif alan anahtarina yazip sonraki alana gecisi hazirlar."""
        nonlocal current_key, buffer
        if current_key:
            value = "\n".join(buffer).strip().strip(",").strip()
            out[current_key] = value
        current_key = ""
        buffer = []

    for raw_line in clean.splitlines():
        line = str(raw_line).rstrip()
        stripped = line.strip()
        match = field_pattern.match(stripped)
        if match:
            # Yeni alan gördüğümüzde önce önceki tamponu sabitleyip sonra yeni anahtara geçilir.
            flush()
            current_key = str(match.group(1) or "").strip().lower()
            first_value = str(match.group(2) or "").strip()
            if first_value:
                buffer.append(first_value)
            continue
        if current_key and stripped:
            buffer.append(stripped)

    flush()
    return out


def _parse_text_list(value: str) -> list[str]:
    """Liste alanlarini JSON, madde imi veya satir listesinden ortak diziye indirger."""
    text = _strip_code_fences(value).strip()
    if not text:
        return []
    loaded = _loads_candidates(text)
    if isinstance(loaded, list):
        return [str(item).strip() for item in loaded if str(item).strip()]
    parts = re.split(r"\n+|^\s*\d+[.)]\s*|\s*[-•]\s+", text, flags=re.MULTILINE)
    return [str(part).strip(" ,") for part in parts if str(part).strip(" ,")]


def _parse_glossary(value: str) -> list[dict]:
    """Glossary alanini dict/list veya 'terim:tanim' satirlarindan normalize eder."""
    text = _strip_code_fences(value).strip()
    if not text:
        return []
    loaded = _loads_candidates(text)
    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, dict)]
    if isinstance(loaded, dict):
        return [
            {"terim": str(term).strip(), "tanim": str(definition).strip()}
            for term, definition in loaded.items()
            if str(term).strip() and str(definition).strip()
        ]

    items = []
    for line in re.split(r"\n+|^\s*[-•]\s*", text, flags=re.MULTILINE):
        line = str(line).strip(" ,")
        if not line:
            continue
        if ":" in line:
            term, definition = line.split(":", 1)
            term = str(term).strip(" \"'")
            definition = str(definition).strip(" \"'")
            if term and definition:
                items.append({"terim": term, "tanim": definition})
    return items


def _parse_quiz(value: str) -> list[dict]:
    """Mini quiz alanini JSON liste veya soru-cevap satirlarindan kurtarmaya calisir."""
    text = _strip_code_fences(value).strip()
    if not text:
        return []
    loaded = _loads_candidates(text)
    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, dict)]

    quiz = []
    question = ""
    for raw_line in text.splitlines():
        line = str(raw_line).strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith(("q:", "soru:")):
            question = line.split(":", 1)[1].strip()
            continue
        if low.startswith(("a:", "cevap:")):
            answer = line.split(":", 1)[1].strip()
            if question:
                quiz.append({"q": question, "a": answer})
                question = ""
            continue
    if question:
        quiz.append({"q": question, "a": ""})
    return quiz


def _parse_bool(value: str):
    """Cok dilli bool metinlerini validator'in kullandigi True/False/None sonucuna cevirir."""
    low = _strip_code_fences(value).strip().strip('",').lower()
    if low in {"true", "evet", "yes", "1"}:
        return True
    if low in {"false", "hayir", "hayır", "no", "0"}:
        return False
    return None


def _salvage_anlamadim_fields(text: str):
    """JSON yerine yari-yapili metin donen AI cevabindan anlamadim alanlarini kurtarir."""
    field_map = _extract_field_map(text)
    if not field_map:
        return None

    out: dict[str, Any] = {}
    for key, value in field_map.items():
        if key in {"one_liner", "very_simple", "trap"}:
            out[key] = _strip_code_fences(value).strip().strip('",')
        elif key == "glossary":
            out[key] = _parse_glossary(value)
        elif key in {"steps", "examples"}:
            out[key] = _parse_text_list(value)
        elif key == "mini_quiz":
            out[key] = _parse_quiz(value)
        elif key == "dokumanda_yok":
            parsed_bool = _parse_bool(value)
            if parsed_bool is not None:
                out[key] = parsed_bool

    return out if out else None


def extract_json(text: Any):
    """Model cevabindan dict/list cikar; gerekirse fenced veya bozuk JSON'u onarmayi dener."""
    if text is None:
        return None

    if isinstance(text, (dict, list)):
        return text

    if not isinstance(text, str):
        text = str(text)

    text = text.strip()
    if not text:
        return None

    parsed = _loads_candidates(text)
    if parsed is not None:
        return parsed

    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        parsed = _loads_candidates(fenced.group(1))
        if parsed is not None:
            return parsed

    salvaged = _salvage_anlamadim_fields(text)
    if salvaged is not None:
        return salvaged

    return None


_DISALLOWED_SOURCE_ID_RE = re.compile(
    r"(?:parca_id|citation_id|citation|kanit:|\[)\s*[:=]?\s*(\d+)",
    re.IGNORECASE,
)
_ANLAMADIM_MIN_TEXT_LENGTH = {
    "one_liner": 18,
    "very_simple": 22,
    "trap": 16,
}
_ANLAMADIM_REQUIRED_FIELDS = (
    "one_liner",
    "very_simple",
    "glossary",
    "steps",
    "examples",
    "trap",
    "mini_quiz",
)


def _clean_text(value: Any) -> str:
    """Whitespace normalize edilmis temiz string yardimcisi."""
    return " ".join(str(value or "").split()).strip()


def _coerce_string_list(value: Any) -> list[str]:
    """String veya liste girdisini temiz bir string listesine cevirir."""
    if isinstance(value, list):
        return [_clean_text(item) for item in value if _clean_text(item)]
    if isinstance(value, str):
        parsed = _parse_text_list(value)
        return [_clean_text(item) for item in parsed if _clean_text(item)]
    return []


def _coerce_comment_list(value: Any) -> list[str]:
    """Block/line comment alanlarini ortak string-list pipeline'ina sokar."""
    return _coerce_string_list(value)


def _coerce_glossary_list(value: Any) -> list[dict]:
    """Glossary alanini terim/tanim sozlukleri listesine normalize eder."""
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = [
            {"terim": key, "tanim": item}
            for key, item in value.items()
        ]
    elif isinstance(value, str):
        items = _parse_glossary(value)
    else:
        items = []

    clean_items = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        term = _clean_text(item.get("terim") or item.get("term") or item.get("kavram"))
        definition = _clean_text(
            item.get("tanim")
            or item.get("definition")
            or item.get("def")
            or item.get("aciklama")
        )
        if not term or not definition:
            continue
        dedupe_key = term.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        clean_items.append({"terim": term, "tanim": definition})
    return clean_items


def _coerce_quiz_list(value: Any) -> list[dict]:
    """Quiz alanini tekrar eden soru ve bos cevaplari ayiklayarak normalize eder."""
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = _parse_quiz(value)
    else:
        items = []

    clean_items = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        question = _clean_text(item.get("q") or item.get("soru"))
        answer = _clean_text(item.get("a") or item.get("cevap"))
        if not question:
            continue
        dedupe_key = question.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        clean_items.append({"q": question, "a": answer})
    return clean_items


def _coerce_citation_list(value: Any) -> tuple[list[int], list[Any]]:
    """Citation listesini int id'lere cevirip bozuk ogeyi ayri dondurur."""
    if not isinstance(value, list):
        return [], []

    clean: list[int] = []
    invalid: list[Any] = []
    seen = set()
    for item in value:
        raw_value = item
        if isinstance(item, dict):
            raw_value = item.get("id", item.get("parca_id", item.get("citation_id")))
        try:
            citation_id = int(raw_value)
        except Exception:
            invalid.append(item)
            continue
        if citation_id in seen:
            continue
        seen.add(citation_id)
        clean.append(citation_id)
    return clean, invalid


def _detect_disallowed_source_ids(answer_text: str, allowed_citation_ids: set[int]) -> list[int]:
    """Cevap icinde allowlist disi citation sizintisi olup olmadigini denetler."""
    if not answer_text:
        return []
    found = []
    for match in _DISALLOWED_SOURCE_ID_RE.finditer(str(answer_text or "")):
        try:
            source_id = int(match.group(1))
        except Exception:
            continue
        if source_id not in allowed_citation_ids and source_id not in found:
            found.append(source_id)
    return found


def normalize_anlamadim_payload(obj: dict | None) -> dict:
    """Anlamadim cevabini beklenen alan adlari ve tiplerle ortak payload'a indirger."""
    obj = obj if isinstance(obj, dict) else {}
    return {
        "one_liner": _clean_text(obj.get("one_liner") or obj.get("ozet_1c") or obj.get("ozet_1cumle")),
        "very_simple": _clean_text(obj.get("very_simple") or obj.get("cok_basit")),
        "themed_example": _clean_text(obj.get("tema_bazli_ornek") or obj.get("themed_example")),
        "alternative_example": _clean_text(obj.get("alternatif_ornek") or obj.get("alternative_example")),
        "glossary": _coerce_glossary_list(obj.get("glossary", obj.get("terimler"))),
        "steps": _coerce_string_list(obj.get("steps", obj.get("adim_adim"))),
        "examples": _coerce_string_list(obj.get("examples", obj.get("ornekler"))),
        "trap": _clean_text(obj.get("trap") or obj.get("tuzak")),
        "function_purpose": _clean_text(obj.get("function_purpose") or obj.get("fonksiyon_amaci")),
        "flow_summary": _clean_text(obj.get("flow_summary") or obj.get("akis_ozeti")),
        "block_comments": _coerce_comment_list(obj.get("block_comments", obj.get("blok_yorumlari"))),
        "line_comments": _coerce_comment_list(obj.get("line_comments", obj.get("satir_yorumlari"))),
        "mini_quiz": _coerce_quiz_list(obj.get("mini_quiz", obj.get("mini_test"))),
        "dokumanda_yok": bool(obj.get("dokumanda_yok", False)),
    }


def analyze_anlamadim_completeness(obj: dict | None, *, quiz_required: bool = True) -> dict:
    """Anlamadim payload'inin minimum alan ve icerik kalitesini puanlar."""
    normalized = normalize_anlamadim_payload(obj)
    alan_yeterlilik = {
        "one_liner": len(normalized["one_liner"]) >= _ANLAMADIM_MIN_TEXT_LENGTH["one_liner"],
        "very_simple": len(normalized["very_simple"]) >= _ANLAMADIM_MIN_TEXT_LENGTH["very_simple"],
        "glossary": any(
            len(_clean_text(item.get("terim"))) >= 2 and len(_clean_text(item.get("tanim"))) >= 12
            for item in normalized["glossary"]
            if isinstance(item, dict)
        ),
        "steps": len([item for item in normalized["steps"] if len(_clean_text(item)) >= 14]) >= 2,
        "examples": len([item for item in normalized["examples"] if len(_clean_text(item)) >= 14]) >= 1,
        "trap": len(normalized["trap"]) >= _ANLAMADIM_MIN_TEXT_LENGTH["trap"],
        "mini_quiz": len(
            [
                item
                for item in normalized["mini_quiz"]
                if len(_clean_text(item.get("q"))) >= 10 and len(_clean_text(item.get("a"))) >= 4
            ]
        ) >= 3 if quiz_required else True,
    }

    required_fields = [alan for alan in _ANLAMADIM_REQUIRED_FIELDS if quiz_required or alan != "mini_quiz"]
    eksik_alanlar = [alan for alan in required_fields if not alan_yeterlilik.get(alan, False)]
    return {
        "normalized": normalized,
        "required_fields": required_fields,
        "alan_yeterlilik": alan_yeterlilik,
        "eksik_alanlar": eksik_alanlar,
        "zayif_alanlar": list(eksik_alanlar),
        "completeness_score": sum(1 for alan in required_fields if alan_yeterlilik.get(alan, False)),
        "yeterli_mi": not eksik_alanlar,
    }


def evaluate_completeness_score(answer_text: str, reference_texts: list[str] | None = None) -> float:
    """Cevabin referans metinlere ne kadar temas ettigini kaba bir completeness skoru ile olcer."""
    answer_terms = set(normalize_query_terms(_safe_text(answer_text)))
    reference_terms = set()
    for text in reference_texts or []:
        reference_terms.update(normalize_query_terms(_safe_text(text)))
    if not reference_terms:
        return 0.0
    return round(len(answer_terms & reference_terms) / (len(reference_terms) + 0.001), 4)


def evaluate_citation_alignment(citation_ids, provided_ids) -> float:
    """Modelin kullandigi citation'lar ile verilen kanitlarin ortusme oranini hesaplar."""
    cited = {int(value) for value in citation_ids or [] if str(value).strip()}
    provided = {int(value) for value in provided_ids or [] if str(value).strip()}
    if not cited:
        return 0.0
    return round(len(cited & provided) / (len(cited) + 0.001), 4)


def evaluate_hallucination_risk(
    *,
    citation_ids,
    provided_ids,
    completeness_score: float,
    supported: bool = True,
    unsupported_reason: str = "",
) -> dict:
    """Citation hizasi ve destek durumu uzerinden halusinasyon riskini aciklamali sekilde dondurur."""
    citation_alignment = evaluate_citation_alignment(citation_ids, provided_ids)
    unsupported_reason = _clean_text(unsupported_reason)
    if unsupported_reason in {"source_leakage", "gecersiz_citation"}:
        risk = 0.98
        reason = unsupported_reason
    elif not supported:
        risk = 0.08 if unsupported_reason == "low_evidence_abstain" else 0.20
        reason = unsupported_reason or "safe_abstain"
    else:
        risk = _clamp01(1.0 - ((0.5 * citation_alignment) + (0.5 * _clamp01(completeness_score))))
        reason = "low_risk"
        if citation_alignment < 0.5:
            reason = "citation_alignment_weak"
        elif completeness_score < 0.60:
            reason = "completeness_low"
    if supported and citation_alignment < 0.5 and reason == "low_risk":
        reason = "citation_alignment_weak"
    elif supported and completeness_score < 0.60 and reason == "low_risk":
        reason = "completeness_low"
    return {
        "citation_alignment_score": round(citation_alignment, 4),
        "hallucination_risk": round(risk, 4),
        "hallucination_reason": reason,
    }


def evaluate_usefulness_score_v2(
    *,
    completeness_score: float,
    hallucination_risk: float,
    supported: bool = True,
    feedback_turu: str = "",
    feedback_weight_score: float = 0.0,
) -> dict:
    """Completeness ve risk sinyallerinden acceptance takibine uygun usefulness skoru uretir."""
    base_usefulness = _clamp01(_clamp01(completeness_score) * (1.0 - _clamp01(hallucination_risk)))
    adjusted = apply_feedback_to_usefulness(
        base_usefulness=base_usefulness,
        feedback_turu=feedback_turu,
        feedback_weight_score=feedback_weight_score,
    )
    usefulness = adjusted["usefulness_score_v2"]
    if not supported:
        usefulness = min(usefulness, 0.25)
    reason = "useful"
    if usefulness < 0.35:
        reason = "low_usefulness"
    elif completeness_score < 0.60:
        reason = "partial_usefulness"
    return {
        "usefulness_score_v2": round(usefulness, 4),
        "usefulness_reason": reason,
        "usefulness_feedback_shift": adjusted["usefulness_feedback_shift"],
    }


def validate_kanitli(obj: dict, evidence_ids: set[int], *, strict_evidence: bool = True) -> dict:
    """Kanitli cevap shape'ini, citation allowlist'ini ve no-leak cizgisini denetler."""
    out = {
        "answer": "",
        "supported": False,
        "citations": [],
        "missing": [],
        "followups": [],
        "unsupported_reason": "",
        "coverage_note": "",
    }
    allowed_citation_ids = {int(value) for value in evidence_ids or set()}
    if isinstance(obj, dict):
        out["answer"] = _clean_text(obj.get("answer", ""))
        out["supported"] = bool(obj.get("supported", False))
        out["missing"] = _coerce_string_list(obj.get("missing", []))
        out["followups"] = _coerce_string_list(obj.get("followups", []))
        out["unsupported_reason"] = _clean_text(obj.get("unsupported_reason"))
        out["coverage_note"] = _clean_text(obj.get("coverage_note"))

        raw_citations = obj.get("citations", obj.get("citation_ids", []))
        clean_citations, invalid_citations = _coerce_citation_list(raw_citations)
        allowlist_disinda = [
            citation_id
            for citation_id in clean_citations
            if citation_id not in allowed_citation_ids
        ]
        answer_leak_ids = (
            _detect_disallowed_source_ids(out["answer"], allowed_citation_ids)
            if strict_evidence
            else []
        )

        if invalid_citations or allowlist_disinda:
            out["unsupported_reason"] = out["unsupported_reason"] or "gecersiz_citation"
            out["coverage_note"] = out["coverage_note"] or "Whitelist disi citation algilandi."
        elif answer_leak_ids:
            out["unsupported_reason"] = out["unsupported_reason"] or "source_leakage"
            out["coverage_note"] = out["coverage_note"] or "Allowlist disi kaynak izi algilandi."
        else:
            out["citations"] = clean_citations

    if not out["citations"]:
        out["supported"] = False
        out["answer"] = "Dokümanda geçmiyor."

    if strict_evidence and out["supported"] and not out["citations"]:
        out["supported"] = False
        out["answer"] = out["answer"] or "Dokümanda geçmiyor."

    return out


def validate_anlamadim(obj: dict, parca_id: int, *, quiz_required: bool = True) -> dict:
    """Anlamadim cevabini son response shape'ine sokup eksik alanlari guvenli fallback'lerle kapatir."""
    normalized = normalize_anlamadim_payload(obj)
    out = {
        "ozet_1c": "",
        "cok_basit": "",
        "tema_bazli_ornek": "",
        "alternatif_ornek": "",
        "terimler": [],
        "adim_adim": [],
        "ornekler": [],
        "tuzak": "",
        "function_purpose": "",
        "flow_summary": "",
        "block_comments": [],
        "line_comments": [],
        "mini_test": [],
        "kanit_parca_idleri": [parca_id],
    }
    if isinstance(obj, dict):
        out["ozet_1c"] = normalized["one_liner"]
        out["cok_basit"] = normalized["very_simple"]
        out["tema_bazli_ornek"] = normalized["themed_example"]
        out["alternatif_ornek"] = normalized["alternative_example"]
        out["terimler"] = normalized["glossary"]
        out["adim_adim"] = normalized["steps"]
        out["ornekler"] = normalized["examples"]
        out["tuzak"] = normalized["trap"]
        out["function_purpose"] = normalized["function_purpose"]
        out["flow_summary"] = normalized["flow_summary"]
        out["block_comments"] = normalized["block_comments"]
        out["line_comments"] = normalized["line_comments"]
        out["mini_test"] = [
            {
                "soru": _clean_text(item.get("q") or item.get("soru")),
                "cevap": _clean_text(item.get("a") or item.get("cevap")),
            }
            for item in normalized["mini_quiz"]
            if isinstance(item, dict) and _clean_text(item.get("q") or item.get("soru"))
        ]

        kp = obj.get("kanit_parca_idleri", [])
        if isinstance(kp, list):
            clean = []
            for x in kp:
                try:
                    clean.append(int(x))
                except Exception:
                    continue
            if parca_id not in clean:
                clean.insert(0, parca_id)
            out["kanit_parca_idleri"] = clean
        else:
            out["kanit_parca_idleri"] = [parca_id]

    if not out["ozet_1c"]:
        out["ozet_1c"] = "Bu bölümün kısa özeti üretilemedi."
    if not out["cok_basit"]:
        out["cok_basit"] = "Bu bölümü daha basit anlatmak için daha fazla bağlam gerekebilir."
    if not out["mini_test"] and quiz_required:
        out["mini_test"] = [
            {"soru": "Bu parçanın ana fikri nedir?", "cevap": out["ozet_1c"]},
            {"soru": "Parçada geçen 1 önemli terim yaz.", "cevap": (out["terimler"][0]["terim"] if out["terimler"] else "—")},
            {"soru": "Bu bilgiyi nerede kullanırsın?", "cevap": "Örnek bir senaryo üzerinden uygularsın."},
        ]

    return out
