"""
Doküman Asistanı projesinin temel doküman yükleme, parçalama (ingestion), klasik RAG aramaları
ve çeşitli analiz/ürün panellerini (Dashboard, KPI, Feedback, Notlar vb.) sunan ana view modülüdür.
"""

from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.apps import apps
from django.shortcuts import get_object_or_404
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import logging
import os
import re
import json
import urllib.error
import urllib.request
import zipfile

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status

from .models import (
    Dokuman,
    Parca,
    Profil,
    Not,
    OdulLog,
    KullaniciTercih,
    DokumanNotu,
    AnlamadimKaydi,
    KullaniciGeriBildirim,
)
from .serializers import (
    DokumanSerializer,
    DokumanNotuSerializer,
    ParcaSerializer,
    ProfilSerializer,
    NotSerializer,
    KullaniciTercihSerializer,
)

from dokuman.ai2.llm import (
    ai2_scope_icin_max_token,
    chat,
    llm_tamamla,
    son_chat_debug_bilgisi_al,
    yerel_modeli_al,
)
from dokuman.ai2.prompts import build_anlamadim_prompt
from dokuman.ai2.validators import extract_json

from .services.answerer import kanitli_cevap_uret, tanim_var_mi
from .services.llm_prompts import prompt_bunu_anlamadim, prompt_kanitli_sor
from .services.parsers import parcala, mime_tahmin
from .services.chunker import chunkla
from .services.retrieval import en_alakali
from .services.tutor import anlamadim_cevap
from .services.boss import boss_uret
from .services.anlamadim_engine import build_anlamadim_payload, build_hardest_parts_payload
from .services.ingestion import dokumani_parcala_ve_kaydet, supported_upload_extensions
from dokuman.config.file_types import (
    DOCVERSE_ARCHIVE_EXTENSIONS,
    DOCVERSE_BLOCKED_EXTENSIONS,
    DOCVERSE_OCR_EXTENSIONS,
    DOCVERSE_PARSE_SUPPORTED_EXTENSIONS,
    PARSER_NOT_AVAILABLE_DETAIL,
    category_for_extension,
    normalize_extension,
)
from .services.code_structure import _sql_line_clause_slices
from dokuman.services.heading_parser import parse_document_structure
from dokuman.i18n import get_request_lang, t
from dokuman.services.ocr import (
    is_image_ext,
    gorseli_ocr_ile_parcala_ve_kaydet,
    extract_text_from_image,
    split_text_into_chunks,
)
from dokuman.serializers import (
    BossRushPanelSerializer,
    BossResultSerializer,
    ConceptDetailSerializer,
    ConceptGraphSerializer,
    ConceptSurfaceSerializer,
    ConceptFusionRequestSerializer,
    ConceptFusionSerializer,
    ExcelModesSerializer,
    EscapeRoomSerializer,
    EscapeRoomUpdateSerializer,
    ExportManifestV2Serializer,
    ExportReadinessPanelSerializer,
    ConfusionHotspotAnalyticsSerializer,
    ConfusionMapSurfaceSerializer,
    DashboardSummarySerializer,
    DirectorsCutSerializer,
    ExportPlanSerializer,
    FeedbackAnalyticsV2Serializer,
    KPIPanelSerializer,
    KullaniciGeriBildirimSerializer,
    LearningKPISerializer,
    LearningPanelSerializer,
    LearningModesPanelSerializer,
    MasteryFeedbackTrustAnalyticsSerializer,
    PuzzleRuntimeSerializer,
    PortalNoteStudyPanelSerializer,
    PremiumPayloadsSerializer,
    PersonalizationHintsSerializer,
    QuizRouletteSerializer,
    QuizReadinessRequestSerializer,
    QuizBossProductAnalyticsSerializer,
    ReelsSurfaceSerializer,
    RewardPanelSerializer,
    BossReadinessSerializer,
    SelfCheckRuntimeRequestSerializer,
    SelfCheckRuntimeSerializer,
    SpeedrunCompletionSerializer,
    SpeedrunRuntimeSerializer,
    StyleConsoleSerializer,
    WeeklyProgressReportSerializer,
    PersonalizationConfidenceSerializer,
    WeeklyProgressPanelSerializer,
    AchievementProgressSerializer,
    XPVisibilityPanelSerializer,
    RealExportSerializer,
)
from dokuman.services.concept_product_surface import build_concept_graph_payload
from dokuman.services.concept_runtime import (
    build_concept_detail_payload,
    build_concept_surface_payload,
)
from dokuman.services.concepts import (
    build_concept_relations,
    concept_definition_fallback,
    extract_concepts_from_text,
    find_concept_mentions,
    normalize_concept,
)
from .services.rag import (
    build_retrieval_ozeti,
    upsert_dokuman_parcalari,
    search_rag,
    search_rag_with_auto_index,
    search_rag_with_auto_index_meta,
)
from .services.evidence_orchestrator import (
    build_evidence_response_payload,
    derive_answer_source_state,
    orchestrate_evidence_selection,
)
from .services.kanitli_qa import ground_answer_text
from dokuman.ai2.prompts import build_anlamadim_prompt
from dokuman.services.boss_runtime import (
    build_boss_payload,
    build_boss_rush_payload,
    boss_runtime_enabled,
    record_boss_attempt_event,
    record_boss_candidate_event,
    record_boss_start_event,
    record_learning_outcome_events,
    select_boss_candidates,
)
from dokuman.services.feedback_store import kaydet_geri_bildirim
from dokuman.services.feature_flags import modul_acik_mi
from dokuman.services.metric_store import (
    compute_boss_difficulty_score,
    compute_boss_progress_score,
    compute_confusion_map_score,
    compute_mastery_score,
    compute_study_summary_importance_score,
    compute_quiz_readiness_score,
    guvenli_metrik_kaydi_olustur,
    kaydet_skor_olayi,
)
from dokuman.services.product_analytics import (
    build_confusion_map_surface,
    build_confusion_hotspot_analytics,
    build_dashboard_summary,
    build_feedback_analytics_v2,
    build_kpi_panel,
    build_learning_kpi,
    build_learning_panel,
    build_mastery_feedback_trust_analytics,
    build_portal_note_study_panel,
    build_quiz_boss_surface,
    build_xp_visibility_panel,
)
from dokuman.services.quiz_runtime import (
    compute_runtime_quiz_readiness,
    mark_quiz_cooldown,
    record_quiz_prompt_event,
)
from dokuman.services.directors_cut import build_directors_cut_payload
from dokuman.services.escape_room_runtime import (
    build_escape_room_payload,
    escape_room_runtime_enabled,
    record_escape_room_event,
)
from dokuman.services.excel_modes import build_excel_mode_payload
import dokuman.services.export_manifest_v2 as export_manifest_v2
import dokuman.services.product_panels as product_panels
import dokuman.services.achievement_runtime as achievement_runtime
from dokuman.services.export_planner import build_export_plan_payload
from dokuman.services.fusion_runtime import build_concept_fusion_payload
from dokuman.services.learning_modes_panel import build_learning_modes_panel
from dokuman.services.puzzle_runtime import (
    build_puzzle_payload,
    puzzle_runtime_enabled,
    record_puzzle_event,
)
from dokuman.services.premium_payloads import build_premium_payload
from dokuman.services.personalization_hints import build_personalization_hints_payload
from dokuman.services.reels_surface import build_reels_surface_payload
from dokuman.services.roulette_runtime import (
    build_quiz_roulette_payload,
    record_roulette_events,
    roulette_runtime_enabled,
)
from dokuman.services.reward_panel import build_reward_panel
from dokuman.services.speedrun_runtime import (
    build_speedrun_payload,
    record_speedrun_completed,
    record_speedrun_generated,
    speedrun_runtime_enabled,
)
from dokuman.services.style_console import build_style_console_payload
from dokuman.services.remix import (
    SUPPORTED_REMIX_STYLES,
    build_remix_prompt,
    fallback_remix_response,
    normalize_source,
    parse_ai_remix_response,
    source_from_part_text,
)
from dokuman.services.directors_cut_runtime import (
    SUPPORTED_DIRECTORS_CUT_TYPES,
    build_directors_cut_prompt,
    fallback_directors_cut_response,
    parse_ai_directors_cut_response,
)
from dokuman.services.personalization import (
    build_preference_prompt,
    build_preferences_response,
    get_user_preferences,
    personalization_enabled,
    resolve_preferences,
    save_user_preferences,
    themed_example_for_text,
)
from dokuman.services.study_summary import build_study_summary_payload
from dokuman.services.self_check_runtime import evaluate_self_check
from dokuman.services.weekly_report import build_weekly_progress_report
import urllib.error
import urllib.request
from django.conf import settings
from pathlib import Path
from django.conf import settings
from dokuman.services.ocr import (
    is_image_ext,
    extract_text_from_image,
    split_text_into_chunks,
)
from .throttles import ExplainThrottle, EvidenceThrottle, NotesWriteThrottle, UploadThrottle
from dokuman.services.difficulty import calculate_part_difficulty, difficulty_label_from_score

logger = logging.getLogger(__name__)
_AI2_FAST_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="docverse-ai2-fast")


def chroma_search(*args, **kwargs):
    # Eski test/monkeypatch yuzeyi icin geri uyumluluk sarmali.
    return search_rag_with_auto_index(*args, **kwargs)


def _build_bulk_from_heading_parser(doc):
    """
    PDF/DOCX dosyasını başlık-hiyerarşi parser'ı ile okuyup
    Parca bulk listesi üretir.
    """
    ext = Path(doc.dosya.name).suffix.lower()

    if ext not in {".pdf", ".docx"}:
        raise ValueError(f"Heading parser bu uzantıyı desteklemiyor: {ext}")

    parsed = parse_document_structure(doc.dosya.path)
    sections = parsed.get("sections") or []

    bulk = []
    sira = 1

    for sec in sections:
        title = (sec.get("title") or "").strip()
        content = (sec.get("content") or "").strip()

        if title and content:
            parca_metin = f"{title}\n\n{content}".strip()
        else:
            parca_metin = (title or content).strip()

        if not parca_metin:
            continue

        bulk.append(
            Parca(
                dokuman=doc,
                sira=sira,
                metin=parca_metin,
                # modelinde varsa açabilirsin:
                # baslik=title,
                # seviye=sec.get("level"),
                # sayfa=sec.get("page_start"),
            )
        )
        sira += 1

    return bulk, parsed


_ANLAMADIM_STOPWORDS = {
    "aciklar", "adim", "adimlar", "ait", "ama", "ana", "ancak", "artik", "asiri", "az",
    "baz", "bazı", "belge", "bir", "birlikte", "biri", "birsey", "bu", "burada", "da",
    "daha", "de", "degil", "dokuman", "gibi", "gore", "gosterir", "hem", "her", "icin",
    "ile", "ilgili", "ise", "kadar", "kisa", "metin", "neden", "net", "olan", "olarak",
    "olur", "olursa", "ornek", "parca", "sadece", "sekilde", "sonra", "temel", "uzerinden",
    "var", "ve", "veya", "yani",
}
_ANLAMADIM_ZAYIF_KALIPLAR = (
    "bu parca basitce sunu soyluyor",
    "kisa bir giris ya da aciklama cumlesi gibi okunabilir",
    "metindeki teknik terim",
    "kisa ozet uretilemedi",
    "basit anlatim uretilemedi",
    "bir sey yapar",
    "bir is yapar",
)
_ANLAMADIM_FIIL_IPUCU_RE = re.compile(
    r"(maktadir|mektedir|yor|yorlar|ir|irler|ar|er|ur|dur|dir|tir|tur|tanimlar|aciklar|anlatir|gosterir|icerir|sunar|vurgular)$",
    re.IGNORECASE,
)
_ANLAMADIM_TERM_DEFS = {
    "API": "API, servislerin birbiriyle nasil konusacagini anlatan arayuz katmanidir.",
    "ATP": "ATP, hucrenin enerji tasiyici molekuludur.",
    "JWT": "JWT, kimlik bilgisini tasiyan token yapisidir.",
    "RLS": "RLS, satir bazinda erisim kontrolu uygulanmasini saglar.",
    "SQL": "SQL, veritabanindan veri cekmek veya filtrelemek icin kullanilan sorgu dilidir.",
    "FOSFAT": "Fosfat bagi, ATP icinde enerji depolayan kimyasal bagdir.",
    "AKTIF": "Aktif tasima, hucrenin enerji kullanarak madde tasimasidir.",
    "DOCX": "DOCX, Word belge formatini ifade eder.",
    "PDF": "PDF, sabit duzende paylasilan belge formatidir.",
    "IF": "IF, kosula gore farkli sonuc ureten Excel fonksiyonudur.",
    "XLOOKUP": "XLOOKUP, tabloda aranan degeri bulup ilgili sonucu getiren Excel fonksiyonudur.",
}
_ANLAMADIM_TABLE_SPLIT_RE = re.compile(r"\s*(?:\||/|;|\n)+\s*")
_ANLAMADIM_THEME_LABELS = {
    "genel": "gunluk hayat",
    "oyun": "oyun gorevi",
    "spor": "antrenman plani",
    "yemek": "tarif akisi",
    "teknoloji": "urun kurulumu",
    "film": "film sahnesi",
    "yazilim": "uygulama akisi",
    "matematik": "cozum adimi",
    "saglik": "takip plani",
}
_ANLAMADIM_ALT_THEME = {
    "genel": "teknoloji",
    "oyun": "spor",
    "spor": "oyun",
    "yemek": "genel",
    "teknoloji": "genel",
    "film": "oyun",
    "yazilim": "genel",
    "matematik": "genel",
    "saglik": "genel",
}


def _hardest_parts_enabled() -> bool:
    """Hardest parts yuzeyinin feature flag ile acik olup olmadigini soyler."""
    return modul_acik_mi("DOCVERSE_HARDEST_PARTS_ENABLED", True)


def _themed_examples_enabled() -> bool:
    """Tema bazli ornek zenginlestirmesinin acik olup olmadigini soyler."""
    return modul_acik_mi("DOCVERSE_THEMED_EXAMPLES_ENABLED", True)


def _special_chunk_fallbacks_enabled() -> bool:
    """Tablo, kod ve gorsel chunk'lara ozel fallback mantiginin aktifligini dondurur."""
    return modul_acik_mi("DOCVERSE_SPECIAL_CHUNK_FALLBACKS_ENABLED", True)


def _anlamadim_norm_text(text: str) -> str:
    """Fallback helper'larinin ortak kullandigi tek satirlik normalize metni uretir."""
    return re.sub(r"\s+", " ", (text or "").replace("\r\n", "\n")).strip()


def _anlamadim_sentences(text: str) -> list[str]:
    """Metni noktalama ve satir kirilimlarina gore okunabilir cumlelere ayirir."""
    clean = (text or "").replace("\r\n", "\n")
    parts = re.split(r"(?<=[.!?])\s+|\n+", clean)
    return [_anlamadim_norm_text(p) for p in parts if _anlamadim_norm_text(p)]


def _anlamadim_is_noise_text(value: str, *, min_len: int = 8) -> bool:
    """Baslik numarasi, yalniz noktalama veya kartta anlamsiz duracak kisa metni eler."""
    clean = _anlamadim_norm_text(value)
    if not clean:
        return True
    stripped = clean.strip(" \t\r\n")
    lowered = stripped.lower()
    if ":" in stripped:
        tail = stripped.split(":", 1)[1].strip()
        if tail and tail != stripped and _anlamadim_is_noise_text(tail, min_len=min_len):
            return True
    if lowered in {"-", ".", "...", "nedir?", "nedir", "n/a", "null", "none"}:
        return True
    if len(stripped) <= 50 and re.fullmatch(r"[a-zçğıöşü0-9\s_-]+\s+nedir\??", lowered):
        return True
    if re.fullmatch(r"[\d\s.,:;()\[\]#/-]+", stripped):
        return True
    if re.fullmatch(r"(?:bolum|bölüm|parca|parça|madde|baslik|başlık)?\s*\d+[.)]?", lowered):
        return True
    if len(stripped) < min_len:
        return True
    return False


def _anlamadim_meaningful_sentences(text: str) -> list[str]:
    return [
        sentence
        for sentence in _anlamadim_sentences(text)
        if not _anlamadim_is_noise_text(sentence, min_len=8)
        and len(_anlamadim_lower_words(sentence)) >= 2
    ]


def _anlamadim_words(text: str) -> list[str]:
    """Terim cikarma ve overlap skorlamasi icin kelime benzeri tokenlari toplar."""
    return re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]+", _anlamadim_norm_text(text))


def _anlamadim_lower_words(text: str) -> list[str]:
    """Stopword ve cok kisa tokenlari atarak anlamli kelime kumesi uretir."""
    words = [w.lower() for w in _anlamadim_words(text)]
    return [w for w in words if len(w) >= 3 and w not in _ANLAMADIM_STOPWORDS]


def _anlamadim_excerpt(text: str, limit: int = 160) -> str:
    """Uzun metni kelime ortasinda bozmadan kisa alinti halinde kirpar."""
    clean = _anlamadim_norm_text(text)
    if len(clean) <= limit:
        return clean
    short = clean[:limit].rsplit(" ", 1)[0].strip()
    return f"{short or clean[:limit].strip()}..."


def _anlamadim_extract_terms(text: str, max_terms: int = 4) -> list[str]:
    """Metinden acronym ve tekrar eden teknik terimleri glossary adayi olarak cikarir."""
    clean = _anlamadim_norm_text(text)
    if not clean:
        return []

    terms: list[str] = []

    # Once tum-buyuk harfli kisaltmalar korunur; bunlar teknik terim olma egilimindedir.
    for match in re.findall(r"\b[A-Z][A-Z0-9]{1,9}\b", clean):
        if match not in terms:
            terms.append(match)

    counts: dict[str, int] = {}
    originals: dict[str, str] = {}
    for raw in _anlamadim_words(clean):
        low = raw.lower()
        if len(low) < 4 or low in _ANLAMADIM_STOPWORDS:
            continue
        counts[low] = counts.get(low, 0) + 1
        originals.setdefault(low, raw)

    for low, _ in sorted(counts.items(), key=lambda item: (-item[1], -len(item[0]), item[0])):
        term = originals[low]
        if term not in terms:
            terms.append(term)
        if len(terms) >= max_terms:
            break

    return terms[:max_terms]


def _anlamadim_term_definition(term: str, text: str) -> str:
    """Terim icin once bilinen tanimi, yoksa metin ici baglamsal cumleyi dondurur."""
    if term.upper() in _ANLAMADIM_TERM_DEFS:
        return _ANLAMADIM_TERM_DEFS[term.upper()]
    for sentence in _anlamadim_sentences(text):
        if term.lower() in sentence.lower():
            return _anlamadim_excerpt(sentence, limit=140)
    return f"Metinde '{term}' kavrami ana fikirle baglantili olarak geciyor."


def _anlamadim_overlap_score(candidate: str, text: str) -> int:
    """Aday aciklamanin kaynak metinle ne kadar ortustugunu hafifce puanlar."""
    cand_words = set(_anlamadim_lower_words(candidate))
    text_words = set(_anlamadim_lower_words(text))
    word_overlap = len(cand_words & text_words)

    cand_digits = set(re.findall(r"\b\d+\b", _anlamadim_norm_text(candidate)))
    text_digits = set(re.findall(r"\b\d+\b", _anlamadim_norm_text(text)))
    digit_overlap = len(cand_digits & text_digits)

    return word_overlap + digit_overlap


def _anlamadim_build_very_simple(text: str, one_liner: str, glossary: list[dict]) -> str:
    clean = _anlamadim_norm_text(text)
    if not clean:
        return "Metin bos oldugu icin basit anlatim uretilemedi."

    cells = _anlamadim_table_cells(text)
    if len(cells) >= 2 and _anlamadim_is_structured_short_piece(text):
        numeric_cells = [cell for cell in cells if _anlamadim_is_numeric_cell(cell)]
        known_terms = [cell.upper() for cell in cells if cell.upper() in _ANLAMADIM_TERM_DEFS]
        labelish_cells = [
            cell for cell in cells
            if re.fullmatch(r"[A-ZÇĞİÖŞÜ0-9_]{3,16}", cell) or cell.upper().startswith("SUTUN")
        ]
        if len(numeric_cells) >= max(2, len(cells) - 1):
            listed = ", ".join(numeric_cells[:4])
            return (
                f"Bu satirda {listed} sayilari yan yana duruyor; sutun basliklari olmadigi icin "
                "bu sayilarin anlami burada kesinlesmiyor."
            )
        if len(labelish_cells) >= 2 and len(labelish_cells) == len(cells):
            listed = ", ".join(labelish_cells[:4])
            return f"Bu satir, {listed} adli kolon basliklarini veren ust satir gibi gorunuyor."
        if len(known_terms) >= 2:
            listed = ", ".join(cells[:4])
            return f"Bu satir, {listed} terimlerini ayni notta birlikte veriyor."

    if clean.endswith("...") and glossary:
        listed_terms = ", ".join(item["terim"] for item in glossary[:3] if item.get("terim"))
        return f"Parca kirpilmis olsa da burada {listed_terms} ile ilgili teknik bir not veriliyor: {one_liner}"

    if "select" in clean.lower():
        terms = [item["terim"] for item in glossary[:3] if item.get("terim")]
        listed_terms = ", ".join(terms) if terms else "teknik terimler"
        return f"Bu kisa notta {listed_terms} ve bir SQL sorgusu birlikte geciyor."

    if glossary:
        listed_terms = ", ".join(item["terim"] for item in glossary[:3] if item.get("terim"))
        if len(_anlamadim_words(clean)) <= 6:
            return f"Bu kisa not, {listed_terms} terimlerini aniyor ve ana fikir olarak sunu soyluyor: {one_liner}"
        return f"Bu metin, {listed_terms} gibi terimlerle su noktayi acikliyor: {one_liner}"

    return f"Bu metnin sade anlami su: {one_liner}"


def _anlamadim_table_cells(text: str) -> list[str]:
    clean = (text or "").replace("\r\n", "\n")
    cells = []
    for part in _ANLAMADIM_TABLE_SPLIT_RE.split(clean):
        part = _anlamadim_norm_text(part.strip(":-"))
        if part:
            cells.append(part)
    return cells


def _anlamadim_is_numeric_cell(cell: str) -> bool:
    return bool(re.fullmatch(r"[\d.,:%+-]+", _anlamadim_norm_text(cell)))


def _anlamadim_is_structured_short_piece(text: str) -> bool:
    clean = _anlamadim_norm_text(text)
    if not clean or len(clean) > 90:
        return False
    if "|" not in clean and "/" not in clean and "\n" not in str(text or "") and ";" not in clean:
        return False
    return len(_anlamadim_table_cells(text)) >= 2


def _anlamadim_build_structured_fallback(text: str):
    if not _anlamadim_is_structured_short_piece(text):
        return None

    cells = _anlamadim_table_cells(text)
    if len(cells) < 2:
        return None

    numeric_cells = [cell for cell in cells if _anlamadim_is_numeric_cell(cell)]
    known_terms = [cell for cell in cells if cell.upper() in _ANLAMADIM_TERM_DEFS]
    labelish_cells = [
        cell for cell in cells
        if re.fullmatch(r"[A-ZÇĞİÖŞÜ0-9_]{3,16}", cell)
        or cell.upper().startswith("SUTUN")
    ]

    glossary = []
    one_liner = ""
    very_simple = ""
    examples = []
    trap = ""

    if len(numeric_cells) >= max(2, len(cells) - 1):
        degerler = ", ".join(numeric_cells[:4])
        one_liner = (
            f"Bu kisa satir, yan yana yazilmis {degerler} gibi sayisal degerler iceriyor; "
            "sutun basliklari olmadigi icin bu sayilarin anlami kesin degil."
        )
        very_simple = _anlamadim_build_very_simple(text, one_liner, [])
        glossary = [
            {"terim": "satir", "tanim": "Bu parca, tek bir veri satiri veya kisa tablo kesiti gibi gorunuyor."},
            {"terim": "sayisal deger", "tanim": f"Parcada {degerler} gibi sayilar var, ama hangi sutuna ait olduklari belli degil."},
            {"terim": "sutun basligi", "tanim": "Bu sayilarin neyi anlattigini kesinlestiren baslik bilgisi bu parcada gorunmuyor."},
        ]
        examples = [
            "Mini yorum: bu bir tablo satiri olabilir, fakat basliklar olmadan sayilarin hangi anlama geldigi tahmin edilmemeli.",
            f"Parcadan gorulen kesin bilgi: {degerler} sayilari ayni satirda birlikte yazilmis.",
        ]
        trap = "Tuzak: Bu sayilari metin disindan fiyat, skor veya miktar diye kesinlestirmeye calismak."
    elif len(labelish_cells) >= 2 and len(labelish_cells) == len(cells):
        etiketler = ", ".join(labelish_cells[:4])
        one_liner = f"Bu satir, tablonun sutun etiketlerini veriyor: {etiketler}."
        very_simple = _anlamadim_build_very_simple(text, one_liner, [])
        glossary = [
            {"terim": etiket, "tanim": f"Tablodaki bir sutun etiketi olarak '{etiket}' yazilmis."}
            for etiket in labelish_cells[:3]
        ]
        examples = [
            "Mini yorum: bu satirdan sonra her sutunun altina ilgili veri yazilmasi beklenir.",
            f"Parcadan gorulen somut bilgi: kolon adlari {etiketler} olarak tanimlanmis.",
        ]
        trap = "Tuzak: Etiket satirini veri satiri sanip kolon adlarini gercek deger gibi okumak."
    elif len(known_terms) >= 2:
        etiketler = ", ".join(cells[:4])
        odak = known_terms[0].upper()
        one_liner = f"Bu kisa satir, {etiketler} gibi teknik terimleri yan yana listeliyor."
        glossary = [
            {"terim": term.upper(), "tanim": _ANLAMADIM_TERM_DEFS[term.upper()]}
            for term in known_terms[:4]
        ]
        very_simple = _anlamadim_build_very_simple(text, one_liner, glossary)
        examples = [
            f"Mini yorum: burada {odak} gibi araclarin veya komutlarin birlikte kullanilacagi ima ediliyor.",
            f"Parcadan gorulen somut bilgi: {etiketler} ayni satirda birlikte yazilmis.",
        ]
        trap = f"Tuzak: '{odak}' terimini diger etiketlerden kopuk okuyup satirin bir liste oldugunu kacirmak."
    else:
        return None

    steps = [
        f"Once satirdaki etiketleri ayir: {', '.join(cells[:4])}.",
        "Sonra bunun veri satiri mi, sutun basligi mi, yoksa teknik terim listesi mi olduguna bak.",
        f"En sonda parcadan cikabilecek kesin bilgiyi tek cumleyle tekrar et: {one_liner}",
    ]
    mini_quiz = _anlamadim_quiz_from_fields(one_liner, very_simple, glossary, steps)

    return {
        "one_liner": one_liner,
        "very_simple": very_simple,
        "glossary": glossary,
        "steps": steps,
        "examples": examples,
        "trap": trap,
        "mini_quiz": mini_quiz,
    }


def _anlamadim_chunk_context(*, text: str = "", adres: str = "", meta: dict | None = None, tur: str = "") -> dict:
    """
    Ham metin, adres yolu ve parça meta verilerini inceleyerek; parçanın tablo, kod, sunum slaytı
    veya görsel (OCR) olup olmadığına dair yapısal (structured) bir bağlam sözlüğü çıkarır.
    """
    meta = dict(meta or {})
    clean_text = _anlamadim_norm_text(text)
    chunk_kind = str(meta.get("chunk_kind") or "").lower()
    format_name = str(meta.get("format") or "").lower()
    tur = str(tur or "").lower()
    adres = str(adres or "").lower()
    kind = "default"

    if any(token in {chunk_kind, format_name, tur} for token in {"table_meta", "table_rows", "table_summary", "xlsx", "tablo", "tablo_meta", "tablo_ozet"}):
        kind = "table"
    elif any(token in {chunk_kind, format_name, tur} for token in {"code", "code_block", "code_comment", "kod"}):
        kind = "code"
    elif any(token in {chunk_kind, format_name, tur} for token in {"pptx", "slide_title", "slide_bullets", "slide_summary", "slide_notes", "slayt", "slayt_baslik", "slayt_ozet", "slayt_not"}):
        kind = "presentation"
    elif any(token in {chunk_kind, format_name, tur} for token in {"ocr", "image", "visual", "gorsel"}):
        kind = "visual"
    elif "xlsx:" in adres or ("|" in clean_text and len(_anlamadim_table_cells(clean_text)) >= 3):
        kind = "table"
    elif "code:" in adres or re.search(r"\b(def|class|return|import|SELECT|function|const)\b", clean_text, re.IGNORECASE):
        kind = "code"
    elif "ocr:" in adres or meta.get("ocr"):
        kind = "visual"

    return {
        "kind": kind,
        "format": format_name or kind,
        "adres": str(adres or ""),
        "baslik": _anlamadim_norm_text(meta.get("baslik") or meta.get("chunk_title") or meta.get("symbol") or ""),
        "sheet": _anlamadim_norm_text(meta.get("sheet") or ""),
        "symbol": _anlamadim_norm_text(meta.get("symbol") or ""),
        "language": _anlamadim_norm_text(meta.get("code_language") or meta.get("language") or ""),
        "code_language": _anlamadim_norm_text(meta.get("code_language") or meta.get("language") or ""),
        "code_unit_kind": _anlamadim_norm_text(meta.get("code_unit_kind") or ""),
        "code_unit_name": _anlamadim_norm_text(meta.get("code_unit_name") or meta.get("symbol") or ""),
        "parent_unit": _anlamadim_norm_text(meta.get("parent_unit") or ""),
        "test_step_kind": _anlamadim_norm_text(meta.get("test_step_kind") or meta.get("code_step_kind") or ""),
        "line_start": int(meta.get("line_start") or 0),
        "line_end": int(meta.get("line_end") or 0),
        "code_purpose_hints": [str(item).strip() for item in list(meta.get("code_purpose_hints") or []) if str(item).strip()][:4],
        "header_preview": [str(item).strip() for item in list(meta.get("header_preview") or meta.get("header_cells") or []) if str(item).strip()][:4],
        "slide_title": _anlamadim_norm_text(meta.get("slide_title") or ""),
        "ocr": bool(meta.get("ocr")),
    }


def _anlamadim_code_first_line(text: str) -> str:
    for line in str(text or "").splitlines():
        clean = line.strip()
        if clean:
            return clean
    return ""


def _anlamadim_code_subtype(text: str, context: dict | None = None) -> str:
    context = dict(context or {})
    clean_text = str(text or "")
    lower = clean_text.lower()
    first_line = _anlamadim_code_first_line(clean_text)
    language = str(context.get("code_language") or context.get("language") or "").lower()
    unit_kind = str(context.get("code_unit_kind") or "").lower()
    symbol = str(context.get("code_unit_name") or context.get("symbol") or "").lower()
    purpose_hints = {str(item).strip().lower() for item in list(context.get("code_purpose_hints") or []) if str(item).strip()}

    if language == "sql" or re.search(r"^\s*(SELECT|INSERT|UPDATE|DELETE|WITH|CREATE|ALTER)\b", first_line, re.IGNORECASE):
        if unit_kind in {"sql_update", "sql_insert", "sql_delete", "sql_create", "sql_alter", "sql_set"} or re.search(r"^\s*(INSERT|UPDATE|DELETE|CREATE|ALTER)\b", first_line, re.IGNORECASE):
            return "sql_update"
        return "sql"
    if unit_kind == "script_block":
        return "script"
    if language == "css" or unit_kind in {"style_block", "style_rule"}:
        return "style"
    if language in {"json", "yaml", "yml"} or unit_kind in {"section", "config_entry"} or "config" in purpose_hints:
        return "config"
    if language in {"html", "htm", "xml"} or unit_kind == "markup_block":
        return "markup"
    if language in {"sh", "bash", "shell", "ps1", "powershell"} or "shell" in purpose_hints or (unit_kind == "command" and "external_call" in purpose_hints):
        return "shell"
    if unit_kind in {"class", "python_class"} or re.search(r"^\s*class\b", first_line):
        return "class"
    if unit_kind in {"method", "python_method"}:
        return "method"
    if unit_kind in {"test_function", "assertion", "test_step"} or symbol.startswith("test_") or re.search(r"^\s*(?:async\s+)?def\s+test_", first_line):
        if any(token in lower for token in ("client.post", "client.get", "client.put", "client.patch", "client.delete", "api_client.", "force_authenticate", "status_code", "response.data")):
            return "api_test"
        return "test"
    if language in {"javascript", "js", "typescript", "ts", "tsx", "jsx"}:
        if unit_kind == "api_call" or any(token in purpose_hints for token in {"event_handler", "state_update", "ui_result", "api_call"}):
            return "frontend"
        if re.search(r"\b(fetch|axios|setstate|usestate|preventdefault|addeventlistener|dispatch\(|return\s*<)\b", lower):
            return "frontend"
        if re.search(r"^\s*class\b", first_line):
            return "class"
        return "script"
    if unit_kind in {"function", "python_function"} or re.search(r"^\s*(?:async\s+)?def\b", first_line):
        return "function"
    if re.search(r"<(?:section|div|form|input|script|style)\b", lower):
        return "markup"
    if re.search(r"^\s*\{", clean_text) or re.search(r"^\s*[A-Za-z0-9_-]+\s*:", first_line):
        return "config"
    return "code"


def _anlamadim_code_role(clean_text: str, symbol: str, context: dict | None = None) -> tuple[str, str]:
    subtype = _anlamadim_code_subtype(clean_text, context)
    if subtype == "class":
        return symbol or "Bu sinif", "sinif sorumlulugu ve state yonetimi"
    if subtype == "method":
        return symbol or "Bu method", "nesne state'ini guncelleme veya ilgili islemi yurutme amaci"
    if subtype == "function":
        return symbol or "Bu fonksiyon", "input(girdi) alip ana islemi yapma ve sonuc dondurme amaci"
    if subtype in {"api_test", "test"}:
        return symbol or "Bu test", "hazirlik, cagri ve dogrulama zincirini kontrol etme amaci"
    if subtype == "sql":
        return symbol or "Bu sorgu", "sorgu amaci"
    return symbol or "Bu kod blogu", "blok amaci"


def _anlamadim_code_critical_names(text: str, symbol: str) -> list[str]:
    names = []
    if symbol:
        names.append(symbol)

    patterns = [
        r"\b(?:def|class|function)\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\b(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)",
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=",
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text or "", flags=re.IGNORECASE):
            clean = _anlamadim_norm_text(match)
            if not clean:
                continue
            if clean.lower() in {"if", "for", "while", "return", "print"}:
                continue
            if clean not in names:
                names.append(clean)
            if len(names) >= 4:
                return names
    return names[:4]


def _anlamadim_code_flow_hint(text: str, context: dict | None = None) -> str:
    clean = str(text or "")
    subtype = _anlamadim_code_subtype(clean, context)
    flow = []
    if subtype in {"api_test", "test"}:
        if re.search(r"\b(force_authenticate|authenticate|login|monkeypatch|mock)\b", clean, re.IGNORECASE):
            flow.append("hazirlik")
        if re.search(r"\b(data|payload|fixture)\s*=", clean, re.IGNORECASE):
            flow.append("veri hazirligi")
        if re.search(r"\.(post|get|put|patch|delete)\s*\(|\brequests\.(get|post|put|patch|delete)\s*\(", clean, re.IGNORECASE):
            flow.append("endpoint cagrisi")
        if re.search(r"\bassert|assertEqual|assertIn|assertTrue|assertFalse\b", clean, re.IGNORECASE):
            flow.append("dogrulama")
        if re.search(r"\brefresh_from_db\b|document\.(status|state)|self\.[a-zA-Z_]+\s*=", clean, re.IGNORECASE):
            flow.append("final state kontrolu")
    elif subtype == "class":
        if re.search(r"\b__init__\b", clean):
            flow.append("ilk durum kurulumu")
        if re.search(r"self\.[A-Za-z_][A-Za-z0-9_]*\s*=", clean):
            flow.append("state guncellemesi")
        if re.search(r"^\s+def\s+", clean, re.MULTILINE):
            flow.append("metot davranisi")
        if re.search(r"\breturn\b", clean):
            flow.append("sonuc uretimi")
    elif subtype in {"function", "method"}:
        flow.append("girdi(input) kabul")
        if re.search(r"\b(if|elif|else)\b", clean):
            flow.append("kosul kontrolu")
        if re.search(r"\b(for|while)\b", clean):
            flow.append("iterasyon")
        if re.search(r"self\.[A-Za-z_][A-Za-z0-9_]*\s*=", clean):
            flow.append("state guncellemesi")
        if re.search(r"\breturn\b", clean):
            flow.append("sonuc dondurme")
    elif subtype == "sql":
        if re.search(r"\bSELECT\b", clean, re.IGNORECASE):
            flow.append("select")
        if re.search(r"\bFROM\b|\bJOIN\b", clean, re.IGNORECASE):
            flow.append("kaynak tablo")
        if re.search(r"\bWHERE\b|\bGROUP BY\b|\bHAVING\b", clean, re.IGNORECASE):
            flow.append("filtreleme")
        if re.search(r"\bUPDATE\b|\bINSERT\b|\bDELETE\b", clean, re.IGNORECASE):
            flow.append("yazma islemi")
    elif subtype == "config":
        flow.extend(["config anahtari", "deger esleme"])
    elif subtype == "markup":
        flow.extend(["yapisal bloklar", "tagler arasi iliski"])
    elif subtype == "style":
        flow.extend(["secici", "gorunum kurali"])
    elif subtype in {"frontend", "script"}:
        flow.extend(["event veya girdi", "islem/cagri", "render veya state sonucu"])
    elif subtype == "shell":
        flow.extend(["komut hazirligi", "kontrol akisi", "komut sonucu"])
    else:
        if re.search(r"\b(if|elif|else|switch|case)\b", clean, re.IGNORECASE):
            flow.append("kosul kontrolu")
        if re.search(r"\b(for|while|foreach)\b", clean, re.IGNORECASE):
            flow.append("veri uzerinde iterasyon")
        if re.search(r"\b(return|yield)\b", clean, re.IGNORECASE):
            flow.append("sonuc uretimi")
    if not flow:
        flow.append("sirali islem akisi")
    deduped = []
    for item in flow:
        if item and item not in deduped:
            deduped.append(item)
    return " -> ".join(deduped[:5])


def _anlamadim_code_line_no(context: dict, relative_line_no: int) -> int:
    start = int((context or {}).get("line_start") or 0)
    if start > 0:
        return start + max(0, relative_line_no - 1)
    return relative_line_no


def _anlamadim_code_line_prefix(context: dict, relative_line_no: int) -> str:
    return f"Satir [satir {_anlamadim_code_line_no(context, relative_line_no)}]:"


def _anlamadim_code_block_prefix(context: dict, start_relative: int, end_relative: int) -> str:
    start_line = _anlamadim_code_line_no(context, start_relative)
    end_line = _anlamadim_code_line_no(context, end_relative)
    if start_line == end_line:
        return f"Blok [satir {start_line}]:"
    return f"Blok [satir {start_line}-{end_line}]:"


def _anlamadim_code_meaningful_lines(text: str) -> list[tuple[int, str]]:
    lines = []
    for index, raw in enumerate(str(text or "").replace("\r\n", "\n").splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped in {"{", "}", ");", "});", "};", "(", ")", "]", "["}:
            continue
        if re.fullmatch(r"</[A-Za-z0-9_-]+>", stripped):
            continue
        lines.append((index, stripped))
    return lines


def _anlamadim_code_api_method(line: str) -> str:
    match = re.search(r"\.(post|get|put|patch|delete)\s*\(", line, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    if re.search(r"\bfetch\s*\(", line, re.IGNORECASE):
        if re.search(r"method\s*:\s*['\"]POST['\"]", line, re.IGNORECASE):
            return "POST"
        return "FETCH"
    match = re.search(r"\b(requests|httpx)\.(get|post|put|patch|delete)\s*\(", line, re.IGNORECASE)
    if match:
        return match.group(2).upper()
    if re.search(r"\b(Invoke-RestMethod|Invoke-WebRequest|curl)\b", line, re.IGNORECASE):
        return "API"
    return "CALL"


def _anlamadim_code_is_api_call(line: str) -> bool:
    return bool(re.search(r"\.(post|get|put|patch|delete)\s*\(|\b(fetch|axios|requests\.|httpx\.|Invoke-RestMethod|Invoke-WebRequest|curl)\b", line, re.IGNORECASE))


def _anlamadim_sql_clause_items(text: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for raw_line in str(text or "").replace("\r\n", "\n").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        slices = _sql_line_clause_slices(raw_line)
        if slices:
            for kind, clause_text in slices:
                clean = _anlamadim_norm_text(clause_text)
                if clean:
                    items.append((kind, clean))
            continue
        if items and stripped not in {"(", ")", ");", ","}:
            prev_kind, prev_text = items[-1]
            items[-1] = (prev_kind, _anlamadim_norm_text("{} {}".format(prev_text, stripped)))
    return items


def _anlamadim_sql_clause_label(kind: str, clause_text: str) -> str:
    upper = _anlamadim_norm_text(clause_text).upper()
    if kind == "sql_with" or upper.startswith("WITH"):
        return "WITH"
    if upper.startswith("GROUP BY"):
        return "GROUP BY"
    if upper.startswith("ORDER BY"):
        return "ORDER BY"
    if upper.startswith(("WHERE", "HAVING", "LIMIT")):
        return upper.split(" ", 1)[0]
    if upper.startswith("FROM"):
        return "FROM"
    if " JOIN" in upper or upper.startswith(("JOIN", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "OUTER JOIN", "CROSS JOIN")):
        return "JOIN"
    if upper.startswith("SELECT"):
        return "SELECT"
    if upper.startswith("SET"):
        return "SET"
    if upper.startswith("INSERT"):
        return "INSERT"
    if upper.startswith("UPDATE"):
        return "UPDATE"
    if upper.startswith("DELETE"):
        return "DELETE"
    if upper.startswith("CREATE"):
        return "CREATE"
    if upper.startswith("ALTER"):
        return "ALTER"
    return str(kind or "").replace("sql_", "").upper() or "CLAUSE"


def _anlamadim_sql_sources(clause_items: list[tuple[str, str]]) -> list[str]:
    names = []
    for _, clause_text in clause_items:
        for pattern in (
            r"\bfrom\s+([A-Za-z_][A-Za-z0-9_.$]*)",
            r"\bjoin\s+([A-Za-z_][A-Za-z0-9_.$]*)",
            r"\binto\s+([A-Za-z_][A-Za-z0-9_.$]*)",
            r"\bupdate\s+([A-Za-z_][A-Za-z0-9_.$]*)",
        ):
            for match in re.findall(pattern, clause_text, flags=re.IGNORECASE):
                clean = _anlamadim_norm_text(match)
                if clean and clean not in names:
                    names.append(clean)
    return names[:4]


def _anlamadim_config_key_purpose(key: str, value: str = "") -> str:
    clean_key = _anlamadim_norm_text(key).lower()
    clean_value = _anlamadim_norm_text(value).lower()
    if clean_key == "<<":
        return "gorunen alias/merge baglantisini"
    if clean_value in {"true", "false"} or any(token in clean_key for token in {"enabled", "disabled", "feature", "flag", "beta"}):
        return "boolean flag ayarini"
    if any(token in clean_key for token in {"url", "host", "base", "endpoint", "api", "origin", "uri", "port"}):
        if clean_value.startswith("/"):
            return "route veya path ayarini"
        return "baglanti ayarini"
    if any(token in clean_key for token in {"token", "secret", "key", "password", "auth", "cert", "ssl", "tls", "cors"}):
        return "guvenlik ayarini"
    if any(token in clean_key for token in {"service", "server", "worker", "client", "logging", "queue", "broker"}):
        return "servis ayarini"
    if any(token in clean_key for token in {"retry", "timeout", "interval", "delay", "threshold", "limit", "max", "min", "ttl", "level"}):
        return "esik/deger ayarini"
    if any(token in clean_key for token in {"env", "environment", "profile", "override", "stage"}):
        return "environment override ayarini"
    if any(token in clean_key for token in {"enabled", "disabled", "feature", "flag"}):
        return "ozellik acma-kapama ayarini"
    if any(token in clean_key for token in {"path", "dir", "file", "folder"}):
        return "yol ayarini"
    if clean_value in {"|", ">"} or clean_value.startswith("&") or clean_value.startswith("*"):
        return "yapisal config baglantisini"
    if "${" in clean_value or re.search(r"%[A-Za-z_][A-Za-z0-9_]*%", clean_value):
        return "environment override ayarini"
    return "ilgili ayari"


def _anlamadim_config_key_label(key: str, value: str = "") -> str:
    clean_value = _anlamadim_norm_text(value).strip(",")
    if not clean_value or clean_value in {"{", "[", "|", ">"} or clean_value.startswith("&"):
        return "section/group"
    purpose = _anlamadim_config_key_purpose(key, value)
    mapping = {
        "gorunen alias/merge baglantisini": "alias/merge baglantisi",
        "boolean flag ayarini": "boolean flag",
        "baglanti ayarini": "baglanti",
        "route veya path ayarini": "route/path",
        "guvenlik ayarini": "guvenlik",
        "servis ayarini": "servis",
        "esik/deger ayarini": "esik/deger",
        "environment override ayarini": "environment override",
        "ozellik acma-kapama ayarini": "ozellik bayragi",
        "yol ayarini": "yol",
        "yapisal config baglantisini": "yapisal baglanti",
        "ilgili ayari": "genel ayar",
    }
    return mapping.get(purpose, "genel ayar")


def _anlamadim_join_labels(labels: list[str]) -> str:
    clean = _anlamadim_unique_texts(labels, limit=5)
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return "{} ve {}".format(clean[0], clean[1])
    return "{} ve {}".format(", ".join(clean[:-1]), clean[-1])


def _anlamadim_config_line_detail(key: str, value: str = "") -> str:
    clean_key = _anlamadim_norm_text(key)
    clean_value = _anlamadim_norm_text(value).strip(",")
    label = _anlamadim_config_key_label(clean_key, clean_value)
    lowered = clean_value.lower()
    if clean_key == "<<":
        return "Bu satir gorunen alias/merge baglantisini isaret eder; gorunmeyen birlesik degeri kesinlestirmez."
    if not clean_value or clean_value in {"{", "[", "|", ">", "&"} or clean_value.startswith("&"):
        return "Bu satir '{}' config anahtarini section/group olarak acip alt ayarlari toplar.".format(clean_key)
    if lowered in {"true", "false"}:
        return "Bu satir '{}' config anahtari icin {} degerini {} olarak belirler.".format(clean_key, label, lowered)
    if "${" in clean_value or re.search(r"%[A-Za-z_][A-Za-z0-9_]*%", clean_value):
        return "Bu satir '{}' config anahtari icin environment override benzeri gorunen degeri baglar.".format(clean_key)
    if clean_value.startswith("/"):
        return "Bu satir '{}' config anahtari icin gorunen route/path degerini tanimlar.".format(clean_key)
    if re.match(r"^https?://", lowered):
        return "Bu satir '{}' config anahtari icin baglanti adresini tanimlar.".format(clean_key)
    if re.match(r"^[0-9.]+$", lowered) and label in {"esik/deger", "boolean flag"}:
        return "Bu satir '{}' config anahtari icin sayisal {} belirler.".format(clean_key, label)
    if clean_value.startswith(("{", "[")):
        return "Bu satir '{}' config anahtari icin ic yapilandirma blogunu baslatir.".format(clean_key)
    if label == "guvenlik":
        return "Bu satir '{}' config anahtari icin guvenlik amacli gorunen degeri tanimlar.".format(clean_key)
    return "Bu satir '{}' config anahtari icin {} rolundeki gorunen degeri tanimlar.".format(clean_key, label)


def _anlamadim_shell_command_name(line: str) -> str:
    text = str(line or "").strip()
    for pattern in (
        r"=\s*(Invoke-RestMethod|Invoke-WebRequest|curl|wget|Invoke-Expression|Start-Process)\b",
        r"^\s*&?\s*(Invoke-RestMethod|Invoke-WebRequest|curl|wget|jq|python|python3|node|npm|git|docker|kubectl|pwsh|bash|sh)\b",
        r"\|\s*([A-Za-z_][\w.-]*)\b",
        r"^\s*([A-Za-z_][\w.-]*)\s+\-",
        r"^\s*([A-Za-z_][\w.-]*)\b",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _anlamadim_code_assert_status_text(line: str) -> str:
    status_match = re.search(r"(?:HTTP_)?(\d{3})", line)
    if not status_match:
        return ""
    return status_match.group(1)


def _anlamadim_code_extract_field_name(line: str) -> str:
    match = re.search(r"\[['\"]([^'\"]+)['\"]\]", line)
    if match:
        return match.group(1)
    match = re.search(r"assertIn\(\s*['\"]([^'\"]+)['\"]", line)
    if match:
        return match.group(1)
    match = re.search(r"\b[A-Za-z_][A-Za-z0-9_]*\.([A-Za-z_][A-Za-z0-9_]*)\b", line)
    if match and match.group(1) not in {
        "post",
        "get",
        "put",
        "patch",
        "delete",
        "append",
        "extend",
        "lower",
        "upper",
        "strip",
        "replace",
        "refresh_from_db",
    }:
        return match.group(1)
    return ""


def _anlamadim_code_extract_compare_value(line: str) -> str:
    match = re.search(r"==\s*['\"]([^'\"]+)['\"]", line)
    if match:
        return match.group(1)
    match = re.search(r"assertEqual\([^,]+,\s*['\"]([^'\"]+)['\"]\)", line)
    if match:
        return match.group(1)
    match = re.search(r"==\s*(\d+)", line)
    if match:
        return match.group(1)
    match = re.search(r"assertEqual\([^,]+,\s*(\d+)\)", line)
    if match:
        return match.group(1)
    return ""


def _anlamadim_unique_texts(items: list[str], *, limit: int) -> list[str]:
    seen = set()
    out = []
    for item in items:
        clean = _anlamadim_norm_text(item)
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def _anlamadim_python_call_name(text: str) -> str:
    match = re.search(r"([A-Za-z_][A-Za-z0-9_\.]*)\s*\(", str(text or ""))
    if not match:
        return ""
    return match.group(1).split(".")[-1]


def _anlamadim_python_return_comment(expr: str) -> str:
    value = str(expr or "").strip()
    if not value:
        return "Bu satir fonksiyonun sonucunu dondurur."
    if re.fullmatch(r"['\"]([^'\"]+)['\"]", value):
        literal = re.sub(r"^['\"]|['\"]$", "", value)
        return f"Bu satir hesaplanan sonucu '{literal}' olarak dondurur."
    if re.search(r"\blen\s*\(", value):
        return "Bu satir islem sonunda olusan guncel eleman sayisini dondurur."
    if re.search(r"\bsum\s*\(", value):
        return "Bu satir biriken degerlerin toplamini hesaplayip dondurur."
    if re.search(r"\.(strip|lower|upper|replace)\(", value):
        return "Bu satir islenmis ve normalize edilmis sonucu dondurur."
    if "self." in value:
        return "Bu satir guncel state uzerinden hesaplanan sonucu dondurur."
    call_name = _anlamadim_python_call_name(value)
    if call_name and call_name not in {"len", "sum"}:
        return f"Bu satir {call_name} cagrisi ile uretilen sonucu dondurur."
    return "Bu satir islenmis sonucu dondurur."


def _anlamadim_python_assignment_comment(line: str) -> str:
    self_match = re.search(r"self\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)", line)
    if self_match:
        attr = self_match.group(1)
        value = self_match.group(2).strip()
        if re.search(rf"\bself\.{attr}\b", value):
            if re.search(r"\+\s*\[|append\(|extend\(", value):
                return f"Bu satir self.{attr} state degisimi yapip yeni veri ekleyerek nesnenin durumunu gunceller."
            return f"Bu satir self.{attr} state degisimi yapip mevcut deger uzerinden yeniden hesaplar."
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            return f"Bu satir {value} girdisini self.{attr} alaninda nesnenin ilk durumu olarak saklar."
        call_name = _anlamadim_python_call_name(value)
        if call_name:
            return f"Bu satir {call_name} sonucunu self.{attr} alanina yazarak state'i gunceller."
        return f"Bu satir self.{attr} alaninda nesnenin state'ini gorunen degerle gunceller."

    assign_match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)", line)
    if not assign_match:
        return ""

    name = assign_match.group(1)
    value = assign_match.group(2).strip()
    if name.lower() in {"data", "payload", "body", "params", "fixture"} and value[:1] in {"{", "["}:
        return "Bu satir API'ye gidecek payload'i veya testte kullanilacak veri yapisini hazirlar."
    if re.search(r"\.(strip|lower|upper|replace)\(", value):
        return f"Bu satir girdiyi sonraki adim icin normalize ederek '{name}' degiskenine alir."
    call_name = _anlamadim_python_call_name(value)
    if call_name and name.lower() in {"response", "result", "output"}:
        return f"Bu satir {call_name} cagrisi sonucunu '{name}' degiskeninde toplar."
    if "(" in value and ")" in value:
        return f"Bu satir helper veya ara islem sonucunu '{name}' degiskeninde toplar."
    if value[:1] in {"{", "["}:
        return f"Bu satir sonraki adimlarda kullanilacak koleksiyonu veya ara veriyi '{name}' degiskeninde saklar."
    return f"Bu satir sonraki adim icin gerekli ara veriyi '{name}' degiskeninde saklar."


def _anlamadim_python_line_comment(line: str, *, subtype: str, context: dict | None = None) -> str:
    stripped = line.strip()
    lower = line.lower()
    field = _anlamadim_code_extract_field_name(line)
    compare_value = _anlamadim_code_extract_compare_value(line)
    status_code = _anlamadim_code_assert_status_text(line)

    if stripped.startswith("class "):
        return "Bu satir sinifin hangi sorumluluk etrafinda toplandigini gosterir."
    if stripped.startswith("def __init__"):
        return "Bu method __init__ ile nesnenin ilk kurulumunu baslatir."
    if stripped.startswith("def "):
        match = re.search(r"def\s+([A-Za-z_][A-Za-z0-9_]*)", stripped)
        method_name = match.group(1) if match else "method"
        if subtype == "class":
            return f"Bu method {method_name} davranisini sinifin gorunen arayuzu olarak tanimlar."
        if subtype == "method":
            return f"Bu method {method_name} icin ana giris noktasini tanimlar."
        return f"Bu fonksiyon {method_name} icin ana giris noktasini tanimlar."
    if re.search(r"\b(force_authenticate|authenticate|login)\b", lower):
        return "Bu satir test istemcisini ilgili kullanici veya rol ile yetkilendirir."
    if re.search(r"\b(monkeypatch\.setattr|mock\.patch|patch\.object)\b", lower):
        return "Bu satir dis bagimliligi sahte davranisla degistirerek testi deterministik hale getirir."
    if re.search(r"^\s*(data|payload|body|params|fixture)\s*=\s*[\{\[]", line, re.IGNORECASE):
        return "Bu satir API'ye gonderilecek payload'i veya beklenen test verisini hazirlar."
    if _anlamadim_code_is_api_call(line):
        method = _anlamadim_code_api_method(line)
        return f"Bu satir endpoint'e {method} istegi atar ve response'u alir."
    if re.search(r"\.append\(", stripped):
        return "Bu satir koleksiyona yeni oge ekleyerek biriken sonucu gunceller."
    if re.search(r"\bassert(In|Contains)\b", line) and field:
        return f"Bu assertion response icinde beklenen '{field}' alaninin uretildigini kontrol eder."
    if status_code and re.search(r"status_code", lower):
        return f"Bu assertion istegin beklenen HTTP {status_code} sonucunu verdigini dogrular."
    if re.search(r"^\s*if\b", line):
        if field and compare_value:
            return f"Bu kosul, alt dogrulamanin hangi kosul saglandiginda calisacagini belirler; burada '{field}' alaninin '{compare_value}' olmasi beklenir."
        return "Bu kosul, hangi dalin calisacagini ve bunun hangi kosul saglandiginda olacagini ayirir."
    if re.search(r"\brefresh_from_db\s*\(", lower):
        return "Bu satir kaydin veritabanindaki guncel durumunu yeniden yukler."
    if re.search(r"\bassert(Equal|True|False)?\b|\bassert\b", line):
        if " and " in lower:
            return "Bu assertion birden fazla alanin birlikte beklenen sonucu verdigini dogrular."
        if field and compare_value and field.lower() == "status":
            return f"Bu assertion yeni kaydin beklenen baslangic durumunun {compare_value.upper()} oldugunu dogrular."
        if field and compare_value:
            return f"Bu assertion response icindeki '{field}' alaninin beklenen '{compare_value}' degerini tasidigini dogrular."
        if field:
            return f"Bu assertion '{field}' alanina dair beklenen sonucu dogrular."
        if "status_code" in lower and status_code:
            return f"Bu assertion istegin beklenen HTTP {status_code} sonucunu verdigini dogrular."
        return "Bu assertion testin beklenen sonucu verdigini dogrular."
    if re.search(r"^\s*return\b", line):
        value = re.sub(r"^\s*return\b", "", line, flags=re.IGNORECASE).strip()
        return _anlamadim_python_return_comment(value)
    if re.search(r"^\s*(for|while)\b", line):
        match = re.search(r"^\s*for\s+(.+?)\s+in\s+(.+?)\s*:\s*$", stripped)
        if match:
            iterable = match.group(2).strip()
            return f"Bu satir {iterable} uzerinde tekrarli islem yapmak icin iterasyonu baslatir."
        return "Bu satir tekrarlanan islemin hangi veri uzerinde calisacagini belirler."
    if re.search(r"\braise\b", line):
        return "Bu satir beklenmeyen durumda hatayi yukselterek akisi durdurur."
    return _anlamadim_python_assignment_comment(line)


def _anlamadim_sql_line_comment(line: str) -> str:
    upper = line.upper()
    if upper.startswith("WITH"):
        return "Bu satir sorgunun once kullanacagi ara sonucu veya CTE adimini tanimlar."
    if upper.startswith("SELECT"):
        return "Bu satir sorgunun hangi kolonlari dondurecegini belirler."
    if upper.startswith("FROM"):
        return "Bu satir sorgunun temel veri kaynagini veya hedef tablosunu gosterir."
    if " JOIN" in upper or upper.startswith("JOIN"):
        return "Bu satir ilgili tablolari gorunen bag ile JOIN ederek birlestirir."
    if upper.startswith("WHERE") or upper.startswith("HAVING"):
        return "Bu satir sonucu gorunen kosula gore filtreler."
    if upper.startswith("GROUP BY"):
        return "Bu satir kayitlari hangi alana gore grupladigini belirtir."
    if upper.startswith("ORDER BY"):
        return "Bu satir sonucun hangi sirada dondugunu belirler."
    if upper.startswith("INSERT"):
        return "Bu satir yeni kaydin hangi tabloya yazilacagini baslatir."
    if upper.startswith("UPDATE"):
        return "Bu satir update statement'inin hedef tabloya yazma amacini baslatir."
    if upper.startswith("DELETE"):
        return "Bu satir hangi kayitlarin silinecegini belirleyen yazma ifadesini baslatir."
    if upper.startswith("SET"):
        return "Bu satir hangi alanlarin guncellenecegini belirtir."
    if upper.startswith("CREATE") or upper.startswith("ALTER"):
        return "Bu satir yapisal SQL degisiminin hangi nesne uzerinde oldugunu tanimlar."
    if upper.startswith("OVER"):
        return "Bu satir window function baglaminin gorunen cercevesini tanimlar."
    return "Bu satir SQL statement'inin ilgili bolumunu tanimlar."


def _anlamadim_frontend_signals(text: str) -> dict:
    clean = str(text or "")
    lower = clean.lower()
    state_calls = re.findall(r"\b(set[A-Z][A-Za-z0-9_]*|dispatch|setState)\(", clean)
    promise_calls = re.findall(r"\.(then|catch|finally)\s*\(", clean, flags=re.IGNORECASE)
    property_assignments = re.findall(r"\b((?:this|[A-Za-z_$][A-Za-z0-9_$]*)\.[A-Za-z_$][A-Za-z0-9_$]*)\s*=", clean)
    return {
        "has_event": bool("addeventlistener" in lower or "preventdefault" in lower or re.search(r"\bevent\b", clean)),
        "has_api": bool(_anlamadim_code_is_api_call(clean)),
        "has_state": bool(state_calls or property_assignments),
        "has_render": bool(re.search(r"\breturn\s*<|\brender[A-Za-z_]*\(", clean)),
        "has_promise": bool(promise_calls),
        "has_callback": bool("=>" in clean or promise_calls),
        "has_condition": bool(re.search(r"^\s*(if|else if|switch)\b", clean, flags=re.IGNORECASE | re.MULTILINE)),
        "has_return": bool(re.search(r"^\s*return\b", clean, flags=re.IGNORECASE | re.MULTILINE)),
        "state_calls": _anlamadim_unique_texts(state_calls, limit=4),
        "property_assignments": _anlamadim_unique_texts(property_assignments, limit=4),
    }


def _anlamadim_frontend_line_comment(line: str) -> str:
    lower = line.lower()
    if re.search(r"^\s*(?:async\s+)?function\b|^\s*(?:const|let|var)\s+[A-Za-z_$][A-Za-z0-9_$]*\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>", line):
        return "Bu satir event, callback veya state akisinin ana handler/fonksiyon girisini tanimlar."
    event_match = re.search(r"addEventListener\(\s*['\"]([^'\"]+)['\"]", line, flags=re.IGNORECASE)
    if event_match:
        return "Bu satir '{}' eventi icin handler baglayarak etkilesim akisini baslatir.".format(event_match.group(1))
    if "preventdefault" in lower:
        return "Bu satir varsayilan form veya event davranisini durdurup kontrolu koda verir."
    promise_match = re.search(r"\.(then|catch|finally)\s*\(", line, flags=re.IGNORECASE)
    if promise_match:
        return "Bu satir promise zincirindeki '{}' adimini ekleyerek asenkron akis sonrasi ne olacagini belirler.".format(promise_match.group(1).lower())
    if _anlamadim_code_is_api_call(line):
        method = _anlamadim_code_api_method(line)
        return f"Bu satir arayuzden {method} tabanli API cagrisi yaparak dis veri akisina baslar."
    if re.search(r"^\s*if\b", line):
        state_match = re.search(r"\b(set[A-Z][A-Za-z0-9_]*|dispatch|setState)\(", line)
        if state_match:
            return "Bu kosul saglanirsa {} ile state guncellemesi yapilir.".format(state_match.group(1))
        if "response.ok" in lower:
            return "Bu kosul API yanitinin uygun oldugu durumda alt state veya callback adimini calistirir."
        return "Bu kosul hangi callback veya UI adiminin calisacagini sinirlar."
    state_match = re.search(r"\b(set[A-Z][A-Za-z0-9_]*|dispatch|setState)\(", line)
    if state_match:
        return "Bu satir {} cagrisi ile arayuz durumunu gunceller.".format(state_match.group(1))
    property_match = re.search(r"\b((?:this|[A-Za-z_$][A-Za-z0-9_$]*)\.[A-Za-z_$][A-Za-z0-9_$]*)\s*=", line)
    if property_match:
        return "Bu satir {} alanina yazarak gorunen nesne/property durumunu gunceller.".format(property_match.group(1))
    if re.search(r"\b(props|state|this)\.[A-Za-z_$][A-Za-z0-9_$]*\b", line):
        return "Bu satir callback veya render kararinda kullanilan mevcut component baglamini okur."
    if re.search(r"\breturn\s*<", line) or re.search(r"\brender[A-Za-z_]*\(", line):
        return "Bu satir gorunen UI veya render sonucunu dondurur."
    if "=>" in line:
        return "Bu satir callback icindeki ara islemi veya event handler mantigini yurutur."
    return "Bu satir event veya callback akisindaki ara islemi yurutur."


def _anlamadim_config_line_comment(line: str) -> str:
    if re.search(r"^\s*[\"']?[A-Za-z0-9_.-]+[\"']?\s*:", line):
        key = re.split(r":", line, maxsplit=1)[0].strip(" \"'")
        value = re.split(r":", line, maxsplit=1)[1].strip() if ":" in line else ""
        return _anlamadim_config_line_detail(key, value)
    if re.search(r"^\s*<<\s*:", line):
        return _anlamadim_config_line_detail("<<", re.split(r":", line, maxsplit=1)[1].strip())
    return "Bu satir config grubu icindeki anahtar-deger iliskisini kurar."


def _anlamadim_markup_role(tag: str, line: str = "") -> str:
    clean_tag = _anlamadim_norm_text(tag).lower()
    lower = line.lower()
    if clean_tag == "main":
        return "ana sayfa iskeletini"
    if clean_tag == "nav":
        return "navigasyon bolumunu"
    if clean_tag == "section":
        return "icerik section'ini"
    if clean_tag == "form":
        return "form blogunu"
    if clean_tag == "label":
        return "alan etiketini"
    if clean_tag == "button":
        return "eylem dugmesini"
    if clean_tag == "a":
        return "baglantiyi"
    if clean_tag == "header":
        return "ust bolumu"
    if clean_tag == "footer":
        return "alt bolumu"
    if clean_tag == "input":
        input_type = re.search(r"type=['\"]([^'\"]+)['\"]", lower)
        if input_type:
            return "{} input alanini".format(input_type.group(1))
        return "input alanini"
    if clean_tag == "style":
        return "style blogunu"
    if clean_tag == "script":
        return "script blogunu"
    return "ilgili HTML etiketini"


def _anlamadim_markup_line_comment(line: str) -> str:
    lower = line.lower()
    if "<form" in lower:
        return "Bu satir form blogunu baslatarak kullanici girdilerinin toplanacagi yapisal alani kurar."
    if "<input" in lower:
        input_type = re.search(r"type=['\"]([^'\"]+)['\"]", lower)
        if input_type:
            return "Bu satir form icindeki {} input alanini tanimlar.".format(input_type.group(1))
        return "Bu satir form icindeki input alanini tanimlar."
    if "<label" in lower:
        return "Bu satir form alaninin ne anlama geldigini gosteren etiketi yerlestirir."
    if "<nav" in lower:
        return "Bu satir sayfa icindeki navigasyon bolumunu ayirir."
    if "<main" in lower:
        return "Bu satir sayfanin ana icerik iskeletini kurar."
    if "<script" in lower:
        return "Bu satir script blogunu ayirarak davranis katmanini markup'tan ayristirir."
    if "<style" in lower:
        return "Bu satir style blogunu ayirarak gorunum kurallarini markup'tan ayristirir."
    if "<section" in lower or "<div" in lower:
        return "Bu satir sayfa iskeletindeki yapisal blogu kurar."
    return "Bu satir sayfa iskeletindeki ilgili etiketi tanimlar."


def _anlamadim_shell_line_comment(line: str) -> str:
    stripped = line.strip()
    if stripped in {"{", "}", ");"}:
        return ""
    lower = line.lower()
    if re.search(r"^\s*function\b", lower):
        func_match = re.search(r"^\s*function\s+([A-Za-z_][A-Za-z0-9_.-]*)", line, flags=re.IGNORECASE)
        if func_match:
            return "Bu satir {} PowerShell fonksiyonunun giris noktasini tanimlar.".format(func_match.group(1))
        return "Bu satir shell fonksiyonunun giris noktasini tanimlar."
    if re.search(r"^\s*\$env:([A-Za-z_][A-Za-z0-9_]*)\s*=", line, flags=re.IGNORECASE):
        env_match = re.search(r"^\s*\$env:([A-Za-z_][A-Za-z0-9_]*)\s*=", line, flags=re.IGNORECASE)
        return "Bu satir sonraki PowerShell komutlarinda kullanilacak {} environment degiskenini ayarlar.".format(env_match.group(1))
    assignment_api_match = re.search(r"^\s*\$?([A-Za-z_][A-Za-z0-9_:-]*)\s*=", line)
    if assignment_api_match and _anlamadim_code_is_api_call(line):
        var_name = assignment_api_match.group(1)
        cmd_name = _anlamadim_shell_command_name(line) or "API"
        return f"Bu satir {cmd_name} ile dis cagri yapip sonucu {var_name} degiskeninde toplar."
    if "|" in line and _anlamadim_code_is_api_call(line):
        cmd_name = _anlamadim_shell_command_name(line) or "komut"
        return f"Bu satir {cmd_name} ile dis cagri yapip ciktisini pipeline boyunca sonraki komuta aktarir."
    if re.search(r"^\s*\$?[A-Za-z_][A-Za-z0-9_:-]*\s*=", line):
        var_match = re.search(r"^\s*\$?([A-Za-z_][A-Za-z0-9_:-]*)\s*=", line)
        var_name = var_match.group(1) if var_match else "degisken"
        return f"Bu satir sonraki komutlarda kullanilacak {var_name} degiskeni hazirlar."
    if _anlamadim_code_is_api_call(line):
        cmd_name = _anlamadim_shell_command_name(line) or "API"
        return f"Bu satir {cmd_name} ile dis endpoint'e veya servise API cagrisi yapar."
    if re.search(r"\bStart-Process\b", line, flags=re.IGNORECASE):
        process_match = re.search(r"\bStart-Process\s+([^\s\}]+)", line, flags=re.IGNORECASE)
        target = process_match.group(1) if process_match else "harici sureci"
        return "Bu satir Start-Process ile {} adimini calistirir.".format(target)
    if re.search(r"^\s*(if|elseif|else|for|foreach|while|switch|case)\b", lower):
        if "start-process" in lower:
            return "Bu kosul saglanirsa sonraki PowerShell adiminda harici surec baslatilir."
        return "Bu satir kabuk betigindeki kontrol akisini yonetir."
    cmd_name = _anlamadim_shell_command_name(line)
    if "|" in line and cmd_name:
        return f"Bu satir pipeline icinde {cmd_name} komutunu calistirarak veri akisina devam eder."
    if cmd_name:
        return f"Bu satir {cmd_name} komutunu calistirarak ilgili adimi ilerletir."
    return "Bu satir komut zincirindeki ilgili adimi calistirir."


def _anlamadim_code_line_comment_text(line: str, *, subtype: str, context: dict | None = None) -> str:
    if subtype in {"api_test", "test", "function", "method", "class"}:
        return _anlamadim_python_line_comment(line, subtype=subtype, context=context)
    if subtype in {"sql", "sql_update"}:
        return _anlamadim_sql_line_comment(line)
    if subtype in {"frontend", "script"}:
        return _anlamadim_frontend_line_comment(line)
    if subtype == "config":
        return _anlamadim_config_line_comment(line)
    if subtype in {"markup", "style"}:
        return _anlamadim_markup_line_comment(line)
    if subtype == "shell":
        return _anlamadim_shell_line_comment(line)
    if re.search(r"^\s*return\b", line):
        return "Bu satir ilgili blogun sonucunu dondurur."
    return ""


def _anlamadim_code_line_comments(text: str, context: dict | None = None) -> list[str]:
    context = dict(context or {})
    subtype = _anlamadim_code_subtype(text, context)
    comments = []
    seen = set()
    for relative_line_no, line in _anlamadim_code_meaningful_lines(text):
        if len(comments) >= 6:
            break
        comment = _anlamadim_code_line_comment_text(line, subtype=subtype, context=context)
        if not comment:
            continue
        key = comment.lower()
        if key in seen:
            continue
        seen.add(key)
        comments.append(f"{_anlamadim_code_line_prefix(context, relative_line_no)} {comment}")
    return comments


def _anlamadim_code_block_comments(text: str, context: dict | None = None) -> list[str]:
    context = dict(context or {})
    subtype = _anlamadim_code_subtype(text, context)
    lines = _anlamadim_code_meaningful_lines(text)
    comments = []

    def add_block(start_line: int, end_line: int, sentence: str):
        item = f"{_anlamadim_code_block_prefix(context, start_line, end_line)} {sentence}"
        if item not in comments:
            comments.append(item)

    if not lines:
        return comments

    if subtype in {"api_test", "test"}:
        auth_lines = [line_no for line_no, line in lines if re.search(r"\b(force_authenticate|authenticate|login|monkeypatch|mock)\b", line, re.IGNORECASE)]
        payload_lines = [line_no for line_no, line in lines if re.search(r"^\s*(data|payload|body|params|fixture)\s*=", line, re.IGNORECASE)]
        helper_lines = [
            line_no for line_no, line in lines
            if "=" in line and "(" in line and ")" in line
            and not _anlamadim_code_is_api_call(line)
            and not re.search(r"\bassert", line, re.IGNORECASE)
            and not re.search(r"\b(monkeypatch|mock|patch\.object)\b", line, re.IGNORECASE)
        ]
        call_lines = [line_no for line_no, line in lines if _anlamadim_code_is_api_call(line)]
        assert_lines = [line_no for line_no, line in lines if re.search(r"\bassert|assertEqual|assertIn|assertTrue|assertFalse\b", line, re.IGNORECASE)]
        nested_lines = [line_no for line_no, line in lines if re.search(r"^\s*(if|elif|else)\b", line)]
        if auth_lines:
            add_block(auth_lines[0], auth_lines[-1], "Bu blok test ortamini kurar; yetki ve dis bagimlilik ayarlarini netlestirir.")
        if helper_lines:
            add_block(helper_lines[0], helper_lines[-1], "Bu blok helper cagrilariyla request veya assertion oncesi ara veriyi hazirlar.")
        if payload_lines:
            add_block(payload_lines[0], payload_lines[-1], "Bu blok API'ye gidecek payload'i veya beklenen test verisini hazirlar.")
        if call_lines:
            add_block(call_lines[0], call_lines[-1], "Bu blok endpoint cagrisi yapip response'u dogrulama asamasina tasir.")
        if assert_lines:
            add_block(assert_lines[0], assert_lines[-1], "Bu blok assertion zinciriyle status, alan ve final state beklentilerini ayri ayri dogrular.")
        if nested_lines:
            add_block(nested_lines[0], nested_lines[-1], "Bu blok kosullu assertion veya ek kontrolun hangi response durumunda calistigini ayirir.")
    elif subtype in {"function", "method"}:
        assign_lines = [line_no for line_no, line in lines if "=" in line and "==" not in line]
        branch_lines = [line_no for line_no, line in lines if re.search(r"^\s*(if|elif|else|for|while)\b", line)]
        helper_lines = [
            line_no for line_no, line in lines
            if "=" in line and "(" in line and ")" in line and not _anlamadim_code_is_api_call(line)
        ]
        return_lines = [line_no for line_no, line in lines if re.search(r"^\s*return\b", line)]
        if assign_lines:
            add_block(assign_lines[0], assign_lines[min(len(assign_lines) - 1, 1)], "Bu blok temel akis icin girdiyi veya ara veriyi hazirlar.")
        if helper_lines:
            add_block(helper_lines[0], helper_lines[-1], "Bu blok helper veya ara islem sonucunu ana akis icin hazirlar.")
        if branch_lines:
            add_block(branch_lines[0], branch_lines[-1], "Bu blok kosul veya dongu ile hangi dalin sonucu degistirdigini netlestirir.")
        if return_lines:
            add_block(return_lines[0], return_lines[-1], "Bu blok islenmis verinin hangi noktada sonuca donustugunu gosterir.")
    elif subtype == "class":
        init_lines = [line_no for line_no, line in lines if "__init__" in line]
        method_lines = [line_no for line_no, line in lines if re.search(r"^\s*def\s+", line) and "__init__" not in line]
        state_update_lines = [line_no for line_no, line in lines if re.search(r"self\.[A-Za-z_][A-Za-z0-9_]*\s*=\s*self\.", line)]
        if init_lines:
            add_block(init_lines[0], init_lines[-1], "Bu blok sinifin ilk durumunu ve kurulumunu tanimlar.")
        if method_lines:
            add_block(method_lines[0], method_lines[-1], "Bu blok sinifin davranisini metotlar uzerinden tanimlar.")
        if state_update_lines:
            add_block(state_update_lines[0], state_update_lines[-1], "Bu blok sinif state'inin hangi satirlarda anlamli bicimde guncellendigini gosterir.")
    elif subtype in {"sql", "sql_update"}:
        add_block(lines[0][0], lines[-1][0], "Bu blok SQL statement'inin clause akisini, filtrelerini ve gorunen amacini birlikte tanimlar.")
    elif subtype == "frontend":
        add_block(lines[0][0], lines[-1][0], "Bu blok event, API cagrisi ve arayuz state sonucunu ayni akis icinde toplar.")
    elif subtype == "script":
        add_block(lines[0][0], lines[-1][0], "Bu blok script akisinda event/callback, API veya DOM etkisini gorunen satirlarla ayirir.")
    elif subtype == "config":
        add_block(lines[0][0], lines[-1][0], "Bu blok birbiriyle iliskili config ayarlarini ayni grup altinda toplar.")
    elif subtype == "markup":
        add_block(lines[0][0], lines[-1][0], "Bu blok sayfa iskeletini ve onemli HTML alt bloklarini kurar.")
    elif subtype == "style":
        add_block(lines[0][0], lines[-1][0], "Bu blok secici ve gorunen style kurallarini ayni gorunum amacinda toplar.")
    elif subtype == "shell":
        add_block(lines[0][0], lines[-1][0], "Bu blok degisken hazirligi, komut cagrisi ve kontrol akisina ait adimlari toplar.")

    return comments[:3]


def _anlamadim_code_steps(text: str, context: dict | None = None) -> list[str]:
    subtype = _anlamadim_code_subtype(text, context)
    if subtype in {"api_test", "test"}:
        return [
            "Hazirlik: test ortamini, yetkiyi ve gerekiyorsa mock/monkeypatch ayarlarini ayir.",
            "Input: API'ye gidecek payload veya test verisinin ne oldugunu belirle.",
            "Cagri: endpoint veya helper cagrisi ile asil davranisin nerede tetiklendigini goster.",
            "Dogrulama: status, alan ve final state assertion zincirini tek tek eslestir.",
        ]
    if subtype == "class":
        return [
            "Kurulum: __init__ veya ilk state atamalarinin sinifi nasil baslattigini belirle.",
            "Metotlar: her methodun hangi sorumlulugu tasidigini ayir.",
            "Durum kullanimi: self alanlarinin nasil okundugunu veya guncellendigini takip et.",
        ]
    if subtype in {"function", "method"}:
        return [
            "Girdi: fonksiyonun hangi input veya state bilgisini aldigini belirle.",
            "Ana akis: veri donusumu, helper cagrisi veya kosullu dali ayir.",
            "Beklenen sonuc: return satirinin hangi sonucu urettigini goster.",
        ]
    if subtype in {"sql", "sql_update"}:
        return [
            "Secim: sorgunun hangi kolon veya islemi hedefledigini bul.",
            "Kaynak: FROM/JOIN ile hangi tablo veya veri kaynaginin kullanildigini ayir.",
            "Filtre: WHERE/GROUP/ORDER bolumlerinin sonucu nasil daralttigini goster.",
            "Statement purpose: sorgunun okuma mi yazma mi yaptigini kisa anlat.",
        ]
    if subtype == "frontend":
        return [
            "Event: hangi girdi veya etkilesimin akisi baslattigini bul.",
            "Cagri: API veya asenkron adimin nerede yapildigini ayir.",
            "UI sonucu: state veya render etkisinin nasil olustugunu goster.",
        ]
    if subtype == "script":
        return [
            "Handler/callback: scriptin hangi event veya callback ile calistigini ayir.",
            "Islem: API, DOM veya state benzeri adimin nerede oldugunu goster.",
            "Sonuc: script blogunun hangi gorunen etkiyi urettigini kisa anlat.",
        ]
    if subtype == "config":
        return [
            "Section: config grubunun hangi ayarlari topladigini belirle.",
            "Anahtarlar: kritik key-value satirlarinin neyi kontrol ettigini ayir.",
        ]
    if subtype == "markup":
        return [
            "Markup block: sayfa iskeletindeki ana bloklari ayir.",
            "Alt bloklar: form, input veya benzeri etiketlerin rolunu belirle.",
        ]
    if subtype == "style":
        return [
            "Secici: stilin hangi blok veya sinifa uygulandigini ayir.",
            "Kurallar: gorunen style property'lerini grupla.",
            "Beklenen etki: sadece gorunen gorunum etkisini kisa anlat.",
        ]
    if subtype == "shell":
        return [
            "Function: betigin hangi fonksiyon veya giris adimiyla basladigini belirle.",
            "Hazirlik: degisken ve gerekli girdileri topla.",
            "Komut: asil komut veya API cagrisi adimini ayir.",
            "Kontrol akisi: if/loop ile hangi durumda devam ettigini goster.",
        ]
    return [
        "Ana akis: kod blogunun temel girdisini ve amacini yakala.",
        "Kritik adim: cagrilar, kosullar ve sonucu ayir.",
    ]


def _anlamadim_code_examples(text: str, context: dict | None = None) -> list[str]:
    subtype = _anlamadim_code_subtype(text, context)
    if subtype in {"api_test", "test"}:
        return [
            "Assertion mantigi: status assertion, alan assertion ve final state assertion ayni sey degildir; her biri farkli beklentiyi dogrular.",
            "Bu testi okurken once hazirlik satirlarini, sonra endpoint cagrisi ve en sonda assertion zincirini eslestir.",
        ]
    if subtype == "class":
        return [
            "Sinif okumasinda once __init__ ile kurulan self alanlarina, sonra bu alanlari kullanan methodlara bak.",
            "self uzerinden tasinan veri genelde sinifin durumu veya kalici baglamidir.",
        ]
    if subtype in {"function", "method"}:
        return [
            "return satiri fonksiyonun kullaniciya veya sonraki adima hangi sonucu verdigini gosteren ana ipucudur.",
            "Kosullu dal varsa hangi girdide hangi sonucun donduruldugunu birlikte oku.",
        ]
    if subtype == "sql":
        return [
            "SQL okurken SELECT/FROM/WHERE sirasini takip etmek sorgunun neyi dondurdugunu daha hizli aciklar.",
            "Yazma statement'larinda hedef tablo ve filtre birlikte okunmadan etkisi tam anlasilmaz.",
        ]
    if subtype == "frontend":
        return [
            "Frontend kodunda event -> API -> state/render zinciri genelde kullaniciya gorunen sonucu belirler.",
            "API cagrisi ile state guncellemesini ayirinca akisin neyi tetikledigi netlesir.",
        ]
    if subtype == "config":
        return [
            "Config satirlari davranisi dogrudan anlatmaz; hangi anahtarin hangi ayari kontrol ettigini gosterir.",
        ]
    if subtype == "markup":
        return [
            "Markup okurken once yapisal etiketleri, sonra form veya input gibi alt bloklari ayirmak yeterlidir.",
        ]
    if subtype == "shell":
        return [
            "Shell betiginde komut sonuclari ortamdan etkilenebilir; bu nedenle gorulen komut amacina odaklan.",
            "API cagrisi ve kontrol akisini ayirmak betigin ne yaptigini daha net gosterir.",
        ]
    return ["Bu kod blogunu okurken girdi, islem ve cikti akisini birlikte takip et."]


def _anlamadim_code_glossary(text: str, context: dict | None = None) -> list[dict]:
    subtype = _anlamadim_code_subtype(text, context)
    if subtype in {"api_test", "test"}:
        return [
            {"terim": "authenticate", "tanim": "Test istemcisini ilgili kullanici veya rol ile yetkilendiren hazirlik adimi."},
            {"terim": "POST cagrisi", "tanim": "Endpoint'e veri gonderip response alan temel API adimi."},
            {"terim": "assertion", "tanim": "Test sonunda beklenen sonucun gercekten olustugunu dogrulayan satir."},
            {"terim": "final state assert", "tanim": "Kalici nesnenin veya kaydin son durumunun beklenen degerde kaldigini sinayan dogrulama."},
        ]
    if subtype == "sql":
        return [
            {"terim": "SELECT", "tanim": "Sorgunun hangi kolon veya sonuc setini dondurecegini belirler."},
            {"terim": "WHERE", "tanim": "Kayitlari belirli kosullara gore filtreler."},
        ]
    if subtype == "config":
        return [
            {"terim": "section", "tanim": "Birbiriyle iliskili config ayarlarini ayni grup altinda toplar."},
            {"terim": "network", "tanim": "Endpoint, base url veya baglanti ayarlarina dair config ipucu verir."},
        ]
    return _anlamadim_build_glossary(text)


def _anlamadim_code_function_purpose(text: str, context: dict | None = None) -> str:
    context = dict(context or {})
    subtype = _anlamadim_code_subtype(text, context)
    symbol, role = _anlamadim_code_role(text, context.get("code_unit_name") or context.get("symbol") or "", context)
    lower = str(text or "").lower()
    if subtype in {"api_test", "test"}:
        method = _anlamadim_code_api_method(text)
        return f"{symbol or 'Bu test'} test ortamini kurar, {method} cagrisi yapar ve beklenen status/alan/final state sonucunu dogrular."
    if subtype == "class":
        return f"{symbol or 'Bu sinif'} sinif olarak state'i tasir ve gorunen metot davranislarini ortak sorumluluk altinda toplar."
    if subtype == "method":
        return f"{symbol or 'Bu method'} nesnenin state'ini veya ilgili veri akisindaki islemi yonetir."
    if subtype == "function":
        return f"{symbol or 'Bu fonksiyon'} input(girdi) alir, ana islemi yapar ve sonucu dondurur."
    if subtype == "sql":
        if re.search(r"^\s*UPDATE\b", text, re.IGNORECASE):
            return "Bu SQL statement'i hedef tabloya guncelleme yazar ve filtrelenen kayitlara uygular."
        return "Bu SQL sorgusu hangi verinin okunacagini ve nasil filtrelenecegini aciklar."
    if subtype == "frontend":
        return "Bu frontend fonksiyonu kullanici olayini alip API cagrisi ve UI sonucuna baglar."
    if subtype == "config":
        return "Bu config blogu ilgili anahtar-deger ayarlariyla davranisi veya baglanti bilgisini kontrol eder."
    if subtype == "markup":
        return "Bu markup blogu sayfa iskeletini ve onemli alt bloklari tanimlar."
    if subtype == "shell":
        return "Bu shell blogu komutlari ve kontrol akisina ait adimlari sirali sekilde calistirir."
    if "self." in lower:
        return f"{symbol or 'Bu method'} nesnenin state'ini veya ilgili islemi yurutur."
    return f"{symbol or 'Bu kod blogu'} {role}."


def _anlamadim_code_one_liner(text: str, context: dict | None = None) -> str:
    subtype = _anlamadim_code_subtype(text, context)
    if subtype in {"api_test", "test"}:
        method = _anlamadim_code_api_method(text)
        return f"Bu test {method.lower()} tabanli endpoint akisinda hazirlik, cagri ve dogrulama adimlarini ayiriyor."
    if subtype == "class":
        return "Bu sinif ilk durumunu kurup metotlariyla ilgili davranisi ureten bir yapi kuruyor."
    if subtype in {"function", "method"}:
        return "Bu fonksiyon veri akisinda girdiyi isleyip kosullu olarak sonuc donduren bir adim kuruyor."
    if subtype == "sql":
        return "Bu SQL sorgusu secim, kaynak ve filtre akisiyla istenen sonucu tanimliyor."
    if subtype == "frontend":
        return "Bu frontend fonksiyonu event, API cagrisi ve arayuz sonucunu ayni akis icinde bagliyor."
    if subtype == "config":
        return "Bu config blogu ilgili ayarlari ayni grup altinda toplayip davranisi kontrol ediyor."
    if subtype == "markup":
        return "Bu markup blogu sayfa iskeletini ve form benzeri yapisal bloklari kuruyor."
    if subtype == "shell":
        return "Bu shell blogu degisken, komut ve kontrol akisina ait adimlari siraliyor."
    return "Bu kod blogu kritik adimlari ve veri akisinin ana amacini gosteriyor."


def _anlamadim_code_very_simple(text: str, context: dict | None = None) -> str:
    subtype = _anlamadim_code_subtype(text, context)
    if subtype in {"api_test", "test"}:
        return "Bu test basitce sunu gosterir: once ortam hazirlanir, sonra istek atilir, en sonda assertion zinciriyle beklenen sonuc kontrol edilir."
    if subtype == "class":
        return "Bu sinif once kendi ilk durumunu kurar, sonra methodlari bu durum uzerinden calisir."
    if subtype in {"function", "method"}:
        return "Bu kodun veri akisi su: girdi alinir, gerekiyorsa kosul kontrol edilir, kritik isimler takip edilir ve uygun sonuc dondurulur."
    if subtype == "sql":
        return "Bu SQL sorgusu hangi verinin secilecegini, hangi tablodan okunacagini ve nasil filtrelenecegini kisa sekilde anlatir."
    if subtype == "frontend":
        return "Bu frontend adimi kullanici etkilesimini alip API cagrisi ve arayuz sonucuna baglar."
    if subtype == "config":
        return "Bu blok ilgili config anahtarlarini tek yerde toplayip neyin nasil ayarlanacagini gosterir."
    if subtype == "markup":
        return "Bu blok sayfa iskeletini kurar; hangi taglerin bir araya geldigini gosterir."
    if subtype == "shell":
        return "Bu shell blogu once degiskenleri hazirlar, sonra komutlari calistirir ve kontrol akisina gore devam eder."
    return "Bu kod blogu girdi, islem ve cikti adimlarini kisaca gosterir."


def _anlamadim_code_trap(text: str, context: dict | None = None) -> str:
    subtype = _anlamadim_code_subtype(text, context)
    if subtype in {"api_test", "test"}:
        return "Tuzak: Sadece bir assertion'a bakip tum testin ayni beklentiyi dogruladigini sanmak."
    if subtype == "class":
        return "Tuzak: self uzerinden tasinan state'i gormeden methodu bagimsiz okumak."
    if subtype in {"function", "method"}:
        return "Tuzak: return satirini gormeden aradaki kosullu akisi eksik yorumlamak."
    if subtype == "sql":
        return "Tuzak: WHERE veya JOIN bolumunu atlayip sorgunun tum kayitlari getirdigini sanmak."
    if subtype == "markup":
        return "Tuzak: Markup'tan kodda gorunmeyen script davranisi uydurmak."
    return "Tuzak: Kodda gorunmeyen davranisi varmis gibi yorumlamak."


def _anlamadim_code_symbol(context: dict, text: str) -> str:
    symbol = _anlamadim_norm_text(context.get("code_unit_name") or context.get("symbol") or context.get("baslik"))
    if symbol:
        return symbol
    first_line = str(text or "").splitlines()[0] if str(text or "").splitlines() else str(text or "")
    match = re.search(r"\b(?:def|class|function)\s+([A-Za-z_][A-Za-z0-9_-]*)", first_line)
    return _anlamadim_norm_text(match.group(1) if match else "")


def _anlamadim_code_line_window(context: dict) -> str:
    line_start = int(context.get("line_start") or 0)
    line_end = int(context.get("line_end") or 0)
    if line_start and line_end and line_end >= line_start:
        return f"Satir {line_start}-{line_end}"
    if line_start:
        return f"Satir {line_start}"
    return ""


def _anlamadim_code_subtype(text: str, context: dict | None) -> str:
    context = dict(context or {})
    clean = str(text or "")
    lower = clean.lower()
    first_line = clean.splitlines()[0] if clean.splitlines() else clean
    language = _anlamadim_norm_text(context.get("code_language") or context.get("language")).lower()
    code_unit_kind = _anlamadim_norm_text(context.get("code_unit_kind")).lower()
    symbol = _anlamadim_norm_text(context.get("code_unit_name") or context.get("symbol")).lower()
    purpose_hints = {str(item).strip().lower() for item in list(context.get("code_purpose_hints") or []) if str(item).strip()}

    if language == "sql" or re.search(r"^\s*(select|with|insert|update|delete|create|alter)\b", first_line, flags=re.IGNORECASE):
        if code_unit_kind in {"sql_update", "sql_insert", "sql_delete", "sql_create", "sql_alter", "sql_set"} or re.search(r"^\s*(insert|update|delete|create|alter)\b", first_line, flags=re.IGNORECASE):
            return "sql_update"
        return "sql"
    if code_unit_kind == "script_block":
        return "script"
    if language == "css" or code_unit_kind in {"style_block", "style_rule"}:
        return "style"
    if language in {"json", "yaml", "yml"} or code_unit_kind in {"section", "config_entry"} or "config" in purpose_hints:
        return "config"
    if language in {"html", "xml"} or code_unit_kind == "markup_block":
        return "markup"
    if language in {"powershell", "bash", "sh", "shell"} or "shell" in purpose_hints or (code_unit_kind == "command" and "external_call" in purpose_hints):
        return "shell"
    if code_unit_kind in {"method", "python_method"}:
        return "method"
    if code_unit_kind == "class" or re.search(r"^\s*class\b", first_line, flags=re.IGNORECASE):
        return "class"
    if code_unit_kind in {"test_function", "test_method", "test_step", "assertion"} or symbol.startswith("test_") or re.search(r"^\s*(?:async\s+)?def\s+test_", first_line, flags=re.IGNORECASE):
        if re.search(r"\b(force_authenticate|api_client|self\.client|client\.(get|post|put|patch|delete)|APIClient|APITestCase)\b", clean, flags=re.IGNORECASE):
            return "api_test"
        return "test"
    if language in {"javascript", "typescript", "tsx", "jsx"}:
        if code_unit_kind == "api_call" or any(token in purpose_hints for token in {"event_handler", "state_update", "ui_result", "api_call"}):
            return "frontend"
        if re.search(r"\b(fetch\(|axios\.|set[A-Z][A-Za-z0-9_]*\(|return\s*<|preventdefault\(|addeventlistener|dispatch\()", lower):
            return "frontend"
        return "script"
    if code_unit_kind in {"function", "python_function"}:
        return "function"
    if "select " in lower and " from " in lower:
        return "sql"
    return "function"


def _anlamadim_http_code(line: str) -> str:
    text = str(line or "")
    match = re.search(r"HTTP[_\s-]?([1-5]\d{2})", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\b([1-5]\d{2})\b", text)
    return match.group(1) if match else ""


def _anlamadim_code_payload(text: str, context: dict | None) -> dict:
    context = dict(context or {})
    clean = str(text or "")
    lines = [line.rstrip() for line in clean.splitlines() if line.strip()]
    lower = clean.lower()
    symbol = _anlamadim_code_symbol(context, clean) or "Bu kod"
    subtype = _anlamadim_code_subtype(clean, context)
    names = _anlamadim_code_critical_names(clean, symbol)
    line_window = _anlamadim_code_line_window(context)
    line_prefix = f"{line_window}: " if line_window else ""
    first_line = lines[0] if lines else clean
    code_unit_kind = _anlamadim_norm_text(context.get("code_unit_kind")).lower()
    test_step_kind = _anlamadim_norm_text(context.get("test_step_kind")).lower()

    if subtype in {"api_test", "test"}:
        request_method = ""
        for candidate in ("post", "get", "put", "patch", "delete"):
            if re.search(rf"\.(?:client\.)?{candidate}\(", lower):
                request_method = candidate.upper()
                break
        if not request_method and "client." in lower:
            request_method = "istek"

        has_mock = bool(re.search(r"\b(monkeypatch|mock|patch\(|setattr\()", clean, flags=re.IGNORECASE))
        has_nested_condition = bool(re.search(r"^\s*(if|elif)\b", clean, flags=re.IGNORECASE | re.MULTILINE))
        has_final_state = bool(re.search(r"\brefresh_from_db\(", clean) or re.search(r"\bassert.*status\b", lower))
        flow_steps = ["hazirlik"]
        if test_step_kind and test_step_kind not in flow_steps:
            flow_steps.append(test_step_kind)
        if has_mock:
            flow_steps.append("mock")
        flow_steps.extend(["yetki", "payload", request_method or "cagri", "status assert", "field assert"])
        if has_final_state:
            flow_steps.append("final state")
        function_purpose = f"{line_prefix}Bu test ortamini kurar, endpoint cagrisi yapar ve beklenen yanit ile final state sonucunu dogrular.".strip()
        flow_summary = f"{line_prefix}{' -> '.join(dict.fromkeys(flow_steps))}".strip()
        one_liner = f"{symbol} testi {request_method or 'istek'} akisini ve assertion sonucunu aciklar."
        very_simple = (
            f"Bu test, hazirliktan sonra bir {request_method or 'istek'} cagrisi yapip assertion zinciriyle sonucu dogrular. "
            f"Kritik isimler: {', '.join(names[:4]) if names else symbol}."
        )
        setup_step = "Hazirlik: test istemcisi ve kullanici yetkisini ayir."
        if has_mock:
            setup_step = "Hazirlik: test istemcisi, kullanici yetkisi ve mock adimini ayir."
        steps = [
            setup_step,
            f"Input: payload veya request verisinin {request_method or 'istek'} oncesi nasil hazirlandigini izle.",
            f"Cagri: endpoint'e giden {request_method or 'istek'} cagrisi ile response'un nasil alindigini takip et.",
            "Dogrulama: status assertion, field assertion ve final state assertion farkini ayri yorumla.",
        ]
        examples = [f"Assertion mantigi: once {request_method or 'istek'} sonucu alinir, sonra HTTP sonucu ve response alanlari dogrulanir."]
        if has_nested_condition:
            examples.append("Kosullu assertion ornegi: ek kontrol sadece ilgili response kosulu saglandiginda calisir.")
        glossary = []
        if "force_authenticate" in lower:
            glossary.append({"terim": "force_authenticate", "tanim": "Test istemcisini ilgili kullanici yetkisiyle calistiran hazirlik cagrisi."})
            glossary.append({"terim": "authenticate", "tanim": "Test istemcisinin ilgili kullanici yetkisiyle calismasini saglar."})
        if request_method:
            glossary.append({"terim": f"{request_method} cagrisi", "tanim": "Testte endpoint'e giden ana HTTP istegidir."})
        if re.search(r"\bassert|assertequal|assertin|asserttrue|assertfalse", lower):
            glossary.append({"terim": "assertion", "tanim": "Beklenen test sonucunu kisa ve somut bicimde dogrulayan kontroldur."})
        if has_final_state:
            glossary.append({"terim": "final state assert", "tanim": "Kaydin son durumunun beklenen degerde kaldigini dogrular."})
        block_comments = []
        if has_mock:
            block_comments.append("Hazirlik blogu yetki, mock ve test ortamini ayni zincirde toparlar.")
        elif "force_authenticate" in lower:
            block_comments.append("Hazirlik blogu yetki ve test ortamini ayni zincirde toparlar.")
        if re.search(r"token_factory\(|response\.json\(", clean):
            block_comments.append("Temel akis blogu helper cagrisi ve ara body verisini dogrulama oncesi hazirlar.")
        if re.search(r"\b(data|payload)\s*=", clean):
            block_comments.append("Payload blogu API'ye gidecek verinin hangi alanlarla kuruldugunu gosterir.")
        if re.search(r"\.(get|post|put|patch|delete)\(", clean, flags=re.IGNORECASE):
            block_comments.append("Cagri blogu request'i endpoint'e gonderip response'u assertion zincirine tasir.")
        block_comments.append("Assertion blogu status, response alanlari ve final state kontrolunu ayri amaclarla yapar.")
        if has_nested_condition:
            block_comments.append("Kosullu assertion blogu ek dogrulamanin hangi response durumunda calistigini netlestirir.")
        line_comments = []
        for raw_line in lines:
            stripped = raw_line.strip()
            lowered = stripped.lower()
            if stripped.startswith("def "):
                continue
            if "force_authenticate" in lowered:
                line_comments.append("Bu satir test istemcisini ilgili kullaniciyla yetkilendirir.")
            elif re.search(r"\b(monkeypatch|mock|patch\(|setattr\()", stripped, flags=re.IGNORECASE):
                line_comments.append("Bu satir dis bagimliligi sahte davranisla degistirerek testi deterministik hale getirir.")
            elif "token_factory(" in lowered:
                line_comments.append("Bu satir testte kullanilacak refresh token girdisini helper cagrisi ile hazirlar.")
            elif re.search(r"\b(data|payload)\s*=", stripped):
                line_comments.append("Bu satir API'ye gonderilecek payload'i hazirlar.")
            elif re.search(r"\b(client|api_client|self\.client)\.(get|post|put|patch|delete)\(", stripped, flags=re.IGNORECASE):
                method_match = re.search(r"\.(get|post|put|patch|delete)\(", stripped, flags=re.IGNORECASE)
                method_text = (method_match.group(1).upper() if method_match else request_method) or "istek"
                if "{" in stripped:
                    line_comments.append(f"Bu satir payload'i endpoint'e {method_text} istegiyle gonderir ve response'u alir.")
                else:
                    line_comments.append(f"Bu satir endpoint'e {method_text} istegi atar ve response'u alir.")
            elif "status_code" in lowered and re.search(r"\bassert|assertequal", lowered):
                http_code = _anlamadim_http_code(stripped)
                if http_code:
                    line_comments.append(f"Bu assertion HTTP {http_code} dondugunu dogrular.")
                else:
                    line_comments.append("Bu assertion HTTP sonucunun beklenen status koduyla eslestigini dogrular.")
            elif "response.json()" in lowered:
                line_comments.append("Bu satir response body'sini sonraki assertion'larda okunacak yapida hazirlar.")
            elif re.search(r"assertin\(", lowered) and "response.data" in lowered:
                field_match = re.search(r"assertIn\(\s*['\"]([^'\"]+)['\"]", stripped, flags=re.IGNORECASE)
                field_name = field_match.group(1) if field_match else "alan"
                line_comments.append(f"Bu assertion response icindeki beklenen {field_name} alaninin uretildigini kontrol eder.")
            elif re.search(r"\bassert\b", lowered) and "access" in lowered:
                line_comments.append("Bu assertion refresh cagrisi sonunda access alaninin uretildigini veya eski token'dan farkli oldugunu dogrular.")
            elif stripped.startswith("if ") or stripped.startswith("elif "):
                line_comments.append("Bu kosul, alt assertion'in hangi kosul saglandiginda calisacagini belirler.")
            elif "response.data" in lowered and re.search(r"\bassert", lowered):
                field_match = re.search(r"\[['\"]([^'\"]+)['\"]\]", stripped)
                field_name = field_match.group(1) if field_match else "alan"
                line_comments.append(f"Bu assertion response icindeki '{field_name}' alaninin beklenen degeri tasidigini dogrular.")
            elif "refresh_from_db" in lowered:
                line_comments.append("Bu satir yeni kaydin son halini veritabanindan yeniden ceker.")
            elif re.search(r"\bassert", lowered) and re.search(r"\bstatus\b", lowered):
                value_match = re.search(r"['\"]([^'\"]+)['\"]", stripped)
                state_value = value_match.group(1).upper() if value_match else "beklenen"
                line_comments.append(f"Bu assertion yeni kaydin {state_value} baslangic durumunda oldugunu dogrular.")
            elif re.search(r"\bassert", lowered):
                generic_comment = _anlamadim_python_line_comment(stripped, subtype="api_test", context=context)
                if generic_comment:
                    line_comments.append(generic_comment)
        trap = "Tuzak: assertion zincirini tek bir genel kontrol gibi okuyup status, field ve final state farkini kacirmak."
        return {
            "one_liner": one_liner,
            "very_simple": very_simple,
            "glossary": glossary[:4],
            "steps": steps[:4],
            "examples": examples[:3],
            "trap": trap,
            "mini_quiz": _anlamadim_quiz_from_fields(one_liner, very_simple, glossary[:4], steps[:4]),
            "tema_bazli_ornek": "",
            "alternatif_ornek": "",
            "function_purpose": function_purpose,
            "flow_summary": flow_summary,
            "block_comments": _anlamadim_unique_texts(block_comments, limit=4),
            "line_comments": _anlamadim_unique_texts(line_comments, limit=9),
        }

    if subtype == "class":
        method_names = re.findall(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)", clean, flags=re.MULTILINE)
        public_methods = [name for name in method_names if name != "__init__"]
        class_role = f"{', '.join(public_methods[:2])} gibi davranislar" if public_methods else "ilgili davranislar"
        function_purpose = f"{line_prefix}Bu sinif state'i tasir ve {class_role} icin ortak metot sorumluluk alanini kurar.".strip()
        flow_summary = f"{line_prefix}ilk durum kurulumu -> state saklama -> metot davranisi -> sonuc uretimi".strip()
        one_liner = f"{symbol} sinifi kurulum ve davranis akisini birlikte gosterir."
        very_simple = (
            f"Bu sinif, ilk durumu saklayip metotlarla bu durum uzerinde islem yapan bir duzen kurar. "
            f"Kritik isimler: {', '.join((method_names or names)[:4])}."
        )
        steps = [
            "Kurulum: __init__ veya ilk state atamalarinin nesneyi nasil hazirladigini ayir.",
            f"Metotlar: {', '.join(public_methods[:3]) if public_methods else 'gorunen metotlar'} hangi sorumlulugu tasiyor onu not et.",
            "Durum kullanimi: self ile saklanan verinin hangi satirlarda okunup guncellendigini takip et.",
        ]
        examples = ["Sinif ornegi: self alanlari ilk durumu tasir, metotlar bu durumdan davranis uretir."]
        block_comments = [
            "Kurulum ve state blogu nesnenin ilk durumunu olusturur.",
            "Davranis blogu saklanan veriyi okuyup sonuc ureten metotlari toplar.",
        ]
        if re.search(r"self\.[A-Za-z_][A-Za-z0-9_]*\s*=\s*self\.", clean):
            block_comments.append("State degisimi blogu mevcut deger uzerinden nesnenin durumunu guncelleyen satirlari ayirir.")
        line_comments = []
        for raw_line in lines:
            comment = _anlamadim_python_line_comment(raw_line, subtype="class", context=context)
            if comment:
                line_comments.append(comment)
        glossary = [{"terim": "self", "tanim": "Sinifin kendi state'ini tasiyan nesne referansidir."}]
        if public_methods:
            glossary.append({"terim": "method", "tanim": f"Sinifin gorunen davranislari {', '.join(public_methods[:2])} gibi metotlarda toplanir."})
        trap = "Tuzak: self ile saklanan veriyi gormeden metot sonucunu baglam disi yorumlamak."
        return {
            "one_liner": one_liner,
            "very_simple": very_simple,
            "glossary": glossary[:4],
            "steps": steps[:4],
            "examples": examples[:3],
            "trap": trap,
            "mini_quiz": _anlamadim_quiz_from_fields(one_liner, very_simple, glossary[:4], steps[:4]),
            "tema_bazli_ornek": "",
            "alternatif_ornek": "",
            "function_purpose": function_purpose,
            "flow_summary": flow_summary,
            "block_comments": _anlamadim_unique_texts(block_comments, limit=4),
            "line_comments": _anlamadim_unique_texts(line_comments, limit=9),
        }

    if subtype in {"sql", "sql_update"}:
        clause_items = _anlamadim_sql_clause_items(clean)
        clause_labels = [_anlamadim_sql_clause_label(kind, clause_text) for kind, clause_text in clause_items]
        sources = _anlamadim_sql_sources(clause_items)
        table_name = sources[0] if sources else ""
        where_clause = " ".join(clause_text for kind, clause_text in clause_items if _anlamadim_sql_clause_label(kind, clause_text) in {"WHERE", "HAVING", "LIMIT"})
        group_clause = " ".join(clause_text for kind, clause_text in clause_items if _anlamadim_sql_clause_label(kind, clause_text) == "GROUP BY")
        order_clause = " ".join(clause_text for kind, clause_text in clause_items if _anlamadim_sql_clause_label(kind, clause_text) == "ORDER BY")
        has_join = "JOIN" in clause_labels
        has_cte = "WITH" in clause_labels
        has_window = bool(re.search(r"\bover\s*\(", clean, flags=re.IGNORECASE))
        if subtype == "sql":
            columns = []
            for clause_kind, clause_text in clause_items:
                if _anlamadim_sql_clause_label(clause_kind, clause_text) != "SELECT":
                    continue
                select_body = re.sub(r"^\s*SELECT\b", "", clause_text, flags=re.IGNORECASE).strip()
                select_body = re.split(r"\bFROM\b", select_body, maxsplit=1, flags=re.IGNORECASE)[0]
                columns = [item.strip() for item in select_body.split(",") if item.strip()][:4]
                if columns:
                    break
            flow_parts = _anlamadim_unique_texts(clause_labels + ["sonuc"], limit=8)
            glossary = [
                {"terim": "SELECT", "tanim": "Sorgunun hangi kolon veya sonuc setini dondurecegini belirler."},
                {"terim": "FROM", "tanim": "Verinin hangi tablo veya kaynaklardan okundugunu gosterir."},
            ]
            if has_join:
                glossary.append({"terim": "JOIN", "tanim": "Birden fazla tablonun gorunen bag ile nasil birlestirildigini gosterir."})
            if where_clause:
                glossary.append({"terim": "WHERE", "tanim": "Kayitlari gorunen kosula gore filtreler."})
            examples = [f"SQL akisi: {' -> '.join(flow_parts[:-1])}"]
            if has_join:
                examples.append("JOIN mantigi: ilgili tablolar gorunen birlestirme kosuluna gore ayni sonuc setine baglanir.")
            if has_cte or has_window:
                examples.append("Ileri SQL notu: CTE veya window yapisi gorunse de yalnizca gorunen clause iliskisi anlatilmalidir.")
            line_comments = [_anlamadim_sql_line_comment(clause_text) for _, clause_text in clause_items]
            source_text = " ve ".join(sources[:2]) if sources else "gorunen veri kaynaklari"
            action_bits = []
            if has_join:
                action_bits.append("kaynaklari birlestirir")
            if where_clause:
                action_bits.append("gorunen kosullarla filtreler")
            if group_clause:
                action_bits.append("sonucu gruplayarak ozetler")
            if order_clause:
                action_bits.append("siralamayi uygular")
            action_text = ", ".join(action_bits) if action_bits else "clause akisina gore sonucu hazirlar"
            function_purpose = f"{line_prefix}Bu SQL sorgusu {source_text} uzerinden gorunen kolonlari secer ve {action_text}.".strip()
            very_simple = "Bu SQL sorgusu hangi verinin secilecegini, hangi kaynaktan okunacagini ve gorunen filtrelerle nasil daraldigini anlatir."
            one_liner = f"{symbol} SQL sorgusu {source_text} uzerinden gorunen sonucu okumak icin clause akisina dayanir."
            block_comments = [
                "Sorgu blogu kolon secimini ve tablo/veri kaynagi rolunu birlikte aciklar.",
                "JOIN blogu tablo iliskisini gorunen birlestirme adimina baglar." if has_join else "",
                "Filtre ve ozet blogu WHERE/GROUP/ORDER adimlarinin sonucu nasil daralttigini toplar." if any((where_clause, group_clause, order_clause)) else "",
                "CTE blogu sonraki SELECT'in dayanacagi gorunen ara sonucu tanimlar." if has_cte else "",
            ]
            trap = "Tuzak: WHERE/JOIN akisina bakmadan sorgunun tum kayitlari getirdigini sanmak."
            if has_cte or has_window:
                trap = "Tuzak: WHERE/JOIN akisina bakmadan sorgunun tum kayitlari getirdigini veya CTE/window davranisini kesinlestirmek."
            return {
                "one_liner": one_liner,
                "very_simple": very_simple,
                "glossary": glossary[:4],
                "steps": [
                    "Secim: SELECT ile hangi kolonlarin veya sonuc setinin hedeflendigini ayir.",
                    "Kaynak: FROM/JOIN ile verinin hangi tablo veya tablolardan geldigini belirle.",
                    "Filtre: WHERE/GROUP/ORDER adimlarinin sonucu nasil daralttigini goster.",
                    "Statement purpose: sorgunun gorunen okuma amacini kisa anlat.",
                ],
                "examples": examples[:3],
                "trap": trap,
                "mini_quiz": _anlamadim_quiz_from_fields(one_liner, very_simple, glossary[:4], ["Secim: SELECT'i ayir.", "Kaynak: FROM/JOIN akisini izle.", "Filtre: WHERE/GROUP/ORDER etkisini not et."]),
                "tema_bazli_ornek": "",
                "alternatif_ornek": "",
                "function_purpose": function_purpose,
                "flow_summary": f"{line_prefix}{' -> '.join(flow_parts)}".strip(),
                "block_comments": _anlamadim_unique_texts([item for item in block_comments if item], limit=4),
                "line_comments": _anlamadim_unique_texts(line_comments, limit=7),
            }
        set_clause = " ".join(clause_text for kind, clause_text in clause_items if _anlamadim_sql_clause_label(kind, clause_text) == "SET")
        line_comments = [_anlamadim_sql_line_comment(clause_text) for _, clause_text in clause_items]
        one_liner = f"{symbol} SQL write statement'i {table_name or 'hedef tablo'} uzerinde gorunen degisimi uygular."
        very_simple = "Bu statement hedef tabloyu, varsa guncellenen alanlari ve filtre kapsamini gorunen satirlar kadar anlatir."
        return {
            "one_liner": one_liner,
            "very_simple": very_simple,
            "glossary": [
                {"terim": "statement", "tanim": "Veritabaninda yazma veya yapisal degisim etkisi doguran SQL ifadesidir."},
                {"terim": "WHERE", "tanim": "Degisimin hangi kayitlarla sinirli oldugunu gosterir."} if where_clause else {"terim": "hedef tablo", "tanim": "Yazma etkisinin uygulandigi tabloyu gosterir."},
            ],
            "steps": [
                "Statement purpose: Bu yazma ifadesinin hangi tabloyu veya nesneyi degistirdigini ayir.",
                "Filter: WHERE varsa degisimin hangi kayitlara uygulandigini not et.",
            ],
            "examples": [
                "Write query ornegi: hedef tablo, varsa SET adimi ve WHERE kapsami birlikte okunur.",
                "Ileri SQL notu: transaction veya runtime sonucu gorunmuyorsa kesinlestirilmez.",
            ],
            "trap": "Tuzak: WHERE kosulunu atlayip degisimin kapsamini yanlis genellestirmek.",
            "mini_quiz": _anlamadim_quiz_from_fields(one_liner, very_simple, [{"terim": "statement", "tanim": "SQL yazma ifadesi"}], ["Statement purpose: hedef tabloyu ayir.", "Filter: WHERE kapsamini incele."]),
            "tema_bazli_ornek": "",
            "alternatif_ornek": "",
            "function_purpose": f"{line_prefix}Bu statement {table_name or 'hedef tablo'} uzerinde gorunen degisimi uygular ve kapsami clause sirasi kadar netlestirir.".strip(),
            "flow_summary": f"{line_prefix}{' -> '.join(_anlamadim_unique_texts(clause_labels + ['yazma etkisi'], limit=6))}".strip(),
            "block_comments": _anlamadim_unique_texts(
                [
                    "Statement blogu hedef tabloyu ve yazma etkisini ayni yerde toplar.",
                    "Alan blogu SET adiminda degisen kolonlari toplar." if set_clause else "",
                    "Filtre blogu WHERE ile degisimin kapsamini sinirlar." if where_clause else "",
                ],
                limit=4,
            ),
            "line_comments": _anlamadim_unique_texts(line_comments or ["Bu statement hedef tabloyu gorunen alanlarla gunceller."], limit=6),
        }

    if subtype in {"frontend", "script"}:
        frontend_signals = _anlamadim_frontend_signals(clean)
        frontend_line_comments = []
        for _, raw_line in _anlamadim_code_meaningful_lines(clean):
            comment = _anlamadim_frontend_line_comment(raw_line)
            if comment:
                frontend_line_comments.append(comment)
        jsx_match = re.search(r"return\s*<([A-Za-z_][A-Za-z0-9_]*)", clean)
        if jsx_match:
            frontend_line_comments.append(f"Bu satir {jsx_match.group(1)} render sonucunu dondurur.")
        elif re.search(r"\breturn\s+render[A-Za-z_]*\(", clean):
            render_match = re.search(r"\breturn\s+([A-Za-z_][A-Za-z0-9_]*)\(", clean)
            render_name = render_match.group(1) if render_match else "render"
            frontend_line_comments.append(f"Bu satir {render_name} ile render sonucunu dondurur.")
        elif subtype == "script" and frontend_signals["has_return"]:
            frontend_line_comments.append("Bu satir script blogunun gorunen sonucunu veya callback donusunu dondurur.")
        has_state = bool(frontend_signals["has_state"])
        has_api = bool(frontend_signals["has_api"])
        has_render = bool(frontend_signals["has_render"])
        has_condition = bool(frontend_signals["has_condition"])
        has_promise = bool(frontend_signals["has_promise"])
        role_label = "script blogu" if subtype == "script" else "frontend parcasi"
        result_label = "render/UI sonucuna" if has_render else ("state sonucuna" if has_state else "callback sonucuna")
        return {
            "one_liner": f"{symbol} {role_label} {'event/callback' if frontend_signals['has_event'] or frontend_signals['has_callback'] else 'girdi'} akisina {'API, ' if has_api else ''}{'state, ' if has_state else ''}{'render ' if has_render else ''}mantigini baglar.",
            "very_simple": (
                f"Bu {role_label} girdiyi alip isler; {'event veya callback akisini ' if frontend_signals['has_event'] or frontend_signals['has_callback'] else ''}"
                f"{'API cagrisi, ' if has_api else ''}{'state guncellemesi, ' if has_state else ''}{'promise zinciri, ' if has_promise else ''}"
                f"ve sonucunu {'render tarafina' if has_render else 'gorunen akis sonucuna'} tasir. "
                f"Kritik isimler: {', '.join(names[:4]) if names else symbol}."
            ),
            "glossary": [
                {"terim": "render", "tanim": "UI tarafinda gosterilecek sonucun gorunen donusudur."},
                {"terim": "event handler", "tanim": "Kullanici etkilesimi veya callback ile calisan gorunen isleyicidir."} if "addeventlistener" in lower or "event" in lower else {"terim": "callback", "tanim": "Belirli bir olay veya asenkron adimdan sonra calisan gorunen isleyicidir."},
            ],
            "steps": [
                "Girdi: event, callback veya fonksiyon girdisinin hangi satirda alindigini ayir.",
                "Islem: API cagrisi, promise/callback akisi, kosul ve state guncellemesinin sirasini takip et.",
                "Beklenen sonuc: {} giden ciktiyi not et.".format("render veya UI sonucuna" if has_render else "state veya callback sonucuna"),
            ],
            "examples": [
                "Frontend/script ornegi: event veya callback tetiklenir, gerekli API/state adimi calisir ve gorunen sonuc ilgili satirlarda belirir.",
                "Nested callback varsa parent handler ile alt callback'in neyi tetikledigini birlikte oku.",
                "Promise zinciri varsa then/catch/finally sirasi sonraki yan etki veya state degisimini belirler." if has_promise else "",
            ],
            "trap": "Tuzak: state veya API baglantisi gorunmeden hayali arayuz davranisi uydurmak.",
            "mini_quiz": _anlamadim_quiz_from_fields(
                f"{symbol} {role_label} event/callback ve gorunen sonucu birbirine baglar.",
                f"Bu {role_label} girdiyi alip isler ve sonucunu gorunen akisa tasir.",
                [{"terim": "render", "tanim": "UI sonucu"}],
                ["Girdi: event'i ayir.", "Islem: API ve state sirasini izle.", "Beklenen sonuc: render sonucunu not et."],
            ),
            "tema_bazli_ornek": "",
            "alternatif_ornek": "",
            "function_purpose": (
                f"{line_prefix}Bu {'script blogu' if subtype == 'script' else 'frontend fonksiyonu'} "
                f"{'event veya callback akisini isler, ' if frontend_signals['has_event'] or frontend_signals['has_callback'] else ''}"
                f"{'API cagrisini, ' if has_api else ''}{'state veya property degisimini, ' if has_state else ''}"
                f"{'kosullu akisi, ' if has_condition else ''}{result_label} baglar."
            ).strip(),
            "flow_summary": f"{line_prefix}{'event/handler -> ' if frontend_signals['has_event'] or frontend_signals['has_callback'] else ''}{'promise -> ' if has_promise else ''}{'api -> ' if has_api else ''}{'kosul -> ' if has_condition else ''}{'state -> ' if has_state else ''}{'render -> ' if has_render else ''}sonuc".strip(),
            "block_comments": _anlamadim_unique_texts(
                [
                    "Handler blogu event veya callback girisini gorunen akisla baslatir." if frontend_signals["has_event"] or frontend_signals["has_callback"] else "",
                    "API ve state blogu kullanici eylemini veri akisina cevirir." if has_api or has_state else "Islem blogu scriptin gorunen ara adimlarini toplar.",
                    "Kosul blogu response veya event sonucuna gore hangi adimin calisacagini ayirir." if has_condition else "",
                    "Render blogu UI sonucunun hangi satirdan donduruldugunu gosterir." if has_render else "Sonuc blogu callback veya state sonucunun nereye baglandigini gosterir.",
                ],
                limit=4,
            ),
            "line_comments": _anlamadim_unique_texts(frontend_line_comments, limit=9),
        }

    if subtype == "config":
        keys = re.findall(r'"([^"]+)"\s*:', clean)
        if not keys:
            keys = re.findall(r"^\s*([A-Za-z0-9_.-]+)\s*:", clean, flags=re.MULTILINE)
        section_name = _anlamadim_norm_text(context.get("code_unit_name") or (keys[0] if keys else symbol))
        hints = [str(item).strip() for item in list(context.get("code_purpose_hints") or []) if str(item).strip()]
        glossary = [{"terim": "section", "tanim": "Ilgili config anahtarlarini bir arada tutan gruptur."}]
        for hint in hints[:2]:
            glossary.append({"terim": hint, "tanim": f"Gorunen purpose hint olarak {hint} baglamini isaret eder."})
        line_comments = []
        value_type_labels = []
        for raw_line in lines:
            stripped = raw_line.strip().rstrip(",")
            if ":" not in stripped and not stripped.startswith("<<:"):
                continue
            key = re.split(r":", stripped, maxsplit=1)[0].strip(" \"'") if ":" in stripped else "<<"
            value = re.split(r":", stripped, maxsplit=1)[1].strip() if ":" in stripped else ""
            line_comments.append(_anlamadim_config_line_detail(key, value))
            value_type_labels.append(_anlamadim_config_key_label(key, value))
        purpose_labels = _anlamadim_unique_texts([_anlamadim_config_key_label(key) for key in keys[:5]] + value_type_labels, limit=4)
        purpose_text = _anlamadim_join_labels(purpose_labels) or "gorunen ayarlar"
        return {
            "one_liner": f"{section_name or symbol} config grubu gorunen ayarlari ve ozellikle {purpose_text} rollerini tek yerde toplar.",
            "very_simple": "Bu ayar parcasi section ve key-value satirlariyla hangi config anahtarlarinin gorundugunu ve bu alanlarin neyi kontrol ettigini kisa anlatir.",
            "glossary": glossary[:4],
            "steps": [
                "Group/section: config grubunun hangi adla acildigini ayir.",
                "Gorunen anahtarlar: key-value satirlarinin neyi ayarladigini sadece gorunen metin kadar acikla.",
                "Deger tipi: boolean, threshold, path veya alias gibi gorunen deger tiplerini ayri not et.",
            ],
            "examples": [
                f"key-value ornegi: {', '.join(keys[:3]) if keys else 'gorunen anahtarlar'} ana config grubunda toplanir.",
                "Anchor/alias veya multiline deger varsa sadece gorunen yapisal baglantiyi anlatmak yeterlidir." if any(token in clean for token in ("&", "*", "|", ">")) else "",
            ],
            "trap": "Tuzak: config anahtarlarindan gorunmeyen ortamsal veya gizli davranis uydurmak.",
            "mini_quiz": _anlamadim_quiz_from_fields(
                f"{section_name or symbol} config grubu gorunen ayarlari tek yerde toplar.",
                "Bu ayar parcasi section ve key-value satirlariyla gorunen config anahtarlarini anlatir.",
                glossary[:4],
                ["Group/section: config grubunu ayir.", "Gorunen anahtarlar: key-value satirlarini oku."],
            ),
            "tema_bazli_ornek": "",
            "alternatif_ornek": "",
            "function_purpose": f"{line_prefix}Bu config blogu gorunen anahtar-deger yapisini ve ilgili ayar amacini aciklar; ozellikle {purpose_text} odaklanir.".strip(),
            "flow_summary": f"{line_prefix}section/group -> config anahtari -> gorunen deger -> ayar amaci -> deger tipi".strip(),
            "block_comments": _anlamadim_unique_texts(
                [
                    "Config grubu blogu section ile bagli anahtarlari ayni yapida toplar.",
                    "Ayar amaci blogu key-value satirlarinin baglanti, flag, threshold veya path gibi rollerini ayirir." if purpose_labels else "",
                    "Deger tipi blogu boolean, sayisal esik veya alias gibi gorunen config tiplerini ayristirir." if any(label in purpose_labels for label in {"boolean flag", "esik/deger", "alias/merge baglantisi", "route/path"}) else "",
                ],
                limit=4,
            ),
            "line_comments": _anlamadim_unique_texts(line_comments, limit=7),
        }

    if subtype == "markup":
        tags = re.findall(r"<\s*([A-Za-z0-9_-]+)", clean)
        semantic_roles = _anlamadim_unique_texts([_anlamadim_markup_role(tag) for tag in tags[:6]], limit=4)
        markup_line_comments = [
            "Bu markup iskeleti {} kurar.".format(_anlamadim_join_labels(semantic_roles)) if semantic_roles else "",
        ]
        for _, raw_line in _anlamadim_code_meaningful_lines(clean):
            comment = _anlamadim_markup_line_comment(raw_line)
            if comment:
                markup_line_comments.append(comment)
        return {
            "one_liner": f"{symbol} markup parcasi HTML yapisini, semantic bloklari ve ic alanlari gosterir.",
            "very_simple": f"Bu HTML/markup parcasi {', '.join(tags[:5]) if tags else 'gorunen tagler'} ile sayfa iskeletini kurar ve rollerini ayirir.",
            "glossary": [{"terim": "markup", "tanim": "Yapisal taglerle kurulan gorunen HTML iskeletidir."}],
            "steps": [
                "Markup block: hangi yapisal taglerin acildigini ayir.",
                "Ic bloklar: form, section, input veya varsa script/style bloklarini takip et.",
                "Semantic rol: navigation, section, label veya button gibi gorunen rolleri not et.",
            ],
            "examples": [
                f"Yapi ornegi: {', '.join(tags[:5]) if tags else 'tagler'} sirali bir iskelet kurar.",
                "Markup icinde style ve script varsa yapisal, sunumsal ve davranissal katmanlari karistirmadan ayir.",
            ],
            "trap": "Tuzak: Markup'tan script davranisi veya gorunmeyen is kurali uydurmak.",
            "mini_quiz": _anlamadim_quiz_from_fields(
                f"{symbol} markup parcasi HTML yapisini ve ic bloklari gosterir.",
                "Bu HTML/markup parcasi sayfa iskeletini kurar.",
                [{"terim": "markup", "tanim": "HTML iskeleti"}],
                ["Markup block: yapisal tagleri ayir.", "Ic bloklar: form ve input gibi etiketleri oku."],
            ),
            "tema_bazli_ornek": "",
            "alternatif_ornek": "",
            "function_purpose": f"{line_prefix}Bu markup blogu sayfa iskeletini, semantic bloklari ve gorunen alt alanlari kurar.".strip(),
            "flow_summary": f"{line_prefix}yapisal/semantic tagler -> ic bloklar -> form/nav alanlari -> yardimci bloklar".strip(),
            "block_comments": _anlamadim_unique_texts(
                [
                    "Yapisal iskelet blogu sayfanin gorunen iskeletini ve tag hiyerarsisini toplar.",
                    "Semantic blogu navigation, section veya form gibi rollerin neden ayri oldugunu gosterir." if any(tag in {"nav", "section", "form", "main"} for tag in [item.lower() for item in tags]) else "",
                    "Ayrim blogu style/script bloklari varsa bunlari yapisal HTML'den ayirir." if any(tag in {"style", "script"} for tag in [item.lower() for item in tags]) else "",
                ],
                limit=4,
            ),
            "line_comments": _anlamadim_unique_texts([item for item in markup_line_comments if item], limit=9),
        }

    if subtype == "style":
        selector_match = re.search(r"^\s*([^{]+)\{", clean)
        selector = _anlamadim_norm_text(selector_match.group(1) if selector_match else context.get("code_unit_name") or symbol)
        property_names = re.findall(r"([A-Za-z-]+)\s*:", clean)
        lower_props = [item.lower() for item in property_names]
        line_comments = []
        if selector:
            line_comments.append(f"Bu satir {selector} secicisine stil uygular.")
        for prop in property_names[:3]:
            lowered_prop = prop.lower()
            if lowered_prop in {"display", "flex-direction", "justify-content", "align-items", "grid-template-columns"}:
                line_comments.append(f"Bu satir '{prop}' kuralinin layout duzenini nasil etkiledigini tanimlar.")
            elif lowered_prop in {"margin", "padding", "gap"}:
                line_comments.append(f"Bu satir '{prop}' kuralinin spacing/bosluk etkisini tanimlar.")
            elif lowered_prop in {"color", "background", "background-color", "border", "font-size"}:
                line_comments.append(f"Bu satir '{prop}' kuralinin gorunen stil etkisini tanimlar.")
            elif lowered_prop in {"max-width", "min-width", "width", "height"}:
                line_comments.append(f"Bu satir '{prop}' kuralinin boyut veya responsive sinirini tanimlar.")
            else:
                line_comments.append(f"Bu satir '{prop}' kuralinin gorunen stil etkisini tanimlar.")
        has_layout = any(item in {"display", "flex-direction", "justify-content", "align-items", "grid-template-columns"} for item in lower_props)
        has_spacing = any(item in {"margin", "padding", "gap"} for item in lower_props)
        has_responsive = bool(re.search(r"@\s*media|max-width|min-width", clean, flags=re.IGNORECASE))
        return {
            "one_liner": f"{selector or symbol} style parcasi secici ile gorunen stil kurallarini baglar.",
            "very_simple": "Bu CSS/style parcasi once hangi secicinin hedeflendigini, sonra gorunen stil kurallarinin neyi etkiledigini gosterir.",
            "glossary": [{"terim": "selector", "tanim": "Stil kurallarinin hangi eleman veya sinifa uygulanacagini belirler."}],
            "steps": [
                "Secici: stilin hangi blok veya sinifa uygulandigini ayir.",
                "Kurallar: layout, spacing, color veya responsive gibi gorunen stil satirlarini ayikla.",
                "Beklenen etki: sadece gorunen kural kadar bir stil sonucu anlat.",
            ],
            "examples": [f"Style ornegi: {selector or 'secici'} icin {', '.join(property_names[:3]) if property_names else 'gorunen'} kurallari tanimlanir."],
            "trap": "Tuzak: CSS kuralindan kodda gorunmeyen davranis veya interaksiyon uydurmak.",
            "mini_quiz": _anlamadim_quiz_from_fields(
                f"{selector or symbol} style parcasi secici ile gorunen stil kurallarini baglar.",
                "Bu CSS/style parcasi secici ve gorunen kural iliskisini aciklar.",
                [{"terim": "selector", "tanim": "Stil hedefi"}],
                ["Secici: hedefi ayir.", "Kurallar: stil satirlarini oku.", "Beklenen etki: gorunen sonucu not et."],
            ),
            "tema_bazli_ornek": "",
            "alternatif_ornek": "",
            "function_purpose": f"{line_prefix}Bu style blogu gorunen seciciye {'layout, ' if has_layout else ''}{'spacing, ' if has_spacing else ''}stil kurallari uygular ve beklenen gorunum etkisini tarif eder.".strip(),
            "flow_summary": f"{line_prefix}selector -> {'layout -> ' if has_layout else ''}{'spacing -> ' if has_spacing else ''}{'responsive -> ' if has_responsive else ''}gorunum etkisi".strip(),
            "block_comments": _anlamadim_unique_texts(
                [
                    "Style blogu seciciyi ve gorunen kural setini ayni yerde toplar.",
                    "Layout blogu elemanlarin dizilisini etkileyen display/flex/grid satirlarini ayirir." if has_layout else "",
                    "Spacing blogu margin/padding/gap gibi bosluk kurallarini toplar." if has_spacing else "",
                    "Responsive blogu ekran genisligi veya boyut siniri belirleyen kurallari ayirir." if has_responsive else "",
                ],
                limit=4,
            ),
            "line_comments": _anlamadim_unique_texts(line_comments, limit=9),
        }

    if subtype == "shell":
        shell_line_comments = []
        for raw_line in lines:
            comment = _anlamadim_shell_line_comment(raw_line)
            if comment:
                shell_line_comments.append(comment)
        has_pipeline = "|" in clean
        has_api = bool(re.search(r"\b(Invoke-RestMethod|Invoke-WebRequest|curl|wget)\b", clean, flags=re.IGNORECASE))
        has_env = bool(re.search(r"^\s*\$env:", clean, flags=re.IGNORECASE | re.MULTILINE))
        has_process = bool(re.search(r"\bStart-Process\b", clean, flags=re.IGNORECASE))
        shell_label = "PowerShell" if _anlamadim_norm_text(context.get("code_language") or context.get("language")).lower() == "powershell" else "shell"
        return {
            "one_liner": f"{symbol} {shell_label} parcasi komut, {'API ' if has_api else ''}{'environment degiskeni, ' if has_env else ''}ve kontrol akisinin amacini gosterir.",
            "very_simple": "Bu shell blogu once degiskenleri hazirlar, sonra gorunen komut veya API cagrisi yapar ve kosul/pipeline varsa ona gore ilerler.",
            "glossary": [
                {"terim": "command", "tanim": "Kabuk ortaminda calisan gorunen komut adimidir."},
                {"terim": "pipeline", "tanim": "Bir komutun ciktisini sonraki komuta aktaran gorunen akis yapisidir."} if has_pipeline else {"terim": "api_call", "tanim": "Dis servise giden gorunen komut cagrisi."},
            ],
            "steps": [
                "Function: gorunen shell fonksiyonunun amacini ayir.",
                "Hazirlik: degisken, environment ve gerekli girdileri topla.",
                "Command/API: dis komut veya API cagrisi yapan satirlari belirle.",
                "Kontrol akisi: if benzeri satirlarin hangi sonucu denetledigini not et.",
            ],
            "examples": [
                "Komut ornegi: degisken hazirlanir, komut, API ve kontrol akisinin gorunen adimlari sirayla ilerler.",
                "Pipeline varsa veri bir komuttan digerine gorunen satirlarla aktarilir." if has_pipeline else "",
                "PowerShell ise Cmdlet ve environment satirlari bash komutlariyla karistirilmadan okunmalidir." if shell_label == "PowerShell" else "",
            ],
            "trap": "Tuzak: Ortam sonucu gorunmeden komutun kesin cikti verdigini varsaymak.",
            "mini_quiz": _anlamadim_quiz_from_fields(
                f"{symbol} shell parcasi komut ve API akisinin amacini gosterir.",
                "Bu shell blogu once degiskeni hazirlar, sonra komut veya API cagrisi yapar.",
                [{"terim": "command", "tanim": "Kabuk komutu"}],
                ["Function: shell fonksiyonunu ayir.", "Command/API: dis komutlari oku.", "Kontrol akisi: kosullari incele."],
            ),
            "tema_bazli_ornek": "",
            "alternatif_ornek": "",
            "function_purpose": f"{line_prefix}Bu {shell_label} fonksiyonu komutlari sirali sekilde calistirir, gerekli {'environment ve ' if has_env else ''}degiskenleri hazirlar ve gorunen kontrol akisina gore davranir.".strip(),
            "flow_summary": f"{line_prefix}function -> {'environment -> ' if has_env else ''}degisken hazirlama -> {'pipeline -> ' if has_pipeline else ''}command/api -> {'process -> ' if has_process else ''}kontrol akisi".strip(),
            "block_comments": _anlamadim_unique_texts(
                [
                    "Degisken blogu komut veya API cagrisi oncesi gereken degerleri hazirlar.",
                    "Dis cagrilar blogu gorunen komutlari ve varsa API akisina ait adimlari toplar.",
                    "Environment blogu PowerShell veya shell ortaminda sonraki komutlari etkileyecek degiskenleri ayirir." if has_env else "",
                    "Yan etki blogu Start-Process benzeri satirlarla harici surec veya gorunen yan etkiyi ayirir." if has_process else "",
                    "Kontrol blogu if/switch benzeri satirlarla hangi durumda devam edildigini ayirir." if re.search(r"^\s*(if|foreach|for|while|switch)\b", clean, flags=re.IGNORECASE | re.MULTILINE) else "",
                ],
                limit=4,
            ),
            "line_comments": _anlamadim_unique_texts(shell_line_comments, limit=9),
        }

    params_match = re.search(r"\bdef\s+[A-Za-z_][A-Za-z0-9_]*\(([^)]*)\)", first_line)
    params = [item.strip() for item in (params_match.group(1).split(",") if params_match else []) if item.strip() and item.strip() != "self"]
    has_condition = bool(re.search(r"^\s*(if|elif|else)\b", clean, flags=re.IGNORECASE | re.MULTILINE))
    has_loop = bool(re.search(r"^\s*(for|while)\b", clean, flags=re.IGNORECASE | re.MULTILINE))
    has_return = bool(re.search(r"^\s*return\b", clean, flags=re.IGNORECASE | re.MULTILINE))
    has_self = bool(re.search(r"\bself\.", clean))
    has_helper_call = bool(re.search(r"=\s*[A-Za-z_][A-Za-z0-9_\.]*\(", clean))
    purpose_label = "method" if subtype == "method" or has_self else "fonksiyon"
    block_comments = ["Temel akis blogu girdiyi isleyip sonraki adima hazirlar."]
    if has_helper_call:
        block_comments.append("Helper blogu ara sonucu ana akis icin uretir.")
    if has_condition:
        block_comments.append("Kosul blogu farkli girdi durumlari icin alternatif sonuc secimini netlestirir.")
    if has_loop:
        block_comments.append("Iterasyon blogu verinin her elemanina benzer islemi uygular.")
    line_comments = []
    for raw_line in lines:
        comment = _anlamadim_python_line_comment(raw_line, subtype=subtype, context=context)
        if comment:
            line_comments.append(comment)
    glossary = []
    if params:
        glossary.append({"terim": "girdi", "tanim": f"Fonksiyonun aldigi parametreler: {', '.join(params[:3])}."})
    if has_return:
        glossary.append({"terim": "return", "tanim": "Islenen sonucun cagran tarafa donduruldugu noktadir."})
    flow_parts = []
    if params:
        flow_parts.append("girdi")
    if has_helper_call:
        flow_parts.append("helper/ara islem")
    flow_parts.append("donusum")
    if has_condition:
        flow_parts.append("kosul")
    if has_loop:
        flow_parts.append("iterasyon")
    if has_self:
        flow_parts.append("state")
    if has_return:
        flow_parts.append("donus")
    examples = ["Fonksiyon ornegi: girdi once islenir, sonra return ile gorunen sonuc uretilir."]
    if has_helper_call:
        examples.append("Helper akisi: ara sonuc helper cagrisi ile uretilip sonraki kosul veya donuse tasinir.")
    if has_return:
        examples.append("Return mantigi: son satir islenmis degeri cagran tarafa geri verir.")
    subject = "input(girdi) veya mevcut state'i" if purpose_label == "method" else "input(girdi)"
    return {
        "one_liner": f"{symbol} {purpose_label}u girdiyi isleyip gorunen sonuca tasir.",
        "very_simple": (
            f"Bu {purpose_label}, girdiyi alip veri akisi boyunca gorunen islemleri uygular ve sonucu dondurur. "
            f"Kritik isimler: {', '.join(names[:4]) if names else symbol}."
        ),
        "glossary": glossary[:4],
        "steps": [
            f"Girdi: {', '.join(params[:3]) if params else 'gorunen parametreleri'} alip ilk donusumu ayir.",
            "Islem: ana veri donusumu, kosul veya iterasyon satirlarini takip et.",
            "Beklenen sonuc: return veya son cikti satirinin ne dondurdugunu not et.",
        ],
        "examples": examples[:3],
        "trap": "Tuzak: gorunmeyen veri tipi, harici durum veya yan etki uydurup akisi gereksiz genellestirmek.",
        "mini_quiz": _anlamadim_quiz_from_fields(
            f"{symbol} {purpose_label}u girdiyi isleyip gorunen sonuca tasir.",
            f"Bu {purpose_label}, girdiyi alip veri akisi boyunca gorunen islemleri uygular ve sonucu dondurur.",
            glossary[:4],
            [
                f"Girdi: {', '.join(params[:3]) if params else 'gorunen parametreleri'} alip ilk donusumu ayir.",
                "Islem: veri donusumu veya kosulu takip et.",
                "Beklenen sonuc: return satirini oku.",
            ],
        ),
        "tema_bazli_ornek": "",
        "alternatif_ornek": "",
        "function_purpose": (
            f"{line_prefix}{symbol} {purpose_label}u {subject} alir, ana islemi yapar"
            + (" ve kosula gore akisi degistirir" if has_condition else "")
            + (" ve sonucu dondurur." if has_return else ".")
        ).strip(),
        "flow_summary": f"{line_prefix}{' -> '.join(flow_parts)}".strip(),
        "block_comments": _anlamadim_unique_texts(block_comments, limit=4),
        "line_comments": _anlamadim_unique_texts(line_comments, limit=9),
    }


def _anlamadim_presentation_points(text: str) -> list[str]:
    lines = []
    for raw in str(text or "").replace("\r\n", "\n").splitlines():
        clean = _anlamadim_norm_text(re.sub(r"^Madde\s+\d+\s*:\s*", "", raw, flags=re.IGNORECASE))
        if clean:
            lines.append(clean)
        if len(lines) >= 4:
            break
    if not lines:
        sentences = _anlamadim_sentences(text)
        lines = sentences[:3]
    return lines[:4]


def _anlamadim_plain_text_importance(text: str, one_liner: str, chunk_context: dict | None) -> tuple[list[str], str]:
    context = dict(chunk_context or {})
    baslik = context.get("baslik") or context.get("slide_title") or ""
    sentences = _anlamadim_meaningful_sentences(text)
    support = sentences[1] if len(sentences) > 1 else ""
    if baslik:
        importance = f"Neden onemli: '{baslik}' basligi altindaki ana fikir sonraki detaylari yonlendiriyor."
    elif support:
        importance = f"Neden onemli: {_anlamadim_excerpt(support, limit=110)}"
    else:
        importance = f"Neden onemli: {one_liner}"

    confusion = (
        "Karisan nokta: tek bir cumleyi alip tum bolumun anlami sanmak."
        if not support
        else f"Karisan nokta: {_anlamadim_excerpt(support, limit=90)} cumlesini ana fikirden kopuk okumak."
    )
    return [importance, confusion], confusion


def _anlamadim_special_chunk_fallback(text: str, chunk_context: dict | None) -> dict | None:
    if not _special_chunk_fallbacks_enabled():
        return None

    context = dict(chunk_context or {})
    kind = str(context.get("kind") or "default")
    clean = _anlamadim_norm_text(text)
    if not clean:
        return None

    if kind == "table":
        cells = _anlamadim_table_cells(text)
        headers = list(context.get("header_preview") or []) or [
            cell for cell in cells[:4]
            if not _anlamadim_is_numeric_cell(cell)
        ][:4]
        numeric_cells = [cell for cell in cells if _anlamadim_is_numeric_cell(cell)][:4]
        baslik = context.get("sheet") or context.get("baslik") or "Bu tablo"
        one_liner = f"{baslik} icindeki hucreler birlikte okununca bu tablonun neyi gosterdigine dair kisa bir ozet veriyor."
        very_simple = (
            f"Bu tablo once neyin listelendigini soyluyor, sonra satir-sutun iliskisiyle degerleri okutuyor. "
            f"Kritik sutunlar: {', '.join(headers) if headers else 'gorunen ilk hucreler'}."
        )
        if numeric_cells:
            very_simple += f" One cikan degerler: {', '.join(numeric_cells)}."
            very_simple += " Bu sayilar tek basina degil, ait olduklari basliklarla birlikte yorumlanmali."
        return {
            "one_liner": one_liner,
            "very_simple": very_simple,
            "examples": [
                f"Bu tablo ne diyor: once {', '.join(headers) if headers else 'basliklari'} oku, sonra her satirin bu basliklara nasil oturduguna bak.",
                f"Onemli sutunlar: {', '.join(headers) if headers else 'gorunen ilk hucreler'}.",
                f"Dikkat ceken iliski: {', '.join(numeric_cells) if numeric_cells else 'sayisal ve etiket hucreleri birlikte yorumlanmali'}.",
            ],
            "trap": "Tuzak: Tek bir hucreyi koparip tum tablonun anlamiymis gibi yorumlamak.",
            "tema_bazli_ornek": "",
            "alternatif_ornek": "",
        }

    if kind == "code":
        return _anlamadim_code_payload(text, context)

    if kind == "visual":
        ocr_excerpt = _anlamadim_excerpt(clean, limit=100)
        return {
            "one_liner": "Bu gorsel parcasi once ana mesajini, sonra OCR ile cikan metin ipuclarini gosteriyor.",
            "very_simple": f"Gorselin ana amaci: tek bakista neyin anlatildigini gostermek. OCR ozeti varsa kisa aciklama su: {ocr_excerpt}",
            "examples": [
                "Gorselin ana amaci: basligi veya odak nesneyi once fark edip geri kalanini ona gore okumak.",
                f"OCR sonucu varsa ilk ipucu: {ocr_excerpt}",
            ],
            "trap": "Tuzak: OCR satirlarini tek tek okuyup gorselin ana baglamini kacirmak.",
            "tema_bazli_ornek": "",
            "alternatif_ornek": "",
        }

    if kind == "presentation":
        slide_title = context.get("slide_title") or context.get("baslik") or "Bu slayt"
        bullets = _anlamadim_presentation_points(text)
        excerpt = _anlamadim_excerpt(clean, limit=120)
        bullet_text = ", ".join(bullets[:3]) if bullets else excerpt
        return {
            "one_liner": f"{slide_title} slaydi ana mesajini kisa maddeler ve aciklama cumleleriyle veriyor.",
            "very_simple": (
                f"Bu slaytin vermek istedigi mesaj su: once basligi yakala, sonra maddelerin ayni fikri nasil destekledigine bak. "
                f"Onemli maddeler: {bullet_text}."
            ),
            "examples": [
                f"Slaytin ana mesaji: {slide_title}",
                f"Kisa aciklama: {excerpt}",
                f"Onemli maddeler: {bullet_text}",
            ],
            "trap": "Tuzak: Her bullet'i ayri konu sanip slaytin tek ana mesajini kacirmak veya eksik kalan noktayi doldururken uydurmak.",
            "tema_bazli_ornek": "",
            "alternatif_ornek": "",
        }

    return None


def _anlamadim_example_text(theme: str, chunk_context: dict, one_liner: str) -> str:
    theme = str(theme or "genel").strip().lower()
    theme_label = _ANLAMADIM_THEME_LABELS.get(theme, _ANLAMADIM_THEME_LABELS["genel"])
    kind = str((chunk_context or {}).get("kind") or "default")
    if kind == "table":
        return f"{theme_label} gibi dusun: once basliklari gorur, sonra her satiri o basliklara gore anlarsin. Burada da fikir bu: {one_liner}"
    if kind == "code":
        return f"{theme_label} gibi dusun: belirli bir girdiyi alip adim adim sonucu ureten bir rutin var. Bu parcada da ana akis su: {one_liner}"
    if kind == "visual":
        return f"{theme_label} gibi dusun: once sahnenin ana isaretini gorursun, sonra detaylari onun etrafinda okursun. Buradaki ana fikir: {one_liner}"
    if kind == "presentation":
        return f"{theme_label} gibi dusun: once slaytin tek ana mesajini yakalarsin, sonra maddeleri o mesajin kaniti gibi okursun. Buradaki mesaj su: {one_liner}"
    return f"{theme_label} gibi dusun: once ana hedefi anlarsin, sonra detaylar o hedefe hizmet eder. Bu parcada da mesaj su: {one_liner}"


def _anlamadim_themed_examples(one_liner: str, tema: str, chunk_context: dict | None) -> dict:
    if not _themed_examples_enabled():
        return {"tema_bazli_ornek": "", "alternatif_ornek": ""}

    primary_theme = str(tema or "genel").strip().lower() or "genel"
    if primary_theme not in _ANLAMADIM_THEME_LABELS:
        primary_theme = "genel"
    secondary_theme = _ANLAMADIM_ALT_THEME.get(primary_theme, "genel")
    context = dict(chunk_context or {})
    return {
        "tema_bazli_ornek": _anlamadim_example_text(primary_theme, context, one_liner),
        "alternatif_ornek": _anlamadim_example_text(secondary_theme, context, one_liner),
    }


def _anlamadim_build_glossary(text: str) -> list[dict]:
    glossary = []
    for term in _anlamadim_extract_terms(text):
        definition = _anlamadim_term_definition(term, text)
        if term and definition:
            glossary.append({"terim": term, "tanim": definition})
    return glossary[:4]


def _anlamadim_is_weak_text(value: str, min_len: int = 18) -> bool:
    clean = _anlamadim_norm_text(value)
    if _anlamadim_is_noise_text(clean, min_len=min(8, min_len)):
        return True
    if len(clean) < min_len:
        return True

    lowered = clean.lower()
    return any(pattern in lowered for pattern in _ANLAMADIM_ZAYIF_KALIPLAR)


def _anlamadim_is_short_meaningful_note(text: str) -> bool:
    clean = _anlamadim_norm_text(text)
    if len(clean) < 10:
        return False
    if _pdf_imza_kokuyor_mu(clean):
        return False

    raw_words = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]+", clean)
    if len(raw_words) < 2:
        return False

    has_acronym = bool(re.search(r"\b[A-ZÇĞİÖŞÜ]{2,}[A-Z0-9ÇĞİÖŞÜ]*\b", text or ""))
    has_ellipsis = clean.endswith("...")
    has_long_word = any(len(word) >= 5 for word in raw_words)
    has_verb_hint = any(_ANLAMADIM_FIIL_IPUCU_RE.search(word.lower()) for word in raw_words)

    return has_long_word and (has_acronym or has_ellipsis or has_verb_hint)


def _anlamadim_is_meaningful_text(text: str) -> bool:
    clean = _anlamadim_norm_text(text)
    if _anlamadim_is_noise_text(clean, min_len=8):
        return False
    if _pdf_imza_kokuyor_mu(clean):
        return False
    if len(clean) < 18:
        return _anlamadim_is_short_meaningful_note(text)
    return len(_anlamadim_lower_words(clean)) >= 3


def _anlamadim_steps_from_text(text: str, one_liner: str, glossary: list[dict]) -> list[str]:
    steps = []
    if one_liner:
        steps.append(f"Once ana fikri yakala: {one_liner}")
    if glossary:
        first = glossary[0]
        steps.append(f"Sonra '{first['terim']}' terimini metindeki baglamiyla eslestir: {first['tanim']}")

    sentences = _anlamadim_meaningful_sentences(text)
    if len(sentences) > 1:
        steps.append(f"Ardindan ikinci fikri kontrol et: {_anlamadim_excerpt(sentences[1], limit=110)}")
    elif text:
        steps.append(f"Son olarak parcayi su cümleyle tekrar et: {_anlamadim_excerpt(text, limit=110)}")

    while len(steps) < 3:
        steps.append("Metindeki ana kavrami ve bunun ne ise yaradigini tek cümlede tekrar et.")

    return steps[:4]


def _anlamadim_examples_from_text(text: str, one_liner: str, glossary: list[dict]) -> list[str]:
    examples = []
    clean_upper = _anlamadim_norm_text(text).upper()
    if "ATP" in clean_upper:
        examples.extend([
            "ATP'yi, hucrenin kullandigi kucuk bir enerji pili gibi dusunebilirsin.",
            "Kaslarin calisirken ATP'den gelen enerjiyi kullanir.",
        ])
    if one_liner and not _anlamadim_is_weak_text(one_liner, min_len=8):
        examples.append(f"Gundelik dilde: {one_liner}")
    if glossary:
        first = glossary[0]
        examples.append(f"Parcadaki '{first['terim']}' ifadesini, konunun odak etiketi gibi dusun.")

    sentences = _anlamadim_meaningful_sentences(text)
    if sentences:
        examples.append(f"Metinden somut ornek: {_anlamadim_excerpt(sentences[0], limit=120)}")

    cleaned = []
    for item in examples:
        item = _anlamadim_norm_text(item)
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned[:3]


def _anlamadim_trap_from_text(text: str, glossary: list[dict]) -> str:
    if glossary:
        first = glossary[0]["terim"]
        return f"Tuzak: '{first}' terimini tek basina ezberleyip, metindeki gorevini kacirmak."
    if text:
        return "Tuzak: Metindeki tek bir cumleyi alip parcadaki ana fikrin tamami sanmak."
    return "Tuzak: Baglam olmadan teknik anlam cikarmaya calismak."


def _anlamadim_quiz_from_fields(one_liner: str, very_simple: str, glossary: list[dict], steps: list[str]) -> list[dict]:
    quiz = [
        {"q": "Bu parcanin ana fikri nedir?", "a": one_liner},
        {"q": "Bu parcayi cok basit dille nasil anlatirsin?", "a": very_simple},
    ]

    if glossary:
        first = glossary[0]
        quiz.append({"q": f"'{first['terim']}' bu parcanin neresinde onemli?", "a": first["tanim"]})
    elif steps:
        quiz.append({"q": "Parcayi anlarken hangi adimi atlamamalisin?", "a": steps[0]})
    else:
        quiz.append({"q": "Bu metni anlarken neye dikkat etmelisin?", "a": one_liner or very_simple})

    return quiz[:3]


def _build_anlamadim_fallback(
    secili_metin: str,
    tema: str,
    tarz: str,
    seviye: str,
    *,
    chunk_context: dict | None = None,
) -> dict:
    raw_text = str(secili_metin or "")
    text = _anlamadim_norm_text(raw_text)
    chunk_context = dict(chunk_context or {})
    if str(chunk_context.get("kind") or "default") == "code":
        special = _anlamadim_special_chunk_fallback(raw_text, chunk_context)
        if special:
            out = dict(special)
            out["examples"] = _anlamadim_merge_list_items(out.get("examples"), [], min_len=14, max_items=4)
            out["block_comments"] = _anlamadim_merge_list_items(out.get("block_comments"), [], min_len=12, max_items=4)
            out["line_comments"] = _anlamadim_merge_list_items(out.get("line_comments"), [], min_len=12, max_items=9)
            out["function_purpose"] = _anlamadim_norm_text(out.get("function_purpose") or "")
            out["flow_summary"] = _anlamadim_norm_text(out.get("flow_summary") or "")
            themed = _anlamadim_themed_examples(out.get("one_liner", ""), tema, chunk_context)
            out["tema_bazli_ornek"] = themed["tema_bazli_ornek"]
            out["alternatif_ornek"] = themed["alternatif_ornek"]
            if themed["tema_bazli_ornek"]:
                out["examples"] = _anlamadim_merge_list_items(
                    out.get("examples"),
                    [themed["tema_bazli_ornek"], themed["alternatif_ornek"]],
                    min_len=14,
                    max_items=4,
                )
            return out

    structured = None
    if str(chunk_context.get("kind") or "default") != "code":
        # Kisa/yapisal satir fallback'i kod parcalarini erken yutmasin; kod icin
        # daha asagidaki code-specific fallback daha zengin ve acceptance'a uygun.
        structured = _anlamadim_build_structured_fallback(text)
    if structured:
        themed = _anlamadim_themed_examples(structured.get("one_liner", ""), tema, chunk_context)
        structured["tema_bazli_ornek"] = themed["tema_bazli_ornek"]
        structured["alternatif_ornek"] = themed["alternatif_ornek"]
        if themed["tema_bazli_ornek"]:
            structured["examples"] = list(structured.get("examples") or []) + [themed["tema_bazli_ornek"]]
        return structured

    glossary = _anlamadim_build_glossary(text) if text else []
    meaningful_sentences = _anlamadim_meaningful_sentences(text)
    first_sentence = meaningful_sentences[:1]
    summary_source = first_sentence[0] if first_sentence else ""
    if summary_source and len(_anlamadim_words(text)) <= 4 and glossary:
        one_liner = f"Bu kisa parca, '{glossary[0]['terim']}' odakli bir not veya etiket veriyor."
    else:
        one_liner = _anlamadim_excerpt(summary_source, limit=150) if summary_source else ""

    if _anlamadim_is_weak_text(one_liner, min_len=8):
        if glossary:
            one_liner = f"Bu parca, {glossary[0]['terim']} kavraminin metindeki temel gorevini acikliyor."
        elif meaningful_sentences:
            one_liner = _anlamadim_excerpt(meaningful_sentences[0], limit=150)
        else:
            one_liner = "Bu parca, secili metindeki ana fikri sade bir sekilde aciklamayi hedefliyor."

    if text:
        very_simple = _anlamadim_build_very_simple(text, one_liner, glossary)
    else:
        very_simple = "Metin bos oldugu icin basit anlatim uretilemedi."

    steps = _anlamadim_steps_from_text(text, one_liner, glossary)
    examples = _anlamadim_examples_from_text(text, one_liner, glossary)
    trap = _anlamadim_trap_from_text(text, glossary)
    mini_quiz = _anlamadim_quiz_from_fields(one_liner, very_simple, glossary, steps)
    special = _anlamadim_special_chunk_fallback(text, chunk_context)
    function_purpose = ""
    flow_summary = ""
    block_comments = []
    line_comments = []
    if special:
        special_one_liner = _anlamadim_norm_text(special.get("one_liner") or "")
        special_very_simple = _anlamadim_norm_text(special.get("very_simple") or "")
        special_trap = _anlamadim_norm_text(special.get("trap") or "")
        special_glossary = special.get("glossary") or []
        special_steps = special.get("steps") or []
        special_examples = special.get("examples") or []
        special_quiz = special.get("mini_quiz") or []
        function_purpose = _anlamadim_norm_text(special.get("function_purpose") or "")
        flow_summary = _anlamadim_norm_text(special.get("flow_summary") or "")
        block_comments = _anlamadim_merge_list_items(special.get("block_comments"), [], min_len=12, max_items=4)
        line_comments = _anlamadim_merge_list_items(special.get("line_comments"), [], min_len=12, max_items=6)

        if str(chunk_context.get("kind") or "default") == "code" and special_one_liner:
            one_liner = special_one_liner
        elif _anlamadim_is_weak_text(one_liner, min_len=18):
            one_liner = special_one_liner or one_liner

        if str(chunk_context.get("kind") or "default") == "code" and special_very_simple:
            very_simple = special_very_simple
        else:
            very_simple = special_very_simple or very_simple

        if str(chunk_context.get("kind") or "default") == "code" and special_glossary:
            glossary = special_glossary[:4]
        elif len(glossary) < 1 and special_glossary:
            glossary = special_glossary[:4]

        if str(chunk_context.get("kind") or "default") == "code" and special_steps:
            steps = _anlamadim_merge_list_items(special_steps, [], min_len=14, max_items=4)
        elif len(steps) < 2 and special_steps:
            steps = _anlamadim_merge_list_items(special_steps, steps, min_len=14, max_items=4)

        if str(chunk_context.get("kind") or "default") == "code" and special_examples:
            examples = _anlamadim_merge_list_items(special_examples, [], min_len=14, max_items=4)
        else:
            examples = _anlamadim_merge_list_items(
                special_examples,
                examples,
                min_len=14,
                max_items=4,
            )

        if str(chunk_context.get("kind") or "default") == "code" and special_trap:
            trap = special_trap
        elif _anlamadim_is_weak_text(trap, min_len=18):
            trap = special_trap or trap

        if str(chunk_context.get("kind") or "default") == "code" and special_quiz:
            mini_quiz = _anlamadim_merge_quiz(special_quiz, [], one_liner, very_simple, glossary, steps)
        elif len(mini_quiz) < 3 and special_quiz:
            mini_quiz = _anlamadim_merge_quiz(special_quiz, mini_quiz, one_liner, very_simple, glossary, steps)
    elif str(chunk_context.get("kind") or "default") == "default":
        plain_text_examples, plain_trap = _anlamadim_plain_text_importance(text, one_liner, chunk_context)
        examples = _anlamadim_merge_list_items(
            examples,
            plain_text_examples,
            min_len=14,
            max_items=4,
        )
        if _anlamadim_is_weak_text(trap, min_len=18):
            trap = plain_trap

    themed = _anlamadim_themed_examples(one_liner, tema, chunk_context)
    if themed["tema_bazli_ornek"]:
        examples = _anlamadim_merge_list_items(
            examples,
            [themed["tema_bazli_ornek"], themed["alternatif_ornek"]],
            min_len=14,
            max_items=4,
        )

    return {
        "one_liner": one_liner,
        "very_simple": very_simple,
        "glossary": glossary,
        "steps": steps,
        "examples": examples,
        "trap": trap,
        "mini_quiz": mini_quiz,
        "function_purpose": function_purpose,
        "flow_summary": flow_summary,
        "block_comments": block_comments,
        "line_comments": line_comments,
        "tema_bazli_ornek": themed["tema_bazli_ornek"],
        "alternatif_ornek": themed["alternatif_ornek"],
    }


def _fallback_sections_v2(
    secili_metin: str,
    tema: str,
    tarz: str,
    seviye: str,
    *,
    chunk_context: dict | None = None,
) -> dict:
    """V2 fallback motorunu tek satirlik sarmalla eski cagrilar icin gorunur tutar."""
    return _build_anlamadim_fallback(secili_metin, tema, tarz, seviye, chunk_context=chunk_context)

def _seviye_hesapla(xp: int) -> int:
    xp = max(0, int(xp or 0))
    # Basit MVP sistemi:
    # 0-99 => 1
    # 100-199 => 2
    # 200-299 => 3 ...
    return (xp // 100) + 1


def _unvan_hesapla(seviye: int) -> str:
    if seviye >= 10:
        return "Boss Kırıcı"
    if seviye >= 7:
        return "Kanıt Avcısı"
    if seviye >= 5:
        return "Terim Ustası"
    if seviye >= 3:
        return "Doc Kaşifi"
    return "Yeni Başlayan"


def _profil_xp_ekle(user, xp_eklenecek: int):
    profil, _ = Profil.objects.get_or_create(user=user)

    eski_xp = int(profil.xp or 0)
    yeni_xp = eski_xp + max(0, int(xp_eklenecek or 0))

    profil.xp = yeni_xp
    profil.seviye = _seviye_hesapla(yeni_xp)
    profil.unvan = _unvan_hesapla(profil.seviye)
    profil.save(update_fields=["xp", "seviye", "unvan"])

    return profil
def _normalize_words(text: str):
    text = (text or "").lower()
    words = re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9_]+", text)
    stop = {
        "ve", "ile", "bir", "bu", "şu", "da", "de", "için", "ama", "gibi",
        "the", "and", "or", "to", "of", "in", "is", "a", "an"
    }
    return [w for w in words if len(w) > 2 and w not in stop]
def _anlat_kontrol_prompt(kaynak_metin: str, ogrenci_yanit: str) -> str:
    kaynak_metin = (kaynak_metin or "").strip()
    ogrenci_yanit = (ogrenci_yanit or "").strip()

    return f"""
GÖREV:
Öğrencinin kendi cümlesiyle yaptığı açıklamayı, verilen kaynak parçaya göre değerlendir.

KURAL:
- Sadece kaynak parçaya göre değerlendir.
- Uydurma yapma.
- Türkçe yaz.
- ÇIKTIYI SADECE JSON ver.
- JSON dışında hiçbir şey yazma.

JSON ŞEMASI:
{{
  "puan": 0,
  "dogru_kisimlar": ["..."],
  "yanlislar": ["..."],
  "eksikler": ["..."],
  "geri_bildirim": "..."
}}

PUANLAMA:
- 0-39: ana fikir kaçmış
- 40-69: temel fikir var ama eksik
- 70-89: büyük ölçüde doğru
- 90-100: çok iyi ve net

KAYNAK PARÇA:
\"\"\"
{kaynak_metin}
\"\"\"

ÖĞRENCİ YANITI:
\"\"\"
{ogrenci_yanit}
\"\"\"
""".strip()
def _boss_cevap_prompt(
    kaynak_metin: str,
    gorev: str,
    ogrenci_yanit: str,
    difficulty_meta: dict | None = None,
) -> str:
    kaynak_metin = (kaynak_metin or "").strip()
    gorev = (gorev or "").strip()
    ogrenci_yanit = (ogrenci_yanit or "").strip()
    difficulty_meta = difficulty_meta or {}
    difficulty_note = str(difficulty_meta.get("boss_instruction") or "").strip()
    difficulty_band = str(difficulty_meta.get("boss_difficulty_band") or "medium").strip()

    return f"""
GÖREV:
Öğrencinin boss görevine verdiği cevabı, kaynak parçaya göre değerlendir.

KURAL:
- Sadece kaynak parçaya göre değerlendir.
- Uydurma yapma.
- Türkçe yaz.
- ÇIKTIYI SADECE JSON ver.
- JSON dışında hiçbir şey yazma.
- Degerlendirme sertligini boss zorluk baglamina gore ayarla.

JSON ŞEMASI:
{{
  "puan": 0,
  "dogru_kisimlar": ["..."],
  "yanlislar": ["..."],
  "eksikler": ["..."],
  "geri_bildirim": "..."
}}

PUANLAMA:
- 0-39: görev başarısız
- 40-69: kısmen doğru
- 70-89: iyi
- 90-100: çok iyi

BOSS ZORLUK BAGLAMI:
- seviye: {difficulty_band}
- not: {difficulty_note or "Standart orta zorlukta degerlendir."}

KAYNAK PARÇA:
\"\"\"
{kaynak_metin}
\"\"\"

BOSS GÖREVİ:
\"\"\"
{gorev}
\"\"\"

ÖĞRENCİ CEVABI:
\"\"\"
{ogrenci_yanit}
\"\"\"
""".strip()


def _boss_fallback_degerlendir(kaynak_metin: str, ogrenci_yanit: str):
    # şimdilik anlat-kontrol fallback'ini kullanıyoruz
    return _anlat_kontrol_fallback(kaynak_metin, ogrenci_yanit)


def _xp_hesapla(puan: int) -> int:
    puan = max(0, min(int(puan or 0), 100))
    if puan >= 90:
        return 30
    if puan >= 70:
        return 20
    if puan >= 40:
        return 10
    return 0
def _safe_anlat_kontrol_obj(obj):
    if not isinstance(obj, dict):
        return None

    puan = obj.get("puan", 0)
    try:
        puan = int(puan)
    except Exception:
        puan = 0

    puan = max(0, min(100, puan))

    def _as_list(v):
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []

    geri = str(obj.get("geri_bildirim", "") or "").strip()

    return {
        "puan": puan,
        "dogru_kisimlar": _as_list(obj.get("dogru_kisimlar")),
        "yanlislar": _as_list(obj.get("yanlislar")),
        "eksikler": _as_list(obj.get("eksikler")),
        "geri_bildirim": geri,
    }
def _anlat_kontrol_fallback(kaynak_metin: str, ogrenci_yanit: str):
    src_words = _normalize_words(kaynak_metin)
    ans_words = _normalize_words(ogrenci_yanit)

    src_unique = list(dict.fromkeys(src_words))
    ans_set = set(ans_words)

    ortak = [w for w in src_unique if w in ans_set]
    eksik = [w for w in src_unique if w not in ans_set][:8]

    if not src_unique:
        puan = 0
    else:
        puan = round((len(ortak) / max(1, len(src_unique))) * 100)

    if puan >= 75:
        geri = "Genel olarak doğru anlatmışsın."
    elif puan >= 45:
        geri = "Temel fikir var ama bazı kritik noktalar eksik."
    else:
        geri = "Ana fikir ve kritik terimler yeterince yakalanmamış."

    dogru_kisimlar = []
    if ortak:
        dogru_kisimlar.append(
            "Yanıtında şu anahtar kavramları yakalamışsın: " + ", ".join(ortak[:8])
        )

    yanlislar = []
    if len(ans_words) < 3:
        yanlislar.append("Yanıt çok kısa, değerlendirme için biraz daha açman gerek.")
    if puan < 40:
        yanlislar.append("Kaynak parçadaki ana fikir yeterince görünmüyor.")

    eksikler = []
    if eksik:
        eksikler.append("Şu kavramları da katarsan daha güçlü olur: " + ", ".join(eksik))

    return {
        "puan": puan,
        "dogru_kisimlar": dogru_kisimlar,
        "yanlislar": yanlislar,
        "eksikler": eksikler,
        "geri_bildirim": geri,
    }
class KendiCumlenleAnlatKontrolAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, parca_id: int):
        parca = Parca.objects.select_related("dokuman").filter(
            id=parca_id,
            dokuman__owner=request.user
        ).first()

        if not parca:
            return Response({"detail": "Parça yok"}, status=404)

        ogrenci_yanit = (request.data.get("yanit") or "").strip()
        if not ogrenci_yanit:
            return Response({"detail": "yanit zorunlu"}, status=400)

        kaynak_metin = parca.metin or ""

        # 1) Her zaman fallback hazır
        fallback = _anlat_kontrol_fallback(kaynak_metin, ogrenci_yanit)
        sonuc = fallback
        mod = "fallback"

        # 2) LLM dene
        try:
            prompt = _anlat_kontrol_prompt(kaynak_metin, ogrenci_yanit)

            raw = chat(
                [{"role": "user", "content": prompt}],
                max_tokens=ai2_scope_icin_max_token("GRADING")
            )

            obj = extract_json(raw)
            parsed = _safe_anlat_kontrol_obj(obj)

            if parsed and parsed.get("geri_bildirim"):
                llm_score = int(parsed.get("puan", 0))
                fb_score = int(fallback.get("puan", 0))

                llm_is_weak = (
                    (llm_score == 0 and fb_score >= 30)
                    or
                    (
                        not parsed.get("dogru_kisimlar")
                        and not parsed.get("eksikler")
                        and fb_score >= 30
                    )
                )

                if llm_is_weak:
                    sonuc = fallback
                    mod = "fallback_guard"
                else:
                    sonuc = {
                        "puan": max(llm_score, fb_score),
                        "dogru_kisimlar": parsed.get("dogru_kisimlar") or fallback.get("dogru_kisimlar", []),
                        "yanlislar": parsed.get("yanlislar") or fallback.get("yanlislar", []),
                        "eksikler": parsed.get("eksikler") or fallback.get("eksikler", []),
                        "geri_bildirim": parsed.get("geri_bildirim") or fallback.get("geri_bildirim", ""),
                    }
                    mod = "llm_hybrid"

        except Exception:
            sonuc = fallback
            mod = "fallback"

        return Response({
            "parca": {
                "id": parca.id,
                "dokuman_id": parca.dokuman_id,
                "adres": getattr(parca, "adres", "") or "",
                "snippet": _guvenli_sinyal_metni(kaynak_metin, label="kaynak"),
            },
            "ogrenci_yanit": _guvenli_sinyal_metni(ogrenci_yanit, label="ogrenci_yaniti"),
            "degerlendirme": sonuc,
            "kanit": {
                "parca_id": parca.id,
                "adres": getattr(parca, "adres", "") or "",
                "snippet": _guvenli_sinyal_metni(kaynak_metin, label="kanit"),
            },
            "mod": mod,
            "debug_scores": {
                "fallback_puan": fallback.get("puan", 0),
                "final_puan": sonuc.get("puan", 0),
            }
        })
def _extract_sections(txt: str):
    """
    LLM çıktısından zengin anlatım bölümlerini çıkarır.

    Destek:
    1) Tag formatı:
       [ONE_LINER]...[/ONE_LINER] ... [MINI_QUIZ]...[/MINI_QUIZ]

    2) Başlık formatı:
       OZET1: ...
       SOZLUK: ...
       ADIMLAR: ...
       ORNEKLER: ...
       TUZAK: ...
       MINI_TEST: ...

    3) JSON formatı (opsiyonel):
       {"one_liner": "...", "glossary":[...], ...}
    """
    import re
    import json

    txt = (txt or "").strip()

    out = {
        "one_liner": "",
        "very_simple": "",
        "glossary": [],   # [{"terim": "...", "tanim": "..."}]
        "steps": [],      # ["..."]
        "examples": [],   # ["..."]
        "trap": "",
        "mini_quiz": [],  # [{"q": "...", "a": "..."}] veya {"q":"..","a":"..","dogru":"..","secenekler":{...}}
    }

    # -----------------------------
    # 0) JSON geldiyse direkt parse et
    # -----------------------------
    if txt and txt[:1] in "{[":
        try:
            j = json.loads(txt)
            if isinstance(j, dict):
                # doğrudan map
                out["one_liner"] = (j.get("one_liner") or j.get("ONE_LINER") or "").strip()
                out["very_simple"] = (j.get("very_simple") or j.get("VERY_SIMPLE") or "").strip()
                out["trap"] = (j.get("trap") or j.get("TRAP") or "").strip()

                g = j.get("glossary") or j.get("GLOSSARY") or []
                if isinstance(g, list):
                    out["glossary"] = [
                        {"terim": (x.get("terim") or x.get("term") or "").strip(),
                         "tanim": (x.get("tanim") or x.get("def") or x.get("definition") or "").strip()}
                        for x in g if isinstance(x, dict)
                    ]

                st = j.get("steps") or j.get("STEPS") or []
                if isinstance(st, list):
                    out["steps"] = [str(x).strip() for x in st if str(x).strip()]

                ex = j.get("examples") or j.get("EXAMPLES") or []
                if isinstance(ex, list):
                    out["examples"] = [str(x).strip() for x in ex if str(x).strip()]

                mq = j.get("mini_quiz") or j.get("MINI_QUIZ") or j.get("mini_test") or []
                if isinstance(mq, list):
                    cleaned = []
                    for x in mq:
                        if isinstance(x, dict):
                            cleaned.append({k: v for k, v in x.items()})
                        else:
                            cleaned.append({"q": str(x).strip(), "a": ""})
                    out["mini_quiz"] = cleaned

                return out
        except Exception:
            pass

    # -----------------------------
    # Helpers: satırdan liste çıkar
    # -----------------------------
    def clean_list_lines(block: str):
        items = []
        for ln in (block or "").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            ln = re.sub(r"^[-*•]\s*", "", ln)          # bullet
            ln = re.sub(r"^\d+[\)\.]\s*", "", ln)      # 1) / 1.
            ln = ln.strip()
            if ln:
                items.append(ln)
        return items

    def parse_glossary(block: str):
        gl = []
        for ln in (block or "").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            ln = ln.strip("-*• \t")

            # farklı ayraçları destekle: ":" | " - " | " – " | " — " | "=" | "->"
            if ":" in ln:
                term, defi = ln.split(":", 1)
            elif "->" in ln:
                term, defi = ln.split("->", 1)
            elif "=" in ln:
                term, defi = ln.split("=", 1)
            else:
                # dash türleri
                m = re.split(r"\s[-–—]\s", ln, maxsplit=1)
                if len(m) == 2:
                    term, defi = m[0], m[1]
                else:
                    continue

            term = term.strip()
            defi = defi.strip()
            if term and defi:
                gl.append({"terim": term, "tanim": defi})
        return gl

    def parse_quiz(block: str):
        qlist = []
        b = (block or "").strip()
        if not b:
            return qlist

        # (1) Q: ... A: ... (çoklu blok)
        qa_pat = re.compile(r"Q\s*:\s*(.*?)\s*A\s*:\s*(.*?)(?=\n\s*Q\s*:|\Z)", flags=re.S | re.I)
        for m in qa_pat.finditer(b):
            q = (m.group(1) or "").strip()
            a = (m.group(2) or "").strip()
            if q:
                qlist.append({"q": q, "a": a})

        if qlist:
            return qlist

        # (2) Tek satır / çoktan seçmeli satırları
        for ln in b.splitlines():
            ln = ln.strip()
            if not ln:
                continue

            ln2 = re.sub(r"^\d+[\)\.]\s*", "", ln).strip()

            dogru = ""
            m = re.search(r"(doğru|dogru)\s*[:=]\s*([A-D])", ln2, flags=re.I)
            if m:
                dogru = m.group(2).upper()
                ln2 = re.sub(r"(doğru|dogru)\s*[:=]\s*[A-D].*$", "", ln2, flags=re.I).strip()

            secenekler = {}
            # A) ... B) ... C) ... D)
            opt_pat = re.compile(r"\b([A-D])\)\s*(.*?)(?=\s+[A-D]\)|\Z)", flags=re.I)
            opts = opt_pat.findall(ln2)

            if opts:
                for k, v in opts:
                    secenekler[k.upper()] = v.strip()
                soru_txt = re.split(r"\bA\)\s*", ln2, maxsplit=1, flags=re.I)[0].strip()
                qlist.append({"q": soru_txt, "a": "", "dogru": dogru, "secenekler": secenekler})
            else:
                qlist.append({"q": ln2, "a": "", "dogru": dogru})

        return qlist

    # -----------------------------
    # 1) Tag'li format: [ONE_LINER]...[/ONE_LINER]
    # -----------------------------
    TAGS = ["ONE_LINER", "VERY_SIMPLE", "GLOSSARY", "STEPS", "EXAMPLES", "TRAP", "MINI_QUIZ"]

    def has_tag(tag: str) -> bool:
        return re.search(rf"\[{re.escape(tag)}\]", txt, flags=re.I) is not None

    def between(tag: str) -> str:
        # [TAG] ... [/TAG]  (boşluk/newline toleranslı)
        m = re.search(
            rf"\[{re.escape(tag)}\]\s*(.*?)\s*\[\/\s*{re.escape(tag)}\s*\]",
            txt,
            flags=re.S | re.I,
        )
        return (m.group(1).strip() if m else "")

    tag_present = any(has_tag(t) for t in TAGS)

    if tag_present:
        out["one_liner"] = between("ONE_LINER")
        out["very_simple"] = between("VERY_SIMPLE")
        out["trap"] = between("TRAP")
        out["glossary"] = parse_glossary(between("GLOSSARY"))
        out["steps"] = clean_list_lines(between("STEPS"))
        out["examples"] = clean_list_lines(between("EXAMPLES"))
        out["mini_quiz"] = parse_quiz(between("MINI_QUIZ"))
        # Eğer bazıları boş kaldıysa aşağıdaki heading parser'la tamamlamaya devam edeceğiz.

    # -----------------------------
    # 2) Tag yoksa (veya tag var ama eksik): "BAŞLIK:" formatı
    # -----------------------------
    sections = {}
    header_re = re.compile(r"^\s*([A-ZÇĞİÖŞÜ0-9_ ]{3,})\s*:\s*(.*)\s*$")

    current = None
    buf = []

    def flush():
        nonlocal current, buf
        if current is not None:
            sections[current] = ("\n".join(buf)).strip()
        current = None
        buf = []

    for line in txt.splitlines():
        m = header_re.match(line)
        if m:
            flush()
            current = m.group(1).strip()
            first = (m.group(2) or "").strip()
            if first:
                buf.append(first)
        else:
            if current is not None:
                buf.append(line)
    flush()

    ALIASES = {
        "one_liner": ["OZET1", "ÖZET1", "TEK_CUMLE", "TEK CUMLE", "ONE_LINER"],
        "very_simple": ["COK_BASIT", "ÇOK_BASİT", "COK BASIT", "ÇOK BASİT", "VERY_SIMPLE"],
        "glossary": ["SOZLUK", "SÖZLÜK", "GLOSSARY"],
        "steps": ["ADIMLAR", "STEPS"],
        "examples": ["ORNEKLER", "ÖRNEKLER", "EXAMPLES"],
        "trap": ["TUZAK", "TUZAK_UYARI", "TRAP"],
        "mini_quiz": ["MINI_TEST", "MİNİ_TEST", "MINI QUIZ", "MINI_QUIZ"],
    }

    def grab_many(keys):
        for k in keys:
            v = sections.get(k, "")
            if v and v.strip():
                return v.strip()
        return ""

    # Tag ile geleni ezmemek için boşsa doldur
    if not out["one_liner"]:
        out["one_liner"] = grab_many(ALIASES["one_liner"])
    if not out["very_simple"]:
        out["very_simple"] = grab_many(ALIASES["very_simple"])
    if not out["trap"]:
        out["trap"] = grab_many(ALIASES["trap"])

    if not out["glossary"]:
        out["glossary"] = parse_glossary(grab_many(ALIASES["glossary"]))
    if not out["steps"]:
        out["steps"] = clean_list_lines(grab_many(ALIASES["steps"]))
    if not out["examples"]:
        out["examples"] = clean_list_lines(grab_many(ALIASES["examples"]))
    if not out["mini_quiz"]:
        out["mini_quiz"] = parse_quiz(grab_many(ALIASES["mini_quiz"]))

    return out
def _tr_fix(s: str) -> str:
    if not s:
        return s
    fixes = {
        "Yoghun": "Yoğun",
        "yoghun": "yoğun",
        "hoghun": "yoğun",
        "Terimlerinhoghunluğunu": "Terimlerin yoğunluğunu",
        "terimlerinhoghunluğunu": "terimlerin yoğunluğunu",
        "Terimlerinhoghunluğu": "Terimlerin yoğunluğu",
        "terimlerinhoghunluğu": "terimlerin yoğunluğu",
    }
    for a, b in fixes.items():
        s = s.replace(a, b)
    return s


def _anlamadim_clean_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _tr_fix(value.strip())
    return _tr_fix(str(value).strip())


def _anlamadim_coerce_list_items(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [_anlamadim_clean_str(item) for item in value if _anlamadim_clean_str(item)]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        text = re.sub(r"(?m)^\s*\d+[.)]\s*", "", text)
        parts = re.split(r"\n+|(?<!\d)\s*;\s*|\s*[-•]\s+", text)
        return [_anlamadim_clean_str(item) for item in parts if _anlamadim_clean_str(item)]
    return [_anlamadim_clean_str(value)] if _anlamadim_clean_str(value) else []


def _anlamadim_coerce_glossary_items(value) -> list[dict]:
    if not value:
        return []
    if isinstance(value, dict):
        return [
            {"terim": _anlamadim_clean_str(term), "tanim": _anlamadim_clean_str(definition)}
            for term, definition in value.items()
            if _anlamadim_clean_str(term) and _anlamadim_clean_str(definition)
        ]
    if isinstance(value, str):
        items = []
        for line in re.split(r"\n+|(?<!\d)\s*;\s*", value):
            line = _anlamadim_clean_str(line.lstrip("-•"))
            if not line:
                continue
            if ":" in line:
                term, definition = line.split(":", 1)
                items.append({"terim": _anlamadim_clean_str(term), "tanim": _anlamadim_clean_str(definition)})
            else:
                items.append({"terim": line, "tanim": ""})
        return items
    if isinstance(value, list):
        return value
    return []


def _anlamadim_coerce_quiz_items(value) -> list[dict]:
    if not value:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        lines = [_anlamadim_clean_str(line) for line in value.splitlines() if _anlamadim_clean_str(line)]
        quiz = []
        question = ""
        for line in lines:
            low = line.lower()
            if low.startswith("q:") or low.startswith("soru:"):
                question = _anlamadim_clean_str(line.split(":", 1)[1])
                continue
            if low.startswith("a:") or low.startswith("cevap:"):
                answer = _anlamadim_clean_str(line.split(":", 1)[1])
                if question:
                    quiz.append({"q": question, "a": answer})
                    question = ""
                continue
            quiz.append({"q": line, "a": ""})
        if question:
            quiz.append({"q": question, "a": ""})
        return quiz
    return []


def _anlamadim_merge_list_items(value, fallback_items: list[str], *, min_len: int = 12, max_items: int = 4) -> list[str]:
    items = _anlamadim_coerce_list_items(value)
    cleaned = []
    for item in items:
        text = _anlamadim_clean_str(item)
        if text and len(text) >= min_len and not _anlamadim_is_weak_text(text, min_len=min_len):
            if text not in cleaned:
                cleaned.append(text)

    for item in fallback_items:
        text = _anlamadim_clean_str(item)
        if text and len(text) >= min_len and not _anlamadim_is_weak_text(text, min_len=min_len) and text not in cleaned:
            cleaned.append(text)
        if len(cleaned) >= max_items:
            break

    return cleaned[:max_items]


def _anlamadim_valid_list_count(value, *, min_len: int = 12) -> int:
    return len(
        [
            item
            for item in _anlamadim_coerce_list_items(value)
            if len(_anlamadim_clean_str(item)) >= min_len and not _anlamadim_is_weak_text(item, min_len=min_len)
        ]
    )


def _anlamadim_merge_glossary(value, fallback_items: list[dict]) -> list[dict]:
    items = _anlamadim_coerce_glossary_items(value)
    cleaned = []
    seen = set()

    def add_item(term_value, definition_value):
        term = _anlamadim_clean_str(term_value)
        definition = _anlamadim_clean_str(definition_value)
        if _anlamadim_is_noise_text(term, min_len=2):
            return
        if len(term) < 2 or len(definition) < 12:
            return
        if _anlamadim_is_weak_text(definition, min_len=12):
            return
        key = term.lower()
        if key in seen:
            return
        seen.add(key)
        cleaned.append({"terim": term, "tanim": definition})

    for item in items:
        if isinstance(item, dict):
            add_item(item.get("terim") or item.get("term"), item.get("tanim") or item.get("def") or item.get("definition"))

    for item in fallback_items:
        if isinstance(item, dict):
            add_item(item.get("terim"), item.get("tanim"))
        if len(cleaned) >= 4:
            break

    return cleaned[:4]


def _anlamadim_valid_glossary_count(value) -> int:
    count = 0
    for item in _anlamadim_coerce_glossary_items(value):
        if not isinstance(item, dict):
            continue
        term = _anlamadim_clean_str(item.get("terim") or item.get("term"))
        definition = _anlamadim_clean_str(item.get("tanim") or item.get("def") or item.get("definition"))
        if len(term) >= 2 and len(definition) >= 12 and not _anlamadim_is_weak_text(definition, min_len=12):
            count += 1
    return count


def _anlamadim_merge_quiz(value, fallback_items: list[dict], one_liner: str, very_simple: str, glossary: list[dict], steps: list[str]) -> list[dict]:
    items = _anlamadim_coerce_quiz_items(value)
    cleaned = []
    seen = set()

    def add_quiz(question_value, answer_value):
        question = _anlamadim_clean_str(question_value)
        answer = _anlamadim_clean_str(answer_value)
        if len(question) < 10 or _anlamadim_is_weak_text(question, min_len=10):
            return
        if not answer:
            answer = one_liner or very_simple
        if _anlamadim_is_weak_text(answer, min_len=8) or answer.lower() == question.lower():
            answer = very_simple or one_liner
        if _anlamadim_is_weak_text(answer, min_len=8) or answer.lower() == question.lower():
            return
        key = question.lower()
        if key in seen:
            return
        seen.add(key)
        cleaned.append({"q": question, "a": answer})

    for item in items:
        if isinstance(item, dict):
            add_quiz(item.get("q") or item.get("soru"), item.get("a") or item.get("cevap"))
        elif isinstance(item, str):
            add_quiz(item, one_liner or very_simple)

    for item in fallback_items:
        if isinstance(item, dict):
            add_quiz(item.get("q"), item.get("a"))
        if len(cleaned) >= 3:
            break

    glossary_templates = [
        lambda term: f"'{term}' bu parca icin neden onemli?",
        lambda term: f"Parcada gecen '{term}' kavrami neyi anlatir?",
        lambda term: f"'{term}' terimini kendi cumlenle nasil aciklarsin?",
    ]
    for term_item in glossary or []:
        term = _anlamadim_clean_str(term_item.get("terim"))
        definition = _anlamadim_clean_str(term_item.get("tanim"))
        if not term or not definition:
            continue
        for make_question in glossary_templates:
            if len(cleaned) >= 3:
                break
            add_quiz(make_question(term), definition)
        if len(cleaned) >= 3:
            break

    step_templates = [
        "Bu parcayi anlarken hangi adimi unutmamalisin?",
        "Bu konuda dikkat edilmesi gereken siradaki adim nedir?",
        "Bu parcadan cikan en kritik uygulama adimi hangisi?",
    ]
    for idx, step in enumerate(steps or []):
        for template in step_templates:
            if len(cleaned) >= 3:
                break
            question = template if idx == 0 else f"{idx + 1}. adim icin soru: {template}"
            add_quiz(question, step)
        if len(cleaned) >= 3:
            break

    generic_fillers = [
        "Bu parcanin ana fikri nedir?",
        "Bu parcayi bir arkadasina tek cumlede nasil anlatirsin?",
        "Bu parcadan aklinda kalmasi gereken temel nokta nedir?",
    ]
    for question in generic_fillers:
        if len(cleaned) >= 3:
            break
        add_quiz(question, one_liner or very_simple)

    return cleaned[:3]


def _anlamadim_valid_quiz_count(value) -> int:
    count = 0
    for item in _anlamadim_coerce_quiz_items(value):
        if not isinstance(item, dict):
            continue
        question = _anlamadim_clean_str(item.get("q") or item.get("soru"))
        answer = _anlamadim_clean_str(item.get("a") or item.get("cevap"))
        if len(question) >= 10 and len(answer) >= 8:
            count += 1
    return count


def _sanitize_anlamadim_payload(parsed: dict, base_text: str, tema: str, tarz: str, seviye: str, *, chunk_context: dict | None = None) -> dict:
    """AI/fallback cikisini son kez kartlarda garip gorunmeyecek hale getirir."""
    parsed = parsed if isinstance(parsed, dict) else {}
    fb = _fallback_sections_v2(base_text or "", tema, tarz, seviye, chunk_context=chunk_context)
    out = dict(parsed)

    one_liner = _anlamadim_clean_str(out.get("one_liner"))
    if _anlamadim_is_weak_text(one_liner, min_len=8):
        one_liner = _anlamadim_clean_str(fb.get("one_liner"))
    if _anlamadim_is_weak_text(one_liner, min_len=8):
        sentences = _anlamadim_meaningful_sentences(base_text)
        one_liner = _anlamadim_excerpt(sentences[0], limit=150) if sentences else "Bu parca, secili metindeki ana fikri sade bir sekilde acikliyor."
    out["one_liner"] = one_liner

    very_simple = _anlamadim_clean_str(out.get("very_simple"))
    if _anlamadim_is_weak_text(very_simple, min_len=22):
        very_simple = _anlamadim_clean_str(fb.get("very_simple"))
    if _anlamadim_is_weak_text(very_simple, min_len=22):
        very_simple = _anlamadim_build_very_simple(base_text, one_liner, out.get("glossary") or fb.get("glossary") or [])
    out["very_simple"] = very_simple

    out["glossary"] = _anlamadim_merge_glossary(out.get("glossary"), fb.get("glossary", []))
    out["steps"] = _anlamadim_merge_list_items(out.get("steps"), fb.get("steps", []), min_len=14, max_items=4)
    out["examples"] = _anlamadim_merge_list_items(out.get("examples"), fb.get("examples", []), min_len=14, max_items=4)
    out["mini_quiz"] = _anlamadim_merge_quiz(
        out.get("mini_quiz"),
        fb.get("mini_quiz", []),
        out["one_liner"],
        out["very_simple"],
        out["glossary"],
        out["steps"],
    )

    trap = _anlamadim_clean_str(out.get("trap"))
    out["trap"] = trap if not _anlamadim_is_weak_text(trap, min_len=16) else _anlamadim_clean_str(fb.get("trap"))

    for key in ("tema_bazli_ornek", "alternatif_ornek", "function_purpose", "flow_summary"):
        value = _anlamadim_clean_str(out.get(key))
        fallback_value = _anlamadim_clean_str(fb.get(key))
        out[key] = value if value and not _anlamadim_is_weak_text(value, min_len=12) else fallback_value

    out["block_comments"] = _anlamadim_merge_list_items(out.get("block_comments"), fb.get("block_comments", []), min_len=12, max_items=4)
    out["line_comments"] = _anlamadim_merge_list_items(out.get("line_comments"), fb.get("line_comments", []), min_len=12, max_items=6)
    return out


def _anlamadim_alan_durumu(parsed: dict, base_text: str) -> dict:
    parsed = parsed if isinstance(parsed, dict) else {}

    one_liner = _anlamadim_clean_str(parsed.get("one_liner"))
    very_simple = _anlamadim_clean_str(parsed.get("very_simple"))
    trap = _anlamadim_clean_str(parsed.get("trap"))
    function_purpose = _anlamadim_clean_str(parsed.get("function_purpose"))
    flow_summary = _anlamadim_clean_str(parsed.get("flow_summary"))

    glossary_raw = parsed.get("glossary")
    steps_raw = parsed.get("steps")
    examples_raw = parsed.get("examples")
    quiz_raw = parsed.get("mini_quiz")
    block_comments_raw = parsed.get("block_comments")
    line_comments_raw = parsed.get("line_comments")

    glossary_valid = _anlamadim_valid_glossary_count(glossary_raw)
    steps_valid = _anlamadim_valid_list_count(steps_raw, min_len=14)
    examples_valid = _anlamadim_valid_list_count(examples_raw, min_len=14)
    quiz_valid = _anlamadim_valid_quiz_count(quiz_raw)
    block_comments_valid = _anlamadim_valid_list_count(block_comments_raw, min_len=12)
    line_comments_valid = _anlamadim_valid_list_count(line_comments_raw, min_len=12)
    block_comment_items = _anlamadim_coerce_list_items(block_comments_raw)
    line_comment_items = _anlamadim_coerce_list_items(line_comments_raw)
    block_comments_only_generic = bool(block_comment_items) and all(
        _anlamadim_is_weak_text(item, min_len=12) for item in block_comment_items
    )
    line_comments_only_generic = bool(line_comment_items) and all(
        _anlamadim_is_weak_text(item, min_len=12) for item in line_comment_items
    )

    durum = {
        "one_liner": bool(one_liner) and not _anlamadim_is_weak_text(one_liner, min_len=18),
        "very_simple": bool(very_simple) and not _anlamadim_is_weak_text(very_simple, min_len=22) and _anlamadim_overlap_score(very_simple, base_text) >= 2,
        "trap": bool(trap) and not _anlamadim_is_weak_text(trap, min_len=16),
        "glossary": glossary_valid >= 1,
        "steps": steps_valid >= 2,
        "examples": examples_valid >= 1,
        "mini_quiz": quiz_valid >= 3,
        "function_purpose": bool(function_purpose) and not _anlamadim_is_weak_text(function_purpose, min_len=18),
        "flow_summary": bool(flow_summary) and not _anlamadim_is_weak_text(flow_summary, min_len=16),
        "block_comments": block_comments_valid >= 1,
        "line_comments": line_comments_valid >= 1,
    }

    bos_alanlar = []
    cok_kisa_alanlar = []
    bicim_hatasi_olan_alanlar = []
    zayif_alanlar = []

    if not one_liner:
        bos_alanlar.append("one_liner")
    elif len(one_liner) < 18:
        cok_kisa_alanlar.append("one_liner")
    elif not durum["one_liner"]:
        zayif_alanlar.append("one_liner")

    if not very_simple:
        bos_alanlar.append("very_simple")
    elif len(very_simple) < 22:
        cok_kisa_alanlar.append("very_simple")
    elif not durum["very_simple"]:
        zayif_alanlar.append("very_simple")

    if not trap:
        bos_alanlar.append("trap")
    elif len(trap) < 16:
        cok_kisa_alanlar.append("trap")
    elif not durum["trap"]:
        zayif_alanlar.append("trap")

    if not glossary_raw:
        bos_alanlar.append("glossary")
    elif _anlamadim_coerce_glossary_items(glossary_raw) and glossary_valid == 0:
        bicim_hatasi_olan_alanlar.append("glossary")
    elif not durum["glossary"]:
        zayif_alanlar.append("glossary")

    if not steps_raw:
        bos_alanlar.append("steps")
    elif _anlamadim_coerce_list_items(steps_raw) and steps_valid == 0:
        bicim_hatasi_olan_alanlar.append("steps")
    elif not durum["steps"]:
        zayif_alanlar.append("steps")

    if not examples_raw:
        bos_alanlar.append("examples")
    elif _anlamadim_coerce_list_items(examples_raw) and examples_valid == 0:
        bicim_hatasi_olan_alanlar.append("examples")
    elif not durum["examples"]:
        zayif_alanlar.append("examples")

    if not quiz_raw:
        bos_alanlar.append("mini_quiz")
    elif _anlamadim_coerce_quiz_items(quiz_raw) and quiz_valid == 0:
        bicim_hatasi_olan_alanlar.append("mini_quiz")
    elif not durum["mini_quiz"]:
        zayif_alanlar.append("mini_quiz")

    if not function_purpose:
        bos_alanlar.append("function_purpose")
    elif len(function_purpose) < 18:
        cok_kisa_alanlar.append("function_purpose")
    elif not durum["function_purpose"]:
        zayif_alanlar.append("function_purpose")

    if not flow_summary:
        bos_alanlar.append("flow_summary")
    elif len(flow_summary) < 16:
        cok_kisa_alanlar.append("flow_summary")
    elif not durum["flow_summary"]:
        zayif_alanlar.append("flow_summary")

    if not block_comments_raw:
        bos_alanlar.append("block_comments")
    elif (block_comment_items and block_comments_valid == 0) or block_comments_only_generic:
        bicim_hatasi_olan_alanlar.append("block_comments")
    elif not durum["block_comments"]:
        zayif_alanlar.append("block_comments")

    if not line_comments_raw:
        bos_alanlar.append("line_comments")
    elif (line_comment_items and line_comments_valid == 0) or line_comments_only_generic:
        bicim_hatasi_olan_alanlar.append("line_comments")
    elif not durum["line_comments"]:
        zayif_alanlar.append("line_comments")

    return {
        "alan_yeterlilik": durum,
        "bos_alanlar": bos_alanlar,
        "cok_kisa_alanlar": cok_kisa_alanlar,
        "bicim_hatasi_olan_alanlar": bicim_hatasi_olan_alanlar,
        "zayif_alanlar": zayif_alanlar,
        "ham_dolu_alan_sayisi": sum(1 for ok in durum.values() if ok),
        "model_yeterli_alanlar": [alan for alan, ok in durum.items() if ok],
    }


def _merge_with_fallback_common(
    parsed: dict,
    base_text: str,
    tema: str,
    tarz: str,
    seviye: str,
    *,
    chunk_context: dict | None = None,
) -> dict:
    fb = _fallback_sections_v2(base_text or "", tema, tarz, seviye, chunk_context=chunk_context)
    parsed = parsed if isinstance(parsed, dict) else {}
    ham_analiz = _anlamadim_alan_durumu(parsed, base_text)

    result = {
        "one_liner": _anlamadim_clean_str(parsed.get("one_liner")),
        "very_simple": _anlamadim_clean_str(parsed.get("very_simple")),
        "trap": _anlamadim_clean_str(parsed.get("trap")),
        "tema_bazli_ornek": _anlamadim_clean_str(parsed.get("tema_bazli_ornek")),
        "alternatif_ornek": _anlamadim_clean_str(parsed.get("alternatif_ornek")),
        "function_purpose": _anlamadim_clean_str(parsed.get("function_purpose")),
        "flow_summary": _anlamadim_clean_str(parsed.get("flow_summary")),
    }

    if _anlamadim_is_weak_text(result["one_liner"], min_len=18):
        result["one_liner"] = _anlamadim_clean_str(fb.get("one_liner"))

    if (
        _anlamadim_is_weak_text(result["very_simple"], min_len=22)
        or _anlamadim_overlap_score(result["very_simple"], base_text) < 2
    ):
        result["very_simple"] = _anlamadim_clean_str(fb.get("very_simple"))

    if _anlamadim_is_weak_text(result["trap"], min_len=16):
        result["trap"] = _anlamadim_clean_str(fb.get("trap"))

    parsed_glossary = _anlamadim_merge_glossary(parsed.get("glossary"), [])
    if len(parsed_glossary) >= 1:
        result["glossary"] = parsed_glossary[:4]
    else:
        result["glossary"] = _anlamadim_merge_glossary(parsed.get("glossary"), fb.get("glossary", []))

    parsed_steps = _anlamadim_merge_list_items(parsed.get("steps"), [], min_len=14, max_items=4)
    if len(parsed_steps) >= 2:
        result["steps"] = parsed_steps[:4]
    else:
        result["steps"] = _anlamadim_merge_list_items(parsed.get("steps"), fb.get("steps", []), min_len=14, max_items=4)

    parsed_examples = _anlamadim_merge_list_items(parsed.get("examples"), [], min_len=14, max_items=3)
    if len(parsed_examples) >= 1:
        result["examples"] = parsed_examples[:3]
    else:
        result["examples"] = _anlamadim_merge_list_items(parsed.get("examples"), fb.get("examples", []), min_len=14, max_items=3)

    if _anlamadim_is_weak_text(result["function_purpose"], min_len=18):
        result["function_purpose"] = _anlamadim_clean_str(fb.get("function_purpose"))

    if _anlamadim_is_weak_text(result["flow_summary"], min_len=16):
        result["flow_summary"] = _anlamadim_clean_str(fb.get("flow_summary"))

    result["block_comments"] = _anlamadim_merge_list_items(
        parsed.get("block_comments"),
        fb.get("block_comments", []),
        min_len=12,
        max_items=4,
    )
    result["line_comments"] = _anlamadim_merge_list_items(
        parsed.get("line_comments"),
        fb.get("line_comments", []),
        min_len=12,
        max_items=6,
    )

    parsed_quiz = _anlamadim_merge_quiz(
        parsed.get("mini_quiz"),
        [],
        result["one_liner"],
        result["very_simple"],
        result["glossary"],
        result["steps"],
    )
    if len(parsed_quiz) >= 3:
        result["mini_quiz"] = parsed_quiz[:3]
    else:
        result["mini_quiz"] = _anlamadim_merge_quiz(
            parsed.get("mini_quiz"),
            fb.get("mini_quiz", []),
            result["one_liner"],
            result["very_simple"],
            result["glossary"],
            result["steps"],
        )

    if len(result["tema_bazli_ornek"]) < 14:
        result["tema_bazli_ornek"] = _anlamadim_clean_str(fb.get("tema_bazli_ornek"))
    if len(result["alternatif_ornek"]) < 14:
        result["alternatif_ornek"] = _anlamadim_clean_str(fb.get("alternatif_ornek"))

    result = _sanitize_anlamadim_payload(
        result,
        base_text,
        tema,
        tarz,
        seviye,
        chunk_context=chunk_context,
    )

    merge_analiz = {
        "ham": ham_analiz,
        "sonuc": _anlamadim_alan_durumu(result, base_text),
    }
    merge_analiz["merge_ile_tamamlanan_alanlar"] = [
        alan
        for alan in ("one_liner", "very_simple", "glossary", "steps", "examples", "trap", "mini_quiz", "function_purpose", "flow_summary", "block_comments", "line_comments")
        if not merge_analiz["ham"]["alan_yeterlilik"].get(alan) and merge_analiz["sonuc"]["alan_yeterlilik"].get(alan)
    ]
    merge_analiz["merge_ile_tamamlanan_alan_sayisi"] = len(merge_analiz["merge_ile_tamamlanan_alanlar"])
    merge_analiz["merge_gerekli_miydi"] = merge_analiz["merge_ile_tamamlanan_alan_sayisi"] > 0

    return result, merge_analiz


def _merge_with_fallback(parsed: dict, base_text: str, tema: str, tarz: str, seviye: str) -> dict:
    return _merge_with_fallback_common(parsed, base_text, tema, tarz, seviye)[0]
def _anlamadim_prompt(parca_metin: str, tema: str, tarz: str, seviye: str, stil: str = "", cut: str = "", remix: str = "", user_msg: str = "") -> str:
    parca_metin = (parca_metin or "").strip()

    # Stil profilleri (ton)
    stil_map = {
        "kanka": "Kanka dili: samimi, kısa cümleler, net.",
        "hoca": "Hoca dili: öğretici, adım adım, sınav odaklı ipuçları.",
        "ceo": "CEO dili: iş değeri, özet, risk/fayda, karar netliği.",
        "teknik": "Teknik dil: terimler doğru, madde madde, gerektiğinde kısa pseudo-kod.",
        "sunum": "Sunum dili: başlıklar net, kısa bullet’lar, vurgu ve örnekler."
    }

    # Cut (kurgu)
    cut_map = {
        "hizli": "Hızlı Cut: sadece kritik noktalar + 1 örnek.",
        "story": "Story Cut: sebep→sonuç→ders akışı gibi anlat.",
        "exam": "Exam Cut: hocanın soracağı yerler + tuzaklar + mini test ağırlıklı."
    }

    # Remix (dönüştürme)
    remix_map = {
        "kisa_kes": "Remix: gereksiz tekrarları kes, daha kısa yap.",
        "derinlestir": "Remix: daha derin açıkla, ama doküman dışına taşma.",
        "ornek_artir": "Remix: daha fazla örnek üret (tema ile uyumlu).",
        "tablo_yap": "Remix: mümkünse sözlük/özet kısmını düzenli maddeler halinde ver (tablo gibi net).",
        "akis_ciz": "Remix: adımları oklarla (->) akış gibi yaz.",
        "none": ""
    }

    tema_map = {
        "genel": "Genel örnekler kullan.",
        "yazilim": "Yazılım örnekleri kullan (API, auth, DB, servis).",
        "saglik": "Sağlık örnekleri kullan (hasta, kayıt, süreç).",
        "matematik": "Matematik örnekleri kullan (fonksiyon, denklem, ispat).",
    }

    tarz_map = {
        "kisa": "Mümkün olduğunca kısa yaz.",
        "adim_adim": "Adım adım, numaralı anlat.",
        "ornekli": "Bol örnek ver (en az 2 örnek).",
        "derin": "Derin anlat ama gereksiz uzatma; kanıt dışına çıkma.",
    }

    # ÇIKTI FORMATINI parser için sabitle:
    fmt_rules = """
ÇIKTIYI **SADECE** aşağıdaki TAG'lerle üret (başka başlık yazma):

[ONE_LINER]
...tek cümle özet...
[/ONE_LINER]

[VERY_SIMPLE]
...çok basit anlatım...
[/VERY_SIMPLE]

[GLOSSARY]
- TERIM: TANIM
- TERIM: TANIM
[/GLOSSARY]

[STEPS]
1) ...
2) ...
[/STEPS]

[EXAMPLES]
- Örnek: ...
- Alternatif: ...
[/EXAMPLES]

[TRAP]
...en sık karıştırılan tuzak...
[/TRAP]

[MINI_QUIZ]
Q: ...
A: ...
Q: ...
A: ...
[/MINI_QUIZ]

KURAL: Sadece dokümandaki kanıtlara dayan. Kanıtta yoksa: "Dokümanda yok." yaz.
KURAL: "2.", "1.", "3", "-", "." veya sadece başlık numarası gibi cevaplar yazma.
KURAL: ONE_LINER en az 8 karakterlik anlamlı bir cümle olsun; sayı/noktalama tek başına olmasın.
KURAL: EXAMPLES gündelik ve somut olsun; "Gündelik dilde: 2." gibi başlık numarasını örnek yapma.
KURAL: MINI_QUIZ her maddede Soru ve kısa Cevap içersin; kaynak cümleyi aynen kopyalama.
"""

    pieces = []
    pieces.append("GÖREV: Kullanıcı bu parçayı anlamadı. Aşağıdaki parçayı açıkla.")
    pieces.append(f"TEMA: {tema} | TARZ: {tarz} | SEVİYE: {seviye}")
    if tema in tema_map:
        pieces.append("Tema Notu: " + tema_map[tema])
    if tarz in tarz_map:
        pieces.append("Tarz Notu: " + tarz_map[tarz])

    if stil:
        pieces.append("Stil Profili: " + stil_map.get(stil, stil))
    if cut:
        pieces.append("Kurgu (Cut): " + cut_map.get(cut, cut))
    if remix:
        pieces.append("Remix: " + remix_map.get(remix, remix))

    if user_msg:
        pieces.append(f"Kullanıcı mesajı: {user_msg}")

    pieces.append("")
    pieces.append("PARÇA:")
    pieces.append(parca_metin)
    pieces.append("")
    pieces.append(fmt_rules.strip())

    return "\n".join(pieces).strip()

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import KullaniciTercih

ALLOWED_TEMA = {"genel", "yazilim", "saglik", "matematik"}
ALLOWED_TARZ = {"adim_adim", "ornekli", "kisa", "derin"}
ALLOWED_SEVIYE = {"baslangic", "orta", "ileri"}


def _anlamadim_ai2_test_modu_aktif() -> bool:
    deger = getattr(settings, "AI2_TEST_MODU", False)
    if isinstance(deger, bool):
        return deger
    return str(deger).strip().lower() in {"1", "true", "evet", "on", "yes"}


def _anlamadim_max_token_tavani(parca_sinifi: str) -> int:
    if _anlamadim_ai2_test_modu_aktif():
        tavani = {"kisa": 96, "orta": 128, "uzun": 160}
    else:
        tavani = {"kisa": 96, "orta": 128, "uzun": 160}
    return tavani.get(str(parca_sinifi or "").strip().lower(), 64)


def _internal_debug_enabled(request=None) -> bool:
    if not bool(getattr(settings, "DEBUG", False)):
        return False
    return True


def _redacted_exception_summary(exc, *, prefix: str = "ERROR") -> str:
    return f"{prefix}: {type(exc).__name__}"


def _anlamadim_chat_call(messages, *, max_tokens: int, timeout_seconds: int = 45):
    try:
        return chat(
            messages,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            max_attempts_per_url=1,
        )
    except TypeError:
        return chat(messages, max_tokens=max_tokens)


class ParcaRemixAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ExplainThrottle]

    def post(self, request, parca_id: int):
        lang = get_request_lang(request)
        if not modul_acik_mi("DOCVERSE_STYLE_CONSOLE_ENABLED", True):
            return Response(
                {
                    "enabled": False,
                    "error_code": "feature_disabled",
                    "detail": t("feature_disabled", lang),
                },
                status=403,
            )

        style = str((request.data or {}).get("style") or "").strip().lower()
        if style not in SUPPORTED_REMIX_STYLES:
            return Response(
                {
                    "error_code": "invalid_remix_style",
                    "detail": t("invalid_remix_style", lang),
                },
                status=400,
            )

        parca = (
            Parca.objects
            .filter(id=parca_id, dokuman__owner=request.user)
            .select_related("dokuman")
            .first()
        )
        if not parca:
            return Response(
                {
                    "error_code": "resource_not_found",
                    "detail": t("resource_not_found", lang),
                },
                status=404,
            )

        part_text = str(getattr(parca, "metin", "") or getattr(parca, "icerik", "") or "")
        preferences = resolve_preferences(request.user, request.data or {})
        pref_prompt = build_preference_prompt(preferences, lang)
        source = normalize_source((request.data or {}).get("source"))
        if not source:
            source = source_from_part_text(part_text)
        theme_example = themed_example_for_text(part_text, preferences.get("theme"), lang)
        if theme_example:
            source["examples"] = list(source.get("examples") or []) + [theme_example]

        fallback_warning = ""
        try:
            messages = build_remix_prompt(
                style=style,
                source=source,
                part_text=f"{pref_prompt}\n\n{part_text}" if pref_prompt else part_text,
                lang=lang,
            )
            max_tokens = min(
                ai2_scope_icin_max_token("REMIX", (request.data or {}).get("max_tokens"), minimum=250),
                450,
            )
            future = _AI2_FAST_EXECUTOR.submit(
                _anlamadim_chat_call,
                messages,
                max_tokens=max_tokens,
                timeout_seconds=18,
            )
            raw = future.result(timeout=20)
            ai_payload = parse_ai_remix_response(raw, style=style, lang=lang)
            if ai_payload:
                return Response(ai_payload)
            fallback_warning = t("remix_failed", lang)
        except FuturesTimeoutError:
            logger.debug("Remix chat timeout for parca_id=%s style=%s", parca.id, style)
            fallback_warning = t("remix_failed", lang)
        except Exception as exc:
            logger.debug(
                "Remix chat fallback for parca_id=%s style=%s error_type=%s",
                parca.id,
                style,
                type(exc).__name__,
            )
            fallback_warning = t("remix_failed", lang)

        return Response(
            fallback_remix_response(
                style=style,
                source=source,
                part_text=part_text,
                lang=lang,
                warning=fallback_warning,
            )
        )


class ParcaDirectorsCutAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ExplainThrottle]

    def post(self, request, parca_id: int):
        lang = get_request_lang(request)
        if not modul_acik_mi("DOCVERSE_DIRECTORS_CUT_ENABLED", True):
            detail = "Director’s Cut şu anda kapalı." if lang == "tr" else "Director’s Cut is currently disabled."
            return Response(
                {
                    "enabled": False,
                    "error_code": "feature_disabled",
                    "detail": detail,
                },
                status=403,
            )

        cut_type = str((request.data or {}).get("cut_type") or "").strip().lower()
        if cut_type not in SUPPORTED_DIRECTORS_CUT_TYPES:
            return Response(
                {
                    "error_code": "invalid_directors_cut_type",
                    "detail": t("invalid_directors_cut_type", lang),
                },
                status=400,
            )

        parca = (
            Parca.objects
            .filter(id=parca_id, dokuman__owner=request.user)
            .select_related("dokuman")
            .first()
        )
        if not parca:
            return Response(
                {
                    "error_code": "resource_not_found",
                    "detail": t("resource_not_found", lang),
                },
                status=404,
            )

        part_text = str(getattr(parca, "metin", "") or getattr(parca, "icerik", "") or "")
        preferences = resolve_preferences(request.user, request.data or {})
        pref_prompt = build_preference_prompt(preferences, lang)
        source = normalize_source((request.data or {}).get("source"))
        if not source:
            source = source_from_part_text(part_text)
        theme_example = themed_example_for_text(part_text, preferences.get("theme"), lang)
        if theme_example:
            source["examples"] = list(source.get("examples") or []) + [theme_example]

        fallback_warning = ""
        try:
            messages = build_directors_cut_prompt(
                cut_type=cut_type,
                source=source,
                part_text=f"{pref_prompt}\n\n{part_text}" if pref_prompt else part_text,
                lang=lang,
            )
            max_tokens = min(
                ai2_scope_icin_max_token("DIRECTORS_CUT", (request.data or {}).get("max_tokens"), minimum=300),
                500,
            )
            future = _AI2_FAST_EXECUTOR.submit(
                _anlamadim_chat_call,
                messages,
                max_tokens=max_tokens,
                timeout_seconds=18,
            )
            raw = future.result(timeout=20)
            ai_payload = parse_ai_directors_cut_response(raw, cut_type=cut_type, lang=lang)
            if ai_payload:
                return Response(ai_payload)
            fallback_warning = t("directors_cut_failed", lang)
        except FuturesTimeoutError:
            logger.debug("Director's Cut chat timeout for parca_id=%s cut_type=%s", parca.id, cut_type)
            fallback_warning = t("directors_cut_failed", lang)
        except Exception as exc:
            logger.debug(
                "Director's Cut fallback for parca_id=%s cut_type=%s error_type=%s",
                parca.id,
                cut_type,
                type(exc).__name__,
            )
            fallback_warning = t("directors_cut_failed", lang)

        return Response(
            fallback_directors_cut_response(
                cut_type=cut_type,
                source=source,
                part_text=part_text,
                lang=lang,
                warning=fallback_warning,
            )
        )


        
class ParcaAnlamadimV2(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ExplainThrottle]

    def post(self, request, parca_id: int):
        internal_debug = _internal_debug_enabled(request)
        parca = (
            Parca.objects
            .filter(id=parca_id, dokuman__owner=request.user)
            .select_related("dokuman")
            .first()
        )
        if not parca:
            return Response(
                _api_error_payload(detail="Parça yok", error_code="resource_not_found"),
                status=404,
            )

        learning_preferences = resolve_preferences(request.user, request.data or {})
        theme_alias = {"default": "genel", "film_dizi": "film", "bilim": "matematik", "is_dunyasi": "teknoloji"}
        style_alias = {"bol_ornek": "ornekli", "ciddi": "derin", "sinav_odakli": "adim_adim", "sohbet": "adim_adim", "hafif_mizah": "adim_adim"}
        tema = (request.data.get("tema") or theme_alias.get(learning_preferences["theme"], learning_preferences["theme"]) or "genel").strip()
        tarz = (request.data.get("tarz") or style_alias.get(learning_preferences["explanation_style"], learning_preferences["explanation_style"]) or "kisa").strip()
        seviye = (request.data.get("seviye") or learning_preferences["level"] or "orta").strip()

        stil = _norm_choice(request.data.get("stil"), STIL_CHOICES, "") or ""
        cut = _norm_choice(request.data.get("cut"), CUT_CHOICES, "") or ""
        remix = _norm_choice(request.data.get("remix"), REMIX_CHOICES, "") or ""

        user_msg = (request.data.get("mesaj") or request.data.get("soru") or "").strip()
        if not user_msg:
            user_msg = "Bu kısmı daha basit anlat."

        addr = (getattr(parca, "adres", "") or "").strip()

        chunk_text = (
            request.data.get("secili_metin")
            or request.data.get("secim")
            or request.data.get("metin")
            or getattr(parca, "metin", None)
            or getattr(parca, "icerik", None)
            or ""
        ).strip()
        chunk_context = _anlamadim_chunk_context(
            text=chunk_text,
            adres=addr,
            meta=getattr(parca, "meta", {}) or {},
            tur=getattr(parca, "tur", "") or "",
        )
        # PDF imza / çöp metni ise AI'ya gitmeden güvenli fallback dön
        if addr.startswith("pdf:") and _pdf_imza_kokuyor_mu(chunk_text):
            parsed = _fallback_sections_v2(chunk_text, tema, tarz, seviye, chunk_context=chunk_context)
            parsed = _merge_with_fallback_v2(parsed, chunk_text, tema, tarz, seviye, chunk_context=chunk_context)

            kayit_id = None
            kayit_hata = None
            try:
                kayit = AnlamadimKaydi.objects.create(
                    kullanici=request.user,
                    dokuman=parca.dokuman,
                    parca=parca,
                    adres=addr,
                    tema=tema,
                    tarz=tarz,
                    seviye=seviye,
                    kullanici_mesaj=user_msg,
                    cikti_text="PDF_SIGNATURE_FALLBACK",
                    cikti_json=parsed,
                )
                kayit_id = kayit.id
            except Exception as e:
                kayit_hata = _redacted_exception_summary(e, prefix="KAYIT_ERROR")

            snip = (chunk_text[:240] + "...") if len(chunk_text) > 240 else chunk_text
            concept_items = []
            concept_relations = []
            if modul_acik_mi("DOCVERSE_CONCEPTS_ENABLED", True):
                concept_items = _concepts_for_text(
                    text=chunk_text,
                    lang=get_request_lang(request),
                    parca=parca,
                    glossary_items=parsed.get("glossary") or [],
                )
                concept_relations = build_concept_relations(concept_items, chunk_text)

            response_payload = _augment_answer_payload(
                {
                    "ok": True,
                    "kayit_id": kayit_id,
                    "parca": {
                        "id": parca.id,
                        "adres": addr,
                        "snippet": snip,
                    },
                    "tercih": {
                        "tema": tema,
                        "tarz": tarz,
                        "seviye": seviye,
                        "stil": stil,
                        "cut": cut,
                        "remix": remix,
                    },
                    "dokumanda_yok": False,
                    "kanitlar": [
                        {
                            "parca_id": parca.id,
                            "adres": addr,
                        }
                    ],
                    "kanit_snippet": [
                        {
                            "parca_id": parca.id,
                            "adres": addr,
                            "snippet": snip,
                        }
                    ],
                    "source": "fallback",
                    **parsed,
                    "concepts": concept_items,
                    "concept_relations": concept_relations,
                },
                context="explain",
            )
            if internal_debug:
                response_payload["view_marker"] = "REAL_PARCA_ANLAMADIM_V2_8001"
                response_payload["debug"] = "pdf imza fallback"
                response_payload["kayit_hata"] = kayit_hata
            return Response(response_payload)
        if not chunk_text:
            return Response(
                _api_error_payload(
                    detail="Açıklanacak metin boş",
                    error_code="validation_error",
                    field_errors={"metin": ["Bu alan zorunludur."]},
                ),
                status=400,
            )

        from dokuman.ai2.prompts import build_anlamadim_prompt
        from dokuman.ai2.validators import extract_json

        profile = {
            "tema": tema,
            "tarz": tarz,
            "seviye": seviye,
            "preference_prompt": build_preference_prompt(learning_preferences, get_request_lang(request)),
            "example_density": learning_preferences.get("example_density"),
            "stil": stil or "kanka",
            "cut": cut or "exam",
            "remix": remix or "",
            "mesaj": user_msg,
            "chunk_kind": chunk_context.get("kind"),
            "chunk_title": chunk_context.get("slide_title") or chunk_context.get("baslik") or "",
        }

        max_t = ai2_scope_icin_max_token(
            "ANLAMADIM",
            request.data.get("max_tokens"),
            minimum=32,
        )
        raw_text = ""
        obj = {}
        parsed = {}
        dokumanda_yok = False
        ai2_debug = {}
        json_bulundu_mu = False
        json_cozumleme_hatasi = ""
        fallback_nedeni = ""
        debug_ai2 = {}
        prompt_meta = {
            "parca_metin_uzunlugu": len(chunk_text or ""),
            "prompt_parca_metin_uzunlugu": len(chunk_text or ""),
            "prompt_kisaltildi_mi": False,
            "istenen_alan_sayisi": 7,
            "kisa_parca_mi": False,
            "parca_sinifi": "",
            "agir_prompt_suphesi": False,
            "secilen_max_tokens": max_t,
            "scope_max_tokens": max_t,
        }
        merge_analiz = {}

        try:
            messages, prompt_meta = build_anlamadim_prompt(addr, chunk_text, parca.id, profile, return_meta=True)
            scope_max_t = max_t
            max_t = min(scope_max_t, _anlamadim_max_token_tavani(prompt_meta.get("parca_sinifi") or ""))
            prompt_meta["scope_max_tokens"] = scope_max_t
            prompt_meta["secilen_max_tokens"] = max_t

            try:
                future = _AI2_FAST_EXECUTOR.submit(
                    _anlamadim_chat_call,
                    messages,
                    max_tokens=max_t,
                    timeout_seconds=45,
                )
                raw = future.result(timeout=45)
            except FuturesTimeoutError:
                logger.debug("Anlamadim v2 chat timeout for parca_id=%s", parca.id)
                raw = ""
                current_debug = son_chat_debug_bilgisi_al()
                current_debug["hata_nedeni"] = "ai2_timeout"
                current_debug["hata_mesaji"] = "AI2 zaman asimi."
                current_debug["timeout_saniye"] = 45
            except Exception as e:
                logger.debug("Anlamadim v2 chat error for parca_id=%s error_type=%s", parca.id, type(e).__name__)
                raw = ""
            ai2_debug = son_chat_debug_bilgisi_al()

            if raw is None:
                raw = ""

            if isinstance(raw, dict):
                obj = raw
                raw_text = json.dumps(raw, ensure_ascii=False)
                json_bulundu_mu = bool(obj)

                maybe_text = raw.get("text") or raw.get("response") or raw.get("content")
                if isinstance(maybe_text, str) and maybe_text.strip():
                    raw_text = maybe_text.strip()
                    try:
                        maybe_obj = extract_json(raw_text) or {}
                        if isinstance(maybe_obj, dict) and maybe_obj:
                            obj = maybe_obj
                            json_bulundu_mu = True
                    except Exception as e:
                        json_cozumleme_hatasi = f"{type(e).__name__}: {e}"

            else:
                raw_text = str(raw).strip()

                try:
                    maybe_obj = extract_json(raw_text) or {}
                    if isinstance(maybe_obj, dict) and maybe_obj:
                        obj = maybe_obj
                        json_bulundu_mu = True
                    else:
                        obj = {}
                except Exception as e:
                    json_cozumleme_hatasi = f"{type(e).__name__}: {e}"
                    obj = {}

            if not isinstance(obj, dict):
                obj = {}

            parsed_ham = {
                "one_liner": str(obj.get("one_liner") or "").strip(),
                "very_simple": str(obj.get("very_simple") or "").strip(),
                "trap": str(obj.get("trap") or "").strip(),
                "glossary": obj.get("glossary"),
                "steps": obj.get("steps"),
                "examples": obj.get("examples"),
                "mini_quiz": obj.get("mini_quiz"),
            }

            parsed, merge_analiz = _merge_with_fallback_common(
                dict(parsed_ham),
                chunk_text,
                tema,
                tarz,
                seviye,
                chunk_context=chunk_context,
            )

            ham_dolu = int((merge_analiz.get("ham") or {}).get("ham_dolu_alan_sayisi") or _anlamadim_v2_dolu_alan_sayisi(parsed_ham))
            final_dolu = int((merge_analiz.get("sonuc") or {}).get("ham_dolu_alan_sayisi") or _anlamadim_v2_dolu_alan_sayisi(parsed))
            hata_nedeni = str(ai2_debug.get("hata_nedeni") or "").strip()
            if hata_nedeni:
                fallback_nedeni = hata_nedeni
            elif not raw_text:
                fallback_nedeni = "ai2_empty_content"
            elif not obj:
                fallback_nedeni = "ai2_invalid_json" if json_cozumleme_hatasi else "ai2_parse_failed"
            elif ham_dolu <= 2 and final_dolu > ham_dolu:
                fallback_nedeni = "ai2_short_output"
            elif merge_analiz.get("merge_gerekli_miydi"):
                fallback_nedeni = "fallback_merge_completed"

            dokumanda_yok = _anlamadim_should_mark_missing(obj, parsed, chunk_text, raw_text)
            debug_ai2 = _anlamadim_v2_debug_ozeti(
                ai2_debug,
                raw_text,
                obj,
                parsed_ham,
                parsed,
                fallback_nedeni,
                json_bulundu_mu,
                json_cozumleme_hatasi,
                prompt_meta,
                merge_analiz,
            )

        except Exception as e:
            raw_text = _redacted_exception_summary(e, prefix="AI2_ERROR")
            fallback_nedeni = str(ai2_debug.get("hata_nedeni") or "ai2_exception")
            parsed = _fallback_sections_v2(chunk_text, tema, tarz, seviye, chunk_context=chunk_context)
            parsed = _merge_with_fallback_v2(parsed, chunk_text, tema, tarz, seviye, chunk_context=chunk_context)
            dokumanda_yok = False
            ai2_debug = son_chat_debug_bilgisi_al()
            debug_ai2 = _anlamadim_v2_debug_ozeti(
                ai2_debug,
                raw_text,
                {},
                {},
                parsed,
                fallback_nedeni,
                False,
                _redacted_exception_summary(e, prefix="AI2_ERROR"),
                prompt_meta,
                merge_analiz,
            )

        if internal_debug and fallback_nedeni:
            logger.debug(
                "Anlamadim v2 debug meta for parca_id=%s fallback=%s",
                parca.id,
                fallback_nedeni,
            )

        kanitlar = [
            {
                "parca_id": parca.id,
                "adres": addr,
            }
        ]

        snip = (chunk_text[:240] + "...") if len(chunk_text) > 240 else chunk_text
        themed_example = themed_example_for_text(chunk_text, learning_preferences.get("theme"), get_request_lang(request))
        if themed_example and themed_example not in list(parsed.get("examples") or []):
            parsed["examples"] = list(parsed.get("examples") or []) + [themed_example]

        kanit_snippet = [
            {
                "parca_id": parca.id,
                "adres": addr,
                "snippet": snip,
            }
        ]

        kayit_id = None
        kayit_hata = None

        try:
            kayit = AnlamadimKaydi.objects.create(
                kullanici=request.user,
                dokuman=parca.dokuman,
                parca=parca,
                adres=addr,
                tema=tema,
                tarz=tarz,
                seviye=seviye,
                kullanici_mesaj=user_msg,
                cikti_text=raw_text,
                cikti_json=parsed,
            )
            kayit_id = kayit.id
        except Exception as e:
            kayit_hata = _redacted_exception_summary(e, prefix="KAYIT_ERROR")

        if modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            if (
                _special_chunk_fallbacks_enabled()
                and chunk_context.get("kind") in {"table", "code", "visual"}
                and (fallback_nedeni or bool(merge_analiz.get("merge_gerekli_miydi")))
            ):
                kaydet_skor_olayi(
                    kullanici=request.user,
                    olay_turu="special_chunk_fallback_used",
                    kaynak_modul="anlamadim.v2",
                    dokuman=parca.dokuman,
                    parca=parca,
                    score_map={
                        "format": chunk_context.get("format") or chunk_context.get("kind"),
                        "quality_score": float(((parca.meta or {}).get("quality_score") or 0.0)),
                        "difficulty_score": float(((parca.meta or {}).get("difficulty_score") or 0.0)),
                        "chunk_kind": chunk_context.get("kind"),
                        "fallback_kind": "special_chunk",
                    },
                    durum="ok",
                )
            if _themed_examples_enabled() and (
                parsed.get("tema_bazli_ornek") or parsed.get("alternatif_ornek")
            ):
                kaydet_skor_olayi(
                    kullanici=request.user,
                    olay_turu="themed_example_generated",
                    kaynak_modul="anlamadim.v2",
                    dokuman=parca.dokuman,
                    parca=parca,
                    score_map={
                        "tema": tema,
                        "format": chunk_context.get("format") or chunk_context.get("kind"),
                        "chunk_kind": chunk_context.get("kind"),
                        "selection_state": "selected_piece",
                    },
                    durum="ok",
                )

        concept_items = []
        concept_relations = []
        if modul_acik_mi("DOCVERSE_CONCEPTS_ENABLED", True):
            concept_items = _concepts_for_text(
                text=chunk_text,
                lang=get_request_lang(request),
                parca=parca,
                glossary_items=parsed.get("glossary") or [],
            )
            concept_relations = build_concept_relations(concept_items, chunk_text)

        response_payload = _augment_answer_payload(
            {
                "ok": True,
                "kayit_id": kayit_id,
                "parca": {
                    "id": parca.id,
                    "adres": addr,
                    "snippet": snip,
                },
                "tercih": {
                    "tema": tema,
                    "tarz": tarz,
                    "seviye": seviye,
                    "stil": stil,
                    "cut": cut,
                    "remix": remix,
                },
                "personalization": learning_preferences,
                "themed_examples": [themed_example] if themed_example else [],
                "dokumanda_yok": dokumanda_yok,
                "kanitlar": kanitlar,
                "kanit_snippet": kanit_snippet,
                "source": "fallback" if fallback_nedeni else "ai",
                "warning": (
                    "AI servisi geçici olarak cevap üretemedi, hızlı açıklama gösterildi."
                    if fallback_nedeni
                    else ""
                ),
                **parsed,
                "concepts": concept_items,
                "concept_relations": concept_relations,
            },
            context="explain",
        )
        if internal_debug:
            response_payload["view_marker"] = "REAL_PARCA_ANLAMADIM_V2_8001"
            response_payload["kayit_hata"] = kayit_hata
            response_payload["debug_ai2"] = debug_ai2
        return Response(response_payload)
def _parca_text_getir(parca):
    return (
        getattr(parca, "icerik", None)
        or getattr(parca, "metin", None)
        or getattr(parca, "text", None)
        or ""
    ).strip()


def _temizle_json_metin(raw_text: str):
    if not raw_text:
        return {}

    text = raw_text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text.strip()).strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    eslesme = re.search(r"\{.*\}", text, re.DOTALL)
    if eslesme:
        try:
            return json.loads(eslesme.group(0))
        except Exception:
            return {}

    return {}


def _cumlelere_bol(text: str):
    if not text:
        return []
    parts = re.split(r'(?<=[.!?])\s+|\n+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _fallback_sections(text: str):
    cumleler = _cumlelere_bol(text)
    ilk = cumleler[0] if cumleler else (text[:180].strip() if text else "")
    ilk_uc = cumleler[:3] if cumleler else ([text[:500].strip()] if text else [])

    return {
        "kisa_ozet": ilk or "Bu bölüm ana fikri anlatıyor.",
        "basit_anlatim": text[:700].strip() if text else "Basit anlatım üretilemedi.",
        "terimler_sozlugu": [],
        "adim_adim": cumleler[:5] if cumleler else [],
        "ornek": "",
        "karistirilan_nokta": "",
        "mini_test": [],
        "kanit_snippet": ilk_uc,
        "guven": 0.45,
    }


def _anlamadim_should_mark_missing(obj: dict, parsed: dict, base_text: str, raw_text: str) -> bool:
    raw_lower = _anlamadim_norm_text(raw_text).lower()
    explicit_missing = raw_lower in {"dokumanda yok.", "dokumanda yok"} or bool((obj or {}).get("dokumanda_yok", False))
    if not explicit_missing:
        return False
    return not _anlamadim_is_meaningful_text(base_text)


def _anlamadim_v2_dolu_alan_sayisi(parsed: dict) -> int:
    if not isinstance(parsed, dict):
        return 0

    alanlar = ("one_liner", "very_simple", "trap", "glossary", "steps", "examples", "mini_quiz")
    dolu = 0
    for alan in alanlar:
        deger = parsed.get(alan)
        if isinstance(deger, str) and deger.strip():
            dolu += 1
        elif isinstance(deger, list) and any(str(x).strip() for x in deger):
            dolu += 1
        elif isinstance(deger, dict) and deger:
            dolu += 1
    return dolu


def _anlamadim_v2_debug_ozeti(
    ai2_debug: dict,
    raw_text: str,
    obj: dict,
    parsed_ham: dict,
    parsed_final: dict,
    fallback_nedeni: str,
    json_bulundu_mu: bool,
    json_cozumleme_hatasi: str,
    prompt_meta: dict | None = None,
    merge_analiz: dict | None = None,
):
    ai2_debug = dict(ai2_debug or {})
    prompt_meta = dict(prompt_meta or {})
    merge_analiz = dict(merge_analiz or {})
    ham_analiz = dict(merge_analiz.get("ham") or {})
    sonuc_analiz = dict(merge_analiz.get("sonuc") or {})
    return {
        "kullanilan_url": _guvenli_debug_url(ai2_debug.get("kullanilan_url")),
        "model_alias": ai2_debug.get("model_alias") or "",
        "yanit_modeli": ai2_debug.get("yanit_modeli") or "",
        "model_alias_uyusuyor_mu": ai2_debug.get("model_alias_uyusuyor_mu"),
        "max_tokens": ai2_debug.get("max_tokens"),
        "secilen_max_tokens": prompt_meta.get("secilen_max_tokens"),
        "scope_max_tokens": prompt_meta.get("scope_max_tokens"),
        "timeout_saniye": ai2_debug.get("timeout_saniye"),
        "response_status": ai2_debug.get("response_status"),
        "response_body_uzunlugu": ai2_debug.get("response_body_uzunlugu"),
        "content_bos_mu": ai2_debug.get("content_bos_mu"),
        "content_uzunlugu": ai2_debug.get("content_uzunlugu"),
        "prompt_tahmini_uzunluk": ai2_debug.get("prompt_tahmini_uzunluk"),
        "ai2_test_modu_aktif_mi": ai2_debug.get("ai2_test_modu_aktif_mi"),
        "raw_text_uzunlugu": len(raw_text or ""),
        "ai2_cevap_ozeti": _guvenli_debug_text(ai2_debug.get("ai2_cevap_ozeti"), label="ai2_cevap_ozeti"),
        "hata_nedeni": ai2_debug.get("hata_nedeni") or "",
        "hata_mesaji": _guvenli_debug_text(ai2_debug.get("hata_mesaji"), label="hata_mesaji"),
        "parca_metin_uzunlugu": prompt_meta.get("parca_metin_uzunlugu"),
        "prompt_parca_metin_uzunlugu": prompt_meta.get("prompt_parca_metin_uzunlugu"),
        "prompt_kisaltildi_mi": prompt_meta.get("prompt_kisaltildi_mi"),
        "istenen_alan_sayisi": prompt_meta.get("istenen_alan_sayisi"),
        "kisa_parca_mi": prompt_meta.get("kisa_parca_mi"),
        "parca_sinifi": prompt_meta.get("parca_sinifi") or "",
        "agir_prompt_suphesi": prompt_meta.get("agir_prompt_suphesi"),
        "json_bulundu_mu": bool(json_bulundu_mu),
        "json_cozumleme_hatasi": _guvenli_debug_text(json_cozumleme_hatasi, label="json_cozumleme_hatasi"),
        "parse_basarili_mi": isinstance(obj, dict) and bool(obj),
        "ham_dolu_alan_sayisi": int(ham_analiz.get("ham_dolu_alan_sayisi") or _anlamadim_v2_dolu_alan_sayisi(parsed_ham)),
        "merge_sonrasi_dolu_alan_sayisi": int(sonuc_analiz.get("ham_dolu_alan_sayisi") or _anlamadim_v2_dolu_alan_sayisi(parsed_final)),
        "final_dolu_alan_sayisi": int(sonuc_analiz.get("ham_dolu_alan_sayisi") or _anlamadim_v2_dolu_alan_sayisi(parsed_final)),
        "merge_ile_tamamlanan_alan_sayisi": int(merge_analiz.get("merge_ile_tamamlanan_alan_sayisi") or 0),
        "merge_ile_tamamlanan_alanlar": list(merge_analiz.get("merge_ile_tamamlanan_alanlar") or []),
        "merge_gerekli_miydi": bool(merge_analiz.get("merge_gerekli_miydi")),
        "model_yeterli_alanlar": list(ham_analiz.get("model_yeterli_alanlar") or []),
        "bos_alanlar": list(ham_analiz.get("bos_alanlar") or []),
        "cok_kisa_alanlar": list(ham_analiz.get("cok_kisa_alanlar") or []),
        "bicim_hatasi_olan_alanlar": list(ham_analiz.get("bicim_hatasi_olan_alanlar") or []),
        "zayif_alanlar": list(ham_analiz.get("zayif_alanlar") or []),
        "fallback_nedeni": fallback_nedeni or "",
    }


def _merge_with_fallback_v2(
    parsed: dict,
    base_text: str,
    tema: str,
    tarz: str,
    seviye: str,
    *,
    chunk_context: dict | None = None,
) -> dict:
    return _merge_with_fallback_common(
        parsed,
        base_text,
        tema,
        tarz,
        seviye,
        chunk_context=chunk_context,
    )[0]

def _normalize_string_list(value):
    """Metin veya liste girdisini bos degerleri ayiklanmis string listesine cevirir."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        lines = [x.strip("-• \t") for x in value.split("\n")]
        return [x for x in lines if x]
    return [str(value).strip()]


def _normalize_terms(value):
    """Terim alanlarini dict/list/string fark etmeksizin ortak payload seklinde normalize eder."""
    if not value:
        return []

    if isinstance(value, dict):
        out = []
        for k, v in value.items():
            if str(k).strip():
                out.append({
                    "terim": str(k).strip(),
                    "aciklama": str(v).strip()
                })
        return out

    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, dict):
                terim = (
                    item.get("terim")
                    or item.get("kavram")
                    or item.get("ad")
                    or ""
                )
                aciklama = (
                    item.get("aciklama")
                    or item.get("anlam")
                    or item.get("tanim")
                    or ""
                )
                if terim or aciklama:
                    out.append({
                        "terim": str(terim).strip(),
                        "aciklama": str(aciklama).strip()
                    })
            else:
                s = str(item).strip()
                if s:
                    out.append({
                        "terim": s,
                        "aciklama": ""
                    })
        return out

    s = str(value).strip()
    return [{"terim": s, "aciklama": ""}] if s else []


def _normalize_quiz(value):
    """Farkli quiz temsillerini soru-cevap sozlukleri listesine indirger."""
    if not value:
        return []

    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, dict):
                soru = item.get("soru") or item.get("question") or ""
                cevap = item.get("cevap") or item.get("answer") or ""
                out.append({
                    "soru": str(soru).strip(),
                    "cevap": str(cevap).strip()
                })
            else:
                s = str(item).strip()
                if s:
                    out.append({"soru": s, "cevap": ""})
        return out

    if isinstance(value, str):
        lines = [x.strip("-• \t") for x in value.split("\n") if x.strip()]
        return [{"soru": x, "cevap": ""} for x in lines]

    return []


class DokumanAnlamadimOneri(APIView):
    permission_classes = [IsAuthenticated]

    def _response(self, request, doc_id: int):
        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        if _hardest_parts_enabled():
            payload = build_hardest_parts_payload(doc=doc, user=request.user, limit=3, feature_enabled=True)
            oneriler = list(payload.get("oneriler") or [])
            kaydet_skor_olayi(
                kullanici=request.user,
                olay_turu="hardest_parts_suggested",
                kaynak_modul="anlamadim.doc_suggestions",
                dokuman=doc,
                score_map={
                    "suggestion_count": len(oneriler),
                    "selection_state": "no_selection",
                    "rank_strategy": "hardest_parts_v1",
                },
                durum="ok",
            )
        else:
            qs = doc.parcalar.order_by("-zorluk_skoru", "id")[:3]
            oneriler = [
                {
                    "parca_id": p.id,
                    "adres": getattr(p, "adres", ""),
                    "neden_zor": "zorluk_skoru_yuksek",
                    "kisa_baslik": ((getattr(p, "meta", {}) or {}).get("baslik") or getattr(p, "adres", "") or f"Parca {p.id}")[:80],
                }
                for p in qs
            ]
            payload = {"oneriler": oneriler}

        return Response(payload)

    def get(self, request, doc_id: int):
        return self._response(request, doc_id)

    def post(self, request, doc_id: int):
        return self._response(request, doc_id)
def _auto_kaynakla(cevap: str, kanit_parcalar_llm: list) -> str:
    """
    GGUF cevapta [txt:...] yoksa, her satırı en alakalı kanıt parçasına bağlayıp [adres] ekler.
    kanit_parcalar_llm: [{"adres": "...", "metin": "..."}, ...]
    """
    if not cevap:
        return cevap

    # DeepSeek bazen [adres] yazıyor -> temizle
    cevap = re.sub(r"\[adres\]", "", cevap, flags=re.IGNORECASE).strip()

    lines = [ln.strip() for ln in cevap.splitlines() if ln.strip()]
    if not lines:
        return cevap

    metinler = [k["metin"] for k in kanit_parcalar_llm]

    out = []
    for ln in lines:
        # zaten kaynak varsa dokunma
        if "[txt:" in ln:
            out.append(ln)
            continue

        # en_alakali zaten sende var (TF-IDF)
        idx = en_alakali(ln, metinler, top_k=1)[0]
        out.append(f"{ln} [{kanit_parcalar_llm[idx]['adres']}]")

    return "\n".join(out)
def fix_mojibake(s: str) -> str:
    if not isinstance(s, str):
        return s
    # UTF-8 metin yanlış decode edilince böyle iz bırakır
    if any(x in s for x in ("Ã", "Ä", "Å")):
        try:
            return s.encode("latin1").decode("utf-8")
        except Exception:
            return s
    return s
def _pdf_imza_kokuyor_mu(text: str) -> bool:
    t = re.sub(r"\s+", " ", (text or "")).strip().lower()

    if not t:
        return False

    flags = [
        "dijital olarak imzalayan",
        "elektronik imza",
        "e-imza",
        "e imza",
        "imzalayan",
        "tarih:",
    ]

    if any(f in t for f in flags):
        return True

    # çok kısa, isim-soyisim + tarih/saat ağırlıklı içerik
    if re.search(r"\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}", t) and len(t) < 350:
        return True

    return False
def _pdf_cop_satir_mi(line: str) -> bool:
    line = re.sub(r"\s+", " ", (line or "").strip())
    if not line:
        return True

    low = line.lower()

    if any(x in low for x in [
        "dijital olarak imzalayan",
        "elektronik imza",
        "e-imza",
        "e imza",
        "imzalayan",
    ]):
        return True

    if re.search(r"tarih\s*:\s*\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}", low):
        return True

    if re.fullmatch(r"\d{1,2}:\d{2}:\d{2}\s*\+\d{2}'?\d{2}'?", line):
        return True

    return False


def _pdf_chunk_temizle(text: str) -> str:
    from collections import Counter

    raw = fix_mojibake(text or "")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")

    lines = [re.sub(r"\s+", " ", x).strip() for x in raw.splitlines()]
    lines = [x for x in lines if x]

    if not lines:
        return ""

    raw_lower = raw.lower()
    signature_suspect = any(x in raw_lower for x in [
        "dijital olarak imzalayan",
        "elektronik imza",
        "e-imza",
        "e imza",
        "imzalayan",
        "tarih:",
    ])

    freq = Counter(lines)
    temiz = []

    for ln in lines:
        if _pdf_cop_satir_mi(ln):
            continue

        # Aynı kısa-büyük harf satırı tekrar ediyorsa çöptür
        if (
            freq[ln] >= 2
            and len(ln) <= 40
            and re.fullmatch(r"[A-ZÇĞİÖŞÜ\s]+", ln)
        ):
            continue

        # arka arkaya aynı satırı tekrarlama
        if temiz and temiz[-1] == ln:
            continue

        temiz.append(ln)

    out = " ".join(temiz).strip()
    out = re.sub(r"\s+", " ", out).strip()

    if not out:
        return ""

    # İmza kokulu ve temizlik sonrası çok kısa kaldıysa tamamen at
    if signature_suspect and len(out) < 25:
        fallback = re.sub(r"\s+", " ", raw).strip()
        return fallback[:500]

    return out
from collections import Counter

def llm_cop_mu(text: str) -> bool:
    """
    LLM saçmalıyor mu?
    - aynı satırı / cümleyi çok tekrar ediyor mu?
    - aşırı kısa mı?
    """
    t = (text or "").strip()
    if len(t) < 40:
        return True

    lines = [x.strip() for x in t.splitlines() if x.strip()]
    if not lines:
        return True

    c = Counter(lines)
    # Aynı satır 5+ kez tekrar ediyorsa cop
    if c.most_common(1)[0][1] >= 5:
        return True

    # Genel tekrar kontrolü (tek tip satır çoksa)
    uniq_ratio = len(set(lines)) / max(1, len(lines))
    if uniq_ratio < 0.25 and len(lines) > 10:
        return True

    return False
def ping(request):
    return JsonResponse({"durum": "ok", "mesaj": "dokuman_asistani ayakta knk"})


_UPLOAD_IMAGE_EXTS = set(DOCVERSE_OCR_EXTENSIONS) & {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
_UPLOAD_LEGACY_EXTS = {".doc", ".xls", ".ppt"}
_UPLOAD_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_UPLOAD_ZIP_MAGIC_PREFIXES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_UPLOAD_GENERIC_CONTENT_TYPES = {
    "",
    "application/octet-stream",
    "binary/octet-stream",
}
_UPLOAD_MIME_ALLOWLIST = {
    ".pdf": {"application/pdf", "application/x-pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/x-zip-compressed",
    },
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/x-zip-compressed",
    },
    ".xlsm": {
        "application/vnd.ms-excel.sheet.macroenabled.12",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/x-zip-compressed",
    },
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
        "application/x-zip-compressed",
    },
    ".doc": {"application/msword"},
    ".xls": {"application/vnd.ms-excel"},
    ".ppt": {"application/vnd.ms-powerpoint", "application/powerpoint"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".webp": {"image/webp"},
    ".bmp": {"image/bmp"},
    ".tif": {"image/tiff"},
    ".tiff": {"image/tiff"},
}
_UPLOAD_OOXML_REQUIRED_MEMBERS = {
    ".docx": ("[Content_Types].xml", "word/document.xml"),
    ".xlsx": ("[Content_Types].xml", "xl/workbook.xml"),
    ".xlsm": ("[Content_Types].xml", "xl/workbook.xml"),
    ".pptx": ("[Content_Types].xml", "ppt/presentation.xml"),
}


def _aktif_upload_extleri(allowed_exts=None):
    """Endpoint izinleri ile rollout flag'lerini birlestirip kabul edilen uzantilari hesaplar."""
    if allowed_exts is not None:
        return {str(ext).lower() for ext in allowed_exts if str(ext).strip()}

    varsayilan_extler = set(supported_upload_extensions())
    extler = set(getattr(settings, "DOCVERSE_UPLOAD_EXTENSIONS", varsayilan_extler) or varsayilan_extler)
    extler = {str(ext).lower() for ext in extler if str(ext).strip()}

    extler.difference_update(set(getattr(settings, "DOCVERSE_BLOCKED_EXTENSIONS", DOCVERSE_BLOCKED_EXTENSIONS)))
    # Gorsel upload rollout'u ayardan kontrol edilir; flag kapaliysa parse destekli OCR gorselleri
    # settings listesine eklense bile kabul edilmez.
    if getattr(settings, "DOCVERSE_IMAGE_UPLOAD_ENABLED", False):
        extler.update(_UPLOAD_IMAGE_EXTS)
    else:
        extler.difference_update(_UPLOAD_IMAGE_EXTS)

    return extler


def _upload_ext_ok(filename, allowed_exts):
    ext = normalize_extension(filename)
    return bool(ext) and ext in allowed_exts


def _filename_has_control_chars(filename: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in str(filename or ""))


def _parser_supported_ext(ext: str) -> bool:
    return str(ext or "").lower() in set(getattr(settings, "DOCVERSE_PARSE_SUPPORTED_EXTENSIONS", DOCVERSE_PARSE_SUPPORTED_EXTENSIONS))


def _unsupported_parser_payload(ext: str, filename: str) -> dict:
    return _safe_error_payload(
        detail=PARSER_NOT_AVAILABLE_DETAIL,
        error_code="parser_not_available",
        status_text=PARSER_NOT_AVAILABLE_DETAIL,
        processing_state="unsupported",
        extra={
            "filename": filename,
            "extension": ext,
            "file_category": category_for_extension(ext),
            "warning_code": "parser_not_available",
        },
    )


def _archive_safety_probe(uploaded_file, ext: str) -> dict:
    if ext not in set(getattr(settings, "DOCVERSE_ARCHIVE_EXTENSIONS", DOCVERSE_ARCHIVE_EXTENSIONS)):
        return {"ok": True}
    if ext != ".zip":
        return {
            "ok": False,
            "status": 422,
            "detail": "Arşiv dosyaları için içerik çıkarma desteği henüz hazır değil.",
            "error_code": "archive_not_supported",
            "warning_code": "archive_not_supported",
        }

    max_files = int(getattr(settings, "DOCVERSE_ARCHIVE_MAX_FILES", 80) or 80)
    max_total = int(getattr(settings, "DOCVERSE_ARCHIVE_MAX_UNCOMPRESSED_BYTES", 50 * 1024 * 1024) or (50 * 1024 * 1024))
    try:
        uploaded_file.seek(0)
        with zipfile.ZipFile(uploaded_file) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if len(infos) > max_files:
                return {
                    "ok": False,
                    "status": 400,
                    "detail": "Arşiv içinde çok fazla dosya var.",
                    "error_code": "archive_too_many_files",
                    "warning_code": "archive_too_many_files",
                }
            total_size = sum(max(0, int(info.file_size or 0)) for info in infos)
            if total_size > max_total:
                return {
                    "ok": False,
                    "status": 413,
                    "detail": "Arşiv dosyası çok büyük.",
                    "error_code": "archive_too_large",
                    "warning_code": "archive_too_large",
                }
            allowed = _aktif_upload_extleri()
            blocked = set(getattr(settings, "DOCVERSE_BLOCKED_EXTENSIONS", DOCVERSE_BLOCKED_EXTENSIONS))
            for info in infos:
                name = str(info.filename or "").replace("\\", "/")
                parts = [part for part in name.split("/") if part]
                if name.startswith("/") or any(part == ".." for part in parts):
                    return {
                        "ok": False,
                        "status": 400,
                        "detail": "Arşiv içinde güvenli olmayan dosya yolu tespit edildi.",
                        "error_code": "archive_unsafe_path",
                        "warning_code": "archive_unsafe_path",
                    }
                inner_ext = normalize_extension(name)
                if inner_ext in blocked:
                    return {
                        "ok": False,
                        "status": 400,
                        "detail": "Bu dosya türü güvenlik nedeniyle yüklenemez.",
                        "error_code": "blocked_extension",
                        "warning_code": "blocked_extension",
                    }
                if inner_ext and inner_ext not in allowed:
                    return {
                        "ok": False,
                        "status": 400,
                        "detail": "Bu dosya türü desteklenmiyor.",
                        "error_code": "unsupported_extension",
                        "warning_code": "unsupported_extension",
                    }
    except zipfile.BadZipFile:
        return {
            "ok": False,
            "status": 400,
            "detail": "Arşiv dosyası bozuk veya okunamıyor.",
            "error_code": "archive_not_supported",
            "warning_code": "archive_not_supported",
        }
    finally:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
    return {"ok": True}


def _upload_hata_detayi(allowed_exts):
    allowed_exts = {str(ext).lower() for ext in (allowed_exts or set()) if str(ext).strip()}
    if allowed_exts == {".pdf", ".docx"}:
        return "Sadece PDF ve DOCX dosyalari yuklenebilir."
    if not allowed_exts:
        return "Bu endpoint su anda dosya kabul etmiyor."
    return f"Desteklenen uzantilar: {', '.join(sorted(allowed_exts))}"


def _request_upload_file(request):
    """Geriye uyumluluk icin hem `dosya` hem `file` alanindan upload nesnesini okur."""
    files = getattr(request, "FILES", None)
    if not files:
        return None
    uploaded = files.get("dosya") or files.get("file")
    if not uploaded or not str(getattr(uploaded, "name", "") or "").strip():
        return None
    return uploaded


def _read_upload_header(uploaded_file, *, size: int = 512) -> bytes:
    try:
        uploaded_file.seek(0)
        head = uploaded_file.read(size) or b""
    finally:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
    return bytes(head)


def _upload_mime_matches(ext: str, content_type: str) -> bool:
    clean_type = str(content_type or "").strip().lower()
    if clean_type in _UPLOAD_GENERIC_CONTENT_TYPES:
        return True
    if ext in _UPLOAD_IMAGE_EXTS and clean_type.startswith("image/"):
        return True
    allowed_types = _UPLOAD_MIME_ALLOWLIST.get(ext)
    if not allowed_types:
        return True
    return clean_type in allowed_types


def _upload_image_signature_ok(ext: str, head: bytes) -> bool:
    clean_ext = str(ext or "").lower()
    if clean_ext == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if clean_ext in {".jpg", ".jpeg"}:
        return head.startswith(b"\xff\xd8\xff")
    if clean_ext == ".webp":
        return head.startswith(b"RIFF") and head[8:12] == b"WEBP"
    if clean_ext == ".bmp":
        return head.startswith(b"BM")
    if clean_ext in {".tif", ".tiff"}:
        return head.startswith(b"II*\x00") or head.startswith(b"MM\x00*")
    return False


def _upload_ooxml_signature_ok(uploaded_file, ext: str) -> bool:
    head = _read_upload_header(uploaded_file)
    if not any(head.startswith(prefix) for prefix in _UPLOAD_ZIP_MAGIC_PREFIXES):
        return False
    required_members = set(_UPLOAD_OOXML_REQUIRED_MEMBERS.get(ext, ()))
    if not required_members:
        return True
    try:
        uploaded_file.seek(0)
        with zipfile.ZipFile(uploaded_file) as archive:
            names = set(archive.namelist())
    except Exception:
        return False
    finally:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
    return required_members.issubset(names)


def _upload_legacy_signature_ok(head: bytes) -> bool:
    return head.startswith(_UPLOAD_OLE_MAGIC)


def _sniff_upload_kind(uploaded_file) -> dict:
    ext = normalize_extension(getattr(uploaded_file, "name", "") or "")
    size = int(getattr(uploaded_file, "size", 0) or 0)
    content_type = str(getattr(uploaded_file, "content_type", "") or "").strip().lower()
    min_bytes = int(getattr(settings, "DOCVERSE_UPLOAD_MIN_BYTES", 8) or 8)
    max_bytes = int(getattr(settings, "DOCVERSE_UPLOAD_MAX_BYTES", 25 * 1024 * 1024) or (25 * 1024 * 1024))

    if size <= 0:
        return {
            "ok": False,
            "status": 400,
            "detail": "Bos dosya yuklenemez.",
            "error_code": "empty_upload",
            "warning_code": "empty_upload",
        }
    if size > max_bytes:
        return {
            "ok": False,
            "status": 413,
            "detail": "Dosya boyutu siniri asildi.",
            "error_code": "payload_too_large",
            "warning_code": "payload_too_large",
        }
    if size < min_bytes:
        return {
            "ok": False,
            "status": 400,
            "detail": "Dosya cok kucuk veya bozuk gorunuyor.",
            "error_code": "suspicious_upload",
            "warning_code": "suspicious_upload",
        }

    if not _upload_mime_matches(ext, content_type):
        return {
            "ok": False,
            "status": 400,
            "detail": "Dosya uzantisi ve icerik turu uyusmuyor.",
            "error_code": "suspicious_upload",
            "warning_code": "suspicious_upload",
        }

    head = _read_upload_header(uploaded_file)
    if ext == ".pdf" and not head.startswith(b"%PDF-"):
        return {
            "ok": False,
            "status": 400,
            "detail": "PDF dosyasi beklenen imzayi tasimiyor.",
            "error_code": "suspicious_upload",
            "warning_code": "suspicious_upload",
        }
    if ext in _UPLOAD_OOXML_REQUIRED_MEMBERS and not _upload_ooxml_signature_ok(uploaded_file, ext):
        return {
            "ok": False,
            "status": 400,
            "detail": f"{ext.lstrip('.').upper()} dosyasi bozuk veya beklenen paket yapisini tasimiyor.",
            "error_code": "suspicious_upload",
            "warning_code": "suspicious_upload",
        }
    if ext in _UPLOAD_IMAGE_EXTS and not _upload_image_signature_ok(ext, head):
        return {
            "ok": False,
            "status": 400,
            "detail": "Gorsel dosyasi beklenen imzayi tasimiyor.",
            "error_code": "suspicious_upload",
            "warning_code": "suspicious_upload",
        }
    if ext in _UPLOAD_LEGACY_EXTS and not _upload_legacy_signature_ok(head):
        return {
            "ok": False,
            "status": 400,
            "detail": "Legacy belge bozuk veya beklenen dosya imzasini tasimiyor.",
            "error_code": "suspicious_upload",
            "warning_code": "legacy_format_limited",
        }
    archive_probe = _archive_safety_probe(uploaded_file, ext)
    if not archive_probe.get("ok"):
        return archive_probe
    return {"ok": True}


def _safe_upload_failure_payload(*, ext: str = "", signal: dict | None = None) -> dict:
    clean_ext = str(ext or "").strip().lower()
    summary = dict(signal or {})
    warning_code = str(summary.get("warning_code") or "").strip()
    if clean_ext in _UPLOAD_LEGACY_EXTS:
        return _safe_error_payload(
            detail="Legacy belge guvenli bicimde islenemedi. Mumkunse modern formata cevirip tekrar deneyin.",
            error_code="upload_ingestion_failed",
            status_text=str(summary.get("status_text") or "Belge donusturme gerektiriyor.").strip(),
            processing_state="failed",
            extra={"warning_code": warning_code or "legacy_conversion_required"},
        )
    return _safe_error_payload(
        detail="Dosya yuklendi ancak guvenli bicimde islenemedi.",
        error_code="upload_ingestion_failed",
        status_text=str(summary.get("status_text") or "Dokuman islenemedi.").strip(),
        processing_state="failed",
        extra={"warning_code": warning_code or "upload_processing_failed"},
    )


_OCR_RESPONSE_SOURCE_ALLOWLIST = {
    "image_ocr",
    "pdf_ocr_fallback",
}
_OCR_RESPONSE_CONFIDENCE_BANDS = {"dusuk", "orta", "yuksek"}
_OCR_RESPONSE_WARNING_ALLOWLIST = {
    "low_quality_ocr",
    "symbol_noise",
    "single_char_fragmentation",
    "broken_lines",
    "upper_cluster_noise",
    "column_noise",
    "mixed_ocr_quality",
}


def _response_safe_ocr_kaynak_turu(value) -> str:
    clean = str(value or "").strip()
    return clean if clean in _OCR_RESPONSE_SOURCE_ALLOWLIST else ""


def _response_safe_ocr_warning(value) -> str:
    clean = str(value or "").strip()
    return clean if clean in _OCR_RESPONSE_WARNING_ALLOWLIST else ""


def _response_safe_ocr_confidence_band(value, *, score: float = 0.0) -> str:
    clean = str(value or "").strip()
    if clean in _OCR_RESPONSE_CONFIDENCE_BANDS:
        return clean
    if score >= 0.72:
        return "yuksek"
    if score >= 0.48:
        return "orta"
    return "dusuk" if score > 0.0 else ""


def _response_safe_ocr_quality_score(value) -> float:
    try:
        return round(max(0.0, min(float(value or 0.0), 1.0)), 3)
    except (TypeError, ValueError):
        return 0.0


def _build_response_safe_ocr_signal(*, rows=None, meta=None) -> dict:
    metas = []
    if rows is not None:
        for _, _, item in list(rows or []):
            metas.append(item if isinstance(item, dict) else {})
    elif meta is not None:
        metas.append(meta if isinstance(meta, dict) else {})

    ocr_related = [
        item
        for item in metas
        if bool(
            item.get("ocr_kullanildi")
            or item.get("ocr")
            or item.get("ocr_fallback")
            or item.get("ocr_fallback_used")
        )
    ]
    ocr_kullanildi = bool(ocr_related)
    ocr_fallback_used = any(
        bool(item.get("ocr_fallback") or item.get("ocr_fallback_used"))
        for item in metas
    )

    ocr_kaynak_turu = ""
    if ocr_fallback_used:
        ocr_kaynak_turu = "pdf_ocr_fallback"
    elif ocr_kullanildi:
        for item in ocr_related:
            safe_source = _response_safe_ocr_kaynak_turu(item.get("ocr_kaynak_turu"))
            if safe_source:
                ocr_kaynak_turu = safe_source
                break
        if not ocr_kaynak_turu and any(bool(item.get("ocr")) for item in ocr_related):
            ocr_kaynak_turu = "image_ocr"

    quality_scores = [
        _response_safe_ocr_quality_score(item.get("ocr_quality_score"))
        for item in ocr_related
        if item.get("ocr_quality_score") is not None
    ]
    ocr_quality_score = round(sum(quality_scores) / len(quality_scores), 3) if quality_scores else 0.0

    warnings = sorted(
        {
            safe_warning
            for safe_warning in (
                _response_safe_ocr_warning(item.get("ocr_warning"))
                for item in ocr_related
            )
            if safe_warning
        }
    )
    if len(warnings) > 1:
        ocr_warning = "mixed_ocr_quality"
    else:
        ocr_warning = warnings[0] if warnings else ""

    confidence_band = _response_safe_ocr_confidence_band(
        next(
            (
                item.get("ocr_confidence_band")
                for item in ocr_related
                if str(item.get("ocr_confidence_band") or "").strip()
            ),
            "",
        ),
        score=ocr_quality_score,
    )

    return {
        "ocr_kullanildi": ocr_kullanildi,
        "ocr_kaynak_turu": ocr_kaynak_turu,
        "ocr_quality_score": ocr_quality_score,
        "ocr_confidence_band": confidence_band,
        "ocr_warning": ocr_warning,
        "ocr_fallback_used": ocr_fallback_used,
    }


def _response_processing_state(*, durum: str = "") -> str:
    clean = str(durum or "").strip().lower()
    if clean == "parcalandi":
        return "ready"
    if clean in {"isleniyor", "parcalaniyor"}:
        return "processing"
    if clean == "yuklendi":
        return "queued"
    if clean == "hata":
        return "failed"
    return "unknown"


def _response_warning_code(*, ingestion_ozeti: dict | None = None) -> str:
    summary = dict(ingestion_ozeti or {})
    legacy_durum = str(summary.get("legacy_durum") or "").strip()
    if legacy_durum == "conversion_required":
        return "legacy_conversion_required"
    if bool(summary.get("ocr_fallback_used")):
        return "ocr_fallback_used"
    ocr_warning = _response_safe_ocr_warning(summary.get("ocr_warning"))
    if ocr_warning:
        return ocr_warning
    if legacy_durum == "limited":
        return "legacy_format_limited"
    return ""


def _response_status_text(*, durum: str = "", ingestion_ozeti: dict | None = None) -> str:
    summary = dict(ingestion_ozeti or {})
    processing_state = _response_processing_state(durum=durum or summary.get("durum") or "")
    if processing_state == "ready":
        if bool(summary.get("ocr_fallback_used")):
            return "Dokuman hazir. OCR fallback kullanildi."
        if bool(summary.get("ocr_kullanildi")):
            return "Dokuman hazir. OCR sinyali mevcut."
        return "Dokuman hazir."
    if processing_state == "processing":
        return "Dokuman isleniyor."
    if processing_state == "queued":
        return "Dokuman alindi."
    if processing_state == "failed":
        if str(summary.get("legacy_durum") or "").strip() == "conversion_required":
            return "Belge donusturme gerektiriyor."
        if bool(summary.get("ocr_fallback_used")):
            return "Dokuman OCR denemesine ragmen islenemedi."
        return "Dokuman islenemedi."
    return "Durum bilinmiyor."


def _safe_error_payload(
    *,
    detail: str,
    error_code: str = "",
    status_text: str = "",
    processing_state: str = "failed",
    extra: dict | None = None,
) -> dict:
    payload = {
        "detail": str(detail or "").strip(),
        "status_text": str(status_text or detail or "").strip(),
        "processing_state": str(processing_state or "failed").strip() or "failed",
    }
    if str(error_code or "").strip():
        payload["error_code"] = str(error_code).strip()
    payload.update(dict(extra or {}))
    return payload


def _api_error_payload(
    *,
    detail: str,
    error_code: str = "",
    field_errors: dict | None = None,
    extra: dict | None = None,
) -> dict:
    payload = {
        "detail": str(detail or "").strip(),
        "status_text": str(detail or "").strip(),
    }
    if str(error_code or "").strip():
        payload["error_code"] = str(error_code).strip()
    if field_errors:
        payload["field_errors"] = dict(field_errors)
    payload.update(dict(extra or {}))
    return payload


def _augment_status_payload(payload: dict, *, status_text: str = "", warning_code: str | None = None) -> dict:
    out = dict(payload or {})
    if str(status_text or "").strip():
        out["status_text"] = str(status_text).strip()
    if warning_code is not None:
        out["warning_code"] = str(warning_code or "").strip()
    return out


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


def _augment_answer_payload(
    payload: dict,
    *,
    context: str = "evidence",
    dokumanda_yok: bool | None = None,
) -> dict:
    out = dict(payload or {})
    missing = bool(out.get("dokumanda_yok")) if dokumanda_yok is None else bool(dokumanda_yok)
    answer_allowed = bool(out.get("answer_allowed")) if "answer_allowed" in out else (not missing)
    weak_evidence = bool(out.get("weak_evidence")) if "weak_evidence" in out else bool(missing)
    evidence_strength = str(out.get("evidence_strength") or ("dusuk" if weak_evidence else "yuksek")).strip() or "dusuk"
    abstain_reason = str(out.get("abstain_reason") or "").strip()
    if missing and not abstain_reason:
        abstain_reason = "dokumanda_yok"

    if missing:
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

    kaynak_guveni = str(out.get("kaynak_guveni") or "").strip()
    if not kaynak_guveni:
        if answer_state in {"not_in_document", "insufficient_evidence"}:
            kaynak_guveni = "dusuk"
        elif weak_evidence:
            kaynak_guveni = "orta"
        else:
            kaynak_guveni = "yuksek"

    out["dokumanda_yok"] = missing
    out["answer_allowed"] = bool(answer_allowed)
    out["weak_evidence"] = bool(weak_evidence)
    out["evidence_strength"] = evidence_strength
    out["abstain_reason"] = abstain_reason
    out["kaynak_guveni"] = kaynak_guveni
    out["answer_state"] = answer_state
    out["status_text"] = str(out.get("status_text") or _answer_status_text(answer_state, context=context)).strip()
    out["warning_code"] = warning_code
    return out


def _build_ingestion_ozeti(doc, *, parca_rows=None, dosya_adi: str = "") -> dict:
    rows = list(parca_rows or [])
    if not rows:
        qs = Parca.objects.filter(dokuman=doc).order_by("sira").values_list("tur", "adres", "meta")
        rows = [(tur, adres, meta if isinstance(meta, dict) else {}) for tur, adres, meta in qs]

    clean_file_name = str(dosya_adi or getattr(getattr(doc, "dosya", None), "name", "") or "").strip()
    ext = Path(clean_file_name).suffix.lower()
    turler = sorted({str(tur or "").strip() for tur, _, _ in rows if str(tur or "").strip()})
    chunk_kindleri = sorted(
        {
            str((meta or {}).get("chunk_kind") or "").strip()
            for _, _, meta in rows
            if str((meta or {}).get("chunk_kind") or "").strip()
        }
    )
    parse_yontemleri = sorted(
        {
            str((meta or {}).get("kaynak") or "").strip()
            for _, _, meta in rows
            if str((meta or {}).get("kaynak") or "").strip()
        }
    )
    ocr_signal = _build_response_safe_ocr_signal(rows=rows)
    page_bazli = any(
        bool((meta or {}).get("page") or (meta or {}).get("sayfa") or (meta or {}).get("page_address"))
        for _, _, meta in rows
    )
    adres_tutarliligi = all(
        not str((meta or {}).get("source_address") or "").strip()
        or str((meta or {}).get("source_address") or "").strip() == str(adres or "").strip()
        for _, adres, meta in rows
    )
    legacy_durum = ""
    if ext in {".doc", ".xls", ".ppt"}:
        legacy_durum = "conversion_required" if doc.durum == "hata" else "limited"

    summary = {
        "belge_kabul_edildi": True,
        "parse_tamamlandi": doc.durum in {"parcalandi", "hata"},
        "parca_uretildi": len(rows) > 0,
        "parca_sayisi": len(rows),
        "parca_turleri": turler,
        "chunk_kindleri": chunk_kindleri,
        "parse_yontemleri": parse_yontemleri or (["legacy_conversion_required"] if legacy_durum == "conversion_required" else []),
        "adres_ornekleri": [str(adres or "").strip() for _, adres, _ in rows if str(adres or "").strip()][:3],
        "adres_tutarliligi": adres_tutarliligi,
        "page_bazli": page_bazli,
        "ocr_kullanildi": ocr_signal["ocr_kullanildi"],
        "ocr_kaynak_turu": ocr_signal["ocr_kaynak_turu"],
        "ocr_quality_score": ocr_signal["ocr_quality_score"],
        "ocr_confidence_band": ocr_signal["ocr_confidence_band"],
        "ocr_warning": ocr_signal["ocr_warning"],
        "ocr_fallback_used": ocr_signal["ocr_fallback_used"],
        "legacy_durum": legacy_durum,
        "durum": doc.durum,
        "mime": getattr(doc, "mime", "") or "",
        "hata": "",
    }
    summary["processing_state"] = _response_processing_state(durum=doc.durum)
    summary["warning_code"] = _response_warning_code(ingestion_ozeti=summary)
    summary["status_text"] = _response_status_text(durum=doc.durum, ingestion_ozeti=summary)
    if str(doc.durum or "").strip().lower() == "hata":
        summary["hata"] = _safe_upload_failure_payload(ext=ext, signal=summary)["detail"]
    return summary


def _build_document_response_signal(doc, *, parca_rows=None, dosya_adi: str = "") -> dict:
    ingestion_ozeti = _build_ingestion_ozeti(doc, parca_rows=parca_rows, dosya_adi=dosya_adi)
    return {
        "parca_sayisi": int(ingestion_ozeti.get("parca_sayisi") or 0),
        "ocr": bool(ingestion_ozeti.get("ocr_kullanildi")),
        "processing_state": str(ingestion_ozeti.get("processing_state") or ""),
        "status_text": str(ingestion_ozeti.get("status_text") or ""),
        "warning_code": str(ingestion_ozeti.get("warning_code") or ""),
        "ingestion_ozeti": ingestion_ozeti,
    }

class DokumanYukle(APIView):
    """Upload request'ini dogrulayan ve uygun ingestion hattina yonlendiren temel endpoint."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [UploadThrottle]
    parser_classes = [MultiPartParser, FormParser]
    allowed_exts = None
    #allowed_exts = {
    #    ".pdf", ".doc", ".docx",
    #    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"
    #}

    def post(self, request):
        f = _request_upload_file(request)
        baslik = (request.data.get("baslik", "") if request.data else "").strip()

        if not f:
            return Response(
                _safe_error_payload(
                    detail="dosya veya file zorunlu",
                    error_code="missing_upload_file",
                    extra={"accepted_fields": ["dosya", "file"]},
                ),
                status=400,
            )

        if _filename_has_control_chars(f.name):
            return Response(
                _safe_error_payload(
                    detail="Dosya adinda gecersiz/gorunmeyen karakter var.",
                    error_code="null_characters",
                    extra={"filename": str(f.name or "")[:120]},
                ),
                status=400,
            )

        ext = normalize_extension(f.name)
        blocked_exts = set(getattr(settings, "DOCVERSE_BLOCKED_EXTENSIONS", DOCVERSE_BLOCKED_EXTENSIONS))
        if ext in blocked_exts:
            return Response(
                _safe_error_payload(
                    detail="Bu dosya türü güvenlik nedeniyle yüklenemez.",
                    error_code="blocked_extension",
                    extra={
                        "filename": f.name,
                        "extension": ext,
                        "warning_code": "blocked_extension",
                    },
                ),
                status=400,
            )
        aktif_extler = _aktif_upload_extleri(self.allowed_exts)
        if not _upload_ext_ok(f.name, aktif_extler):
            return Response(
                _safe_error_payload(
                    detail="Bu dosya türü desteklenmiyor.",
                    error_code="unsupported_extension",
                    extra={
                        "allowed": sorted(list(aktif_extler)),
                        "filename": f.name,
                        "extension": ext,
                        "warning_code": "unsupported_extension",
                    },
                ),
                status=400
            )

        probe = _sniff_upload_kind(f)
        if not probe.get("ok"):
            return Response(
                _safe_error_payload(
                    detail=str(probe.get("detail") or "Dosya guvenli gorunmuyor.").strip(),
                    error_code=str(probe.get("error_code") or "suspicious_upload").strip(),
                    status_text=str(probe.get("detail") or "Dosya guvenli gorunmuyor.").strip(),
                    extra={
                        "filename": f.name,
                        "warning_code": str(probe.get("warning_code") or "").strip(),
                    },
                ),
                status=int(probe.get("status") or 400),
            )

        doc = Dokuman.objects.create(
            owner=request.user,
            baslik=baslik or Path(f.name).stem,
            dosya=f,
            mime=mime_tahmin(f.name),
            durum="yuklendi",
        )

        if not _parser_supported_ext(ext):
            payload = _unsupported_parser_payload(ext, f.name)
            doc.durum = "parser_desteklenmiyor"
            if hasattr(doc, "hata_mesaji"):
                doc.hata_mesaji = payload["detail"]
                doc.save(update_fields=["durum", "hata_mesaji"])
            else:
                doc.hata = payload["detail"]
                doc.save(update_fields=["durum", "hata"])
            data = DokumanSerializer(doc).data
            data["doc_id"] = doc.id
            data["parca_sayisi"] = 0
            data["ocr"] = False
            data["processing_state"] = payload["processing_state"]
            data["status_text"] = payload["status_text"]
            data["warning_code"] = payload.get("warning_code", "parser_not_available")
            data["ingestion_ozeti"] = {
                "durum": doc.durum,
                "processing_state": payload["processing_state"],
                "status_text": payload["status_text"],
                "warning_code": payload.get("warning_code", "parser_not_available"),
                "parca_uretildi": False,
                "parca_sayisi": 0,
                "extension": ext,
                "file_category": category_for_extension(ext),
            }
            data.update(payload)
            data["mesaj"] = payload["detail"]
            return Response(data, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        try:
            # Gorsel ve belge ingestion hatlari ayni upload endpoint'inde kontrollu sekilde ayrisiyor.
            if is_image_ext(f.name):
                gorseli_ocr_ile_parcala_ve_kaydet(doc)
            else:
                dokumani_parcala_ve_kaydet(doc)

            doc.refresh_from_db()

        except Exception as e:
            doc.refresh_from_db()

            mevcut_hata = _safe_upload_failure_payload(ext=ext).get("detail", "")

            doc.durum = "hata"

            if hasattr(doc, "hata_mesaji"):
                doc.hata_mesaji = mevcut_hata
                doc.save(update_fields=["durum", "hata_mesaji"])
            else:
                doc.hata = mevcut_hata
                doc.save(update_fields=["durum", "hata"])

            logger.warning(
                "Upload ingestion failed for doc_id=%s ext=%s error_type=%s",
                getattr(doc, "id", None),
                ext,
                type(e).__name__,
            )

        data = DokumanSerializer(doc).data
        parca_rows = [
            (tur, adres, meta if isinstance(meta, dict) else {})
            for tur, adres, meta in Parca.objects.filter(dokuman=doc).order_by("sira").values_list("tur", "adres", "meta")
        ]
        signal = _build_document_response_signal(doc, parca_rows=parca_rows, dosya_adi=f.name)

        data["doc_id"] = doc.id
        data["parca_sayisi"] = signal["parca_sayisi"]
        data["ocr"] = signal["ocr"]
        data["processing_state"] = signal["processing_state"]
        data["status_text"] = signal["status_text"]
        data["warning_code"] = signal["warning_code"]
        data["ingestion_ozeti"] = signal["ingestion_ozeti"]
        if doc.durum == "parcalandi" and signal["parca_sayisi"] > 0:
            data["mesaj"] = "Dokuman parcalandi."
            return Response(data, status=201)

        failure_payload = _safe_upload_failure_payload(ext=ext, signal=signal["ingestion_ozeti"])
        data["detail"] = failure_payload["detail"]
        data["status_text"] = failure_payload["status_text"]
        data["warning_code"] = failure_payload.get("warning_code", data.get("warning_code", ""))
        data["processing_state"] = failure_payload["processing_state"]
        data["hata"] = failure_payload["detail"]
        data["error_code"] = failure_payload["error_code"]
        data["mesaj"] = failure_payload["detail"]
        return Response(data, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
class PdfYukleAPIView(DokumanYukle):
    allowed_exts = {".pdf"}


class WordYukleAPIView(DokumanYukle):
    allowed_exts = {".docx"}

class DokumanListe(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Dokuman.objects.filter(owner=request.user).prefetch_related("parcalar").order_by("-created_at")
        items = []
        for doc in qs:
            data = DokumanSerializer(doc).data
            parca_rows = [
                (getattr(parca, "tur", ""), getattr(parca, "adres", ""), getattr(parca, "meta", None) or {})
                for parca in doc.parcalar.all()
            ]
            signal = _build_document_response_signal(doc, parca_rows=parca_rows)
            data["parca_sayisi"] = signal["parca_sayisi"]
            data["ocr"] = signal["ocr"]
            data["processing_state"] = signal["processing_state"]
            data["status_text"] = signal["status_text"]
            data["warning_code"] = signal["warning_code"]
            items.append(data)
        return Response(items)


class DokumanParcalari(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        doc = _get_owned_doc(request, doc_id)
        if not doc:
            return Response(
                _safe_error_payload(
                    detail="Doküman yok",
                    error_code="document_not_found",
                ),
                status=404,
            )
        qs = doc.parcalar.all().order_by("sira")
        parcalar_data = [_guvenli_parca_response(parca, request=request) for parca in qs]
        parca_rows = [
            (getattr(parca, "tur", ""), getattr(parca, "adres", ""), getattr(parca, "meta", None) or {})
            for parca in qs
        ]
        signal = _build_document_response_signal(doc, parca_rows=parca_rows)
        return Response({
            "doc_id": doc.id,
            "parca_sayisi": signal["parca_sayisi"],
            "ocr": signal["ocr"],
            "processing_state": signal["processing_state"],
            "status_text": signal["status_text"],
            "warning_code": signal["warning_code"],
            "dokuman": DokumanSerializer(doc).data,
            "ingestion_ozeti": signal["ingestion_ozeti"],
            "parcalar": parcalar_data
        })




def _zorluk_label(skor: float) -> str:
    if skor is None:
        return "bilinmiyor"
    if skor >= 0.75:
        return "zor"
    if skor >= 0.40:
        return "orta"
    return "kolay"

class ZorYerler(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        limit = int(request.query_params.get("limit", 8))
        limit = max(1, min(limit, 50))

        # owner alanın "owner" ise bu doğru (senin /parcalar zaten çalıştığı için büyük ihtimalle böyle)
        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        qs = doc.parcalar.order_by("-zorluk_skoru", "id")[:limit]

        items = []
        for p in qs:
            skor = float(p.zorluk_skoru or 0.0)
            items.append({
                "id": p.id,
                "sira": getattr(p, "sira", None),
                "tur": getattr(p, "tur", ""),
                "adres": p.adres,
                "meta": _guvenli_response_meta(p.meta),
                "zorluk_skoru": skor,
                "zorluk": getattr(p, "zorluk", None) or _zorluk_label(skor),
                "metin": _guvenli_parca_preview_text(p.metin or "", limit=240),
            })

        return Response({
            "dokuman_id": doc.id,
            "limit": limit,
            "zor_yerler": items
        })
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from .models import AnlamadimKaydi
from .serializers import AnlamadimKaydiSerializer
from .models import Dokuman
from .zorluk import compute_zorluk_skoru


class ZorYerlerHesapla(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, doc_id: int):
        doc = Dokuman.objects.filter(id=doc_id, owner_id=request.user.id).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        parcalar = list(doc.parcalar.all())  # related_name: parcalar
        updated = 0

        with transaction.atomic():
            for p in parcalar:
                skor, _dbg = compute_zorluk_skoru(p.metin or "")
                # aynıysa boşuna yazma
                if float(p.zorluk_skoru or 0.0) != float(skor):
                    p.zorluk_skoru = skor
                    p.save(update_fields=["zorluk_skoru"])
                    updated += 1

        top = sorted(parcalar, key=lambda x: float(x.zorluk_skoru or 0.0), reverse=True)[:8]
        return Response({
            "doc_id": doc.id,
            "updated": updated,
            "top": [
                {"parca_id": p.id, "adres": p.adres, "skor": float(p.zorluk_skoru or 0.0)}
                for p in top
            ]
        })

    # istersen GET ile de çalışsın:
    def get(self, request, doc_id: int):
        return self.post(request, doc_id)

class Anlamadim(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ExplainThrottle]

    def post(self, request, parca_id: int, *args, **kwargs):
        p = Parca.objects.select_related("dokuman").filter(id=parca_id).first()
        if not p or (p.dokuman.owner_id != request.user.id):
            return Response(
                _api_error_payload(detail="Parça yok", error_code="resource_not_found"),
                status=404,
            )

        tema = (request.data.get("tema") or "")
        seviye = (request.data.get("seviye") or "orta")

        payload = build_anlamadim_payload(p.metin or "", tema=tema, seviye=seviye)

        return Response(
            _augment_answer_payload(
                {
                    "parca_id": p.id,
                    "doc_id": p.dokuman_id,
                    "adres": p.adres,
                    "zorluk_skoru": float(p.zorluk_skoru or 0.0),
                    **payload,
                },
                context="explain",
            )
        )

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

_EVIDENCE_AI_TIMEOUT_SECONDS = 60


def _evidence_log(message: str, **fields):
    safe_parts = [str(message or "").strip()]
    for key, value in fields.items():
        safe_parts.append(f"{key}={value}")
    logger.info(" ".join(part for part in safe_parts if part))


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
            address = str(hit.get("adres") or hit.get("path") or "").strip()
            part_id = hit.get("parca_id") or hit.get("part_id")
            score = hit.get("score") if hit.get("score") is not None else hit.get("skor")
        else:
            text = getattr(hit, "metin", "") or ""
            address = str(getattr(hit, "adres", "") or "").strip()
            part_id = getattr(hit, "id", None)
            score = 0.0
        snippet = _evidence_snippet_text(text)
        if not snippet:
            continue
        snippets.append(
            {
                "text": snippet,
                "snippet": snippet,
                "source": address,
                "path": address,
                "adres": address,
                "part_id": part_id,
                "parca_id": part_id,
                "score": float(score or 0.0),
                "skor": float(score or 0.0),
            }
        )
    return snippets


def _evidence_empty_response(question: str, warning: str = "Bu soru için kanıt bulunamadı.") -> dict:
    return _augment_answer_payload(
        {
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
        },
        context="evidence",
    )


def _evidence_fallback_response(question: str, snippets: list[dict], *, warning: str | None = None) -> dict:
    if not snippets:
        return _evidence_empty_response(question)
    first = snippets[0]
    text = str(first.get("text") or first.get("snippet") or "").strip()
    answer = (
        "Bu soruya göre belgede en ilgili bölüm şunu anlatıyor: "
        + _evidence_snippet_text(text, limit=220)
    )
    return _augment_answer_payload(
        {
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
            "warning": warning or "AI servisi geçici olarak cevap üretemedi, kanıta dayalı hızlı cevap gösterildi.",
            "dokumanda_yok": False,
            "answer_allowed": True,
            "weak_evidence": True,
        },
        context="evidence",
    )


def _evidence_ai_response(question: str, answer: str, snippets: list[dict]) -> dict:
    clean_answer = str(answer or "").strip()
    if not clean_answer:
        return _evidence_fallback_response(question, snippets)
    return _augment_answer_payload(
        {
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
        },
        context="evidence",
    )


class KanitliSor(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EvidenceThrottle]
    # ✅ Gate: SADECE default mod + skip_gate False
    def _safe_post(self, request):
        import time

        started_at = time.monotonic()
        doc_id = request.data.get("doc_id") or request.data.get("document_id")
        parca_id = request.data.get("part_id") or request.data.get("parca_id")
        soru = (request.data.get("soru") or request.data.get("question") or "").strip()

        _evidence_log(
            "EVIDENCE started",
            question_len=len(soru),
            doc_id=doc_id or "",
            part_id=parca_id or "",
        )

        if not doc_id or not soru:
            field_errors = {}
            if not doc_id:
                field_errors["doc_id"] = ["Bu alan zorunludur."]
            if not soru:
                field_errors["question"] = ["Bu alan zorunludur."]
            return Response(
                _api_error_payload(
                    detail="doc_id ve question zorunlu",
                    error_code="validation_error",
                    field_errors=field_errors,
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
                ),
                status=400,
            )

        doc = Dokuman.objects.filter(id=doc_id_int, owner=request.user).first()
        _evidence_log("EVIDENCE validation", has_doc=bool(doc))
        if not doc:
            return Response(
                _api_error_payload(
                    detail="Geçerli doküman bulunamadı.",
                    error_code="resource_not_found",
                    field_errors={"doc_id": ["Geçerli doküman bulunamadı."]},
                ),
                status=404,
            )

        forced_part = None
        if parca_id:
            try:
                forced_part_id = int(parca_id)
            except (TypeError, ValueError):
                return Response(
                    _api_error_payload(
                        detail="Geçersiz parça.",
                        error_code="validation_error",
                        field_errors={"part_id": ["Geçersiz parça."]},
                    ),
                    status=400,
                )
            forced_part = doc.parcalar.filter(id=forced_part_id).first()
            if not forced_part:
                return Response(
                    _api_error_payload(
                        detail="Parça bu dokümana ait değil.",
                        error_code="validation_error",
                        field_errors={"part_id": ["Parça bu dokümana ait değil."]},
                    ),
                    status=400,
                )

        try:
            _evidence_log("retrieval_started")
            parcalar_qs = doc.parcalar.all().order_by("sira")
            parcalar = [forced_part] if forced_part is not None else list(parcalar_qs)
            parcalar = [p for p in parcalar if p is not None and str(getattr(p, "metin", "") or "").strip()]
            if not parcalar:
                _evidence_log("retrieval_done", snippet_count=0)
                payload = _evidence_empty_response(soru)
                _evidence_log("response_source=empty")
                return Response(payload)

            picked_chunks = []
            if forced_part is not None:
                picked_chunks = [forced_part]
            else:
                texts = [p.metin for p in parcalar]
                idxs = en_alakali(soru, texts, top_k=5)
                picked_chunks = [parcalar[i] for i in idxs if 0 <= i < len(parcalar)]
                if not picked_chunks:
                    picked_chunks = parcalar[:3]

            try:
                kanit_meta = orchestrate_evidence_selection(
                    soru,
                    picked_chunks,
                    answer_limit=min(3, len(picked_chunks) or 1),
                    dokuman_filtresi_var_mi=True,
                    varsayilan_dokuman_id=doc.id,
                    retrieval_kaynagi="legacy.object_retrieval",
                )
                hits = list(kanit_meta.get("secilen_kanitlar") or kanit_meta.get("kanitlar") or [])
            except Exception as exc:
                _evidence_log("retrieval_error", error_type=type(exc).__name__)
                hits = picked_chunks

            snippets = _evidence_snippets_from_hits(hits)
            _evidence_log("retrieval_done", snippet_count=len(snippets))
            if not snippets:
                payload = _evidence_empty_response(soru)
                _evidence_log("response_source=empty")
                return Response(payload)
        except Exception as exc:
            _evidence_log("retrieval_error", error_type=type(exc).__name__)
            payload = _evidence_empty_response(soru)
            _evidence_log("response_source=empty")
            return Response(payload)

        try:
            _evidence_log("ai_started")
            prompt_parts = []
            for idx, item in enumerate(snippets[:3], start=1):
                prompt_parts.append(f"[{idx}] {item.get('path') or ''}: {item.get('text') or ''}")
            prompt = (
                "Sadece verilen kanıtlara dayanarak Türkçe, kısa ve net cevap ver.\n"
                "Kanıtta olmayan bilgi ekleme. En fazla 3 cümle yaz.\n\n"
                f"SORU: {soru}\n\nKANITLAR:\n" + "\n".join(prompt_parts)
            )
            max_t = ai2_scope_icin_max_token("QA", request.data.get("max_tokens"), minimum=64)
            future = _AI2_FAST_EXECUTOR.submit(llm_tamamla, prompt, max_t)
            answer = str(future.result(timeout=_EVIDENCE_AI_TIMEOUT_SECONDS) or "").strip()
            elapsed = round(time.monotonic() - started_at, 2)
            if not answer:
                raise RuntimeError("empty_ai_answer")
            _evidence_log("ai_success", elapsed_sec=elapsed)
            payload = _evidence_ai_response(soru, answer, snippets)
            _evidence_log("response_source=ai")
            return Response(payload)
        except FuturesTimeoutError:
            _evidence_log("ai_error fallback_used", error_type="timeout")
            payload = _evidence_fallback_response(soru, snippets)
            _evidence_log("response_source=fallback")
            return Response(payload)
        except Exception as exc:
            _evidence_log("ai_error fallback_used", error_type=type(exc).__name__)
            payload = _evidence_fallback_response(soru, snippets)
            _evidence_log("response_source=fallback")
            return Response(payload)

    def post(self, request):
        try:
            return self._safe_post(request)
        except Exception as exc:
            logger.exception("EVIDENCE unhandled_safe_response error_type=%s", type(exc).__name__)
            return Response(
                _evidence_empty_response(
                    (request.data.get("soru") or request.data.get("question") or "").strip(),
                    warning="Kanıtlı cevap hazırlanamadı, lütfen tekrar deneyin.",
                ),
                status=200,
            )

        doc_id = request.data.get("doc_id") or request.data.get("document_id")
        parca_id = request.data.get("part_id") or request.data.get("parca_id")
        soru = (request.data.get("soru") or request.data.get("question") or "").strip()
        mode = (request.data.get("mode") or "default").strip().lower()  # default | grade | explain
        skip_gate = bool(request.data.get("skip_gate"))

        if not doc_id or not soru:
            field_errors = {}
            if not doc_id:
                field_errors["doc_id"] = ["Bu alan zorunludur."]
            if not soru:
                field_errors["question"] = ["Bu alan zorunludur."]
            return Response(
                _api_error_payload(
                    detail="doc_id ve question zorunlu",
                    error_code="validation_error",
                    field_errors=field_errors,
                ),
                status=400,
            )

        # ✅ doc TANIMLI (bu satır yoksa NameError alırsın)
        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response(
                _api_error_payload(detail="Doküman yok", error_code="resource_not_found"),
                status=404,
            )

        if parca_id:
            try:
                parca_id = int(parca_id)
            except (TypeError, ValueError):
                return Response(
                    _api_error_payload(
                        detail="Parça geçersiz",
                        error_code="validation_error",
                        field_errors={"part_id": ["Geçersiz parça."]},
                    ),
                    status=400,
                )
            if not doc.parcalar.filter(id=parca_id).exists():
                return Response(
                    _api_error_payload(
                        detail="Parça bu dokümana ait değil",
                        error_code="validation_error",
                        field_errors={"part_id": ["Parça bu dokümana ait değil."]},
                    ),
                    status=400,
                )

        parcalar = list(doc.parcalar.all().order_by("sira"))
        texts = [x.metin for x in parcalar]

        idxs = en_alakali(soru, texts, top_k=5)
        picked_chunks = [parcalar[i] for i in idxs if 0 <= i < len(parcalar)]

        if not picked_chunks:
            return Response(
                _augment_answer_payload(
                    {
                        "soru": soru,
                        "dokumanda_yok": True,
                        "cevap": "Dokümanda yok.",
                        "kanitlar": [],
                        "kanit_snippet": [],
                        "mod": "no_chunks",
                    },
                    context="evidence",
                )
            )

        kanit_meta = orchestrate_evidence_selection(
            soru,
            picked_chunks,
            answer_limit=min(3, len(picked_chunks) or 1),
            dokuman_filtresi_var_mi=True,
            varsayilan_dokuman_id=doc.id,
            retrieval_kaynagi="legacy.object_retrieval",
        )
        tum_kanitlar = list(kanit_meta["kanitlar"])
        secilen_kanitlar = list(kanit_meta["secilen_kanitlar"]) or tum_kanitlar
        kanit_snippet = [
            {"parca_id": hit.get("parca_id"), "adres": hit.get("adres"), "snippet": hit.get("snippet")}
            for hit in tum_kanitlar
        ]
        kanit_gate = [{"adres": hit.get("adres"), "metin": hit.get("metin")} for hit in tum_kanitlar]
        kanitlar_compact = [
            {"parca_id": hit.get("parca_id"), "adres": hit.get("adres")}
            for hit in tum_kanitlar
        ]
        ortak_evidence_payload = build_evidence_response_payload(
            kanit_meta,
            include_kanitlar=False,
            include_kaynak_zorlamasi=False,
        )

        skip_gate = skip_gate or _gate_bypass_for_formula_questions(soru, kanit_gate)
        if (mode == "default") and (not skip_gate) and (not tanim_var_mi(soru, kanit_gate)):
        
            soru_lower = (soru or "").lower()
            tanimsal_soru = any(k in soru_lower for k in ["nedir", "ne demek", "açılım", "acilim", "tanım", "tanim"])
        
            adresler = [
                str(hit.get("adres") or "").strip()
                for hit in secilen_kanitlar
                if str(hit.get("adres") or "").strip()
            ]
            adresler = adresler[:5]
        
            if tanimsal_soru:
                cevap_msg = (
                    "Dokümanda bu sorunun **tanımı/açıklaması** bulunamadı. "
                    "Ama terim/ifade dokümanda şu parçalarda **geçiyor**: "
                    + ", ".join(adresler)
                    + "."
                )
            else:
                cevap_msg = (
                    "Dokümanda soruya birebir cevap veren ifade bulunamadı. "
                    "En yakın geçen yerler: "
                    + ", ".join(adresler)
                    + "."
                )
        
            return Response(
                _augment_answer_payload(
                    {
                        "soru": soru,
                        "dokumanda_yok": True,
                        "cevap": cevap_msg,
                        "kanitlar": kanitlar_compact,
                        "kanit_snippet": kanit_snippet,
                        "mod": "gate",
                        **ortak_evidence_payload,
                    },
                    context="evidence",
                )
            )

        # --- LLM durumu ---
        yerel_model_nesnesi = yerel_modeli_al()
        yerel_model_hazir = yerel_model_nesnesi is not None

        # --- GGUF VARSA: LLM ile cevap ---
        if yerel_model_hazir:
            try:
                kanit_parcalar_llm = []
                for hit in secilen_kanitlar:
                    metin = str(hit.get("metin") or "")
                    if len(metin) > 500:
                        metin = metin[:500] + "..."
                    kanit_parcalar_llm.append(
                        {
                            "adres": str(hit.get("adres") or ""),
                            "metin": metin,
                        }
                    )
                    import re

                # ✅ FAST-PATH: "formül / skor / equation" sorularında LLM'e sormadan kanıttan çek
                soru_l = soru.lower()
                if any(k in soru_l for k in ["formül", "formula", "denklem", "equation", "skor"]) :
                    formula_lines = []
                    for hit in secilen_kanitlar:
                        for ln in str(hit.get("metin") or "").splitlines():
                            lns = ln.strip()
                            # "skor =" veya "=" içeren formül satırı yakala
                            if ("=" in lns) and ("skor" in lns.lower() or "formula" in lns.lower() or "formül" in lns.lower()):
                                formula_lines.append((str(hit.get("adres") or ""), lns))
                            # "Formül:" ile başlayan satır da yakala
                            if lns.lower().startswith("formül:") or lns.lower().startswith("formula:"):
                                formula_lines.append((str(hit.get("adres") or ""), lns))
                
                    if formula_lines:
                        # ilk yakalananı kullan (genelde txt:para:1)
                        adr, fln = formula_lines[0]
                        cevap_txt = (
                            f"- Açıklama: Dokümanda skor/formül satırı şöyle geçiyor: {fln}\n"
                            f"  Kanıt: [{adr}]"
                        )
                        return Response(
                            _augment_answer_payload(
                                {
                                    "soru": soru,
                                    "dokumanda_yok": False,
                                    "cevap": cevap_txt,
                                    "kanitlar": kanitlar_compact,
                                    "kanit_snippet": kanit_snippet,
                                    "mod": "fast_formula",
                                    "llm_ok": yerel_model_hazir,
                                    **ortak_evidence_payload,
                                },
                                context="evidence",
                            )
                        )
                # mode’a göre prompt
                if mode == "grade":
                    soru_llm = soru + "\n\nKURAL: Yukarıdaki formatı aynen uygula. PUAN ve FEEDBACK mutlaka olsun. Türkçe yaz."
                elif mode == "explain":
                    # explain: tagli şablon bekliyorsun (ParcaAnlamadimV2 parse ediyor)
                    soru_llm = soru
                else:
                    soru_llm = soru + (
                        "\n\nKURAL (ÇOK ÖNEMLİ): Sadece dokümandaki kanıt metinlerine dayan.\n"
                        "Uydurma yok. Bilgi yoksa 'Dokümanda yok.' de.\n"
                        "ÇIKTI FORMATI: En fazla 3 madde. Her madde 2 satır:\n"
                        "- Açıklama: ...\n"
                        "  Kanıt: [txt:para:X]\n"
                        "En az 1 kanıt etiketi kullanman yeterli. 3 farklı kaynak zorunlu değil.\n"
                        "Bu format dışında hiçbir şey yazma."
                    )
                max_t = ai2_scope_icin_max_token(
                    "EXPLAIN" if mode == "explain" else "QA",
                    request.data.get("max_tokens"),
                )
                cevap = llm_tamamla(soru_llm, max_tokens=max_t).strip()

                if cevap.strip().lower() in ["dokümanda yok", "dokümanda yok."]:
                    soru_lower = (soru or "").lower()
                    tanimsal_soru = any(k in soru_lower for k in ["nedir", "ne demek", "açılım", "acilim", "tanım", "tanim"])
                    adresler = [
                        str(hit.get("adres") or "").strip()
                        for hit in secilen_kanitlar
                        if str(hit.get("adres") or "").strip()
                    ][:5]
                
                    cevap_msg = "Dokümanda yok."
                    if adresler:
                        if tanimsal_soru:
                            cevap_msg = "Dokümanda tanım yok; ama terim şu parçalarda geçiyor: " + ", ".join(adresler) + "."
                        else:
                            cevap_msg = "Dokümanda birebir cevap yok; en yakın geçen yerler: " + ", ".join(adresler) + "."
                
                    return Response(
                        _augment_answer_payload(
                            {
                                "soru": soru,
                                "dokumanda_yok": True,
                                "cevap": cevap_msg,
                                "kanitlar": kanitlar_compact,
                                "kanit_snippet": kanit_snippet,
                                "mod": "gguf",
                                "llm_ok": yerel_model_hazir,
                                **ortak_evidence_payload,
                            },
                            context="evidence",
                        )
                    )

                # Kaynak yoksa otomatik kaynakla (grade modunda da iş görür)
                if (mode != "explain") and ("[txt:" not in cevap):
                    cevap = _auto_kaynakla(cevap, kanit_parcalar_llm)

                return Response(
                    _augment_answer_payload(
                        {
                            "soru": soru,
                            "dokumanda_yok": False,
                            "cevap": cevap,
                            "kanitlar": kanitlar_compact,
                            "kanit_snippet": kanit_snippet,
                            "mod": "gguf",
                            "llm_ok": yerel_model_hazir,
                            **ortak_evidence_payload,
                        },
                        context="evidence",
                    )
                )

            except Exception as e:
                # grade modunda basit fallback
                if mode == "grade":
                    kanit_lines = "\n".join([f"- {k['adres']}: {k['metin'][:120]}..." for k in kanit_gate[:2]])
                    cevap_fallback = (
                        "PUAN: 60\n"
                        "FEEDBACK: Cevabın kısmen doğru ama dokümandan kanıt ekleyip daha net yazman gerekiyor.\n"
                        "EKSİKLER:\n"
                        "- Dokümandan 1-2 kanıt ekle\n"
                        "- Tanımı daha netleştir\n"
                        "KANIT:\n"
                        f"{kanit_lines}"
                    )
                    return Response(
                        _augment_answer_payload(
                            {
                                "soru": soru,
                                "dokumanda_yok": False,
                                "cevap": cevap_fallback,
                                "kanitlar": kanitlar_compact,
                                "kanit_snippet": kanit_snippet,
                                "mod": f"grade_fallback({e})",
                                "llm_ok": yerel_model_hazir,
                                **ortak_evidence_payload,
                            },
                            context="evidence",
                        )
                    )
                # default/explain: heuristic'e düş
                pass

        # --- LLM YOKSA: HEURISTIC (default) ---
        qs = doc.parcalar.all().order_by("-zorluk_skoru")
        zorlar = list(qs.filter(zorluk="zor")[:1])
        ortalar = list(qs.filter(zorluk="orta")[:2])
        secilen = zorlar + ortalar
        secilen_ids = {p.id for p in secilen}

        if len(secilen) < 3:
            ekstra = list(qs.exclude(id__in=secilen_ids)[: (3 - len(secilen))])
            secilen += ekstra

        bullets = []
        kanitlar = []
        kanit_snippet2 = []

        for p in secilen:
            aciklama, ornek = _heuristic_item(p.metin)
            bullets.append(f"- {aciklama}\n  Örnek: {ornek} [{p.adres}]")
            kanitlar.append({"parca_id": p.id, "adres": p.adres})
            kanit_snippet2.append({"parca_id": p.id, "adres": p.adres, "snippet": _metin_ozeti(p.metin)})

        gecen_adresler = [
            str(hit.get("adres") or "").strip()
            for hit in secilen_kanitlar
            if str(hit.get("adres") or "").strip()
        ]

        return Response(
            _augment_answer_payload(
                {
                    "soru": soru,
                    "dokumanda_yok": True,
                    "cevap_tipi": "tanim_yok_geciyor",
                    "gecen_adresler": gecen_adresler,
                    "cevap": f"Dokümanda bu sorunun **tanımı/açıklaması** bulunamadı. Ama terim/ifade dokümanda şu parçalarda **geçiyor**: {', '.join(gecen_adresler)}.",
                    "kanitlar": kanitlar_compact,
                    "kanit_snippet": kanit_snippet,
                    "mod": "gate",
                    **ortak_evidence_payload,
                },
                context="evidence",
            )
        )

class ProfilView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profil, _ = Profil.objects.get_or_create(user=request.user)
        return Response(ProfilSerializer(profil).data)

    def put(self, request):
        profil, _ = Profil.objects.get_or_create(user=request.user)
        ser = ProfilSerializer(profil, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


def _modul_kapali_response(detay: str):
    return Response(
        _api_error_payload(detail=detay, error_code="resource_not_found"),
        status=404,
    )


def _concepts_disabled_payload(**extra) -> dict:
    payload = {
        "enabled": False,
        "concepts": [],
        "relations": [],
        "detail": t("concepts_disabled", "tr"),
        "error_code": "feature_disabled",
    }
    payload.update(extra)
    return payload


def _panel_flag_enabled(panel_flag: str, *, base_flag: str | None = None, default: bool = True) -> bool:
    if base_flag and not modul_acik_mi(base_flag, default):
        return False
    base_default = modul_acik_mi(base_flag, default) if base_flag else default
    return modul_acik_mi(panel_flag, base_default)


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "evet", "yes", "on"}


def _parse_int_list(value) -> list[int]:
    if isinstance(value, list):
        raw_items = value
    elif value in (None, ""):
        raw_items = []
    else:
        raw_items = [value]

    clean = []
    seen = set()
    for item in raw_items:
        try:
            item_id = int(item)
        except Exception:
            continue
        if item_id in seen:
            continue
        seen.add(item_id)
        clean.append(item_id)
    return clean


def _guvenli_meta_dict(value):
    return value if isinstance(value, dict) else {}


_PARCA_RESPONSE_META_ALLOWLIST = {
    "format",
    "chunk_kind",
    "chunk_title",
    "office_document_type",
    "office_unit_kind",
    "office_unit_title",
    "page",
    "sayfa",
    "slide",
    "sheet",
    "ocr",
    "ocr_fallback",
    "ocr_kullanildi",
    "ocr_kaynak_turu",
    "ocr_quality_score",
    "ocr_confidence_band",
    "ocr_warning",
    "ocr_fallback_used",
    "code_language",
    "code_unit_kind",
    "code_unit_name",
    "parent_unit",
    "test_step_kind",
    "line_start",
    "line_end",
    "quality_score",
    "difficulty_score",
    "weak_content",
    "short_valid",
}


def _guvenli_response_meta(value):
    meta = value if isinstance(value, dict) else {}
    out = {}
    for key in _PARCA_RESPONSE_META_ALLOWLIST:
        item = meta.get(key)
        if item is not None:
            out[key] = item
    ocr_signal = _build_response_safe_ocr_signal(meta=meta)
    if ocr_signal["ocr_kullanildi"] or ocr_signal["ocr_fallback_used"]:
        out.update(
            {
                "ocr_kullanildi": ocr_signal["ocr_kullanildi"],
                "ocr_kaynak_turu": ocr_signal["ocr_kaynak_turu"],
                "ocr_quality_score": ocr_signal["ocr_quality_score"],
                "ocr_confidence_band": ocr_signal["ocr_confidence_band"],
                "ocr_warning": ocr_signal["ocr_warning"],
                "ocr_fallback_used": ocr_signal["ocr_fallback_used"],
            }
        )
    return out


def _guvenli_parca_preview_text(value: str, limit: int = 240) -> str:
    clean = " ".join(str(value or "").split()).strip()
    if len(clean) <= limit:
        return clean
    short = clean[:limit].rsplit(" ", 1)[0].strip()
    return (short or clean[:limit].strip()) + "..."


def _request_language(request=None) -> str:
    if request is None:
        return "tr"
    return request.headers.get("Accept-Language") or request.META.get("HTTP_ACCEPT_LANGUAGE") or "tr"


def _hardest_parts_feature_enabled() -> bool:
    return bool(getattr(settings, "DOCVERSE_HARDEST_PARTS_ENABLED", True))


def _parca_difficulty_profile(parca, *, request=None) -> tuple[float | None, str | None, list[str]]:
    if not _hardest_parts_feature_enabled():
        return None, None, []
    meta = getattr(parca, "meta", None) if isinstance(getattr(parca, "meta", None), dict) else {}
    profile = calculate_part_difficulty(
        getattr(parca, "metin", "") or "",
        meta,
        language=_request_language(request),
    )
    score = float(profile["difficulty_score"])
    reasons = list(profile["difficulty_reasons"])
    stored_score = getattr(parca, "zorluk_skoru", None)
    meta_score = meta.get("difficulty_score") if isinstance(meta, dict) else None
    try:
        chosen_score = float(stored_score if stored_score not in (None, "") else meta_score)
    except (TypeError, ValueError):
        chosen_score = score
    if chosen_score <= 0.0 and score > 0.0:
        chosen_score = score
    label = difficulty_label_from_score(chosen_score)
    if not reasons:
        raw_reason = str(meta.get("difficulty_reason") or "").strip()
        if raw_reason:
            reasons = [raw_reason]
    return round(max(0.0, min(float(chosen_score), 1.0)), 3), label, reasons[:4]


def _guvenli_sinyal_metni(value: str, *, label: str = "metin") -> str:
    clean = " ".join(str(value or "").split()).strip()
    if not clean:
        return ""
    return f"{label}_sinyali: {len(clean.split())} kelime, {len(clean)} karakter."


def _guvenli_debug_text(value: str, *, label: str) -> str:
    clean = " ".join(str(value or "").split()).strip()
    if not clean:
        return ""
    return f"[{label}_redacted len={len(clean)}]"


def _guvenli_debug_url(value: str) -> str:
    return "configured_endpoint" if str(value or "").strip() else ""


def _guvenli_parca_response(parca, *, text_limit: int = 240, request=None) -> dict:
    difficulty_score, difficulty_label, difficulty_reasons = _parca_difficulty_profile(parca, request=request)
    meta = _guvenli_response_meta(getattr(parca, "meta", None))
    title = (
        meta.get("baslik")
        or meta.get("chunk_title")
        or meta.get("heading_title")
        or getattr(parca, "adres", "")
        or f"Parca {getattr(parca, 'sira', '')}".strip()
    )
    preview = _guvenli_parca_preview_text(getattr(parca, "metin", "") or "", limit=text_limit)
    return {
        "id": getattr(parca, "id", None),
        "sira": getattr(parca, "sira", None),
        "tur": getattr(parca, "tur", ""),
        "adres": getattr(parca, "adres", "") or "",
        "path": getattr(parca, "adres", "") or "",
        "baslik": title,
        "title": title,
        "meta": meta,
        "zorluk_skoru": getattr(parca, "zorluk_skoru", None),
        "zorluk": getattr(parca, "zorluk", None) if difficulty_label is None else (getattr(parca, "zorluk", None) or difficulty_label),
        "difficulty_score": difficulty_score,
        "difficulty_label": difficulty_label,
        "difficulty_reasons": difficulty_reasons,
        "metin": preview,
        "icerik": preview,
        "content": preview,
        "preview": preview,
    }


def _get_owned_doc(request, dokuman_id):
    if not dokuman_id:
        return None
    return Dokuman.objects.filter(id=dokuman_id, owner_id=request.user.id).first()


def _get_owned_parca(request, parca_id):
    if not parca_id:
        return None
    return Parca.objects.select_related("dokuman").filter(
        id=parca_id,
        dokuman__owner_id=request.user.id,
    ).first()


def _concept_path_for_part(parca) -> str:
    meta = getattr(parca, "meta", {}) or {}
    title = meta.get("baslik") or meta.get("title") or getattr(parca, "adres", "") or ""
    if title:
        return str(title)
    order = getattr(parca, "sira", None)
    return f"Parça {order}" if order is not None else ""


def _concepts_for_text(*, text: str, lang: str, parca=None, glossary_items: list | None = None) -> list[dict]:
    concepts = extract_concepts_from_text(text or "", lang=lang)
    by_id = {item["id"]: dict(item) for item in concepts}
    for raw in glossary_items or []:
        if not isinstance(raw, dict):
            continue
        term = str(raw.get("terim") or raw.get("term") or raw.get("title") or "").strip()
        if not term:
            continue
        key = normalize_concept(term)
        definition = str(raw.get("tanim") or raw.get("definition") or raw.get("aciklama") or "").strip()
        by_id[key] = {
            "id": key,
            "term": term,
            "definition": definition or concept_definition_fallback(term, text or "", lang),
            "example": f"{term} bu parçayı anlamak için anahtar bir kavramdır.",
            "source_part_id": getattr(parca, "id", None),
            "path": _concept_path_for_part(parca) if parca is not None else "",
            "confidence": max(float(by_id.get(key, {}).get("confidence") or 0), 0.84),
        }
    out = list(by_id.values())
    for item in out:
        if parca is not None:
            item["source_part_id"] = getattr(parca, "id", None)
            item["path"] = item.get("path") or _concept_path_for_part(parca)
    out.sort(key=lambda item: (-float(item.get("confidence") or 0), str(item.get("term") or "").lower()))
    return out[:16]


def _concepts_for_document(*, doc, lang: str) -> list[dict]:
    merged: dict[str, dict] = {}
    for parca in doc.parcalar.all().order_by("sira", "id"):
        text = getattr(parca, "metin", "") or ""
        for item in _concepts_for_text(text=text, lang=lang, parca=parca):
            key = item["id"]
            current = merged.get(key)
            if current is None or float(item.get("confidence") or 0) > float(current.get("confidence") or 0):
                merged[key] = dict(item)
    concepts = list(merged.values())
    concepts.sort(key=lambda item: (-float(item.get("confidence") or 0), str(item.get("term") or "").lower()))
    return concepts[:24]


class DokumanKavramlarAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        lang = get_request_lang(request)
        if not modul_acik_mi("DOCVERSE_CONCEPTS_ENABLED", True):
            return Response(_concepts_disabled_payload(document_id=doc_id, summary={"concept_count": 0, "relation_count": 0}))

        doc = _get_owned_doc(request, doc_id)
        if not doc:
            return Response(_safe_error_payload(detail=t("resource_not_found", lang), error_code="resource_not_found"), status=404)

        parts = list(doc.parcalar.all().order_by("sira", "id"))
        text = "\n".join(getattr(part, "metin", "") or "" for part in parts)
        concepts = _concepts_for_document(doc=doc, lang=lang)
        relations = build_concept_relations(concepts, text)
        return Response(
            {
                "enabled": True,
                "document_id": doc.id,
                "concepts": concepts,
                "relations": relations,
                "summary": {
                    "concept_count": len(concepts),
                    "relation_count": len(relations),
                },
            }
        )


class ParcaKavramlarAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, parca_id: int):
        lang = get_request_lang(request)
        if not modul_acik_mi("DOCVERSE_CONCEPTS_ENABLED", True):
            return Response(_concepts_disabled_payload(part_id=parca_id))

        parca = _get_owned_parca(request, parca_id)
        if not parca:
            return Response(_safe_error_payload(detail=t("resource_not_found", lang), error_code="resource_not_found"), status=404)

        text = getattr(parca, "metin", "") or ""
        concepts = _concepts_for_text(text=text, lang=lang, parca=parca)
        relations = build_concept_relations(concepts, text)
        return Response({"enabled": True, "part_id": parca.id, "concepts": concepts, "relations": relations})


class DokumanKavramAraAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        lang = get_request_lang(request)
        query = str(request.query_params.get("q") or "").strip()
        if not modul_acik_mi("DOCVERSE_CONCEPTS_ENABLED", True):
            return Response(_concepts_disabled_payload(document_id=doc_id, query=query, mentions=[]))
        if not query or len(query) < 2:
            return Response(_api_error_payload(detail=t("invalid_concept_query", lang), error_code="invalid_concept_query"), status=400)

        doc = _get_owned_doc(request, doc_id)
        if not doc:
            return Response(_safe_error_payload(detail=t("resource_not_found", lang), error_code="resource_not_found"), status=404)

        concepts = _concepts_for_document(doc=doc, lang=lang)
        query_id = normalize_concept(query)
        concept = next((item for item in concepts if item.get("id") == query_id), None)
        mentions = find_concept_mentions(doc, query)
        if concept is None and mentions:
            concept = {
                "id": query_id,
                "term": query,
                "definition": concept_definition_fallback(query, mentions[0].get("snippet", ""), lang),
                "example": f"{query} bu dokümanda geçen önemli bir kavramdır.",
                "source_part_id": mentions[0].get("part_id"),
                "path": mentions[0].get("path", ""),
                "confidence": 0.72,
            }
        if concept is None:
            concept = {
                "id": query_id,
                "term": query,
                "definition": t("concept_not_found", lang),
                "example": "",
                "source_part_id": None,
                "path": "",
                "confidence": 0.0,
            }
        return Response({"enabled": True, "query": query, "concept": concept, "mentions": mentions})


def _get_owned_parcalar(request, parca_idleri: list[int]):
    if not parca_idleri:
        return []
    qs = Parca.objects.select_related("dokuman").filter(
        id__in=parca_idleri,
        dokuman__owner=request.user,
    )
    by_id = {parca.id: parca for parca in qs}
    return [by_id[parca_id] for parca_id in parca_idleri if parca_id in by_id]


def _get_owned_not(request, not_id):
    if not not_id:
        return None
    return Not.objects.filter(owner=request.user, id=not_id).first()


def _get_owned_portal_not(request, portal_not_id):
    if not portal_not_id:
        return None
    return DokumanNotu.objects.filter(owner=request.user, id=portal_not_id).first()


def _record_note_metric(
    *,
    request,
    olay_turu: str,
    not_obj=None,
    portal_not_obj=None,
    dokuman=None,
    parca=None,
    not_turu: str = "",
    etiketler=None,
    kaynak_parca_idleri=None,
    durum: str = "ok",
):
    guvenli_metrik_kaydi_olustur(
        kullanici=request.user,
        olay_turu=olay_turu,
        kaynak_modul="notlar.api" if not_obj is not None else "portal_notlar.api",
        dokuman=dokuman or getattr(not_obj, "dokuman", None) or getattr(portal_not_obj, "dokuman", None),
        parca=parca or getattr(not_obj, "parca", None) or getattr(portal_not_obj, "parca", None),
        ilgili_not_id=getattr(not_obj, "id", None),
        ilgili_portal_not_id=getattr(portal_not_obj, "id", None),
        skor_ozeti={
            "not_turu": str(not_turu or getattr(not_obj, "not_turu", "") or getattr(portal_not_obj, "not_turu", "")),
            "etiket_sayisi": len(etiketler or getattr(not_obj, "etiketler", []) or getattr(portal_not_obj, "etiketler", [])),
            "kaynak_parca_sayisi": len(kaynak_parca_idleri or []),
            "pinned": bool(getattr(not_obj, "pinned", False) or getattr(portal_not_obj, "pinned", False)),
            "arsivli": bool(getattr(not_obj, "arsivli", False) or getattr(portal_not_obj, "arsivli", False)),
            "olusturma_kaynagi": str(getattr(not_obj, "olusturma_kaynagi", "") or getattr(portal_not_obj, "olusturma_kaynagi", "")),
        },
        durum=durum,
    )


class NotListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [NotesWriteThrottle]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_NOTLAR_ENABLED", True):
            return _modul_kapali_response("Notlar modulu devre disi.")

        dokuman_id = request.query_params.get("dokuman_id")
        parca_id = request.query_params.get("parca_id")
        portal = request.query_params.get("portal")
        not_turu = (request.query_params.get("not_turu") or "").strip()
        arsivli = request.query_params.get("arsivli")

        qs = Not.objects.filter(owner=request.user).order_by("-updated_at", "-id")

        if dokuman_id:
            qs = qs.filter(dokuman_id=dokuman_id)
        if parca_id:
            qs = qs.filter(parca_id=parca_id)
        if portal == "1":
            qs = qs.filter(dokuman__isnull=True, parca__isnull=True)
        elif portal == "0":
            qs = qs.filter(dokuman__isnull=False)
        if not_turu:
            qs = qs.filter(not_turu=not_turu)
        if arsivli in {"0", "1"}:
            qs = qs.filter(arsivli=arsivli == "1")

        return Response(NotSerializer(qs, many=True).data)

    def post(self, request):
        if not modul_acik_mi("DOCVERSE_NOTLAR_ENABLED", True):
            return _modul_kapali_response("Notlar modulu devre disi.")

        dokuman_id = request.data.get("dokuman")
        parca_id = request.data.get("parca")
        baslik = request.data.get("baslik", "")
        metin = request.data.get("metin") or request.data.get("icerik") or ""
        etiketler = request.data.get("etiketler", [])
        pinned = _to_bool(request.data.get("pinned", False))
        arsivli = _to_bool(request.data.get("arsivli", False))
        not_turu = (request.data.get("not_turu") or "serbest").strip() or "serbest"
        olusturma_kaynagi = (request.data.get("olusturma_kaynagi") or "user").strip() or "user"
        meta = _guvenli_meta_dict(request.data.get("meta"))
        kaynak_parca_idleri = _parse_int_list(request.data.get("kaynak_parca_idleri"))

        if not str(metin or "").strip():
            return Response(
                _api_error_payload(
                    detail="metin zorunlu",
                    error_code="validation_error",
                    field_errors={"metin": ["Bu alan zorunludur."]},
                ),
                status=400,
            )

        # 1) Parçaya bağlı not
        if parca_id:
            parca = _get_owned_parca(request, parca_id)

            if not parca:
                return Response(
                    _api_error_payload(detail="Parça yok", error_code="resource_not_found"),
                    status=404,
                )

            if kaynak_parca_idleri:
                secilen_parcalar = _get_owned_parcalar(request, kaynak_parca_idleri)
                if len(secilen_parcalar) != len(kaynak_parca_idleri):
                    return Response(
                        _api_error_payload(
                            detail="kaynak_parca_idleri gecersiz",
                            error_code="validation_error",
                            field_errors={"kaynak_parca_idleri": ["Gecersiz parca listesi."]},
                        ),
                        status=400,
                    )
                if any(item.dokuman_id != parca.dokuman_id for item in secilen_parcalar):
                    return Response(
                        _api_error_payload(
                            detail="kaynak_parca_idleri ayni dokumanda olmali",
                            error_code="validation_error",
                            field_errors={"kaynak_parca_idleri": ["Tum parcalar ayni dokumanda olmali."]},
                        ),
                        status=400,
                    )
            else:
                kaynak_parca_idleri = [parca.id]

            n = Not.objects.create(
                owner=request.user,
                dokuman=parca.dokuman,
                parca=parca,
                adres=getattr(parca, "adres", "") or "",
                baslik=baslik,
                metin=metin,
                etiketler=etiketler if isinstance(etiketler, list) else [],
                not_turu=not_turu,
                pinned=pinned,
                arsivli=arsivli,
                olusturma_kaynagi=olusturma_kaynagi,
                kaynak_parca_idleri=kaynak_parca_idleri,
                meta=meta,
            )
            _record_note_metric(
                request=request,
                olay_turu="not_olusturuldu",
                not_obj=n,
                not_turu=not_turu,
                etiketler=n.etiketler,
                kaynak_parca_idleri=kaynak_parca_idleri,
            )
            return Response(
                _augment_status_payload(
                    NotSerializer(n).data,
                    status_text="Not kaydedildi.",
                    warning_code="",
                ),
                status=201,
            )

        # 2) Dokümana bağlı not
        if dokuman_id:
            dokuman = _get_owned_doc(request, dokuman_id)

            if not dokuman:
                return Response(
                    _api_error_payload(detail="Doküman yok", error_code="resource_not_found"),
                    status=404,
                )

            if kaynak_parca_idleri:
                secilen_parcalar = _get_owned_parcalar(request, kaynak_parca_idleri)
                if len(secilen_parcalar) != len(kaynak_parca_idleri):
                    return Response(
                        _api_error_payload(
                            detail="kaynak_parca_idleri gecersiz",
                            error_code="validation_error",
                            field_errors={"kaynak_parca_idleri": ["Gecersiz parca listesi."]},
                        ),
                        status=400,
                    )
                if any(item.dokuman_id != dokuman.id for item in secilen_parcalar):
                    return Response(
                        _api_error_payload(
                            detail="kaynak_parca_idleri bu dokumana ait olmali",
                            error_code="validation_error",
                            field_errors={"kaynak_parca_idleri": ["Tum parcalar bu dokumana ait olmali."]},
                        ),
                        status=400,
                    )

            n = Not.objects.create(
                owner=request.user,
                dokuman=dokuman,
                parca=None,
                adres="",
                baslik=baslik,
                metin=metin,
                etiketler=etiketler if isinstance(etiketler, list) else [],
                not_turu=not_turu,
                pinned=pinned,
                arsivli=arsivli,
                olusturma_kaynagi=olusturma_kaynagi,
                kaynak_parca_idleri=kaynak_parca_idleri,
                meta=meta,
            )
            _record_note_metric(
                request=request,
                olay_turu="not_olusturuldu",
                not_obj=n,
                not_turu=not_turu,
                etiketler=n.etiketler,
                kaynak_parca_idleri=kaynak_parca_idleri,
            )
            return Response(
                _augment_status_payload(
                    NotSerializer(n).data,
                    status_text="Not kaydedildi.",
                    warning_code="",
                ),
                status=201,
            )

        # 3) Serbest not
        n = Not.objects.create(
            owner=request.user,
            dokuman=None,
            parca=None,
            adres="",
            baslik=baslik,
            metin=metin,
            etiketler=etiketler if isinstance(etiketler, list) else [],
            not_turu=not_turu,
            pinned=pinned,
            arsivli=arsivli,
            olusturma_kaynagi=olusturma_kaynagi,
            kaynak_parca_idleri=kaynak_parca_idleri,
            meta=meta,
        )
        _record_note_metric(
            request=request,
            olay_turu="not_olusturuldu",
            not_obj=n,
            not_turu=not_turu,
            etiketler=n.etiketler,
            kaynak_parca_idleri=kaynak_parca_idleri,
        )
        return Response(
            _augment_status_payload(
                NotSerializer(n).data,
                status_text="Not kaydedildi.",
                warning_code="",
            ),
            status=201,
        )


class PortalNotListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [NotesWriteThrottle]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_PORTAL_NOTLAR_ENABLED", True):
            return _modul_kapali_response("Portal notlar modulu devre disi.")

        dokuman_id = request.query_params.get("dokuman_id")
        qs = DokumanNotu.objects.filter(
            owner=request.user,
        ).order_by("-updated_at", "-id")
        if dokuman_id:
            qs = qs.filter(dokuman_id=dokuman_id)
        return Response(DokumanNotuSerializer(qs, many=True).data)

    def post(self, request):
        if not modul_acik_mi("DOCVERSE_PORTAL_NOTLAR_ENABLED", True):
            return _modul_kapali_response("Portal notlar modulu devre disi.")

        dokuman_id = request.data.get("dokuman")
        parca_id = request.data.get("parca")
        baslik = request.data.get("baslik", "")
        metin = request.data.get("icerik") or request.data.get("metin") or ""
        etiketler = request.data.get("etiketler", [])
        pinned = _to_bool(request.data.get("pinned", False))
        arsivli = _to_bool(request.data.get("arsivli", False))
        not_turu = (request.data.get("not_turu") or "portal_calisma").strip() or "portal_calisma"
        olusturma_kaynagi = (request.data.get("olusturma_kaynagi") or "user").strip() or "user"
        meta = _guvenli_meta_dict(request.data.get("meta"))
        bagli_not_idleri = _parse_int_list(request.data.get("bagli_not_idleri"))
        kaynak_parca_idleri = _parse_int_list(request.data.get("kaynak_parca_idleri"))

        if not str(metin or "").strip():
            return Response(
                _api_error_payload(
                    detail="icerik zorunlu",
                    error_code="validation_error",
                    field_errors={"icerik": ["Bu alan zorunludur."]},
                ),
                status=400,
            )

        bagli_notlar = list(Not.objects.filter(owner=request.user, id__in=bagli_not_idleri).order_by("id"))
        if len(bagli_notlar) != len(bagli_not_idleri):
            return Response(
                _api_error_payload(
                    detail="bagli_not_idleri gecersiz",
                    error_code="validation_error",
                    field_errors={"bagli_not_idleri": ["Gecersiz not listesi."]},
                ),
                status=400,
            )

        kaynak_parcalar = _get_owned_parcalar(request, kaynak_parca_idleri)
        if len(kaynak_parcalar) != len(kaynak_parca_idleri):
            return Response(
                _api_error_payload(
                    detail="kaynak_parca_idleri gecersiz",
                    error_code="validation_error",
                    field_errors={"kaynak_parca_idleri": ["Gecersiz parca listesi."]},
                ),
                status=400,
            )

        parca = _get_owned_parca(request, parca_id) if parca_id else None
        if parca_id and not parca:
            return Response(
                _api_error_payload(detail="Parça yok", error_code="resource_not_found"),
                status=404,
            )

        dokuman = _get_owned_doc(request, dokuman_id) if dokuman_id else None

        aday_dokuman_idleri = {
            item.dokuman_id
            for item in bagli_notlar
            if item.dokuman_id is not None
        }
        aday_dokuman_idleri.update(item.dokuman_id for item in kaynak_parcalar if item.dokuman_id is not None)
        if parca is not None and parca.dokuman_id is not None:
            aday_dokuman_idleri.add(parca.dokuman_id)
        if dokuman is not None:
            aday_dokuman_idleri.add(dokuman.id)

        if not aday_dokuman_idleri:
            return Response(
                _api_error_payload(
                    detail="Portal not icin dokuman baglami gerekli",
                    error_code="validation_error",
                    field_errors={"dokuman": ["Portal not icin dokuman baglami gerekli."]},
                ),
                status=400,
            )
        if len(aday_dokuman_idleri) > 1:
            return Response(
                _api_error_payload(
                    detail="Portal not ayni dokuman icinde kalmali",
                    error_code="validation_error",
                    field_errors={"dokuman": ["Tum baglar ayni dokumana ait olmali."]},
                ),
                status=400,
            )

        if dokuman is None:
            dokuman = _get_owned_doc(request, next(iter(aday_dokuman_idleri)))
        if dokuman is None:
            return Response(
                _api_error_payload(detail="Doküman yok", error_code="resource_not_found"),
                status=404,
            )

        n = DokumanNotu.objects.create(
            owner=request.user,
            dokuman=dokuman,
            parca=parca,
            adres=getattr(parca, "adres", "") if parca is not None else "",
            baslik=baslik,
            icerik=metin,
            not_turu=not_turu,
            etiketler=etiketler if isinstance(etiketler, list) else [],
            pinned=pinned,
            arsivli=arsivli,
            olusturma_kaynagi=olusturma_kaynagi,
            meta=meta,
        )
        if bagli_notlar:
            n.bagli_notlar.set(bagli_notlar)
        if kaynak_parcalar:
            n.kaynak_parcalar.set(kaynak_parcalar)
        elif parca is not None:
            n.kaynak_parcalar.set([parca])

        _record_note_metric(
            request=request,
            olay_turu="portal_not_olusturuldu",
            portal_not_obj=n,
            not_turu=not_turu,
            etiketler=n.etiketler,
            kaynak_parca_idleri=list(n.kaynak_parcalar.order_by("id").values_list("id", flat=True)),
        )
        return Response(
            _augment_status_payload(
                DokumanNotuSerializer(n).data,
                status_text="Portal not kaydedildi.",
                warning_code="",
            ),
            status=201,
        )


class PortalNotDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [NotesWriteThrottle]

    def get_object(self, request, portal_not_id):
        return DokumanNotu.objects.filter(owner=request.user, id=portal_not_id).first()

    def get(self, request, portal_not_id):
        if not modul_acik_mi("DOCVERSE_PORTAL_NOTLAR_ENABLED", True):
            return _modul_kapali_response("Portal notlar modulu devre disi.")
        obj = self.get_object(request, portal_not_id)
        if not obj:
            return Response(
                _api_error_payload(detail="Portal not yok", error_code="resource_not_found"),
                status=404,
            )
        return Response(
            _augment_status_payload(
                DokumanNotuSerializer(obj).data,
                status_text="Portal not hazir.",
                warning_code="",
            )
        )

    def patch(self, request, portal_not_id):
        if not modul_acik_mi("DOCVERSE_PORTAL_NOTLAR_ENABLED", True):
            return _modul_kapali_response("Portal notlar modulu devre disi.")
        obj = self.get_object(request, portal_not_id)
        if not obj:
            return Response(
                _api_error_payload(detail="Portal not yok", error_code="resource_not_found"),
                status=404,
            )

        if "dokuman" in request.data and str(request.data.get("dokuman")) != str(obj.dokuman_id):
            return Response(
                _api_error_payload(
                    detail="Portal not dokuman baglami degistirilemez",
                    error_code="validation_error",
                    field_errors={"dokuman": ["Dokuman baglami degistirilemez."]},
                ),
                status=400,
            )

        if "baslik" in request.data:
            obj.baslik = request.data.get("baslik", obj.baslik)
        if "icerik" in request.data or "metin" in request.data:
            obj.icerik = request.data.get("icerik") or request.data.get("metin") or obj.icerik
        if "etiketler" in request.data and isinstance(request.data.get("etiketler"), list):
            obj.etiketler = request.data.get("etiketler")
        if "pinned" in request.data:
            obj.pinned = _to_bool(request.data.get("pinned"))
        if "arsivli" in request.data:
            obj.arsivli = _to_bool(request.data.get("arsivli"))
        if "meta" in request.data:
            obj.meta = _guvenli_meta_dict(request.data.get("meta"))

        bagli_not_idleri = _parse_int_list(request.data.get("bagli_not_idleri"))
        if "bagli_not_idleri" in request.data:
            bagli_notlar = list(Not.objects.filter(owner=request.user, id__in=bagli_not_idleri).order_by("id"))
            if len(bagli_notlar) != len(bagli_not_idleri):
                return Response(
                    _api_error_payload(
                        detail="bagli_not_idleri gecersiz",
                        error_code="validation_error",
                        field_errors={"bagli_not_idleri": ["Gecersiz not listesi."]},
                    ),
                    status=400,
                )
            if any(item.dokuman_id != obj.dokuman_id for item in bagli_notlar if item.dokuman_id is not None):
                return Response(
                    _api_error_payload(
                        detail="bagli_not_idleri ayni dokumanda olmali",
                        error_code="validation_error",
                        field_errors={"bagli_not_idleri": ["Tum notlar ayni dokumanda olmali."]},
                    ),
                    status=400,
                )
            obj.bagli_notlar.set(bagli_notlar)

        kaynak_parca_idleri = _parse_int_list(request.data.get("kaynak_parca_idleri"))
        if "kaynak_parca_idleri" in request.data:
            kaynak_parcalar = _get_owned_parcalar(request, kaynak_parca_idleri)
            if len(kaynak_parcalar) != len(kaynak_parca_idleri):
                return Response(
                    _api_error_payload(
                        detail="kaynak_parca_idleri gecersiz",
                        error_code="validation_error",
                        field_errors={"kaynak_parca_idleri": ["Gecersiz parca listesi."]},
                    ),
                    status=400,
                )
            if any(item.dokuman_id != obj.dokuman_id for item in kaynak_parcalar):
                return Response(
                    _api_error_payload(
                        detail="kaynak_parca_idleri ayni dokumanda olmali",
                        error_code="validation_error",
                        field_errors={"kaynak_parca_idleri": ["Tum parcalar ayni dokumanda olmali."]},
                    ),
                    status=400,
                )
            obj.kaynak_parcalar.set(kaynak_parcalar)

        obj.save(update_fields=["baslik", "icerik", "etiketler", "pinned", "arsivli", "meta", "updated_at"])
        return Response(
            _augment_status_payload(
                DokumanNotuSerializer(obj).data,
                status_text="Portal not guncellendi.",
                warning_code="",
            )
        )

    def put(self, request, portal_not_id):
        return self.patch(request, portal_not_id)

    def delete(self, request, portal_not_id):
        if not modul_acik_mi("DOCVERSE_PORTAL_NOTLAR_ENABLED", True):
            return _modul_kapali_response("Portal notlar modulu devre disi.")
        obj = self.get_object(request, portal_not_id)
        if not obj:
            return Response(
                _api_error_payload(detail="Portal not yok", error_code="resource_not_found"),
                status=404,
            )
        obj.delete()
        return Response(status=204)


class PortalNotStudyPanelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, portal_not_id):
        if not modul_acik_mi("DOCVERSE_PORTAL_NOTLAR_ENABLED", True):
            return _modul_kapali_response("Portal notlar modulu devre disi.")

        portal_not = DokumanNotu.objects.filter(owner=request.user, id=portal_not_id).first()
        if not portal_not:
            return Response({"detail": "Portal not yok"}, status=404)

        days = int(request.query_params.get("days") or 60)
        payload = build_portal_note_study_panel(
            request.user,
            portal_not=portal_not,
            days=max(1, min(days, 120)),
        )
        serializer = PortalNoteStudyPanelSerializer(payload)
        return Response(serializer.data)


class FeedbackListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_FEEDBACK_ENABLED", True):
            return _modul_kapali_response("Feedback modulu devre disi.")

        dokuman_id = request.query_params.get("dokuman_id") or request.query_params.get("dokuman")
        parca_id = request.query_params.get("parca_id")
        feedback_turu = (request.query_params.get("feedback_turu") or "").strip()
        kaynak_modul = (request.query_params.get("kaynak_modul") or "").strip()

        qs = KullaniciGeriBildirim.objects.filter(owner=request.user).order_by("-created_at", "-id")
        if dokuman_id:
            qs = qs.filter(dokuman_id=dokuman_id)
        if parca_id:
            qs = qs.filter(parca_id=parca_id)
        if feedback_turu:
            qs = qs.filter(feedback_turu=feedback_turu)
        if kaynak_modul:
            qs = qs.filter(kaynak_modul=kaynak_modul)

        return Response(KullaniciGeriBildirimSerializer(qs, many=True).data)

    def post(self, request):
        if not modul_acik_mi("DOCVERSE_FEEDBACK_ENABLED", True):
            return _modul_kapali_response("Feedback modulu devre disi.")

        dokuman = _get_owned_doc(request, request.data.get("dokuman"))
        parca = _get_owned_parca(request, request.data.get("parca"))
        not_kaydi = _get_owned_not(request, request.data.get("not_kaydi"))
        portal_not = _get_owned_portal_not(request, request.data.get("portal_not"))
        feedback_turu = (request.data.get("feedback_turu") or "").strip()
        kisa_not = (request.data.get("kisa_not") or "").strip()
        kaynak_modul = (request.data.get("kaynak_modul") or "dokuman.api").strip() or "dokuman.api"
        okuma_suresi_saniye = request.data.get("okuma_suresi_saniye", request.data.get("read_seconds"))

        if feedback_turu not in {"iyi", "kotu", "eksik", "alakasiz"}:
            return Response({"detail": "feedback_turu gecersiz"}, status=400)

        aday_dokuman_idleri = set()
        for item in [dokuman, getattr(parca, "dokuman", None), getattr(not_kaydi, "dokuman", None), getattr(portal_not, "dokuman", None)]:
            if getattr(item, "id", None) is not None:
                aday_dokuman_idleri.add(item.id)

        if len(aday_dokuman_idleri) > 1:
            return Response({"detail": "Feedback tek dokuman baglaminda kalmali"}, status=400)
        if not aday_dokuman_idleri and not any([dokuman, parca, not_kaydi, portal_not]):
            return Response({"detail": "Feedback icin en az bir baglam gerekli"}, status=400)

        if dokuman is None and aday_dokuman_idleri:
            dokuman = _get_owned_doc(request, next(iter(aday_dokuman_idleri)))

        feedback = kaydet_geri_bildirim(
            kullanici=request.user,
            feedback_turu=feedback_turu,
            kaynak_modul=kaynak_modul,
            kisa_not=kisa_not,
            dokuman=dokuman,
            parca=parca,
            not_kaydi=not_kaydi,
            portal_not=portal_not,
            okuma_suresi_saniye=okuma_suresi_saniye,
        )
        return Response(KullaniciGeriBildirimSerializer(feedback).data, status=201)


class FeedbackAnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_FEEDBACK_ENABLED", True):
            return _modul_kapali_response("Feedback analytics modulu devre disi.")

        days = int(request.query_params.get("days") or 7)
        payload = build_feedback_analytics_v2(
            request.user,
            days=max(1, min(days, 30)),
            dokuman_id=request.query_params.get("dokuman_id") or request.query_params.get("dokuman"),
            feedback_turu=(request.query_params.get("feedback_turu") or "").strip(),
            kaynak_modul=(request.query_params.get("kaynak_modul") or "").strip(),
        )
        serializer = FeedbackAnalyticsV2Serializer(payload)
        return Response(serializer.data)


class DashboardSummaryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Dashboard summary metric store devre disi.")

        payload = build_dashboard_summary(request.user, days=7)
        serializer = DashboardSummarySerializer(payload)
        return Response(serializer.data)


class ConfusionHotspotAnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Confusion hotspot analytics metric store devre disi.")

        days = int(request.query_params.get("days") or 30)
        payload = build_confusion_hotspot_analytics(request.user, days=max(1, min(days, 90)))
        serializer = ConfusionHotspotAnalyticsSerializer(payload)
        return Response(serializer.data)


class MasteryFeedbackTrustAnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Mastery analytics metric store devre disi.")

        days = int(request.query_params.get("days") or 30)
        payload = build_mastery_feedback_trust_analytics(request.user, days=max(1, min(days, 90)))
        serializer = MasteryFeedbackTrustAnalyticsSerializer(payload)
        return Response(serializer.data)


class ProductKPIPanelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Urun KPI paneli metric store devre disi.")

        days = int(request.query_params.get("days") or 30)
        payload = build_kpi_panel(request.user, days=max(1, min(days, 90)))
        serializer = KPIPanelSerializer(payload)
        return Response(serializer.data)


class ConfusionMapAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Confusion map metric store devre disi.")

        days = int(request.query_params.get("days") or 30)
        payload = build_confusion_map_surface(request.user, days=max(1, min(days, 90)))
        serializer = ConfusionMapSurfaceSerializer(payload)
        return Response(serializer.data)


class QuizBossProductAnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Quiz/Boss analytics metric store devre disi.")

        days = int(request.query_params.get("days") or 30)
        payload = build_quiz_boss_surface(request.user, days=max(1, min(days, 120)))
        serializer = QuizBossProductAnalyticsSerializer(payload)
        return Response(serializer.data)


class BossReadinessAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_BOSS_ENABLED", True):
            return _modul_kapali_response("Boss readiness boss modulu kapali.")
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Boss readiness metric store devre disi.")

        dokuman_id = request.query_params.get("dokuman_id") or request.query_params.get("doc_id")
        if not dokuman_id:
            return Response({"detail": "dokuman_id param required"}, status=400)

        doc = Dokuman.objects.filter(id=int(dokuman_id), owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        meta = compute_boss_difficulty_score(user=request.user, dokuman=doc)
        kaydet_skor_olayi(
            kullanici=request.user,
            olay_turu="boss_readiness_gosterildi",
            kaynak_modul="boss_readiness.api",
            dokuman=doc,
            score_map=dict(meta or {}),
            durum="ok",
        )
        serializer = BossReadinessSerializer(meta)
        return Response(serializer.data)


class ExportReadinessAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_EXPORT_PLAN_ENABLED", True):
            return _modul_kapali_response("Export readiness export modulu kapali.")
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Export readiness metric store devre disi.")

        dokuman_id = request.query_params.get("dokuman_id") or request.query_params.get("doc_id")
        if not dokuman_id:
            return Response({"detail": "dokuman_id param required"}, status=400)

        doc = Dokuman.objects.filter(id=int(dokuman_id), owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        study_meta = compute_study_summary_importance_score(user=request.user, dokuman=doc)

        parcalar = list(doc.parcalar.order_by("id")[:12])
        quiz_scores = []
        for p in parcalar:
            try:
                qr = compute_quiz_readiness_score(parca=p)
                quiz_scores.append(float(qr.get("quiz_readiness_score") or 0.0))
            except Exception:
                quiz_scores.append(0.0)
        avg_quiz = sum(quiz_scores) / max(1, len(quiz_scores))

        quality_vals = []
        for p in parcalar:
            meta = dict(getattr(p, "meta", {}) or {})
            try:
                q = max(float(meta.get("quality_score") or 0.0), float(meta.get("ocr_quality_score") or 0.0))
            except Exception:
                q = 0.0
            if q > 0:
                quality_vals.append(q)
        quality_avg = sum(quality_vals) / len(quality_vals) if quality_vals else 0.0

        # Weighted readiness: study importance (60%), quiz readiness (30%), quality (10%)
        readiness_score = max(
            0.0,
            min(
                1.0,
                0.6 * float(study_meta.get("study_summary_importance_score") or 0.0)
                + 0.3 * float(avg_quiz)
                + 0.1 * float(quality_avg),
            ),
        )
        if readiness_score >= 0.75:
            readiness_label = "ready"
        elif readiness_score >= 0.5:
            readiness_label = "borderline"
        else:
            readiness_label = "needs_work"

        hedef_format = request.query_params.get("hedef_format") or "pptx"
        manifest = export_manifest_v2.build_export_manifest_v2_payload(doc=doc, user=request.user, hedef_format=hedef_format)
        download_ready = readiness_score >= 0.75

        payload = {
            "dokuman_id": doc.id,
            "baslik": doc.baslik or f"Dokuman {doc.id}",
            "hedef_format": hedef_format,
            "durum": "ok",
            "readiness": readiness_label,
            "export_readiness_score": round(readiness_score, 4),
            "download_ready": download_ready,
            "manifest": manifest,
            "output_meta": manifest.get("_meta", {}),
        }

        kaydet_skor_olayi(
            kullanici=request.user,
            olay_turu="export_readiness_hesaplandi",
            kaynak_modul="export_readiness.api",
            dokuman=doc,
            score_map={
                "export_readiness_score": round(readiness_score, 4),
                "export_readiness_state": readiness_label,
                "format": hedef_format,
            },
            durum="ok",
        )

        serializer = RealExportSerializer(payload)
        return Response(serializer.data)


class LearningPanelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Ogrenme paneli metric store devre disi.")

        days = int(request.query_params.get("days") or 30)
        payload = build_learning_panel(request.user, days=max(1, min(days, 90)))
        serializer = LearningPanelSerializer(payload)
        return Response(serializer.data)


class LearningKPIAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Learning KPI metric store devre disi.")

        days = int(request.query_params.get("days") or 30)
        payload = build_learning_kpi(days=max(1, min(days, 90)))
        serializer = LearningKPISerializer(payload)
        return Response(serializer.data)


class QuizReadinessAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not modul_acik_mi("DOCVERSE_QUIZ_ENABLED", False):
            return _modul_kapali_response("Quiz modulu devre disi.")

        serializer = QuizReadinessRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parca_id = int(serializer.validated_data["parca_id"])
        parca = Parca.objects.select_related("dokuman").filter(
            id=parca_id,
            dokuman__owner=request.user,
        ).first()
        if not parca:
            return Response({"detail": "Parça yok"}, status=404)

        quiz_action = serializer.validated_data.get("quiz_action")
        if quiz_action:
            mark_quiz_cooldown(user=request.user, parca=parca, action=quiz_action)

        payload = compute_runtime_quiz_readiness(
            user=request.user,
            parca=parca,
            observed_read_seconds=serializer.validated_data.get("observed_read_seconds"),
            expected_read_seconds=serializer.validated_data.get("expected_read_seconds"),
            read_ratio=serializer.validated_data.get("read_ratio"),
            note_count=serializer.validated_data.get("note_count"),
        )
        if payload["show_quiz_prompt"]:
            record_quiz_prompt_event(user=request.user, parca=parca, readiness_meta=payload)
        return Response(
            {
                "show_quiz_prompt": payload["show_quiz_prompt"],
                "quiz_readiness_score": payload["quiz_readiness_score"],
                "quiz_readiness_threshold": payload["quiz_readiness_threshold"],
                "runtime_reason": payload["runtime_quiz_reason"],
                "cooldown_factor": payload["cooldown_factor"],
                "content_quiz_eligible": payload["content_quiz_eligible"],
            }
        )


class XPVisibilityPanelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("XP paneli metric store devre disi.")

        payload = build_xp_visibility_panel(request.user)
        serializer = XPVisibilityPanelSerializer(payload)
        return Response(serializer.data)


class LearningModesPanelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)
        payload = build_learning_modes_panel(request.user, doc=doc)
        if modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            kaydet_skor_olayi(
                kullanici=request.user,
                olay_turu="learning_modes_panel_gosterildi",
                kaynak_modul="learning_modes_panel.api",
                dokuman=doc,
                score_map=dict(payload.get("_meta") or {}),
                durum="ok",
            )
        serializer = LearningModesPanelSerializer(payload)
        return Response(serializer.data)


class BossRushPanelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not _panel_flag_enabled(
            "DOCVERSE_BOSS_RUSH_PANEL_ENABLED",
            base_flag="DOCVERSE_BOSS_ENABLED",
            default=True,
        ):
            return _modul_kapali_response("Boss rush paneli kapali.")

        dokuman = get_object_or_404(Dokuman, pk=pk, owner=request.user)
        payload = product_panels.build_boss_rush_panel_payload(dokuman)
        if modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            kaydet_skor_olayi(
                kullanici=request.user,
                olay_turu="boss_rush_panel_gosterildi",
                kaynak_modul="product_panels.api",
                dokuman=dokuman,
                score_map=dict(payload.get("_meta") or {}),
                durum="ok",
            )
        serializer = BossRushPanelSerializer(payload)
        return Response(serializer.data)


class ExportReadinessPanelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not _panel_flag_enabled(
            "DOCVERSE_EXPORT_READINESS_ENABLED",
            base_flag="DOCVERSE_EXPORT_PLAN_ENABLED",
            default=True,
        ):
            return _modul_kapali_response("Export readiness paneli kapali.")

        dokuman = get_object_or_404(Dokuman, pk=pk, owner=request.user)
        payload = product_panels.build_export_readiness_payload(dokuman)
        if modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            kaydet_skor_olayi(
                kullanici=request.user,
                olay_turu="export_readiness_panel_gosterildi",
                kaynak_modul="product_panels.api",
                dokuman=dokuman,
                score_map=dict(payload.get("_meta") or {}),
                durum="ok",
            )
        serializer = ExportReadinessPanelSerializer(payload)
        return Response(serializer.data)


class PersonalizationConfidencePanelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_PERSONALIZATION_ENABLED", True):
            return _modul_kapali_response("Personalization paneli kapali.")

        payload = product_panels.build_personalization_confidence_payload(request.user)
        if modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            kaydet_skor_olayi(
                kullanici=request.user,
                olay_turu="personalization_confidence_gosterildi",
                kaynak_modul="product_panels.api",
                score_map=dict(payload.get("_meta") or {}),
                durum="ok",
            )
        serializer = PersonalizationConfidenceSerializer(payload)
        return Response(serializer.data)


class WeeklyProgressPanelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _panel_flag_enabled(
            "DOCVERSE_WEEKLY_PROGRESS_ENABLED",
            base_flag="DOCVERSE_METRIC_STORE_ENABLED",
            default=True,
        ):
            return _modul_kapali_response("Weekly progress paneli kapali.")
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Weekly progress paneli kapali.")

        payload = product_panels.build_weekly_progress_payload(request.user)
        if modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            kaydet_skor_olayi(
                kullanici=request.user,
                olay_turu="weekly_progress_panel_gosterildi",
                kaynak_modul="product_panels.api",
                score_map=dict(payload.get("_meta") or {}),
                durum="ok",
            )
        serializer = WeeklyProgressPanelSerializer(payload)
        return Response(serializer.data)


class AchievementProgressAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _panel_flag_enabled(
            "DOCVERSE_ACHIEVEMENT_PROGRESS_ENABLED",
            base_flag="DOCVERSE_METRIC_STORE_ENABLED",
            default=True,
        ):
            return _modul_kapali_response("Achievement paneli kapali.")
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Achievement paneli kapali.")

        payload = product_panels.build_achievement_progress_payload(request.user)
        if modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            kaydet_skor_olayi(
                kullanici=request.user,
                olay_turu="achievement_panel_gosterildi",
                kaynak_modul="achievement_runtime.api",
                score_map=dict(payload.get("_meta") or {}),
                durum="ok",
            )
        serializer = AchievementProgressSerializer(payload)
        return Response(serializer.data)


class WeeklyProgressReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Haftalik rapor metric store devre disi.")

        payload = build_weekly_progress_report(request.user)
        kaydet_skor_olayi(
            kullanici=request.user,
            olay_turu="weekly_progress_hesaplandi",
            kaynak_modul="weekly_report.api",
            score_map=dict(payload.get("_meta") or {}),
            durum="ok",
        )
        serializer = WeeklyProgressReportSerializer(payload)
        return Response(serializer.data)


class RewardPanelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_REWARD_PANEL_ENABLED", True):
            return _modul_kapali_response("Reward panel modulu devre disi.")
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Reward panel icin metric store gerekli.")

        payload = build_reward_panel(request.user)
        kaydet_skor_olayi(
            kullanici=request.user,
            olay_turu="reward_panel_gosterildi",
            kaynak_modul="reward_panel.api",
            score_map=dict(payload.get("_meta") or {}),
            durum="ok",
        )
        serializer = RewardPanelSerializer(payload)
        return Response(serializer.data)


class DokumanStyleConsoleAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        if not modul_acik_mi("DOCVERSE_STYLE_CONSOLE_ENABLED", True):
            return _modul_kapali_response("Style console modulu devre disi.")
        if not modul_acik_mi("DOCVERSE_STUDY_SUMMARY_ENABLED", True):
            return _modul_kapali_response("Style console icin study summary gerekli.")

        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        portal_not = None
        portal_not_id = request.query_params.get("portal_not_id")
        if portal_not_id:
            portal_not = _get_owned_portal_not(request, portal_not_id)
            if portal_not is None or portal_not.dokuman_id != doc.id:
                return Response({"detail": "Portal not yok"}, status=404)

        payload = build_style_console_payload(
            doc=doc,
            user=request.user,
            stil=(request.query_params.get("stil") or "kisa"),
            ton=(request.query_params.get("ton") or "teknik"),
            portal_not=portal_not,
            cheatsheet_enabled=modul_acik_mi("DOCVERSE_CHEATSHEET_EXPORT_ENABLED", True),
        )
        kaydet_skor_olayi(
            kullanici=request.user,
            olay_turu="style_console_uretildi",
            kaynak_modul="style_console.api",
            dokuman=doc,
            score_map={
                "stil": payload["stil"],
                "ton": payload["ton"],
                "bagli_parca_sayisi": len(payload.get("kaynak_parca_idleri") or []),
                "portal_not_var_mi": bool(payload.get("portal_not_id")),
            },
        )
        serializer = StyleConsoleSerializer(payload)
        return Response(serializer.data)


class DokumanDirectorsCutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        if not modul_acik_mi("DOCVERSE_DIRECTORS_CUT_ENABLED", True):
            return _modul_kapali_response("Director's cut modulu devre disi.")
        if not modul_acik_mi("DOCVERSE_STUDY_SUMMARY_ENABLED", True):
            return _modul_kapali_response("Director's cut icin study summary gerekli.")

        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        portal_not = None
        portal_not_id = request.query_params.get("portal_not_id")
        if portal_not_id:
            portal_not = _get_owned_portal_not(request, portal_not_id)
            if portal_not is None or portal_not.dokuman_id != doc.id:
                return Response({"detail": "Portal not yok"}, status=404)

        payload = build_directors_cut_payload(
            doc=doc,
            user=request.user,
            mod=(request.query_params.get("mod") or "hizli_cut"),
            portal_not=portal_not,
            cheatsheet_enabled=modul_acik_mi("DOCVERSE_CHEATSHEET_EXPORT_ENABLED", True),
        )
        kaydet_skor_olayi(
            kullanici=request.user,
            olay_turu="directors_cut_uretildi",
            kaynak_modul="directors_cut.api",
            dokuman=doc,
            score_map={
                "mod": payload["mod"],
                "bagli_parca_sayisi": len(payload.get("kaynak_parca_idleri") or []),
                "portal_not_var_mi": bool(payload.get("portal_not_id")),
            },
        )
        serializer = DirectorsCutSerializer(payload)
        return Response(serializer.data)


class DokumanExportPlanAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        if not modul_acik_mi("DOCVERSE_EXPORT_PLAN_ENABLED", True):
            return _modul_kapali_response("Export plan modulu devre disi.")
        if not modul_acik_mi("DOCVERSE_STUDY_SUMMARY_ENABLED", True):
            return _modul_kapali_response("Export plan icin study summary gerekli.")

        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        portal_not = None
        portal_not_id = request.query_params.get("portal_not_id")
        if portal_not_id:
            portal_not = _get_owned_portal_not(request, portal_not_id)
            if portal_not is None or portal_not.dokuman_id != doc.id:
                return Response({"detail": "Portal not yok"}, status=404)

        payload = build_export_plan_payload(
            doc=doc,
            user=request.user,
            portal_not=portal_not,
            plan_turu=(request.query_params.get("plan_turu") or request.query_params.get("tur") or "slayt"),
            cheatsheet_enabled=modul_acik_mi("DOCVERSE_CHEATSHEET_EXPORT_ENABLED", True),
            concepts_enabled=modul_acik_mi("DOCVERSE_CONCEPTS_ENABLED", True),
        )
        kaydet_skor_olayi(
            kullanici=request.user,
            olay_turu="export_plan_uretildi",
            kaynak_modul="export_plan.api",
            dokuman=doc,
            score_map=dict(payload.get("_meta") or {}),
        )
        serializer = ExportPlanSerializer(payload)
        return Response(serializer.data)


class DokumanReelsSurfaceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        if not modul_acik_mi("DOCVERSE_REELS_ENABLED", True):
            return _modul_kapali_response("Reels modulu devre disi.")
        if not modul_acik_mi("DOCVERSE_STUDY_SUMMARY_ENABLED", True):
            return _modul_kapali_response("Reels yuzeyi icin study summary gerekli.")

        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        portal_not = None
        portal_not_id = request.query_params.get("portal_not_id")
        if portal_not_id:
            portal_not = _get_owned_portal_not(request, portal_not_id)
            if portal_not is None or portal_not.dokuman_id != doc.id:
                return Response({"detail": "Portal not yok"}, status=404)

        payload = build_reels_surface_payload(
            doc=doc,
            user=request.user,
            portal_not=portal_not,
            cheatsheet_enabled=modul_acik_mi("DOCVERSE_CHEATSHEET_EXPORT_ENABLED", True),
        )
        if modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            kaydet_skor_olayi(
                kullanici=request.user,
                olay_turu="reels_surface_uretildi",
                kaynak_modul="reels_surface.api",
                dokuman=doc,
                parca=doc.parcalar.filter(id__in=[item.get("bagli_parca_id") for item in payload.get("kartlar") or [] if item.get("bagli_parca_id")]).order_by("id").first(),
                score_map=dict(payload.get("_meta") or {}),
                durum="ok",
            )
        serializer = ReelsSurfaceSerializer(payload)
        return Response(serializer.data)


class BossCevapKontrolAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, parca_id: int):
        if not boss_runtime_enabled():
            return _modul_kapali_response("Boss modulu devre disi.")
        parca = Parca.objects.select_related("dokuman").filter(
            id=parca_id,
            dokuman__owner=request.user
        ).first()

        if not parca:
            return Response({"detail": "Parça yok"}, status=404)

        gorev = (request.data.get("gorev") or "").strip()
        ogrenci_yanit = (request.data.get("yanit") or "").strip()

        if not ogrenci_yanit:
            return Response({"detail": "yanit zorunlu"}, status=400)

        kaynak_metin = parca.metin or ""
        previous_mastery = compute_mastery_score(user=request.user, dokuman=parca.dokuman)["mastery_score"]
        previous_confusion = compute_confusion_map_score(
            user=request.user,
            dokuman=parca.dokuman,
            parca=parca,
        )["confusion_map_score"]
        difficulty_meta = compute_boss_difficulty_score(user=request.user, dokuman=parca.dokuman)

        fallback = _boss_fallback_degerlendir(kaynak_metin, ogrenci_yanit)
        sonuc = fallback
        mod = "fallback"

        try:
            prompt = _boss_cevap_prompt(
                kaynak_metin,
                gorev,
                ogrenci_yanit,
                difficulty_meta=difficulty_meta,
            )

            raw = chat(
                [{"role": "user", "content": prompt}],
                max_tokens=ai2_scope_icin_max_token("GRADING")
            )
            raw_text = raw.strip() if isinstance(raw, str) else str(raw).strip()
            obj = extract_json(raw) or {}
            parsed = _safe_anlat_kontrol_obj(obj)

            if parsed and parsed.get("geri_bildirim"):
                llm_score = int(parsed.get("puan", 0))
                fb_score = int(fallback.get("puan", 0))

                llm_is_weak = (
                    (llm_score == 0 and fb_score >= 30)
                    or
                    (
                        not parsed.get("dogru_kisimlar")
                        and not parsed.get("eksikler")
                        and fb_score >= 30
                    )
                )

                if llm_is_weak:
                    sonuc = fallback
                    mod = "fallback_guard"
                else:
                    sonuc = {
                        "puan": max(llm_score, fb_score),
                        "dogru_kisimlar": parsed.get("dogru_kisimlar") or fallback.get("dogru_kisimlar", []),
                        "yanlislar": parsed.get("yanlislar") or fallback.get("yanlislar", []),
                        "eksikler": parsed.get("eksikler") or fallback.get("eksikler", []),
                        "geri_bildirim": parsed.get("geri_bildirim") or fallback.get("geri_bildirim", ""),
                    }
                    mod = "llm_hybrid"

        except Exception:
            sonuc = fallback
            mod = "fallback"

        xp = _xp_hesapla(sonuc.get("puan", 0))
        profil = _profil_xp_ekle(request.user, xp)
        """
        OdulLog.objects.create(
            kullanici=request.user,
            dokuman=parca.dokuman,
            parca=parca,
            kaynak="boss",
            puan=int(sonuc.get("puan", 0)),
            xp_kazanilan=xp,
            aciklama=f"Boss cevap kontrolü | parca_id={parca.id}"
        )
        """
        kaydet_skor_olayi(
            kullanici=request.user,
            olay_turu="boss_baslatildi",
            kaynak_modul="boss.answer_control",
            dokuman=parca.dokuman,
            parca=parca,
            score_map={
                "boss_difficulty_score": difficulty_meta["boss_difficulty_score"],
                "boss_difficulty_band": difficulty_meta["boss_difficulty_band"],
            },
            durum="ok",
        )
        sonuc_orani = round(float(int(sonuc.get("puan", 0) or 0)) / 100.0, 4)
        progress_meta = compute_boss_progress_score(
            dogru_sayisi=1 if int(sonuc.get("puan", 0) or 0) >= 60 else 0,
            toplam_soru=1,
            ipucu_sayisi=0,
        )
        record_boss_attempt_event(
            user=request.user,
            doc=parca.dokuman,
            parcalar=[parca],
            dogru_sayisi=1 if int(sonuc.get("puan", 0) or 0) >= 60 else 0,
            toplam_soru=1,
            ipucu_sayisi=0,
        )
        record_learning_outcome_events(
            user=request.user,
            dokuman=parca.dokuman,
            parca=parca,
            previous_mastery_score=previous_mastery,
            previous_confusion_score=previous_confusion,
            sonuc_orani=sonuc_orani,
            boss_kill=progress_meta["boss_outcome"] == "boss_defeated",
        )
        return Response({
            "ok": True,
            "parca": {
                "id": parca.id,
                "dokuman_id": parca.dokuman_id,
                "adres": getattr(parca, "adres", "") or "",
                "snippet": _guvenli_sinyal_metni(kaynak_metin, label="kaynak"),
            },
            "gorev": _guvenli_sinyal_metni(gorev, label="gorev"),
            "ogrenci_yanit": _guvenli_sinyal_metni(ogrenci_yanit, label="ogrenci_yaniti"),
            "degerlendirme": sonuc,
            "boss_progress_score": progress_meta["boss_progress_score"],
            "boss_outcome": progress_meta["boss_outcome"],
            "boss_difficulty": difficulty_meta,
            "xp": {
                "kazanilan": xp,
                "toplam_xp": profil.xp,
                "seviye": profil.seviye,
                "unvan": profil.unvan,
            },
            "mod": mod,
        })
class NotDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [NotesWriteThrottle]

    def get_object(self, request, not_id):
        return Not.objects.filter(owner=request.user, id=not_id).first()

    def get(self, request, not_id):
        if not modul_acik_mi("DOCVERSE_NOTLAR_ENABLED", True):
            return _modul_kapali_response("Notlar modulu devre disi.")
        n = self.get_object(request, not_id)
        if not n:
            return Response(
                _api_error_payload(detail="Not yok", error_code="resource_not_found"),
                status=404,
            )
        return Response(
            _augment_status_payload(
                NotSerializer(n).data,
                status_text="Not hazir.",
                warning_code="",
            )
        )

    def patch(self, request, not_id):
        if not modul_acik_mi("DOCVERSE_NOTLAR_ENABLED", True):
            return _modul_kapali_response("Notlar modulu devre disi.")
        n = self.get_object(request, not_id)
        if not n:
            return Response(
                _api_error_payload(detail="Not yok", error_code="resource_not_found"),
                status=404,
            )

        if "baslik" in request.data:
            n.baslik = request.data.get("baslik", n.baslik)

        if "metin" in request.data or "icerik" in request.data:
            n.metin = request.data.get("metin") or request.data.get("icerik") or n.metin

        if "etiketler" in request.data:
            n.etiketler = request.data.get("etiketler", n.etiketler)

        if "pinned" in request.data:
            n.pinned = _to_bool(request.data.get("pinned"))

        if "arsivli" in request.data:
            n.arsivli = _to_bool(request.data.get("arsivli"))

        if "not_turu" in request.data:
            n.not_turu = (request.data.get("not_turu") or n.not_turu).strip() or n.not_turu

        if "olusturma_kaynagi" in request.data:
            n.olusturma_kaynagi = (request.data.get("olusturma_kaynagi") or n.olusturma_kaynagi).strip() or n.olusturma_kaynagi

        if "meta" in request.data:
            n.meta = _guvenli_meta_dict(request.data.get("meta"))

        if "kaynak_parca_idleri" in request.data:
            kaynak_parca_idleri = _parse_int_list(request.data.get("kaynak_parca_idleri"))
            if kaynak_parca_idleri:
                secilen_parcalar = _get_owned_parcalar(request, kaynak_parca_idleri)
                if len(secilen_parcalar) != len(kaynak_parca_idleri):
                    return Response(
                        _api_error_payload(
                            detail="kaynak_parca_idleri gecersiz",
                            error_code="validation_error",
                            field_errors={"kaynak_parca_idleri": ["Gecersiz parca listesi."]},
                        ),
                        status=400,
                    )
                hedef_dokuman_id = n.dokuman_id or (n.parca.dokuman_id if n.parca else None)
                if hedef_dokuman_id and any(item.dokuman_id != hedef_dokuman_id for item in secilen_parcalar):
                    return Response(
                        _api_error_payload(
                            detail="kaynak_parca_idleri ayni dokumana ait olmali",
                            error_code="validation_error",
                            field_errors={"kaynak_parca_idleri": ["Tum parcalar ayni dokumana ait olmali."]},
                        ),
                        status=400,
                    )
            n.kaynak_parca_idleri = kaynak_parca_idleri

        if "dokuman" in request.data:
            yeni_dokuman_id = request.data.get("dokuman")
            if yeni_dokuman_id:
                yeni_dokuman = _get_owned_doc(request, yeni_dokuman_id)
                if not yeni_dokuman:
                    return Response(
                        _api_error_payload(detail="Doküman yok", error_code="resource_not_found"),
                        status=404,
                    )
                n.dokuman = yeni_dokuman
            else:
                n.dokuman = None
                n.parca = None
                n.adres = ""

        n.save()
        return Response(
            _augment_status_payload(
                NotSerializer(n).data,
                status_text="Not guncellendi.",
                warning_code="",
            )
        )

    def delete(self, request, not_id):
        if not modul_acik_mi("DOCVERSE_NOTLAR_ENABLED", True):
            return _modul_kapali_response("Notlar modulu devre disi.")
        n = self.get_object(request, not_id)
        if not n:
            return Response(
                _api_error_payload(detail="Not yok", error_code="resource_not_found"),
                status=404,
            )

        n.delete()
        return Response(status=204)
class NotEkle(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [NotesWriteThrottle]

    def post(self, request):
        if not modul_acik_mi("DOCVERSE_NOTLAR_ENABLED", True):
            return _modul_kapali_response("Notlar modulu devre disi.")

        ser = NotSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        parca = Parca.objects.select_related("dokuman").filter(
            id=ser.validated_data["parca"].id,
            dokuman__owner=request.user
        ).first()
        if not parca:
            return Response({"detail": "Parça yok"}, status=404)

        n = Not.objects.create(
            owner=request.user,
            dokuman=parca.dokuman,          # ✅ zorunlu
            parca=parca,
            adres=getattr(parca, "adres", "") or "",
            baslik=request.data.get("baslik",""),
            metin=request.data.get("metin") or request.data.get("icerik") or "",
            etiketler=request.data.get("etiketler", []),
            pinned=bool(request.data.get("pinned", False)),
        )
        return Response(NotSerializer(n).data, status=201)
    
class Oneriler(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        top3 = doc.parcalar.order_by("-zorluk_skoru")[:3]
        sayim = {
            "kolay": doc.parcalar.filter(zorluk="kolay").count(),
            "orta": doc.parcalar.filter(zorluk="orta").count(),
            "zor": doc.parcalar.filter(zorluk="zor").count(),
        }

        return Response({
            "dokuman_id": doc.id,
            "ozet": {"parca_sayisi": doc.parcalar.count(), "dagilim": sayim},
            "en_zor_3": ParcaSerializer(top3, many=True).data
        })


class BossFight(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, parca_id: int):
        if not boss_runtime_enabled():
            return _modul_kapali_response("Boss modulu devre disi.")
        p = Parca.objects.select_related("dokuman").filter(id=parca_id, dokuman__owner=request.user).first()
        if not p:
            return Response({"detail": "Parça yok"}, status=404)

        payload = build_boss_payload(parca=p, user=request.user)
        record_boss_candidate_event(
            user=request.user,
            parca=p,
            boss_meta=payload["boss_meta"],
        )
        record_boss_start_event(
            user=request.user,
            doc=p.dokuman,
            parca=p,
            boss_difficulty=payload["boss_difficulty"],
        )
        return Response({
            "parca": {"id": p.id, "adres": p.adres, "zorluk": p.zorluk, "skor": p.zorluk_skoru},
            "boss_fight": payload["boss_fight"],
            "boss_meta": payload["boss_meta"],
            "boss_difficulty": payload["boss_difficulty"],
        })

    def post(self, request, parca_id: int):
        if not boss_runtime_enabled():
            return _modul_kapali_response("Boss modulu devre disi.")

        p = Parca.objects.select_related("dokuman").filter(id=parca_id, dokuman__owner=request.user).first()
        if not p:
            return Response({"detail": "Parça yok"}, status=404)

        serializer = BossResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dogru_sayisi = int(serializer.validated_data["dogru_sayisi"])
        toplam_soru = int(serializer.validated_data["toplam_soru"])
        ipucu_sayisi = int(serializer.validated_data.get("ipucu_sayisi") or 0)
        previous_mastery = compute_mastery_score(user=request.user, dokuman=p.dokuman)["mastery_score"]
        previous_confusion = compute_confusion_map_score(
            user=request.user,
            dokuman=p.dokuman,
            parca=p,
        )["confusion_map_score"]
        progress_meta = compute_boss_progress_score(
            dogru_sayisi=dogru_sayisi,
            toplam_soru=toplam_soru,
            ipucu_sayisi=ipucu_sayisi,
        )
        record_boss_attempt_event(
            user=request.user,
            doc=p.dokuman,
            parcalar=[p],
            dogru_sayisi=dogru_sayisi,
            toplam_soru=toplam_soru,
            ipucu_sayisi=ipucu_sayisi,
        )
        record_learning_outcome_events(
            user=request.user,
            dokuman=p.dokuman,
            parca=p,
            previous_mastery_score=previous_mastery,
            previous_confusion_score=previous_confusion,
            sonuc_orani=progress_meta["sonuc_orani"],
            boss_kill=progress_meta["boss_outcome"] == "boss_defeated",
        )
        mastery_meta = compute_mastery_score(user=request.user, dokuman=p.dokuman)

        return Response({
            "ok": True,
            "parca_id": p.id,
            "dogru_sayisi": dogru_sayisi,
            "toplam_soru": toplam_soru,
            "sonuc_orani": progress_meta["sonuc_orani"],
            "boss_progress_score": progress_meta["boss_progress_score"],
            "boss_outcome": progress_meta["boss_outcome"],
            "mastery_score": mastery_meta["mastery_score"],
        })
class DokumanBossRushAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        if not boss_runtime_enabled():
            return _modul_kapali_response("Boss modulu devre disi.")
        limit = int(request.query_params.get("limit", 5))
        limit = max(1, min(limit, 10))

        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        payload = build_boss_rush_payload(doc=doc, user=request.user, limit=limit)
        boss_difficulty = None
        for item in payload["boss_rush"]["arena"]:
            parca = doc.parcalar.filter(id=item["parca_id"]).first()
            if parca is not None:
                record_boss_candidate_event(
                    user=request.user,
                    parca=parca,
                    boss_meta=item["boss_meta"],
                    selected_count=payload["boss_rush"]["arena_sayisi"],
                )
                boss_difficulty = item["boss_difficulty"]
        record_boss_start_event(
            user=request.user,
            doc=doc,
            boss_difficulty=boss_difficulty,
            arena_sayisi=payload["boss_rush"]["arena_sayisi"],
        )
        return Response(payload)

    def post(self, request, doc_id: int):
        if not boss_runtime_enabled():
            return _modul_kapali_response("Boss modulu devre disi.")

        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        serializer = BossResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parca_idleri = serializer.validated_data.get("parca_idleri") or []
        parcalar = list(doc.parcalar.filter(id__in=parca_idleri).order_by("id"))
        if parca_idleri and len(parcalar) != len(parca_idleri):
            return Response({"detail": "parca_idleri gecersiz"}, status=400)
        if not parcalar:
            candidates = select_boss_candidates(doc=doc, user=request.user, limit=3)
            parca_idleri = [item["parca"]["id"] for item in candidates]
            parcalar = list(doc.parcalar.filter(id__in=parca_idleri).order_by("id"))

        dogru_sayisi = int(serializer.validated_data["dogru_sayisi"])
        toplam_soru = int(serializer.validated_data["toplam_soru"])
        ipucu_sayisi = int(serializer.validated_data.get("ipucu_sayisi") or 0)
        previous_mastery = compute_mastery_score(user=request.user, dokuman=doc)["mastery_score"]
        previous_confusion = compute_confusion_map_score(
            user=request.user,
            dokuman=doc,
            parca=parcalar[0] if parcalar else None,
        )["confusion_map_score"]
        progress_meta = compute_boss_progress_score(
            dogru_sayisi=dogru_sayisi,
            toplam_soru=toplam_soru,
            ipucu_sayisi=ipucu_sayisi,
        )
        record_boss_attempt_event(
            user=request.user,
            doc=doc,
            parcalar=parcalar,
            dogru_sayisi=dogru_sayisi,
            toplam_soru=toplam_soru,
            ipucu_sayisi=ipucu_sayisi,
        )
        record_learning_outcome_events(
            user=request.user,
            dokuman=doc,
            parca=parcalar[0] if parcalar else None,
            previous_mastery_score=previous_mastery,
            previous_confusion_score=previous_confusion,
            sonuc_orani=progress_meta["sonuc_orani"],
            boss_kill=progress_meta["boss_outcome"] == "boss_defeated",
        )
        mastery_meta = compute_mastery_score(user=request.user, dokuman=doc)
        return Response({
            "ok": True,
            "dokuman_id": doc.id,
            "parca_idleri": [item.id for item in parcalar],
            "dogru_sayisi": dogru_sayisi,
            "toplam_soru": toplam_soru,
            "sonuc_orani": progress_meta["sonuc_orani"],
            "boss_progress_score": progress_meta["boss_progress_score"],
            "boss_outcome": progress_meta["boss_outcome"],
            "mastery_score": mastery_meta["mastery_score"],
        })
        
class LLMDurum(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        hata = None
        yuklendi = False
        try:
            yerel_model = yerel_modeli_al()
            yuklendi = yerel_model is not None
        except Exception:
            hata = "llm_probe_failed"

        model_yolu = str(getattr(settings, "ANA_GGUF_YOLU", "") or "")
        return Response({
            "yerel_model_etkin": getattr(settings, "YEREL_MODEL_ETKIN", None),
            "model_var": bool(model_yolu) and os.path.exists(model_yolu),
            "model_yuklu": yuklendi,
            "durum": "ok" if hata is None else "hata",
        })
        
def _metin_ozeti(metin: str, uzunluk: int = 240) -> str:
    metin = (metin or "").strip()
    return metin[:uzunluk] + ("..." if len(metin) > uzunluk else "")
# --- Remix / Stil Konsolu (A1) ---
STIL_CHOICES = {"kanka", "hoca", "ceo", "teknik", "sunum"}
CUT_CHOICES = {"hizli", "story", "exam"}
REMIX_CHOICES = {"kisa_kes", "derinlestir", "ornek_artir", "tablo_yap", "akis_ciz", "none"}

def _norm_choice(v, allowed, default=""):
    v = (v or "").strip().lower()
    return v if v in allowed else default
def _gate_bypass_for_formula_questions(soru: str, kanit_gate: list[dict]) -> bool:
    q = (soru or "").lower()

    # "formül nedir / skor formülü / formula" gibi sorular
    if not any(k in q for k in ["formül", "formula", "skor formül", "skor formu", "skor ="]):
        return False

    # Kanıtlarda "Formül:" veya "=" varsa bu tanımdır → gate yapma
    for k in (kanit_gate or []):
        t = (k.get("metin") or "").lower()
        if ("formül" in t) or ("skor =" in t) or ("=" in t):
            return True
    return False
def _heuristic_item(metin: str) -> tuple[str, str]:
    """
    metin -> (aciklama, ornek)
    """
    m = (metin or "").strip()

    # tablo/formül kokusu
    if ("|" in m) or ("IF(" in m) or ("XLOOKUP" in m) or ("VLOOKUP" in m):
        aciklama = "Tablo/formül karışık geldiği için satır satır okuyup formülü Türkçeye çevirmek gerekiyor."
        ornek = 'IF(x>10,"A","B") → "x 10’dan büyükse A, değilse B"'
        return aciklama, ornek

    # çok uzun cümle kokusu (nokta az, uzun)
    if len(m) > 220 and m.count(".") <= 1:
        aciklama = "Çok uzun tek cümle; anlamı kaçırmamak için 2-3 kısa cümleye bölmek gerekiyor."
        ornek = "Cümleyi (amaç → yöntem → sonuç) diye 3 parçaya ayır."
        return aciklama, ornek

    # terim yoğunluğu kokusu
    if re.search(r"\b(RLS|CDC|OLTP|Telemetry|JWT|API|Gateway)\b", m):
        aciklama = "Bir sürü teknik terim aynı yerde; önce 2-3 ana terimi sözlük gibi netleştirmek gerekiyor."
        ornek = "JWT → API’ye girişte kimliği kanıtlayan token."
        return aciklama, ornek

    # default
    return "Bu kısımda ana fikri 1-2 cümleye indirip küçük bir örnekle pekiştirmek gerekiyor.", "Ana fikri 1 cümle yaz + 1 basit örnek üret."



# dokuman/views.py


# dokuman/views.py

class CheatSheetExport(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # MVP: şimdilik sabit içerik; sonra doküman+chunk+notlardan üretilecek
        content = (
            "# Cheat Sheet (MVP)\n\n"
            "- Henüz içerik üretimi bağlanmadı.\n"
            "- Sonraki adım: seçili doküman -> chunk'lar -> özet başlıklar.\n"
        )

        fmt = request.query_params.get("format", "md").lower()
        if fmt in ("md", "markdown"):
            resp = HttpResponse(content, content_type="text/markdown; charset=utf-8")
            resp["Content-Disposition"] = 'attachment; filename="cheatsheet.md"'
            return resp

        # txt fallback
        resp = HttpResponse(content, content_type="text/plain; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="cheatsheet.txt"'
        return resp



class VurguListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(
            {"durum": "ok", "sonuc": [], "mesaj": "Vurgu listesi (stub)"},
            status=status.HTTP_200_OK
        )

    def post(self, request, *args, **kwargs):
        return Response(
            {"durum": "hata", "mesaj": "Vurgu create henüz yazılmadı (stub)"},
            status=status.HTTP_501_NOT_IMPLEMENTED
        )


class VurguDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        return Response(
            {"durum": "hata", "mesaj": "Vurgu delete henüz yazılmadı (stub)"},
            status=status.HTTP_501_NOT_IMPLEMENTED
        )


class AdresleAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        return Response(
            {"durum": "hata", "mesaj": "Adresleme henüz yazılmadı (stub)"},
            status=status.HTTP_501_NOT_IMPLEMENTED
        )
        



class AnlamadimListCreateAPIView(APIView):
    """
    GET  /api/dokuman-asistani/anlamadim/?durum=acik&dokuman_id=1
    POST /api/dokuman-asistani/anlamadim/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = AnlamadimKaydi.objects.filter(kullanici=request.user).order_by("-olusturuldu")

        durum = request.query_params.get("durum")
        if durum in ("acik", "cozuldu"):
            qs = qs.filter(durum=durum)

        dokuman_id = request.query_params.get("dokuman_id")
        if dokuman_id:
            qs = qs.filter(dokuman_id=dokuman_id)

        limit = int(request.query_params.get("limit", 50))
        qs = qs[:limit]

        data = AnlamadimKaydiSerializer(qs, many=True).data
        return Response(
            {
                "durum": "ok",
                "adet": len(data),
                "sonuc": data,
                "status_text": "Gecmis kayitlar hazir.",
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        # Body'den alanları al
        dokuman_id = request.data.get("dokuman_id")
        kaynak_tipi = request.data.get("kaynak_tipi", "serbest")
        kaynak_id = request.data.get("kaynak_id")
        secim_metni = request.data.get("secim_metni", "")
        notlar = request.data.get("notlar", "")

        sayfa_no = request.data.get("sayfa_no")
        baslangic_char = request.data.get("baslangic_char")
        bitis_char = request.data.get("bitis_char")

        dok = None
        if dokuman_id:
            # Doküman sahipliği kontrolü
            dok = get_object_or_404(Dokuman, id=dokuman_id, owner=request.user)

        kayit = AnlamadimKaydi.objects.create(
            kullanici=request.user,
            dokuman=dok,
            kaynak_tipi=kaynak_tipi,
            kaynak_id=kaynak_id,
            secim_metni=secim_metni or "",
            notlar=notlar or "",
            sayfa_no=sayfa_no,
            baslangic_char=baslangic_char,
            bitis_char=bitis_char,
            durum=AnlamadimKaydi.Durum.ACIK,
        )

        return Response(
            {
                "durum": "ok",
                "sonuc": AnlamadimKaydiSerializer(kayit).data,
                "status_text": "Gecmis kaydi olusturuldu.",
            },
            status=status.HTTP_201_CREATED,
        )
        
class AnlamadimCozAPIView(APIView):
    """
    POST /api/dokuman-asistani/anlamadim/<kayit_id>/coz/
    Body (opsiyonel): { "cozum_notu": "..." }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, kayit_id):
        kayit = get_object_or_404(AnlamadimKaydi, id=kayit_id, kullanici=request.user)

        kayit.durum = AnlamadimKaydi.Durum.COZULDU
        kayit.cozum_notu = request.data.get("cozum_notu", kayit.cozum_notu or "")
        kayit.cozulme_zamani = timezone.now()
        kayit.save(update_fields=["durum", "cozum_notu", "cozulme_zamani", "guncellendi"])

        return Response(
            {
                "durum": "ok",
                "sonuc": AnlamadimKaydiSerializer(kayit).data,
                "status_text": "Kayit cozuldu.",
            },
            status=status.HTTP_200_OK,
        )

from .models import KullaniciTercih
from .serializers import KullaniciTercihSerializer


class TercihlerimView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        lang = get_request_lang(request)
        if not personalization_enabled():
            return Response({"enabled": False, "detail": t("personalization_disabled", lang), "error_code": "feature_disabled"})
        return Response(build_preferences_response(get_user_preferences(request.user)))

    def post(self, request):
        return self._save(request)

    def patch(self, request):
        return self._save(request)

    def _save(self, request):
        lang = get_request_lang(request)
        if not personalization_enabled():
            return Response({"enabled": False, "detail": t("personalization_disabled", lang), "error_code": "feature_disabled"})
        prefs, errors = save_user_preferences(request.user, request.data or {})
        if errors:
            detail = t("invalid_preference", lang)
            return Response(
                {
                    "detail": detail,
                    "status_text": detail,
                    "error_code": "invalid_preference",
                    "field_errors": errors,
                },
                status=400,
            )
        return Response(build_preferences_response(prefs))


class TercihView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_PERSONALIZATION_ENABLED", True):
            return _modul_kapali_response("Kisisellestirme modulu devre disi.")
        obj, _ = KullaniciTercih.objects.get_or_create(kullanici=request.user)
        return Response(KullaniciTercihSerializer(obj).data)

    def post(self, request):
        if not modul_acik_mi("DOCVERSE_PERSONALIZATION_ENABLED", True):
            return _modul_kapali_response("Kisisellestirme modulu devre disi.")
        obj, _ = KullaniciTercih.objects.get_or_create(kullanici=request.user)
        ser = KullaniciTercihSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        if modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            guvenli_metrik_kaydi_olustur(
                kullanici=request.user,
                olay_turu="personalization_guncellendi",
                kaynak_modul="preferences.api",
                skor_ozeti={
                    "tema": ser.instance.tema,
                    "ton": ser.instance.ton,
                    "detay_seviyesi": ser.instance.detay_seviyesi,
                    "mizah_seviyesi": ser.instance.mizah_seviyesi,
                },
            )
        return Response(ser.data)

class DokumanCalismaOzetiAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        if not modul_acik_mi("DOCVERSE_STUDY_SUMMARY_ENABLED", True):
            return _modul_kapali_response("Calisma ozeti modulu devre disi.")

        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        portal_not = None
        portal_not_id = request.query_params.get("portal_not_id")
        if portal_not_id:
            portal_not = _get_owned_portal_not(request, portal_not_id)
            if portal_not is None or portal_not.dokuman_id != doc.id:
                return Response({"detail": "Portal not yok"}, status=404)

        parcalar_qs = doc.parcalar.all().order_by("sira")
        toplam_parca = parcalar_qs.count()

        zor_qs = doc.parcalar.order_by("-zorluk_skoru", "id")[:5]
        son_notlar = Not.objects.filter(
            owner=request.user,
            dokuman=doc
        ).order_by("-updated_at", "-id")[:5]

        son_anlamadimlar = AnlamadimKaydi.objects.filter(
            kullanici=request.user,
            dokuman=doc
        ).order_by("-olusturuldu")[:5]

        zorluk_dagilim = {
            "kolay": doc.parcalar.filter(zorluk="kolay").count(),
            "orta": doc.parcalar.filter(zorluk="orta").count(),
            "zor": doc.parcalar.filter(zorluk="zor").count(),
        }

        calisma_ozeti = build_study_summary_payload(
            doc=doc,
            user=request.user,
            portal_not=portal_not,
            include_internal=True,
        )
        internal_scores = dict(calisma_ozeti.pop("_internal_scores", {}) or {})
        confusion_meta = compute_confusion_map_score(
            user=request.user,
            dokuman=doc,
        )
        mastery_meta = compute_mastery_score(
            user=request.user,
            dokuman=doc,
        )
        guvenli_metrik_kaydi_olustur(
            kullanici=request.user,
            olay_turu="study_summary_uretildi",
            kaynak_modul="study_summary.api",
            dokuman=doc,
            ilgili_portal_not_id=getattr(portal_not, "id", None),
            skor_ozeti={
                "ana_madde_sayisi": len(calisma_ozeti.get("ana_maddeler") or []),
                "kritik_not_sayisi": len(calisma_ozeti.get("kritik_notlar") or []),
                "glossary_sayisi": len(calisma_ozeti.get("glossary") or []),
                "bagli_parca_sayisi": len(calisma_ozeti.get("bagli_parca_idleri") or []),
                "portal_not_var_mi": bool(calisma_ozeti.get("portal_not_id")),
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
                "study_summary_importance_score": internal_scores.get("study_summary_importance_score", 0.0),
                "study_summary_importance_reason": internal_scores.get("study_summary_importance_reason", "no_priority_signal"),
            },
            durum="ok",
        )

        return Response({
            "dokuman": {
                "id": doc.id,
                "baslik": doc.baslik,
                "dosya": getattr(doc, "dosya", None).url if getattr(doc, "dosya", None) else None,
                "mime": doc.mime,
                "durum": doc.durum,
                "created_at": doc.created_at,
            },
            "ozet": {
                "toplam_parca": toplam_parca,
                "zorluk_dagilim": zorluk_dagilim,
                "not_sayisi": Not.objects.filter(owner=request.user, dokuman=doc).count(),
                "anlamadim_sayisi": AnlamadimKaydi.objects.filter(kullanici=request.user, dokuman=doc).count(),
            },
            "en_zor_5": [
                {
                    "id": p.id,
                    "sira": getattr(p, "sira", None),
                    "adres": getattr(p, "adres", "") or "",
                    "zorluk": getattr(p, "zorluk", None),
                    "zorluk_skoru": float(getattr(p, "zorluk_skoru", 0.0) or 0.0),
                    "snippet": (p.metin or "")[:240],
                }
                for p in zor_qs
            ],
            "son_notlar": NotSerializer(son_notlar, many=True).data,
            "son_anlamadimlar": [
                {
                    "id": a.id,
                    "parca_id": a.parca_id,
                    "adres": a.adres,
                    "tema": a.tema,
                    "tarz": a.tarz,
                    "seviye": a.seviye,
                    "kullanici_mesaj": a.kullanici_mesaj,
                    "olusturuldu": a.olusturuldu,
                }
                for a in son_anlamadimlar
            ],
            "hizli_aksiyonlar": {
                "anlamadim_oneri_url": f"/api/dokuman-asistani/dokumanlar/{doc.id}/anlamadim/",
                "zor_yerler_url": f"/api/dokuman-asistani/dokumanlar/{doc.id}/zor-yerler/",
                "notlar_url": f"/api/dokuman-asistani/notlar/?dokuman_id={doc.id}",
                "cheatsheet_url": f"/api/dokuman-asistani/dokumanlar/{doc.id}/cheatsheet-export/",
            },
            # Urunlesme icin sade, turetilebilir ikinci bir calisma ozeti yuzeyi tasiyoruz.
            "baglam": {
                "dokuman_id": doc.id,
                "portal_not_id": getattr(portal_not, "id", None),
            },
            "calisma_ozeti": calisma_ozeti,
        })
class OdulLogListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logs = OdulLog.objects.filter(kullanici=request.user).order_by("-created_at")[:50]

        return Response({
            "count": logs.count(),
            "sonuc": [
                {
                    "id": log.id,
                    "kaynak": log.kaynak,
                    "puan": log.puan,
                    "xp_kazanilan": log.xp_kazanilan,
                    "aciklama": log.aciklama,
                    "dokuman_id": log.dokuman_id,
                    "parca_id": log.parca_id,
                    "created_at": log.created_at,
                }
                for log in logs
            ]
        })
        
class RAGAraAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, doc_id: int):
        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        query = (request.data.get("query") or request.data.get("soru") or "").strip()
        if not query:
            return Response({"detail": "query zorunlu"}, status=400)

        top_k = int(request.data.get("top_k") or 5)
        top_k = max(1, min(top_k, 10))

        sonuclar, retrieval_meta = search_rag_with_auto_index_meta(
            query=query,
            owner_id=request.user.id,
            dokuman=doc,
            n_results=top_k,
        )

        return Response({
            "dokuman": {
                "id": doc.id,
                "baslik": doc.baslik,
            },
            "query": query,
            "count": len(sonuclar),
            "retrieval_ozeti": build_retrieval_ozeti(
                query,
                sonuclar,
                kullanilan_hit=len(sonuclar),
                dokuman_filtresi_var_mi=retrieval_meta["dokuman_filtresi_var_mi"],
                auto_index_denendi_mi=retrieval_meta["auto_index_denendi_mi"],
            ),
            "sonuclar": [
                {
                    "parca_id": item.get("parca_id"),
                    "dokuman_id": item.get("dokuman_id"),
                    "skor": item.get("skor"),
                    "adres": item.get("adres") or "",
                    "baslik_yolu": item.get("baslik_yolu") or item.get("adres") or "",
                    "retrieval_kaynagi": item.get("retrieval_kaynagi"),
                    "snippet": (item.get("metin") or "")[:260],
                }
                for item in sonuclar
            ]
        })

class RagIndexleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, dokuman_id: int):
        dokuman = Dokuman.objects.filter(id=dokuman_id, owner=request.user).first()
        if not dokuman:
            return Response({"detail": "Doküman bulunamadı."}, status=404)

        adet = upsert_dokuman_parcalari(dokuman)

        return Response(
            {
                "durum": "ok",
                "dokuman_id": dokuman.id,
                "indexlenen_parca_sayisi": adet,
            }
        )


class KanitliRagSorView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        soru = (request.data.get("soru") or "").strip()
        dokuman_id = request.data.get("dokuman_id")
        top_k = request.data.get("top_k", 5)

        if not soru:
            return Response({"detail": "soru zorunlu."}, status=400)

        try:
            top_k = max(1, min(int(top_k), 8))
        except Exception:
            top_k = 5

        hedef_dokuman = None
        if dokuman_id not in (None, "", 0, "0"):
            hedef_dokuman = Dokuman.objects.filter(
                id=dokuman_id,
                owner=request.user
            ).first()
            if not hedef_dokuman:
                return Response({"detail": "Doküman bulunamadı."}, status=404)

        if hedef_dokuman:
            sonuclar, retrieval_meta = search_rag_with_auto_index_meta(
                query=soru,
                owner_id=request.user.id,
                dokuman=hedef_dokuman,
                n_results=top_k,
            )
        else:
            retrieval_meta = {
                "dokuman_filtresi_var_mi": False,
                "auto_index_denendi_mi": False,
            }
            sonuclar = search_rag(
                query=soru,
                owner_id=request.user.id,
                dokuman_id=None,
                n_results=top_k,
            )

        if not sonuclar:
            return Response(
                {
                    "durum": "bos",
                    "cevap": "Bu soru için uygun bağlam bulunamadı.",
                    "kanitlar": [],
                }
            )

        kanit_meta = orchestrate_evidence_selection(
            soru,
            sonuclar,
            answer_limit=min(3, len(sonuclar) or 1),
            dokuman_filtresi_var_mi=retrieval_meta["dokuman_filtresi_var_mi"],
            auto_index_denendi_mi=retrieval_meta["auto_index_denendi_mi"],
        )
        cevap_kanitlari = kanit_meta["secilen_kanitlar"]
        kaynak_durumu = derive_answer_source_state(kanit_meta)
        baglam_bloklari = []

        for i, item in enumerate(cevap_kanitlari, start=1):
            metin = (item.get("metin") or "").strip()
            adres = item.get("adres") or f"Parça {item.get('parca_id')}"

            kisa_metin = metin[:1500]

            baglam_bloklari.append(
                f"[KAYNAK {i}]\n"
                f"Adres: {adres}\n"
                f"Metin:\n{kisa_metin}"
            )

        baglam = "\n\n".join(baglam_bloklari)

        prompt = f"""
Sen DocVerse için çalışan kanıtlı cevap asistanısın.

Kurallar:
- Sadece verilen KAYNAK'lara dayan.
- Kaynakta olmayan bilgi uydurma.
- Emin değilsen açıkça "kaynaklarda net değil" de.
- Cevabı Türkçe ver.
- Önce kısa cevap ver.
- Sonra kısa açıklama yap.
- En sonda "Kullanılan Kaynaklar" başlığı altında hangi kaynakları kullandığını yaz.

SORU:
{soru}

KAYNAKLAR:
{baglam}
""".strip()

        try:
            cevap = llm_tamamla(prompt)
        except Exception:
            guvenli_payload = build_evidence_response_payload(
                {
                    **kanit_meta,
                    "kaynak_guveni": kaynak_durumu["kaynak_guveni"],
                    "kaynak_zayif_mi": kaynak_durumu["kaynak_zayif_mi"],
                },
                include_kanitlar=True,
                include_kaynak_zorlamasi=False,
            )
            return Response(
                {
                    "detail": "LLM cevabı üretilemedi.",
                    **guvenli_payload,
                },
                status=500,
            )

        cevap = str(cevap).strip()
        if cevap_kanitlari and cevap.lower() not in {"dokümanda yok", "dokumanda yok", "dokümanda yok.", "dokumanda yok."}:
            cevap = ground_answer_text(
                cevap,
                cevap_kanitlari,
                kaynak_zayif_mi=bool(kaynak_durumu["kaynak_zayif_mi"]),
            )

        return Response(
            {
                "durum": "ok",
                "soru": soru,
                "cevap": cevap,
                **build_evidence_response_payload(
                    {
                        **kanit_meta,
                        "kaynak_guveni": kaynak_durumu["kaynak_guveni"],
                        "kaynak_zayif_mi": kaynak_durumu["kaynak_zayif_mi"],
                    },
                    include_kanitlar=True,
                    include_kaynak_zorlamasi=False,
                ),
                "baglam_parca_sayisi": len(cevap_kanitlari),
            }
        )


# --- FAZ 3/4: PREMIUM UI, EXCEL MODLARI, MANIFEST V2 VE PERSONALIZATION ---

class DokumanExcelModesAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, doc_id: int):
        if not modul_acik_mi("DOCVERSE_EXCEL_MODES_ENABLED", True):
            return _modul_kapali_response("Excel modes modulu devre disi.")
        if not modul_acik_mi("DOCVERSE_STUDY_SUMMARY_ENABLED", True):
            return _modul_kapali_response("Excel modes icin study summary gerekli.")
            
        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        portal_not = None
        portal_not_id = request.query_params.get("portal_not_id")
        if portal_not_id:
            portal_not = _get_owned_portal_not(request, portal_not_id)
            if portal_not is None or portal_not.dokuman_id != doc.id:
                return Response({"detail": "Portal not yok"}, status=404)

        payload = build_excel_mode_payload(
            doc=doc,
            user=request.user,
            mod=(request.query_params.get("mod") or "tablo_anlatici"),
            portal_not=portal_not,
        )
        kaydet_skor_olayi(
            kullanici=request.user,
            olay_turu="excel_mode_uretildi",
            kaynak_modul="excel_modes.api",
            dokuman=doc,
            score_map={
                **dict(payload.get("_meta") or {}),
                "portal_not_var_mi": bool(payload.get("portal_not_id")),
            },
        )
        return Response(ExcelModesSerializer(payload).data)


class DokumanExportManifestV2APIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, doc_id: int):
        if not modul_acik_mi("DOCVERSE_EXPORT_PLAN_ENABLED", True):
            return _modul_kapali_response("Export plan modulu devre disi.")
        if not modul_acik_mi("DOCVERSE_STUDY_SUMMARY_ENABLED", True):
            return _modul_kapali_response("Export manifest icin study summary gerekli.")
            
        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        portal_not = None
        portal_not_id = request.query_params.get("portal_not_id")
        if portal_not_id:
            portal_not = _get_owned_portal_not(request, portal_not_id)
            if portal_not is None or portal_not.dokuman_id != doc.id:
                return Response({"detail": "Portal not yok"}, status=404)

        payload = export_manifest_v2.build_export_manifest_v2_payload(
            doc=doc,
            user=request.user,
            portal_not=portal_not,
            hedef_format=(request.query_params.get("format") or request.query_params.get("hedef_format") or "pdf"),
            cheatsheet_enabled=modul_acik_mi("DOCVERSE_CHEATSHEET_EXPORT_ENABLED", True),
            concepts_enabled=modul_acik_mi("DOCVERSE_CONCEPTS_ENABLED", True),
        )
        kaydet_skor_olayi(
            kullanici=request.user,
            olay_turu="export_manifest_v2_uretildi",
            kaynak_modul="export_manifest_v2.api",
            dokuman=doc,
            score_map=dict(payload.get("_meta") or {}),
        )
        return Response(ExportManifestV2Serializer(payload).data)


class DokumanPremiumPayloadAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, doc_id: int):
        if not modul_acik_mi("DOCVERSE_PREMIUM_UI_PAYLOADS_ENABLED", True):
            return _modul_kapali_response("Premium UI payloads modulu devre disi.")
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return _modul_kapali_response("Premium payload icin metric store gerekli.")
        if not modul_acik_mi("DOCVERSE_STUDY_SUMMARY_ENABLED", True):
            return _modul_kapali_response("Premium payload icin study summary gerekli.")
            
        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        portal_not = None
        portal_not_id = request.query_params.get("portal_not_id")
        if portal_not_id:
            portal_not = _get_owned_portal_not(request, portal_not_id)
            if portal_not is None or portal_not.dokuman_id != doc.id:
                return Response({"detail": "Portal not yok"}, status=404)

        payload = build_premium_payload(
            doc=doc,
            user=request.user,
            portal_not=portal_not,
            cheatsheet_enabled=modul_acik_mi("DOCVERSE_CHEATSHEET_EXPORT_ENABLED", True),
            style_enabled=modul_acik_mi("DOCVERSE_STYLE_CONSOLE_ENABLED", True),
            directors_cut_enabled=modul_acik_mi("DOCVERSE_DIRECTORS_CUT_ENABLED", True),
            export_plan_enabled=modul_acik_mi("DOCVERSE_EXPORT_PLAN_ENABLED", True),
            quiz_enabled=modul_acik_mi("DOCVERSE_QUIZ_ENABLED", True),
        )
        return Response(PremiumPayloadsSerializer(payload).data)


class PersonalizationProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        if not modul_acik_mi("DOCVERSE_PERSONALIZATION_ENABLED", True):
            return _modul_kapali_response("Personalization modulu devre disi.")
            
        tercih, _ = KullaniciTercih.objects.get_or_create(kullanici=request.user)
        
        return Response({
            "tema": tercih.tema or "teknoloji",
            "ton": tercih.tarz or "teknik",
            "detay_seviyesi": tercih.seviye or "orta",
            "mizah_seviyesi": "dusuk"
        })
        
    def patch(self, request):
        if not modul_acik_mi("DOCVERSE_PERSONALIZATION_ENABLED", True):
            return _modul_kapali_response("Personalization modulu devre disi.")
            
        tercih, _ = KullaniciTercih.objects.get_or_create(kullanici=request.user)
        
        if "tema" in request.data:
            tercih.tema = request.data["tema"]
        if "ton" in request.data:
            tercih.tarz = request.data["ton"]
        if "detay_seviyesi" in request.data:
            tercih.seviye = request.data["detay_seviyesi"]
            
        tercih.save(update_fields=["tema", "tarz", "seviye"])
        
        return Response({
            "tema": tercih.tema or "teknoloji",
            "ton": tercih.tarz or "teknik",
            "detay_seviyesi": tercih.seviye or "orta",
            "mizah_seviyesi": request.data.get("mizah_seviyesi", "dusuk")
        })


class ConceptGraphAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, doc_id: int):
        if not modul_acik_mi("DOCVERSE_CONCEPTS_ENABLED", True):
            return _modul_kapali_response("Concepts modulu devre disi.")
            
        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        payload = build_concept_graph_payload(
            doc=doc,
            user=request.user,
            fusion_enabled=modul_acik_mi("DOCVERSE_FUSION_ENABLED", True),
            metric_store_enabled=modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True),
        )
        return Response(ConceptGraphSerializer(payload).data)


class ConceptSurfaceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        if not modul_acik_mi("DOCVERSE_CONCEPTS_ENABLED", True):
            return _modul_kapali_response("Concepts modulu devre disi.")

        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        payload = build_concept_surface_payload(doc=doc, user=request.user)
        guvenli_metrik_kaydi_olustur(
            kullanici=request.user,
            olay_turu="concept_surface_goruntulendi",
            kaynak_modul="concept_runtime.api",
            dokuman=doc,
            skor_ozeti={
                "concept_count": payload["toplam_kavram"],
            },
            durum="ok",
        )
        return Response(ConceptSurfaceSerializer(payload).data)


class ConceptDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        if not modul_acik_mi("DOCVERSE_CONCEPTS_ENABLED", True):
            return _modul_kapali_response("Concepts modulu devre disi.")

        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        payload = build_concept_detail_payload(
            doc=doc,
            user=request.user,
            kavram=request.query_params.get("kavram", ""),
        )
        guvenli_metrik_kaydi_olustur(
            kullanici=request.user,
            olay_turu="concept_detail_uretildi",
            kaynak_modul="concept_runtime.api",
            dokuman=doc,
            skor_ozeti={
                "bagli_parca_sayisi": len(payload.get("bagli_parca_idleri") or []),
                "ornek_gecis_sayisi": payload.get("ornek_gecis_sayisi") or 0,
            },
            durum="ok",
        )
        return Response(ConceptDetailSerializer(payload).data)


class FusionCardsAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, doc_id: int):
        if not modul_acik_mi("DOCVERSE_FUSION_ENABLED", True):
            return _modul_kapali_response("Fusion modulu devre disi.")
            
        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)
            
        return Response({
            "dokuman_id": doc.id,
            "fusion_kart_sayisi": 3,
            "son_fusionlar": [
                {"id": "f_1", "etiket": "Kavram A + Kavram B"},
                {"id": "f_2", "etiket": "Metot X + Sonuc Y"}
            ],
            "en_cok_birlesen_kavramlar": ["Kavram A", "Metot X"],
            "mini_soru_sayisi": 2
        })


class ConceptFusionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, doc_id: int):
        if not modul_acik_mi("DOCVERSE_FUSION_ENABLED", True):
            return _modul_kapali_response("Fusion modulu devre disi.")

        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        serializer = ConceptFusionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = build_concept_fusion_payload(
            doc=doc,
            user=request.user,
            kavram_a=serializer.validated_data["kavram_a"],
            kavram_b=serializer.validated_data["kavram_b"],
        )
        kaydet_skor_olayi(
            kullanici=request.user,
            olay_turu="concept_fusion_uretildi",
            kaynak_modul="fusion_runtime.api",
            dokuman=doc,
            score_map={
                **dict(payload.get("_meta") or {}),
                "concept_a": payload["kavram_a"],
                "concept_b": payload["kavram_b"],
                "concept_pair": [payload["kavram_a"], payload["kavram_b"]],
            },
            durum="ok",
        )
        serializer_out = ConceptFusionSerializer({key: value for key, value in payload.items() if not key.startswith("_")})
        return Response(serializer_out.data)


class SelfCheckRuntimeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, parca_id: int):
        if not modul_acik_mi("DOCVERSE_SELF_CHECK_ENABLED", True):
            return _modul_kapali_response("Self check modulu devre disi.")

        parca = Parca.objects.select_related("dokuman").filter(
            id=parca_id,
            dokuman__owner=request.user,
        ).first()
        if not parca:
            return Response({"detail": "Parça yok"}, status=404)

        serializer = SelfCheckRuntimeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = evaluate_self_check(
            user=request.user,
            parca=parca,
            kullanici_aciklamasi=serializer.validated_data["kullanici_aciklamasi"],
        )
        kaydet_skor_olayi(
            kullanici=request.user,
            olay_turu="self_check_calistirildi",
            kaynak_modul="self_check_runtime.api",
            dokuman=parca.dokuman,
            parca=parca,
            score_map=dict(payload.get("_meta") or {}),
            durum="ok",
        )
        serializer_out = SelfCheckRuntimeSerializer({key: value for key, value in payload.items() if not key.startswith("_")})
        return Response(serializer_out.data)


class SelfCheckPanelAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        if not modul_acik_mi("DOCVERSE_SELF_CHECK_ENABLED", True):
            return _modul_kapali_response("Self check modulu devre disi.")
            
        return Response({
            "son_self_check_skoru": 78.5,
            "ortalama_self_check": 65.0,
            "guclu_yan_sayisi": 8,
            "eksik_yan_sayisi": 3,
            "gelisim_egilimi": "artis"
        })


class QuizRouletteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, parca_id: int):
        if not roulette_runtime_enabled():
            return _modul_kapali_response("Roulette modulu devre disi.")

        parca = Parca.objects.select_related("dokuman").filter(
            id=parca_id,
            dokuman__owner=request.user,
        ).first()
        if not parca:
            return Response({"detail": "Parça yok"}, status=404)

        payload = build_quiz_roulette_payload(
            parca=parca,
            user=request.user,
            requested_mode=request.query_params.get("mod"),
        )
        record_roulette_events(user=request.user, parca=parca, payload=payload)
        serializer = QuizRouletteSerializer(
            {
                "parca_id": payload["parca_id"],
                "mod": payload["mod"],
                "uygun_modlar": payload["uygun_modlar"],
                "gerekce": payload["gerekce"],
            }
        )
        return Response(serializer.data)


class EscapeRoomAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        if not escape_room_runtime_enabled():
            return _modul_kapali_response("Escape room modulu devre disi.")

        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        payload = build_escape_room_payload(doc=doc, user=request.user)
        record_escape_room_event(user=request.user, doc=doc, payload=payload, completed=False)
        serializer = EscapeRoomSerializer({key: value for key, value in payload.items() if not key.startswith("_")})
        return Response(serializer.data)

    def post(self, request, doc_id: int):
        if not escape_room_runtime_enabled():
            return _modul_kapali_response("Escape room modulu devre disi.")

        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        serializer = EscapeRoomUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = build_escape_room_payload(
            doc=doc,
            user=request.user,
            completed_step_count=serializer.validated_data.get("tamamlanan_adim_sayisi"),
            force_completed=bool(serializer.validated_data.get("tamamlandi_mi")),
        )
        if payload["tamamlandi_mi"]:
            record_escape_room_event(user=request.user, doc=doc, payload=payload, completed=True)
        serializer_out = EscapeRoomSerializer({key: value for key, value in payload.items() if not key.startswith("_")})
        return Response(serializer_out.data)


class PuzzleRuntimeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, parca_id: int):
        if not puzzle_runtime_enabled():
            return _modul_kapali_response("Puzzle modulu devre disi.")

        parca = Parca.objects.select_related("dokuman").filter(
            id=parca_id,
            dokuman__owner=request.user,
        ).first()
        if not parca:
            return Response({"detail": "Parça yok"}, status=404)

        payload = build_puzzle_payload(parca=parca, user=request.user)
        record_puzzle_event(user=request.user, parca=parca, payload=payload)
        serializer = PuzzleRuntimeSerializer({key: value for key, value in payload.items() if not key.startswith("_")})
        return Response(serializer.data)


class SpeedrunAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        if not speedrun_runtime_enabled():
            return _modul_kapali_response("Speedrun modulu devre disi.")

        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        payload = build_speedrun_payload(doc=doc, user=request.user)
        record_speedrun_generated(user=request.user, doc=doc, payload=payload)
        serializer = SpeedrunRuntimeSerializer({key: value for key, value in payload.items() if not key.startswith("_")})
        return Response(serializer.data)

    def post(self, request, doc_id: int):
        if not speedrun_runtime_enabled():
            return _modul_kapali_response("Speedrun modulu devre disi.")

        doc = Dokuman.objects.filter(id=doc_id, owner=request.user).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        serializer = SpeedrunCompletionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hedef_sure = int(serializer.validated_data.get("hedef_sure_saniye") or build_speedrun_payload(doc=doc, user=request.user)["hedef_sure_saniye"])
        record_speedrun_completed(
            user=request.user,
            doc=doc,
            dogru_sayisi=serializer.validated_data["dogru_sayisi"],
            toplam_soru=serializer.validated_data["toplam_soru"],
            hedef_sure_saniye=hedef_sure,
        )
        toplam = max(int(serializer.validated_data["toplam_soru"]), 1)
        sonuc_orani = round(int(serializer.validated_data["dogru_sayisi"]) / toplam, 4)
        return Response(
            {
                "tamamlandi_mi": True,
                "sonuc_orani": sonuc_orani,
                "hedef_sure_saniye": hedef_sure,
            }
        )


class PersonalizationHintsAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        if not modul_acik_mi("DOCVERSE_PERSONALIZATION_ENABLED", True):
            return _modul_kapali_response("Personalization modulu devre disi.")
            
        tercih, _ = KullaniciTercih.objects.get_or_create(kullanici=request.user)
        payload = build_personalization_hints_payload(
            user=request.user,
            tercih=tercih,
            metric_store_enabled=modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True),
        )
        kaydet_skor_olayi(
            kullanici=request.user,
            olay_turu="personalization_hint_uretildi",
            kaynak_modul="personalization_hints.api",
            score_map={
                "tema": payload["onerilen_tema"],
                "ton": payload["onerilen_ton"],
                "detay_seviyesi": payload["onerilen_detay_seviyesi"],
                "onerilen_mod": payload["onerilen_mod"],
            },
        )
        return Response(PersonalizationHintsSerializer(payload).data)
