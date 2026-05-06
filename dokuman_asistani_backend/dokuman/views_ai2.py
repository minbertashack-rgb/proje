"""AI2 tabanli kanitli cevap, anlamadim aciklamasi ve mini quiz yuzeylerini yoneten API katmani."""

import logging
import multiprocessing
import re
import time
from queue import Empty

from django.core.exceptions import FieldError
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .ai2.llm import ai2_scope_icin_max_token, chat
from .ai2.prompts import build_kanitli_prompt, build_anlamadim_prompt
from .ai2.evidence_runner import evidence_ai_chat_worker
from .ai2.validators import (
    analyze_anlamadim_completeness,
    evaluate_completeness_score,
    evaluate_hallucination_risk,
    evaluate_usefulness_score_v2,
    extract_json,
    normalize_anlamadim_payload,
    validate_kanitli,
    validate_anlamadim,
)
from .i18n import get_request_lang, language_instruction, t
from .services.evidence_orchestrator import (
    build_evidence_response_payload,
    derive_answer_source_state,
    orchestrate_evidence_selection,
    prepare_evidence_candidates,
)
from .services.feature_flags import modul_acik_mi
from .services.kanitli_qa import ground_answer_text, retrieve_evidence_standardized
from .services.personalization import build_preference_prompt, resolve_preferences, themed_example_for_text
from .services.metric_store import (
    compute_confusion_map_score,
    compute_mastery_score,
    kaydet_skor_olayi,
)
from .services.boss_runtime import record_learning_outcome_events
from .services.quiz_runtime import (
    build_mini_quiz_gate,
    enqueue_quiz_acceptance_event,
    mark_quiz_cooldown,
    record_mini_quiz_event,
    record_quiz_readiness_event,
)
from .serializers import QuizResultSerializer
from .throttles import EvidenceThrottle, ExplainThrottle

logger = logging.getLogger(__name__)
_EVIDENCE_AI_TIMEOUT_SECONDS = 45
_EVIDENCE_AI_HTTP_TIMEOUT_SECONDS = max(1, _EVIDENCE_AI_TIMEOUT_SECONDS - 5)
_EVIDENCE_AI_MAX_TOKENS = 96


class EvidenceAITimeoutError(TimeoutError):
    pass


def _run_evidence_ai_chat_with_deadline(messages: list[dict], *, max_tokens: int) -> str:
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue(maxsize=1)
    process = ctx.Process(
        target=evidence_ai_chat_worker,
        args=(queue, messages, max_tokens, _EVIDENCE_AI_HTTP_TIMEOUT_SECONDS),
    )
    process.daemon = True
    process.start()
    process.join(_EVIDENCE_AI_TIMEOUT_SECONDS)
    if process.is_alive():
        process.terminate()
        process.join(3)
        queue.close()
        raise EvidenceAITimeoutError("evidence_ai_timeout")

    try:
        result = queue.get_nowait()
    except Empty as exc:
        raise RuntimeError(f"evidence_ai_empty_process_result exitcode={process.exitcode}") from exc
    finally:
        queue.close()

    if result.get("ok"):
        return str(result.get("value") or "")
    error_type = str(result.get("error_type") or "RuntimeError")
    error = str(result.get("error") or "AI cevabı alınamadı.")
    raise RuntimeError(f"{error_type}: {error}")

# Modellerin isimleri projede farklı olabilir diye fallback koyuyorum.
try:
    from .models import Dokuman, KullaniciTercih, Parca
except Exception:
    from .models import Dokuman
    try:
        from .models import KullaniciTercih
    except Exception:
        KullaniciTercih = None
    try:
        from .models import DokumanParca as Parca
    except Exception:
        Parca = None

_DEFAULT_THEME = "genel"
_ALLOWED_THEMES = {"genel", "yazilim", "teknoloji", "matematik", "saglik", "spor", "yemek", "oyun", "film"}
_THEME_PATTERNS = {
    "genel": "Bunu, gunluk bir is akisini daha az hata ile tekrar etmek gibi dusun.",
    "teknoloji": "Bunu, bir uygulamada istek islenirken dogru modulu secmek gibi dusun.",
    "yazilim": "Bunu, kod akisini takip edip hangi fonksiyonun ne zaman calistigini anlamak gibi dusun.",
    "matematik": "Bunu, problemi adim adim cozup hangi verinin hangi sonuca gittigini izlemek gibi dusun.",
    "saglik": "Bunu, once bulgulari tabloya koyup sonra dogru yoruma gitmek gibi dusun.",
    "spor": "Bunu, mac istatistiklerine bakip hangi hamlenin sonucu degistirdigini okumak gibi dusun.",
    "yemek": "Bunu, tarifte malzeme ile adimlarin neden o sirada verildigini anlamak gibi dusun.",
    "oyun": "Bunu, oyunda hangi esyanin hangi gorevi actigini okuyup strateji kurmak gibi dusun.",
    "film": "Bunu, sahneleri izleyip hangi detaylarin ana hikayeye baglandigini fark etmek gibi dusun.",
}
_ALTERNATIVE_THEME_MAP = {
    "genel": "Diger aci: once ana fikri bul, sonra destekleyen iki ipucunu ayir.",
    "teknoloji": "Alternatif aci: bunu bir API yerine veri akisi cizimi gibi okuyup girdi-ciktiya bak.",
    "yazilim": "Alternatif aci: bunu test senaryosu gibi dusun ve once beklenen ciktiyi tahmin et.",
    "matematik": "Alternatif aci: bunu formulu ezberlemek yerine hangi degiskenin neyi etkiledigini takip ederek oku.",
    "saglik": "Alternatif aci: bunu bir hasta notu gibi dusunup ana bulgu ve yorumu ayir.",
    "spor": "Alternatif aci: bunu skor tablosu gibi dusunup kritik satiri once oku.",
    "yemek": "Alternatif aci: bunu tarif yerine kontrol listesi gibi okuyup temel iki adimi sec.",
    "oyun": "Alternatif aci: bunu gorev zinciri gibi dusunup hangi adimin kilidi actigina bak.",
    "film": "Alternatif aci: bunu sahne ozeti gibi dusunup ana olay ve yan detayi ayir.",
}


def _api_error_payload(*, detail: str, error_code: str = "", field_errors: dict | None = None, lang: str = "tr") -> dict:
    translated = t(error_code, lang) if error_code else ""
    detail_text = translated or str(detail or "").strip()
    payload = {
        "detail": detail_text,
        "status_text": detail_text,
    }
    if str(error_code or "").strip():
        payload["error_code"] = str(error_code).strip()
    if field_errors:
        payload["field_errors"] = dict(field_errors)
    return payload


def _answer_status_text(answer_state: str, *, context: str = "evidence") -> str:
    kind = "Aciklama" if context == "explain" else "Kanitli cevap"
    state = str(answer_state or "").strip()
    if state == "answered":
        return f"{kind} hazir."
    if state == "answered_with_weak_evidence":
        return f"{kind} hazir, ancak kanit zayif."
    if state == "insufficient_evidence":
        return "Yeterli kanit bulunamadi."
    if state == "not_in_document":
        return "Dokumanda gecmiyor."
    return f"{kind} hazir."


def _augment_answer_payload(payload: dict) -> dict:
    out = dict(payload or {})
    context = "evidence" if ("answer" in out or "supported" in out or "citations" in out) else "explain"
    dokumanda_yok = bool(out.get("dokumanda_yok"))
    supported = bool(out.get("supported")) if "supported" in out else not dokumanda_yok
    answer_allowed = bool(out.get("answer_allowed")) if "answer_allowed" in out else supported
    weak_evidence = bool(out.get("weak_evidence")) if "weak_evidence" in out else bool(out.get("kaynak_zayif_mi"))
    evidence_strength = str(out.get("evidence_strength") or ("dusuk" if weak_evidence or not answer_allowed else "yuksek")).strip() or "dusuk"
    abstain_reason = str(out.get("abstain_reason") or "").strip()
    kaynak_guveni = str(out.get("kaynak_guveni") or ("dusuk" if weak_evidence or not answer_allowed else "yuksek")).strip() or "dusuk"

    if dokumanda_yok:
        answer_state = "not_in_document"
    elif not answer_allowed:
        answer_state = "insufficient_evidence"
    elif weak_evidence:
        answer_state = "answered_with_weak_evidence"
    else:
        answer_state = "answered"

    warning_code = str(out.get("warning_code") or "").strip()
    if not warning_code:
        if answer_state == "not_in_document":
            warning_code = "document_missing_answer"
        elif answer_state in {"insufficient_evidence", "answered_with_weak_evidence"} or weak_evidence:
            warning_code = "weak_evidence"
        else:
            warning_code = ""

    out["dokumanda_yok"] = dokumanda_yok
    out["supported"] = supported
    out["answer_allowed"] = answer_allowed
    out["weak_evidence"] = weak_evidence
    out["evidence_strength"] = evidence_strength
    out["abstain_reason"] = abstain_reason
    out["kaynak_guveni"] = kaynak_guveni
    out["answer_state"] = answer_state
    out["status_text"] = str(out.get("status_text") or _answer_status_text(answer_state, context=context)).strip()
    out["warning_code"] = warning_code
    return out


def _clean_text(value) -> str:
    """Bosluklari tekillestirip helper'larin ortak kullandigi temiz metni uret."""
    return " ".join(str(value or "").split()).strip()


def _weak_text(value: str, *, min_len: int = 18) -> bool:
    """Kisa veya jenerik gorunen aciklamalari fallback tetigi icin isaretle."""
    clean = _clean_text(value)
    if len(clean) < min_len:
        return True
    lowered = clean.lower()
    return lowered.startswith("bu parca") or lowered.startswith("bu bolum")


def _weak_comment_list(items, *, min_count: int = 2) -> bool:
    """Block/line comment listesi yetersizse fallback zenginlestirmesini tetikler."""
    cleaned = []
    for item in list(items or []):
        text = _clean_text(item)
        if text and text not in cleaned:
            cleaned.append(text)
    return len(cleaned) < min_count


def _safe_theme(value: str) -> str:
    """Tema tercihini izinli sabitlere indirger; bilinmeyenleri varsayilana duser."""
    clean = _clean_text(value).lower()
    return clean if clean in _ALLOWED_THEMES else _DEFAULT_THEME


def _get_preference_value(user, field_name: str) -> str:
    """Tercihi once relation uzerinden, gerekirse fallback model sorgusundan okur."""
    tercih = getattr(user, "doc_tercih", None)
    if tercih is not None:
        return _clean_text(getattr(tercih, field_name, ""))
    if KullaniciTercih is None:
        return ""
    tercih = KullaniciTercih.objects.filter(kullanici=user).first()
    return _clean_text(getattr(tercih, field_name, "")) if tercih is not None else ""


def _build_anlamadim_profile(request) -> dict:
    """Request ve kullanici tercihlerini tek profile birlestirip prompt katmanina hazirlar."""
    request_data = getattr(request, "data", {}) or {}
    tema = _safe_theme(request_data.get("tema") or _get_preference_value(request.user, "tema") or _DEFAULT_THEME)
    tarz = _clean_text(request_data.get("tarz") or _get_preference_value(request.user, "tarz") or "adim_adim") or "adim_adim"
    seviye = _clean_text(request_data.get("seviye") or _get_preference_value(request.user, "seviye") or "orta") or "orta"
    stil = _clean_text(request_data.get("stil") or _get_preference_value(request.user, "ton") or "hoca") or "hoca"
    return {
        "tema": tema,
        "tarz": tarz,
        "seviye": seviye,
        "stil": stil,
    }


def _chunk_kind_from_parca(parca) -> str:
    """Parca meta'sindan tablo, kod veya gorsel gibi explanation odagini cikartir."""
    meta = getattr(parca, "meta", {}) or {}
    adres = str(getattr(parca, "adres", "") or "").lower()
    tur = str(getattr(parca, "tur", "") or "").lower()
    chunk_kind = str(meta.get("chunk_kind") or "").lower()
    if bool(meta.get("ocr")) or tur == "ocr":
        return "image"
    if "table" in chunk_kind or "tablo" in tur or adres.startswith("xlsx:") or ":tablo:" in adres:
        return "table"
    if tur == "kod" or meta.get("format") == "code" or adres.startswith("code:"):
        return "code"
    return ""


def _table_headers(text: str, parca) -> list[str]:
    """Tablo fallback'i icin once meta'dan, yoksa ham metinden gorunen basliklari toplar."""
    meta = getattr(parca, "meta", {}) or {}
    headers = list(meta.get("header_preview") or [])
    if headers:
        return [item for item in headers if _clean_text(item)][:4]
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if lines and lines[0].lower().startswith("basliklar:"):
        return [_clean_text(item) for item in lines[0].split(":", 1)[1].split("|") if _clean_text(item)][:4]
    match = re.search(r"Basliklar:\s*([^\\n]+)", str(text or ""), flags=re.IGNORECASE)
    if match:
        return [_clean_text(item) for item in match.group(1).split("|") if _clean_text(item)][:4]
    return []


def _table_focus_row(text: str) -> str:
    """Tabloda aciklamanin odaklanacagi ornek satiri secmeye calisir."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    for line in lines:
        if line.lower().startswith("satir "):
            return _clean_text(line)
    match = re.search(r"(Satir\s+\d+:\s+[^\\n]+)", str(text or ""), flags=re.IGNORECASE)
    if match:
        return _clean_text(match.group(1))
    return _clean_text(lines[-1]) if lines else ""


def _code_symbol(parca, text: str) -> str:
    """Kod chunk'i icin aciklamada gecmesi gereken ana sembol adini bulur."""
    meta = getattr(parca, "meta", {}) or {}
    symbol = _clean_text(meta.get("code_unit_name") or meta.get("symbol") or meta.get("parent_unit"))
    if symbol:
        return symbol
    first_line = _clean_text(str(text or "").splitlines()[0] if str(text or "").splitlines() else "")
    match = re.search(r"\b(def|class|function)\s+([A-Za-z_][\w]*)", first_line)
    return match.group(2) if match else ""


def _code_lines(text: str) -> list[str]:
    """Bos satirlari ayiklayip kod fallback'lerinin line odakli calismasini kolaylastirir."""
    return [line.rstrip() for line in str(text or "").splitlines() if line.strip()]


def _code_subtype(parca, text: str) -> str:
    """Kod parcasini test, sql, class veya frontend gibi daha anlamli alt turlere ayirir."""
    meta = getattr(parca, "meta", {}) or {}
    code_unit_kind = _clean_text(meta.get("code_unit_kind")).lower()
    language = _clean_text(meta.get("code_language") or meta.get("language")).lower()
    clean = str(text or "")
    first_line = clean.splitlines()[0] if clean.splitlines() else clean
    lower = clean.lower()
    if language == "sql" or re.search(r"^\s*(select|with|insert|update|delete)\b", first_line, flags=re.IGNORECASE):
        return "sql"
    if code_unit_kind in {"class"} or re.search(r"^\s*class\b", first_line, flags=re.IGNORECASE):
        return "class"
    if code_unit_kind in {"test_function", "test_method", "test_step"} or re.search(r"^\s*(?:async\s+)?def\s+test_", first_line, flags=re.IGNORECASE):
        if re.search(r"\b(self\.client\.|client\.(get|post|put|patch|delete)|force_authenticate|APIClient|APITestCase)\b", clean, flags=re.IGNORECASE):
            return "api_test"
        return "test"
    if code_unit_kind in {"method", "python_method"}:
        return "method"
    if language in {"javascript", "typescript", "tsx", "jsx"} or re.search(r"\b(useState|useEffect|set[A-Z][A-Za-z0-9_]*\(|fetch\(|axios\.|return\s*<)", clean):
        return "frontend"
    if "select " in lower and " from " in lower:
        return "sql"
    return "function"


def _special_chunk_payload(parca, text: str) -> dict:
    """Tablo, kod ve gorsel gibi ozel chunk'lar icin kuralli fallback aciklamasi uretir."""
    kind = _chunk_kind_from_parca(parca)
    if not kind:
        return {}
    raw_text = str(text or "")
    text = _clean_text(raw_text)

    meta = getattr(parca, "meta", {}) or {}
    quality_score = float(meta.get("quality_score") or 0.0)
    is_low_evidence = bool(meta.get("weak_content")) or (0.0 < quality_score < 0.25 and quality_score != 0.0)

    if is_low_evidence:
        return {
            "one_liner": "Bu içerik çok kısa veya belirsiz olduğu için net bir anlam çıkarılamadı.",
            "very_simple": "Görünürde yeterli kanıt veya yapısal bütünlük bulunmuyor. Bu parça muhtemelen eksik veya gürültülü bir içeriğe sahip.",
            "steps": [
                "Mevcut kısa veya gürültülü metni incele.",
                "Eksik bağlamı göz önünde bulundur.",
                "Kesin bir yargıya varmaktan kaçın."
            ],
            "examples": ["Görünür kanıt yetersiz olduğundan kesin bir örnek veya kullanım verilemiyor."],
            "trap": "Tuzak: Yetersiz veya parçalı metne dayanarak kesin varsayımlarda bulunmak.",
            "dokumanda_yok": True,
        }

    if kind == "table":
        headers = _table_headers(raw_text, parca)
        focus_row = _table_focus_row(raw_text)
        header_note = ", ".join(headers) if headers else "gorunen sutunlar"
        return {
            "one_liner": f"Bu tablo, veriyi satir ve sutun halinde karsilastirmak icin verilmis.",
            "very_simple": (
                f"Bu tablo ne diyor: ana bilgi {header_note} etrafinda toplanmis. "
                f"Kritik satir veya gorunen veri: {focus_row or 'tablodaki ilk dolu satir'}."
            ),
            "steps": [
                f"Once sutunlara bak: {header_note}.",
                f"Sonra kritik satiri ayir: {focus_row or 'ilk dolu satir'}.",
                "En sonda satir ile sutun iliskisini tek cumlede ozetle.",
            ],
            "examples": [
                f"Tablo yorumu: once {header_note} basliklarini oku, sonra satirdaki degerin ne anlattigini eslestir.",
            ],
            "trap": "Tuzak: sutun basligini gormeden hucreyi tek basina yorumlamak.",
        }
    if kind == "code":
        from .views import _anlamadim_chunk_context, _anlamadim_code_payload

        context = _anlamadim_chunk_context(
            text=raw_text,
            adres=getattr(parca, "adres", "") or "",
            meta=getattr(parca, "meta", {}) or {},
            tur=getattr(parca, "tur", "") or "",
        )
        return _anlamadim_code_payload(raw_text, context)
    ocr_brief = text[:100]
    return {
        "one_liner": "Bu gorsel, metin veya etiket iceren bir goruntu parcasi sunuyor.",
        "very_simple": f"Gorselin ana amaci, gorunen bilgi parcasini hizli gostermek. OCR ozeti: {ocr_brief}.",
        "steps": [
            "Once gorselde hangi ana etiket veya metin gorunuyor onu ayir.",
            "Sonra bu bilginin neyi acikladigini baglamla eslestir.",
            "En sonda OCR metnini tek cumlede yeniden ifade et.",
        ],
        "examples": [
            "Gorsel yorumu: bunu ekran goruntusu veya etiket karti gibi dusun ve ana mesaji bul.",
        ],
        "trap": "Tuzak: OCR ile gelen kisa metni baglam disi kesin yorum gibi okumak.",
    }


def _theme_examples(*, tema: str, parca, text: str, one_liner: str, glossary: list[dict]) -> dict:
    """Tema secimine gore ayni parcayi ikinci bir aciyla anlatan ornek ciftini uretir."""
    theme = _safe_theme(tema)
    meta = getattr(parca, "meta", {}) or {}
    focus = ""
    if glossary and isinstance(glossary[0], dict):
        focus = _clean_text(glossary[0].get("terim"))
    focus = focus or _clean_text(meta.get("chunk_title") or meta.get("baslik") or getattr(parca, "adres", "")) or "bu konu"
    base = _THEME_PATTERNS.get(theme, _THEME_PATTERNS[_DEFAULT_THEME])
    alternative = _ALTERNATIVE_THEME_MAP.get(theme, _ALTERNATIVE_THEME_MAP[_DEFAULT_THEME])
    one_liner = _clean_text(one_liner) or _clean_text(text[:120]) or "ana fikir"
    return {
        "tema_bazli_ornek": f"{base} Burada odak nokta: {focus}. Ana fikir: {one_liner}",
        "alternatif_ornek": f"{alternative} Bu parcada once {focus} ipucunu, sonra ana fikri kontrol et.",
        "theme_source": "request_or_preference" if theme == _safe_theme(tema) else "default",
    }


def _ensure_examples(payload: dict, parca, text: str, tema: str) -> tuple[dict, dict]:
    """Eksik ornek alanlarini ozel chunk ve tema fallback'leriyle tamamlar."""
    result = dict(payload or {})
    meta = {
        "special_chunk_used": False,
        "special_chunk_kind": "",
        "themed_examples_used": False,
        "theme_source": "",
    }
    special = {}
    if modul_acik_mi("DOCVERSE_SPECIAL_CHUNK_FALLBACKS_ENABLED", True):
        special = _special_chunk_payload(parca, text)
        if special:
            if special.get("dokumanda_yok") is True:
                result["dokumanda_yok"] = True
                result["one_liner"] = special["one_liner"]
                result["very_simple"] = special["very_simple"]
                result["steps"] = list(special.get("steps") or [])
                result["examples"] = list(special.get("examples") or [])
                result["trap"] = special.get("trap", "")
                meta["special_chunk_used"] = True
                meta["special_chunk_kind"] = _chunk_kind_from_parca(parca)
            else:
                if _weak_text(result.get("one_liner", ""), min_len=20):
                    result["one_liner"] = special["one_liner"]
                if _weak_text(result.get("very_simple", ""), min_len=28):
                    result["very_simple"] = special["very_simple"]
                    meta["special_chunk_used"] = True
                if len(result.get("steps") or []) < 2 or meta["special_chunk_used"]:
                    result["steps"] = list(special["steps"])
                    meta["special_chunk_used"] = True
                if len(result.get("examples") or []) < 1 or meta["special_chunk_used"]:
                    result["examples"] = list(special["examples"])
                    meta["special_chunk_used"] = True
                if _weak_text(result.get("trap", ""), min_len=18):
                    result["trap"] = special["trap"]
                    meta["special_chunk_used"] = True
                if _weak_text(result.get("function_purpose", ""), min_len=18) and _clean_text(special.get("function_purpose")):
                    result["function_purpose"] = _clean_text(special.get("function_purpose"))
                    meta["special_chunk_used"] = True
                if _weak_text(result.get("flow_summary", ""), min_len=18) and _clean_text(special.get("flow_summary")):
                    result["flow_summary"] = _clean_text(special.get("flow_summary"))
                    meta["special_chunk_used"] = True
                if _weak_comment_list(result.get("block_comments"), min_count=min(2, len(list(special.get("block_comments") or [])) or 1)) and list(special.get("block_comments") or []):
                    result["block_comments"] = [_clean_text(item) for item in (special.get("block_comments") or []) if _clean_text(item)][:4]
                    meta["special_chunk_used"] = True
                if _weak_comment_list(result.get("line_comments"), min_count=min(4, len(list(special.get("line_comments") or [])) or 1)) and list(special.get("line_comments") or []):
                    result["line_comments"] = [_clean_text(item) for item in (special.get("line_comments") or []) if _clean_text(item)][:9]
                    meta["special_chunk_used"] = True
                meta["special_chunk_kind"] = _chunk_kind_from_parca(parca)

    if not modul_acik_mi("DOCVERSE_THEMED_EXAMPLES_ENABLED", True):
        result["tema_bazli_ornek"] = _clean_text(result.get("tema_bazli_ornek"))
        result["alternatif_ornek"] = _clean_text(result.get("alternatif_ornek"))
        return result, meta

    themed = _theme_examples(
        tema=tema,
        parca=parca,
        text=text,
        one_liner=result.get("one_liner", ""),
        glossary=result.get("glossary", []),
    )
    if _weak_text(result.get("tema_bazli_ornek", ""), min_len=24):
        result["tema_bazli_ornek"] = themed["tema_bazli_ornek"]
        meta["themed_examples_used"] = True
    if _weak_text(result.get("alternatif_ornek", ""), min_len=24):
        result["alternatif_ornek"] = themed["alternatif_ornek"]
        meta["themed_examples_used"] = True
    examples = [_clean_text(item) for item in (result.get("examples") or []) if _clean_text(item)]
    for item in (result.get("tema_bazli_ornek"), result.get("alternatif_ornek")):
        clean = _clean_text(item)
        if clean and clean not in examples:
            examples.append(clean)
    result["examples"] = examples[:3]
    meta["theme_source"] = themed["theme_source"]
    return result, meta

def _prompt_evidence_from_canonical_hits(hits: list[dict]) -> list[dict]:
    """Canonical retrieval hit'lerini prompt'un bekledigi yalın evidence sekline cevirir."""
    return [
        {
            "parca_id": hit.get("parca_id"),
            "addr": hit.get("adres", ""),
            "text": hit.get("metin", ""),
            "chunk_kind": hit.get("chunk_kind", ""),
            "format": hit.get("format", ""),
            "code_language": hit.get("code_language", ""),
            "code_unit_kind": hit.get("code_unit_kind", ""),
            "code_unit_name": hit.get("code_unit_name", ""),
            "parent_unit": hit.get("parent_unit", ""),
            "line_start": hit.get("line_start"),
            "line_end": hit.get("line_end"),
            "code_purpose_hints": list(hit.get("code_purpose_hints") or []),
        }
        for hit in hits
    ]


def _allowed_citation_ids_from_hits(hits: list[dict]) -> list[int]:
    """Prompt ve validator katmaninin paylasacagi izinli citation listesini uretir."""
    seen = set()
    out = []
    for hit in hits or []:
        try:
            parca_id = int(hit.get("parca_id"))
        except Exception:
            continue
        if parca_id in seen:
            continue
        seen.add(parca_id)
        out.append(parca_id)
    return out


def _strict_evidence_mode_enabled() -> bool:
    """Guardrail rollout'unu ayardan okuyup citation kurallarini merkezden kontrol eder."""
    return bool(getattr(settings, "AI2_STRICT_EVIDENCE_MODE", True))


def _low_evidence_threshold() -> float:
    """Dusuk kanit kisa-devresinde kullanilan alt guven esigini normalize eder."""
    try:
        return float(getattr(settings, "AI2_LOW_EVIDENCE_THRESHOLD", 0.2))
    except Exception:
        return 0.2


def _should_abstain_for_low_evidence(kanit_meta: dict) -> bool:
    """
    RAG (Retrieval) aşamasından gelen kanıtların yetersiz veya konuyla çok alakasız olduğu durumlarda,
    modelin halüsinasyon görmesini engellemek için LLM'e hiç gitmeden doğrudan ret (abstain) kararı verir.
    """
    secilen_kanitlar = list(kanit_meta.get("secilen_kanitlar") or [])
    retrieval_ozeti = dict(kanit_meta.get("retrieval_ozeti") or {})
    coverage_ratio = float(retrieval_ozeti.get("soru_terim_kapsama_orani") or 0.0)
    retrieval_kalitesi = str(retrieval_ozeti.get("retrieval_kalitesi") or "").strip()
    kaynak_guveni = str(kanit_meta.get("kaynak_guveni") or "dusuk").strip()

    if not secilen_kanitlar:
        return True
    if retrieval_kalitesi == "zayif" and coverage_ratio < _low_evidence_threshold():
        return True
    if kaynak_guveni == "dusuk" and coverage_ratio < _low_evidence_threshold():
        return True
    return False


def _build_low_evidence_abstain_response(kanit_meta: dict) -> dict:
    """Dusuk kanit durumunda response shape'ini bozmadan guvenli abstain payload'i kurar."""
    evidence_payload = build_evidence_response_payload(
        kanit_meta,
        include_kanitlar=False,
    )
    kaynak_durumu = derive_answer_source_state(
        kanit_meta,
        citation_ids=[],
        citation_required=False,
    )
    out = {
        "answer": "Dokümanda geçmiyor.",
        "supported": False,
        "dokumanda_yok": True,
        "citations": [],
        "missing": ["Yeterli kanıt bulunamadı."],
        "followups": [],
        "unsupported_reason": "low_evidence_abstain",
        "coverage_note": "LLM cagrisi oncesi kanit yetersiz bulundu.",
    }
    out.update(evidence_payload)
    out["kullanilan_kanitlar"] = []
    out["kaynak_guveni"] = kaynak_durumu["kaynak_guveni"]
    out["kaynak_zayif_mi"] = True
    out["retrieval_ozeti"] = evidence_payload["retrieval_ozeti"]
    return out


def _record_ai2_eval_metrics(
    *,
    user,
    doc=None,
    used_hits: list[dict] | None = None,
    response_payload: dict | None = None,
    unsupported_reason: str = "",
):
    """Kanitli cevap akisinda no-leak uyumlu eval skorlarini metric store'a yazar."""
    used_hits = list(used_hits or [])
    response_payload = dict(response_payload or {})
    # Response shape'ini bozmadan sadece türetilmiş kalite/metrik sinyalleri hesaplanır.
    confusion_meta = compute_confusion_map_score(
        user=user,
        dokuman=doc,
        parca=None,
    )
    mastery_meta = compute_mastery_score(
        user=user,
        dokuman=doc,
    )
    completeness_score = evaluate_completeness_score(
        response_payload.get("answer", ""),
        [hit.get("metin", "") for hit in used_hits],
    )
    hallucination_meta = evaluate_hallucination_risk(
        citation_ids=response_payload.get("citations", []),
        provided_ids=[hit.get("parca_id") for hit in used_hits if hit.get("parca_id") is not None],
        completeness_score=completeness_score,
        supported=bool(response_payload.get("supported")),
        unsupported_reason=unsupported_reason or response_payload.get("unsupported_reason", ""),
    )
    usefulness_meta = evaluate_usefulness_score_v2(
        completeness_score=completeness_score,
        hallucination_risk=hallucination_meta["hallucination_risk"],
        supported=bool(response_payload.get("supported")),
    )
    # Ham cevap ya da retrieval metni saklanmaz; yalnızca açıklayıcı skor alanları tutulur.
    kaydet_skor_olayi(
        kullanici=user,
        olay_turu="ai2_cevap_degerlendirildi",
        kaynak_modul="ai2.kanitli_cevap",
        dokuman=doc,
        score_map={
            "completeness_score": completeness_score,
            "hallucination_risk": hallucination_meta["hallucination_risk"],
            "usefulness_score_v2": usefulness_meta["usefulness_score_v2"],
            "citation_alignment_score": hallucination_meta["citation_alignment_score"],
            "confusion_map_score": confusion_meta["confusion_map_score"],
            "confusion_reason": confusion_meta["confusion_reason"],
            "confusion_incomplete_ratio": confusion_meta["confusion_incomplete_ratio"],
            "confusion_quiz_fail_ratio": confusion_meta["confusion_quiz_fail_ratio"],
            "confusion_revisit_ratio": confusion_meta["confusion_revisit_ratio"],
            "confusion_high_dwell_ratio": confusion_meta["confusion_high_dwell_ratio"],
            "mastery_score": mastery_meta["mastery_score"],
            "mastery_reason": mastery_meta["mastery_reason"],
            "mastery_quiz_success_ratio": mastery_meta["mastery_quiz_success_ratio"],
            "mastery_usefulness_avg": mastery_meta["mastery_usefulness_avg"],
            "mastery_repeat_penalty": mastery_meta["mastery_repeat_penalty"],
            "unsupported_reason": unsupported_reason or response_payload.get("unsupported_reason", ""),
            "supported": bool(response_payload.get("supported")),
            "fallback_json_kullanildi": bool(response_payload.get("fallback_json_kullanildi")),
            "kaynak_guveni": response_payload.get("kaynak_guveni", ""),
            "abstention_uygulandi_mi": bool(response_payload.get("unsupported_reason") == "low_evidence_abstain"),
        },
        durum="ok" if response_payload.get("supported") else "hata",
    )


def _record_anlamadim_eval_metrics(
    *,
    user,
    parca,
    completeness_meta: dict,
    response_payload: dict,
):
    """Anlamadim response'unun yeterlilik sinyallerini parça bazlı metriclere taşır."""
    completeness_score = float(completeness_meta.get("completeness_score") or 0.0) / 7.0
    confusion_meta = compute_confusion_map_score(
        user=user,
        dokuman=getattr(parca, "dokuman", None),
        parca=parca,
    )
    mastery_meta = compute_mastery_score(
        user=user,
        dokuman=getattr(parca, "dokuman", None),
    )
    usefulness_meta = evaluate_usefulness_score_v2(
        completeness_score=completeness_score,
        hallucination_risk=0.0,
    )
    # Burada da raw explanation yerine sadece score/reason alanları saklanır.
    kaydet_skor_olayi(
        kullanici=user,
        olay_turu="ai2_anlamadim_degerlendirildi",
        kaynak_modul="ai2.anlamadim",
        dokuman=getattr(parca, "dokuman", None),
        parca=parca,
        score_map={
            "completeness_score": completeness_score,
            "usefulness_score_v2": usefulness_meta["usefulness_score_v2"],
            "confusion_map_score": confusion_meta["confusion_map_score"],
            "confusion_reason": confusion_meta["confusion_reason"],
            "confusion_incomplete_ratio": confusion_meta["confusion_incomplete_ratio"],
            "confusion_quiz_fail_ratio": confusion_meta["confusion_quiz_fail_ratio"],
            "confusion_revisit_ratio": confusion_meta["confusion_revisit_ratio"],
            "confusion_high_dwell_ratio": confusion_meta["confusion_high_dwell_ratio"],
            "mastery_score": mastery_meta["mastery_score"],
            "mastery_reason": mastery_meta["mastery_reason"],
            "mastery_quiz_success_ratio": mastery_meta["mastery_quiz_success_ratio"],
            "mastery_usefulness_avg": mastery_meta["mastery_usefulness_avg"],
            "mastery_repeat_penalty": mastery_meta["mastery_repeat_penalty"],
            "fallback_json_kullanildi": bool(response_payload.get("fallback_json_kullanildi")),
            "supported": not bool(response_payload.get("dokumanda_yok")),
        },
        durum="ok",
    )


def _merge_anlamadim_with_fallback(
    normalized_obj: dict,
    *,
    parca,
    text: str,
    tema: str,
    tarz: str,
    seviye: str,
    quiz_required: bool = True,
) -> tuple[dict, dict, bool, dict]:
    """
    Eksik, kalitesiz veya standart dışı AI2 Anlamadım çıktısını kurallı fallback (kurtarma)
    verisiyle yamalar, zenginleştirir ve son eksiklik analizini yapar.
    """
    analiz_once = analyze_anlamadim_completeness(normalized_obj, quiz_required=quiz_required)
    normalized_result = dict(analiz_once["normalized"])
    fallback_used = False

    if not analiz_once["yeterli_mi"]:
        # Mevcut kural tabanli fallback motorunu sadece eksik/zayif alanlari toparlamak icin kullaniyoruz.
        from .views import _merge_with_fallback_common

        normalized_result, _merge_analiz = _merge_with_fallback_common(
            dict(normalized_result),
            text,
            tema,
            tarz,
            seviye,
        )
        fallback_used = True

    normalized_result, enrichment_meta = _ensure_examples(
        normalized_result,
        parca=parca,
        text=text,
        tema=tema,
    )
    analiz_sonra = analyze_anlamadim_completeness(normalized_result, quiz_required=quiz_required)
    return normalized_result, analiz_sonra, fallback_used, enrichment_meta


def get_parca_for_user(parca_id: int, user):
    """Parca'yi kullanici sahipligiyle arar; model farkliliklarinda kontrollu fallback uygular."""
    if Parca is None:
        return None

    # 1) dokuman__owner üzerinden dene
    try:
        return Parca.objects.select_related("dokuman").filter(id=parca_id, dokuman__owner=user).first()
    except FieldError:
        pass

    # 2) owner alanı varsa
    try:
        return Parca.objects.filter(id=parca_id, owner=user).first()
    except Exception as exc:
        logger.debug("Owned parca lookup failed for parca_id=%s error_type=%s", parca_id, type(exc).__name__)
        return None


def get_doc_parcalar_for_user(doc_id: int, user, limit: int = 80):
    """Dokumana ait parcalari retrieval katmaninin bekledigi sade liste formatinda dondurur."""
    # 1) Dokuman owner kontrolü
    doc = None
    try:
        doc = Dokuman.objects.filter(id=doc_id, owner=user).first()
    except Exception as exc:
        logger.debug("Owned doc lookup failed for doc_id=%s error_type=%s", doc_id, type(exc).__name__)
        doc = None

    if not doc:
        return None, []

    # Parçaları çek
    try:
        qs = doc.parcalar.all()
    except Exception:
        try:
            qs = Parca.objects.filter(dokuman_id=doc.id)
        except Exception:
            qs = Parca.objects.none()

    qs = qs.order_by("id")[:limit]
    parcalar = []
    for p in qs:
        addr = getattr(p, "adres", "") or getattr(p, "addr", "") or ""
        text = getattr(p, "metin", "") or getattr(p, "text", "") or ""
        parcalar.append({"parca_id": p.id, "addr": addr, "text": text})
    return doc, parcalar


def _evidence_log(message: str, **fields):
    parts = [str(message or "").strip()]
    for key, value in fields.items():
        parts.append(f"{key}={value}")
    logger.info(" ".join(part for part in parts if part))


def _evidence_snippet_text(value: str, limit: int = 320) -> str:
    clean = " ".join(str(value or "").split()).strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit].rsplit(" ", 1)[0].strip() + "..."


def _evidence_snippets_from_hits(hits) -> list[dict]:
    snippets = []
    for hit in list(hits or [])[:5]:
        if isinstance(hit, dict):
            text = hit.get("snippet") or hit.get("metin") or hit.get("text") or ""
            addr = str(hit.get("adres") or hit.get("addr") or hit.get("path") or "").strip()
            part_id = hit.get("parca_id") or hit.get("part_id")
            score = hit.get("score") if hit.get("score") is not None else hit.get("skor")
        else:
            text = getattr(hit, "metin", "") or getattr(hit, "text", "") or ""
            addr = str(getattr(hit, "adres", "") or getattr(hit, "addr", "") or "").strip()
            part_id = getattr(hit, "id", None)
            score = 0.0
        snippet = _evidence_snippet_text(text)
        if not snippet:
            continue
        snippets.append(
            {
                "text": snippet,
                "snippet": snippet,
                "source": addr,
                "path": addr,
                "adres": addr,
                "part_id": part_id,
                "parca_id": part_id,
                "score": float(score or 0.0),
                "skor": float(score or 0.0),
            }
        )
    return snippets


def _evidence_empty_response(question: str, warning: str | None = None, *, lang: str = "tr") -> dict:
    warning = warning or t("evidence_empty", lang)
    return _augment_answer_payload(
        {
            "question": question,
            "soru": question,
            "answer": "",
            "cevap": "",
            "snippets": [],
            "evidence": [],
            "kanitlar": [],
            "kanit_snippet": [],
            "source": "empty",
            "warning": warning,
            "dokumanda_yok": True,
            "answer_allowed": False,
            "weak_evidence": True,
        }
    )


def _evidence_fallback_response(question: str, snippets: list[dict], *, warning: str | None = None, lang: str = "tr") -> dict:
    if not snippets:
        return _evidence_empty_response(question, lang=lang)
    text = str(snippets[0].get("text") or snippets[0].get("snippet") or "").strip()
    answer = t("fallback_answer_prefix", lang) + _evidence_snippet_text(text, limit=220)
    return _augment_answer_payload(
        {
            "question": question,
            "soru": question,
            "answer": answer,
            "cevap": answer,
            "snippets": snippets,
            "evidence": snippets,
            "kanitlar": [
                {"parca_id": item.get("parca_id"), "adres": item.get("adres"), "score": item.get("score")}
                for item in snippets
            ],
            "kanit_snippet": [
                {"parca_id": item.get("parca_id"), "adres": item.get("adres"), "snippet": item.get("text")}
                for item in snippets
            ],
            "source": "fallback",
            "warning": warning or t("fallback_warning", lang),
            "dokumanda_yok": False,
            "answer_allowed": True,
            "weak_evidence": True,
        }
    )


def _evidence_ai_response(question: str, answer: str, snippets: list[dict], *, lang: str = "tr") -> dict:
    clean_answer = str(answer or "").strip()
    if not clean_answer:
        return _evidence_fallback_response(question, snippets, lang=lang)
    return _augment_answer_payload(
        {
            "question": question,
            "soru": question,
            "answer": clean_answer,
            "cevap": clean_answer,
            "snippets": snippets,
            "evidence": snippets,
            "kanitlar": [
                {"parca_id": item.get("parca_id"), "adres": item.get("adres"), "score": item.get("score")}
                for item in snippets
            ],
            "kanit_snippet": [
                {"parca_id": item.get("parca_id"), "adres": item.get("adres"), "snippet": item.get("text")}
                for item in snippets
            ],
            "source": "ai",
            "warning": "",
            "dokumanda_yok": False,
            "answer_allowed": True,
            "weak_evidence": False,
        }
    )


class KanitliCevapAI2APIView(APIView):
    """AI2 kanitli cevap akisini retrieval, guardrail ve grounding ile yurutur."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [EvidenceThrottle]

    def _safe_post(self, request):
        started_at = time.monotonic()
        response_lang = get_request_lang(request)
        response_language_instruction = language_instruction(response_lang)
        learning_preferences = resolve_preferences(request.user, request.data or {})
        preference_prompt = build_preference_prompt(learning_preferences, response_lang)
        question = (request.data.get("question") or request.data.get("soru") or "").strip()
        doc_id = request.data.get("doc_id") or request.data.get("document_id")
        part_id = request.data.get("part_id") or request.data.get("parca_id")

        def _with_personalization(payload, sample_text=""):
            payload["personalization"] = learning_preferences
            themed = themed_example_for_text(sample_text or question, learning_preferences.get("theme"), response_lang)
            payload["themed_examples"] = [themed] if themed else []
            return payload

        _evidence_log(
            "EVIDENCE started",
            question_len=len(question),
            doc_id=doc_id or "",
            part_id=part_id or "",
        )

        if not question:
            return Response(
                _api_error_payload(
                    detail="question zorunlu",
                    error_code="question_required",
                    field_errors={"question": ["Bu alan zorunludur."]},
                    lang=response_lang,
                ),
                status=400,
            )

        try:
            top_k = int(request.data.get("top_k") or 5)
        except (TypeError, ValueError):
            top_k = 5
        top_k = max(1, min(top_k, 10))

        evidence = request.data.get("evidence")
        doc = None
        standardized_ev = []
        try:
            _evidence_log("retrieval_started")
            if isinstance(evidence, list) and evidence:
                raw_evidence = []
                for item in evidence:
                    if not isinstance(item, dict):
                        continue
                    text = str(item.get("text") or item.get("snippet") or item.get("metin") or "").strip()
                    if not text:
                        continue
                    raw_evidence.append(
                        {
                            "parca_id": item.get("parca_id") or item.get("part_id") or 0,
                            "addr": str(item.get("addr") or item.get("adres") or item.get("path") or ""),
                            "text": text,
                        }
                    )
                if not raw_evidence:
                    return Response(
                        _api_error_payload(
                            detail="evidence boş/bozuk",
                            error_code="validation_error",
                            field_errors={"evidence": ["Gecersiz evidence listesi."]},
                            lang=response_lang,
                        ),
                        status=400,
                    )
                candidate_meta = prepare_evidence_candidates(
                    raw_evidence,
                    retrieval_kaynagi="ai2.request_evidence",
                    varsayilan_dokuman_id=None,
                )
                standardized_ev = list(candidate_meta.get("aday_kanitlar") or [])
            else:
                if not doc_id:
                    return Response(
                        _api_error_payload(
                            detail="doc_id veya evidence vermelisin",
                            error_code="document_required",
                            field_errors={"doc_id": ["Bu alan zorunludur."]},
                            lang=response_lang,
                        ),
                        status=400,
                    )
                try:
                    doc_id_int = int(doc_id)
                except (TypeError, ValueError):
                    return Response(
                        _api_error_payload(
                            detail="Geçerli doküman bulunamadı.",
                            error_code="validation_error",
                            field_errors={"doc_id": ["Geçerli doküman bulunamadı."]},
                            lang=response_lang,
                        ),
                        status=400,
                    )
                doc, parcalar = get_doc_parcalar_for_user(doc_id_int, request.user, limit=120)
                _evidence_log("EVIDENCE validation", has_doc=bool(doc))
                if not doc:
                    return Response(
                        _api_error_payload(
                            detail="Geçerli doküman bulunamadı.",
                            error_code="resource_not_found",
                            field_errors={"doc_id": ["Geçerli doküman bulunamadı."]},
                            lang=response_lang,
                        ),
                        status=404,
                    )
                if part_id:
                    try:
                        part_id_int = int(part_id)
                    except (TypeError, ValueError):
                        return Response(
                            _api_error_payload(
                                detail="Geçersiz parça.",
                                error_code="validation_error",
                                field_errors={"part_id": ["Geçersiz parça."]},
                                lang=response_lang,
                            ),
                            status=400,
                        )
                    if not any(int(p.get("parca_id") or 0) == part_id_int for p in parcalar):
                        return Response(
                            _api_error_payload(
                                detail="Parça bu dokümana ait değil.",
                                error_code="validation_error",
                                field_errors={"part_id": ["Parça bu dokümana ait değil."]},
                                lang=response_lang,
                            ),
                            status=400,
                        )
                    parcalar = [p for p in parcalar if int(p.get("parca_id") or 0) == part_id_int]

                source_rows = [
                    (p["parca_id"], p.get("addr", ""), p.get("text", ""))
                    for p in parcalar
                    if str(p.get("text") or "").strip()
                ]
                if not source_rows:
                    _evidence_log("retrieval_done", snippet_count=0)
                    payload = _with_personalization(_evidence_empty_response(question, lang=response_lang))
                    _evidence_log("response_source=empty")
                    return Response(payload, status=200)
                standardized_ev = retrieve_evidence_standardized(
                    question,
                    source_rows,
                    dokuman_id=doc.id,
                    limit=top_k,
                )

            try:
                kanit_meta = orchestrate_evidence_selection(
                    question,
                    standardized_ev,
                    answer_limit=max(1, min(2, len(standardized_ev) or 1)),
                    dokuman_filtresi_var_mi=bool(doc_id),
                    varsayilan_dokuman_id=getattr(doc, "id", None),
                )
                hits = list(kanit_meta.get("secilen_kanitlar") or kanit_meta.get("kanitlar") or standardized_ev)
            except Exception as exc:
                _evidence_log("retrieval_error", error_type=type(exc).__name__)
                hits = standardized_ev

            snippets = _evidence_snippets_from_hits(hits)
            _evidence_log("retrieval_done", snippet_count=len(snippets))
            if not snippets:
                payload = _with_personalization(_evidence_empty_response(question, lang=response_lang))
                _evidence_log("response_source=empty")
                return Response(payload, status=200)
        except Exception as exc:
            _evidence_log("retrieval_error", error_type=type(exc).__name__)
            payload = _with_personalization(_evidence_empty_response(question, lang=response_lang))
            _evidence_log("response_source=empty")
            return Response(payload, status=200)

        try:
            _evidence_log("ai_started")
            messages = build_kanitli_prompt(
                question,
                [
                    {
                        "parca_id": item.get("parca_id"),
                        "addr": item.get("path") or item.get("adres") or "",
                        "text": item.get("text") or item.get("snippet") or "",
                    }
                    for item in snippets[:3]
                ],
                allowed_citation_ids=[item.get("parca_id") for item in snippets if item.get("parca_id") is not None],
                strict_evidence=_strict_evidence_mode_enabled(),
                language_instruction=f"{response_language_instruction}\n{preference_prompt}".strip(),
            )
            raw = _run_evidence_ai_chat_with_deadline(
                messages,
                max_tokens=min(ai2_scope_icin_max_token("QA"), _EVIDENCE_AI_MAX_TOKENS),
            )
            try:
                obj = extract_json(raw) or {}
                answer = str(obj.get("answer") or obj.get("cevap") or raw or "").strip()
            except Exception as exc:
                _evidence_log("ai_error fallback_used", error_type=f"json_{type(exc).__name__}")
                answer = str(raw or "").strip()
            if not answer:
                raise RuntimeError("empty_ai_answer")
            elapsed = round(time.monotonic() - started_at, 2)
            _evidence_log("ai_success", elapsed_sec=elapsed)
            payload = _with_personalization(
                _evidence_ai_response(question, answer, snippets, lang=response_lang),
                answer,
            )
            _evidence_log("response_source=ai")
            return Response(payload, status=200)
        except EvidenceAITimeoutError:
            _evidence_log("ai_error fallback_used", error_type="timeout")
            payload = _with_personalization(_evidence_fallback_response(question, snippets, lang=response_lang))
            _evidence_log("response_source=fallback")
            return Response(payload, status=200)
        except Exception as exc:
            _evidence_log("ai_error fallback_used", error_type=type(exc).__name__)
            payload = _with_personalization(_evidence_fallback_response(question, snippets, lang=response_lang))
            _evidence_log("response_source=fallback")
            return Response(payload, status=200)

    def post(self, request):
        try:
            return self._safe_post(request)
        except Exception as exc:
            logger.exception("EVIDENCE unhandled_safe_response error_type=%s", type(exc).__name__)
            question = (request.data.get("question") or request.data.get("soru") or "").strip()
            response_lang = get_request_lang(request)
            return Response(
                _evidence_empty_response(
                    question,
                    warning=t("evidence_failed", response_lang),
                    lang=response_lang,
                ),
                status=200,
            )

        """
        Body seçenekleri:
        A) { "question": "...", "doc_id": 1, "top_k": 5 }
        B) { "question": "...", "evidence": [{"parca_id":33,"addr":"...","text":"..."}] }
        """
        question = (request.data.get("question") or "").strip()
        if not question:
            return Response(
                _api_error_payload(
                    detail="question zorunlu",
                    error_code="validation_error",
                    field_errors={"question": ["Bu alan zorunludur."]},
                ),
                status=400,
            )

        top_k = int(request.data.get("top_k") or 5)

        # 1. ADIM: İstemci tarafından zorunlu olarak verilen 'evidence' varsa onu kullan, 
        # yoksa verilen 'doc_id' üzerinden otomatik RAG araması (retrieval) yap.
        evidence = request.data.get("evidence")
        if isinstance(evidence, list) and evidence:
            # Istemci kaniti geldiginde once onu normalize edip ayni canonical yuzeye indiriyoruz.
            ev = []
            for e in evidence:
                try:
                    ev.append({
                        "parca_id": int(e.get("parca_id")),
                        "addr": str(e.get("addr", "")),
                        "text": str(e.get("text", "")),
                    })
                except Exception:
                    continue
            if not ev:
                return Response(
                    _api_error_payload(
                        detail="evidence boş/bozuk",
                        error_code="validation_error",
                        field_errors={"evidence": ["Gecersiz evidence listesi."]},
                    ),
                    status=400,
                )
            candidate_meta = prepare_evidence_candidates(
                ev,
                retrieval_kaynagi="ai2.request_evidence",
                varsayilan_dokuman_id=None,
            )
            standardized_ev = candidate_meta["aday_kanitlar"]
        else:
            doc_id = request.data.get("doc_id")
            if not doc_id:
                return Response(
                    _api_error_payload(
                        detail="doc_id veya evidence vermelisin",
                        error_code="validation_error",
                        field_errors={"doc_id": ["Bu alan zorunludur."]},
                    ),
                    status=400,
                )

            doc, parcalar = get_doc_parcalar_for_user(int(doc_id), request.user, limit=120)
            if not doc:
                return Response(
                    _api_error_payload(detail="Doküman yok", error_code="resource_not_found"),
                    status=404,
                )

            evidence_doc_id = doc.id
            # Request'te kanit yoksa retrieval bu dokumana bagli kontrollu evidence listesini kurar.
            standardized_ev = retrieve_evidence_standardized(
                question,
                [
                    (p["parca_id"], p.get("addr", ""), p.get("text", ""))
                    for p in parcalar
                ],
                dokuman_id=doc.id,
                limit=max(1, min(top_k, 10)),
            )

        evidence_doc_id = doc.id if "doc" in locals() and doc is not None else None
        allowed_citation_ids = _allowed_citation_ids_from_hits(standardized_ev)
        evidence_ids = set(allowed_citation_ids)
        on_kanit_meta = orchestrate_evidence_selection(
            question,
            standardized_ev,
            answer_limit=max(1, min(2, len(standardized_ev) or 1)),
            dokuman_filtresi_var_mi=bool(request.data.get("doc_id")),
            varsayilan_dokuman_id=evidence_doc_id,
        )

        # 2. ADIM: Düşük kanıt güvenliğinde, LLM'e gitmeden önce işlemi kes ve kontrollü ret (abstain) dön.
        if _should_abstain_for_low_evidence(on_kanit_meta):
            low_evidence_out = _build_low_evidence_abstain_response(on_kanit_meta)
            _record_ai2_eval_metrics(
                user=request.user,
                doc=doc if "doc" in locals() else None,
                used_hits=[],
                response_payload=low_evidence_out,
                unsupported_reason="low_evidence_abstain",
            )
            return Response(_augment_answer_payload(low_evidence_out), status=200)

        # 3. ADIM: Katı (strict) yönlendirmelere sahip kanıtlı cevap LLM prompt'unu oluştur.
        response_lang = get_request_lang(request)
        messages = build_kanitli_prompt(
            question,
            _prompt_evidence_from_canonical_hits(standardized_ev),
            allowed_citation_ids=allowed_citation_ids,
            strict_evidence=_strict_evidence_mode_enabled(),
            language_instruction=language_instruction(response_lang),
        )

        # 4. ADIM: Yapay zeka modeliyle konuş ve gelen yanıtın doğruluğunu/şeklini doğrula (validation).
        try:
            raw = chat(messages, max_tokens=ai2_scope_icin_max_token("QA"))
            obj = extract_json(raw)
            out = validate_kanitli(
                obj,
                evidence_ids,
                strict_evidence=_strict_evidence_mode_enabled(),
            )
        except Exception:
            out = {
                "answer": "Dokümanda geçmiyor.",
                "supported": False,
                "dokumanda_yok": True,
                "citations": [],
                "missing": [],
                "followups": [],
                "unsupported_reason": "ai2_exception",
                "coverage_note": "",
            }

        # 5. ADIM: Modelin seçtiği kanıt referansları ile gerçek veritabanı kanıtlarını eşleştir (grounding).
        # Modelin secimleri yeniden orkestre edilerek response'a sadece gercek ve izinli kanitlar tasinir.
        model_selected_ids = list(out.get("citations") or [])
        kanit_meta = orchestrate_evidence_selection(
            question,
            standardized_ev,
            answer_limit=max(1, len(model_selected_ids) or min(2, len(standardized_ev) or 1)),
            dokuman_filtresi_var_mi=bool(request.data.get("doc_id")),
            forced_parca_idleri=model_selected_ids if model_selected_ids else [],
            varsayilan_dokuman_id=evidence_doc_id,
        )
        kullanilan_kanitlar = kanit_meta["secilen_kanitlar"]
        evidence_payload = build_evidence_response_payload(
            kanit_meta,
            include_kanitlar=False,
        )
        kullanilan_parca_idleri = evidence_payload["kullanilan_parca_idleri"]
        kullanilan_kanit_idleri = evidence_payload["kullanilan_kanit_idleri"]
        kullanilan_adresler = evidence_payload["kullanilan_adresler"]
        retrieval_ozeti = evidence_payload["retrieval_ozeti"]
        kaynak_durumu = derive_answer_source_state(
            kanit_meta,
            citation_ids=model_selected_ids,
            citation_required=True,
        )
        kaynak_guveni = kaynak_durumu["kaynak_guveni"]
        kaynak_zayif_mi = bool(
            kaynak_durumu["kaynak_zayif_mi"]
            or not kullanilan_kanitlar
        )

        if not model_selected_ids or not kullanilan_kanitlar:
            out["supported"] = False
            out["citations"] = []
            out["answer"] = "Dokümanda geçmiyor."
        else:
            out["citations"] = list(kullanilan_parca_idleri)
            out["answer"] = ground_answer_text(
                out.get("answer"),
                kullanilan_kanitlar,
                kaynak_zayif_mi=kaynak_zayif_mi,
            )

        out.update(evidence_payload)
        out["kullanilan_kanitlar"] = list(evidence_payload.get("kullanilan_kanitlar") or [])
        out["kaynak_guveni"] = kaynak_guveni
        out["kaynak_zayif_mi"] = kaynak_zayif_mi
        out["retrieval_ozeti"] = retrieval_ozeti
        out["dokumanda_yok"] = not bool(out.get("supported"))
        _record_ai2_eval_metrics(
            user=request.user,
            doc=doc if "doc" in locals() else None,
            used_hits=kullanilan_kanitlar,
            response_payload=out,
            unsupported_reason=out.get("unsupported_reason", ""),
        )
        return Response(_augment_answer_payload(out), status=200)


class AnlamadimAI2APIView(APIView):
    """AI2 anlamadim cevabini profile, kalite sinyallerine ve fallback'lere gore uretir."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ExplainThrottle]

    def post(self, request, parca_id: int):
        """
        Body:
        { "tema":"oyun|teknoloji|yemek|spor|film", "seviye":"baslangic|orta|ileri", "stil":"kanka|hoca|teknik|sunum" }
        """
        p = get_parca_for_user(int(parca_id), request.user)
        if not p:
            return Response(
                _api_error_payload(detail="Parça yok", error_code="resource_not_found"),
                status=404,
            )

        addr = getattr(p, "adres", "") or getattr(p, "addr", "") or ""
        text = getattr(p, "metin", "") or getattr(p, "text", "") or ""

        # Prompt profiline kalite, zorluk ve chunk turu sinyallerini tek yerde ekliyoruz.
        profile = _build_anlamadim_profile(request)
        response_lang = get_request_lang(request)
        profile["response_language"] = response_lang
        profile["language_instruction"] = language_instruction(response_lang)
        quiz_gate = build_mini_quiz_gate(parca=p, text=text)
        record_quiz_readiness_event(user=request.user, parca=p, gate_meta=quiz_gate)
        profile["quality_score"] = float(((getattr(p, "meta", None) or {}).get("quality_score")) or 0.0)
        profile["difficulty_score"] = float(((getattr(p, "meta", None) or {}).get("difficulty_score")) or getattr(p, "zorluk_skoru", 0.0) or 0.0)
        profile["weak_content"] = bool(((getattr(p, "meta", None) or {}).get("weak_content")))
        profile["chunk_kind"] = _chunk_kind_from_parca(p)
        profile["chunk_title"] = _clean_text(
            ((getattr(p, "meta", None) or {}).get("chunk_title"))
            or ((getattr(p, "meta", None) or {}).get("baslik"))
            or addr
        )
        profile["language"] = _clean_text(
            ((getattr(p, "meta", None) or {}).get("code_language"))
            or ((getattr(p, "meta", None) or {}).get("language"))
            or ""
        )
        profile["line_start"] = int((((getattr(p, "meta", None) or {}).get("line_start")) or 0) or 0)
        profile["line_end"] = int((((getattr(p, "meta", None) or {}).get("line_end")) or 0) or 0)
        code_unit_kind = _clean_text((((getattr(p, "meta", None) or {}).get("code_unit_kind")) or ""))
        profile["code_unit_kind"] = code_unit_kind
        profile["code_unit_name"] = _clean_text((((getattr(p, "meta", None) or {}).get("code_unit_name")) or ((getattr(p, "meta", None) or {}).get("symbol")) or ""))
        profile["test_step_kind"] = _clean_text((((getattr(p, "meta", None) or {}).get("test_step_kind")) or ((getattr(p, "meta", None) or {}).get("code_step_kind")) or ""))
        profile["code_purpose_hints"] = [str(item).strip() for item in (((getattr(p, "meta", None) or {}).get("code_purpose_hints")) or []) if str(item).strip()][:4]
        if profile["chunk_kind"] == "code":
            if code_unit_kind in {"test_function", "test_method", "test_step"}:
                if re.search(r"\b(self\.client\.|api_client\.|client\.(get|post|put|patch|delete)|force_authenticate|APIClient|APITestCase)\b", text, flags=re.IGNORECASE):
                    profile["code_subtype"] = "api_test"
                else:
                    profile["code_subtype"] = "test"
            elif code_unit_kind in {"method", "python_method"}:
                profile["code_subtype"] = "method"
            elif code_unit_kind == "class":
                profile["code_subtype"] = "class"
            elif profile["language"] == "sql":
                profile["code_subtype"] = "sql"
            elif profile["language"] in {"javascript", "typescript", "tsx", "jsx"}:
                profile["code_subtype"] = "frontend"
            elif code_unit_kind == "script_block":
                profile["code_subtype"] = "script"
            elif profile["language"] in {"css", "scss", "less"} or code_unit_kind in {"style_rule", "style_block"}:
                profile["code_subtype"] = "style"
            elif profile["language"] in {"html", "xml"} or code_unit_kind == "markup_block":
                profile["code_subtype"] = "markup"
            elif profile["language"] in {"json", "yaml", "yml"} or code_unit_kind in {"config_entry", "section"}:
                profile["code_subtype"] = "config"
            elif profile["language"] in {"powershell", "bash", "sh"} or code_unit_kind in {"shell", "command", "api_call"}:
                profile["code_subtype"] = "shell"
            else:
                profile["code_subtype"] = "function"
        profile["quiz_gate_meta"] = quiz_gate
        profile["quiz_readiness_score"] = quiz_gate["quiz_readiness_score"]
        profile["quiz_reason"] = quiz_gate["quiz_reason"]
        profile["mini_quiz_aktif"] = quiz_gate["quiz_eligible"]

        messages = build_anlamadim_prompt(addr, text, p.id, profile)

        try:
            raw = chat(messages, max_tokens=ai2_scope_icin_max_token("ANLAMADIM"))
            obj = extract_json(raw)
            normalized_obj = normalize_anlamadim_payload(obj)
            # AI cevabi eksikse kuralli fallback motoru sadece gerekli alanlari tamamlar.
            normalized_obj, completeness_meta, fallback_used, enrichment_meta = _merge_anlamadim_with_fallback(
                normalized_obj,
                parca=p,
                text=text,
                tema=profile["tema"],
                tarz=profile["tarz"],
                seviye=profile["seviye"],
                quiz_required=quiz_gate["quiz_eligible"],
            )
            out = validate_anlamadim(normalized_obj, p.id, quiz_required=quiz_gate["quiz_eligible"])
            if fallback_used:
                out["fallback_json_kullanildi"] = True
            if not completeness_meta["yeterli_mi"]:
                out["completeness_score"] = completeness_meta["completeness_score"]
                out["eksik_alanlar"] = list(completeness_meta["eksik_alanlar"])
            if not quiz_gate["quiz_eligible"]:
                out["mini_test"] = []
        except Exception:
            # Model cevabi bozulsa bile shape ve acceptance cizgisi fallback payload ile korunur.
            normalized_obj, completeness_meta, fallback_used, enrichment_meta = _merge_anlamadim_with_fallback(
                {},
                parca=p,
                text=text,
                tema=profile["tema"],
                tarz=profile["tarz"],
                seviye=profile["seviye"],
                quiz_required=quiz_gate["quiz_eligible"],
            )
            out = validate_anlamadim(normalized_obj, p.id, quiz_required=quiz_gate["quiz_eligible"])
            if fallback_used:
                out["fallback_json_kullanildi"] = True
            if not completeness_meta["yeterli_mi"]:
                out["completeness_score"] = completeness_meta["completeness_score"]
                out["eksik_alanlar"] = list(completeness_meta["eksik_alanlar"])
            if not quiz_gate["quiz_eligible"]:
                out["mini_test"] = []

        if enrichment_meta.get("themed_examples_used"):
            kaydet_skor_olayi(
                kullanici=request.user,
                olay_turu="themed_example_generated",
                kaynak_modul="ai2.anlamadim",
                dokuman=getattr(p, "dokuman", None),
                parca=p,
                score_map={
                    "tema": profile["tema"],
                    "mod": enrichment_meta.get("theme_source") or "themed_examples",
                    "secilen_parca_sayisi": 1,
                },
                durum="ok",
            )
        if enrichment_meta.get("special_chunk_used"):
            kaydet_skor_olayi(
                kullanici=request.user,
                olay_turu="special_chunk_fallback_used",
                kaynak_modul="ai2.anlamadim",
                dokuman=getattr(p, "dokuman", None),
                parca=p,
                score_map={
                    "format": enrichment_meta.get("special_chunk_kind") or "generic",
                    "mod": "special_chunk_fallback",
                    "secilen_parca_sayisi": 1,
                },
                durum="ok",
            )

        record_mini_quiz_event(
            user=request.user,
            parca=p,
            gate_meta=quiz_gate,
            generated_count=len(out.get("mini_test") or []),
        )
        _record_anlamadim_eval_metrics(
            user=request.user,
            parca=p,
            completeness_meta=completeness_meta,
            response_payload=out,
        )
        return Response(_augment_answer_payload(out), status=200)


class MiniQuizResultAPIView(APIView):
    """Mini quiz sonucunu kaydedip kabul etkisini mastery/confusion metriklerine yansitir."""
    permission_classes = [IsAuthenticated]

    def post(self, request, parca_id: int):
        """Mini quiz sonucunu kaydedip acceptance etkisini ogrenme metriklerine dagitir."""
        if not modul_acik_mi("DOCVERSE_QUIZ_ENABLED", True):
            return Response({"detail": "Quiz modulu devre disi."}, status=404)

        p = get_parca_for_user(int(parca_id), request.user)
        if not p:
            return Response({"detail": "Parça yok"}, status=404)

        serializer = QuizResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dogru_sayisi = int(serializer.validated_data["dogru_sayisi"])
        toplam_soru = int(serializer.validated_data["toplam_soru"])
        sonuc_orani = round(float(dogru_sayisi) / max(toplam_soru, 1), 4)
        previous_mastery = compute_mastery_score(
            user=request.user,
            dokuman=getattr(p, "dokuman", None),
        )["mastery_score"]
        previous_confusion = compute_confusion_map_score(
            user=request.user,
            dokuman=getattr(p, "dokuman", None),
            parca=p,
        )["confusion_map_score"]

        # Sonuç hem acceptance olayına hem de öğrenme çıktılarına aynı oranla taşınır.
        kaydet_skor_olayi(
            kullanici=request.user,
            olay_turu="mini_quiz_sonuclandi",
            kaynak_modul="ai2.mini_quiz",
            dokuman=getattr(p, "dokuman", None),
            parca=p,
            score_map={
                "dogru_sayisi": dogru_sayisi,
                "toplam_soru": toplam_soru,
                "sonuc_orani": sonuc_orani,
            },
            durum="ok",
        )
        # Acceptance kaydı ile cooldown/öğrenme çıktıları aynı transaction benzeri niyetle peş peşe işlenir.
        enqueue_quiz_acceptance_event(
            user=request.user,
            parca=p,
            dogru_sayisi=dogru_sayisi,
            toplam_soru=toplam_soru,
            sonuc_orani=sonuc_orani,
        )
        mark_quiz_cooldown(user=request.user, parca=p, action="completed")
        record_learning_outcome_events(
            user=request.user,
            dokuman=getattr(p, "dokuman", None),
            parca=p,
            previous_mastery_score=previous_mastery,
            previous_confusion_score=previous_confusion,
            sonuc_orani=sonuc_orani,
            boss_kill=False,
        )
        mastery_meta = compute_mastery_score(
            user=request.user,
            dokuman=getattr(p, "dokuman", None),
        )
        return Response(
            {
                "ok": True,
                "parca_id": p.id,
                "dogru_sayisi": dogru_sayisi,
                "toplam_soru": toplam_soru,
                "sonuc_orani": sonuc_orani,
                "mastery_score": mastery_meta["mastery_score"],
            },
            status=200,
        )
