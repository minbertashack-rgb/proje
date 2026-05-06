from __future__ import annotations

import re
import logging
from datetime import timedelta
from typing import Any

from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from dokuman.models import AnlamadimKaydi, KullaniciGeriBildirim, MetrikKaydi
from dokuman.services.feature_flags import modul_acik_mi
from dokuman.services.phase2_scores import compute_feedback_weight_score as compute_feedback_read_weight

logger = logging.getLogger(__name__)

try:
    from oyun.models import BossDeneme
except Exception:
    BossDeneme = None

_PATH_LIKE_RE = re.compile(r"(?:[a-zA-Z]:\\|\\\\|/|\.{2}[\\/])")
_SENSITIVE_TEXT_RE = re.compile(r"(?:\bsecret\b|\bprompt\b|\braw\b|ham_)", re.IGNORECASE)
_LABEL_STATE_KEYS = {"concept_a", "concept_b", "concept_pair"}

_ALLOWED_NUMERIC_SCORE_KEYS = {
    "quality_score",
    "ocr_quality_score",
    "difficulty_score",
    "cheatsheet_priority_score",
    "boss_candidate_score",
    "quiz_readiness_score",
    "feedback_weight_score",
    "study_summary_importance_score",
    "completeness_score",
    "hallucination_risk",
    "usefulness_score_v2",
    "evidence_confidence",
    "citation_alignment_score",
    "confusion_map_score",
    "mastery_score",
    "etiket_sayisi",
    "kaynak_parca_sayisi",
    "ana_madde_sayisi",
    "kritik_not_sayisi",
    "glossary_sayisi",
    "bagli_parca_sayisi",
    "kullanilan_parca_sayisi",
    "kisa_not_uzunlugu",
    "read_ratio",
    "expected_read_seconds",
    "observed_read_seconds",
    "confusion_incomplete_ratio",
    "confusion_quiz_fail_ratio",
    "confusion_revisit_ratio",
    "confusion_high_dwell_ratio",
    "mastery_quiz_success_ratio",
    "mastery_usefulness_avg",
    "mastery_repeat_penalty",
    "feedback_speed_score",
    "feedback_spam_penalty",
    "feedback_context_bonus",
    "dogru_sayisi",
    "toplam_soru",
    "sonuc_orani",
    "secilen_parca_sayisi",
    "arena_sayisi",
    "boss_difficulty_score",
    "boss_progress_score",
    "mastery_progress_delta",
    "learning_momentum_score",
    "confusion_recovery_score",
    "reward_priority_score",
    "boss_adayi_sayisi",
    "cooldown_factor",
    "note_count",
    "boss_retry_count",
    "ipucu_sayisi",
    "concept_count",
    "self_check_score",
    "critical_concept_count",
    "matched_concept_count",
    "hallucinated_term_count",
    "concept_overlap_ratio",
    "ortak_parca_sayisi",
    "ornek_gecis_sayisi",
    "roulette_option_count",
    "escape_target_count",
    "escape_step_count",
    "escape_completed_step_count",
    "escape_progress_score",
    "puzzle_blank_count",
    "speedrun_target_seconds",
    "speedrun_sentence_count",
    "reels_selected_count",
    "weekly_progress_score",
    "weekly_goal_progress_score",
    "boss_rush_readiness_score",
    "export_readiness_score",
    "personalization_confidence_score",
    "achievement_progress_score",
    "quiz_count",
    "boss_count",
    "boss_wins",
    "self_check_count",
    "suggestion_count",
    "section_count",
    "slide_count",
    "avg_difficulty",
    "peak_difficulty",
    "high_confusion_ratio",
    "candidate_chunk_count",
    "cooldown_minutes",
    "mastery_confusion_balance",
    "recent_boss_success",
    "recent_boss_recency",
    "doc_length_norm",
    "short_dense_hard_ratio",
    "low_candidate_penalty",
    "triviality_penalty",
    "task_completion",
    "completed_goals",
    "goal_volume_score",
    "development_score",
    "variety_score",
    "current_streak_days",
    "summary_count",
    "fusion_count",
    "reels_count",
    "streak_norm",
    "mastery_delta_norm",
    "confusion_drop_norm",
    "learning_variety",
    "note_engagement",
    "abandonment_ratio",
    "chunk_norm",
    "density_score",
    "quality_avg",
    "heading_avg",
    "table_flag",
    "code_flag",
    "image_flag",
    "cheatsheet_flag",
    "summary_flag",
    "portal_note_flag",
    "note_flag",
    "manifest_v2_flag",
    "presentation_plan_flag",
    "structural_variety",
    "too_short_penalty",
    "has_presentation_plan",
    "pref_defined",
    "default_flag",
    "data_volume",
    "usage_volume",
    "mode_consistency",
    "style_remix_usage",
    "accepted_suggestion_ratio",
    "override_instability",
    "repeat_rejection_ratio",
    "behavior_alignment",
    "drift_score",
    "rejection_ratio",
    "theme_margin",
    "tone_margin",
    "target_badge_progress",
}
_ALLOWED_STATE_KEYS = {
    "quality_reason",
    "ocr_quality_reason",
    "difficulty_reason",
    "cheatsheet_reason",
    "quiz_reason",
    "feedback_reason",
    "unsupported_reason",
    "supported",
    "fallback_json_kullanildi",
    "kaynak_guveni",
    "abstention_uygulandi_mi",
    "weak_content",
    "ocr_strict_quality_mode",
    "chunk_sayisi",
    "kaydedilen_parca_sayisi",
    "is_cheatsheet",
    "quiz_ready",
    "feedback_ignored",
    "confusion_reason",
    "mastery_reason",
    "feedback_weight_reason",
    "study_summary_importance_reason",
    "cheatsheet_priority_reason",
    "quiz_skip_reason",
    "quiz_eligible",
    "boss_reason",
    "boss_parca_idleri",
    "boss_rush_state",
    "export_readiness_state",
    "personalization_state",
    "weekly_goal_state",
    "achievement_state",
    "zorluk_bandi",
    "onerilen_format",
    "format",
    "feedback_turu",
    "kaynak_modul",
    "not_turu",
    "olusturma_kaynagi",
    "pinned",
    "arsivli",
    "dokuman_var_mi",
    "parca_var_mi",
    "not_var_mi",
    "portal_not_var_mi",
    "boss_difficulty_band",
    "boss_progress_reason",
    "recovery_reason",
    "reward_priority_reason",
    "boss_outcome",
    "eureka_triggered",
    "quiz_action",
    "show_quiz_prompt",
    "tema",
    "ton",
    "detay_seviyesi",
    "mizah_seviyesi",
    "stil",
    "mod",
    "excel_mode",
    "export_plan_turu",
    "hedef_format",
    "onerilen_mod",
    "concept_a",
    "concept_b",
    "concept_pair",
    "roulette_mode",
    "roulette_reason",
    "unlock_reason_code",
    "escape_status",
    "puzzle_status",
    "speedrun_status",
    "chunk_kind",
    "fallback_kind",
    "selection_state",
    "rank_strategy",
    "secondary_theme",
    "output_format",
    "source_manifest_version",
    "output_created",
    "readiness",
}


def _looks_sensitive_metric_text(value: str) -> bool:
    clean = " ".join(str(value or "").split()).strip()
    if not clean:
        return False
    if _PATH_LIKE_RE.search(clean):
        return True
    if _SENSITIVE_TEXT_RE.search(clean):
        return True
    return False


def _sanitize_metric_text(
    value: Any,
    *,
    max_len: int,
    max_words: int,
    redacted: str = "[redacted]",
) -> str:
    clean = " ".join(str(value or "").split()).strip()
    if not clean:
        return ""
    if _looks_sensitive_metric_text(clean):
        return redacted
    if len(clean) > max_len:
        return redacted
    if len(clean.split()) > max_words:
        return redacted
    return clean


def _sanitize_metric_value(value: Any, *, key: str = ""):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        if key in _LABEL_STATE_KEYS:
            return _sanitize_metric_text(value, max_len=40, max_words=4, redacted="")
        return _sanitize_metric_text(value, max_len=48, max_words=6)
    if isinstance(value, dict):
        out = {}
        for nested_key, item in value.items():
            clean_item = _sanitize_metric_value(item, key=str(nested_key)[:48])
            if clean_item in ("", [], {}):
                continue
            out[str(nested_key)[:48]] = clean_item
        return out
    if isinstance(value, list):
        limit = 2 if key == "concept_pair" else 12
        out = []
        for item in value[:limit]:
            clean_item = _sanitize_metric_value(item, key=key)
            if clean_item in ("", [], {}):
                continue
            out.append(clean_item)
        return out
    return str(value)[:48]


def _safe_metric_summary(score_map: dict | None = None) -> dict:
    clean = {}
    for key, value in (score_map or {}).items():
        key = str(key or "").strip()
        if not key:
            continue
        if key in _ALLOWED_NUMERIC_SCORE_KEYS:
            if isinstance(value, bool):
                clean[key] = bool(value)
            elif isinstance(value, (int, float)):
                clean[key] = round(float(value), 4)
            continue
        if key in _ALLOWED_STATE_KEYS:
            clean_value = _sanitize_metric_value(value, key=key)
            if clean_value in ("", [], {}):
                continue
            clean[key] = clean_value
    return clean


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def _safe_avg(values) -> float:
    clean = []
    for value in values or []:
        try:
            clean.append(float(value))
        except Exception:
            continue
    if not clean:
        return 0.0
    return sum(clean) / len(clean)


def _safe_metric_number(score_map: dict | None, key: str) -> float:
    try:
        return float((score_map or {}).get(key) or 0.0)
    except Exception:
        return 0.0


def _safe_metric_bool(score_map: dict | None, key: str) -> bool:
    return bool((score_map or {}).get(key))


def _bounded_ratio(numerator: float, denominator: float, *, fallback: float = 0.0) -> float:
    try:
        den = float(denominator or 0.0)
        if den <= 0:
            return _clamp01(fallback)
        return _clamp01(float(numerator or 0.0) / den)
    except Exception:
        return _clamp01(fallback)


def _normalized_count(count: int | float, full_mark: int | float) -> float:
    try:
        return _clamp01(float(count or 0.0) / max(float(full_mark or 1.0), 1.0))
    except Exception:
        return 0.0


def _context_metric_qs(*, user, dokuman=None, parca=None, olay_turu: str | None = None, gun: int | None = None):
    qs = MetrikKaydi.objects.filter(kullanici=user)
    if dokuman is not None:
        qs = qs.filter(dokuman=dokuman)
    if parca is not None:
        qs = qs.filter(parca=parca)
    if olay_turu:
        qs = qs.filter(olay_turu=olay_turu)
    if gun:
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=max(1, int(gun))))
    return qs


def _context_feedback_qs(*, user, dokuman=None, parca=None, son_dakika: int | None = None):
    qs = KullaniciGeriBildirim.objects.filter(owner=user)
    if dokuman is not None:
        qs = qs.filter(dokuman=dokuman)
    if parca is not None:
        qs = qs.filter(parca=parca)
    if son_dakika:
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(minutes=max(1, int(son_dakika))))
    return qs


def _context_quiz_attempt_qs(*, user, dokuman=None, gun: int | None = None):
    if BossDeneme is None:
        return None

    qs = BossDeneme.objects.filter(kullanici=user)
    if dokuman is not None:
        qs = qs.filter(soru__context_doc_id=getattr(dokuman, "id", dokuman))
    if gun:
        qs = qs.filter(olusturuldu__gte=timezone.now() - timedelta(days=max(1, int(gun))))
    return qs


def context_quiz_attempt_qs(*, user, dokuman=None, gun: int | None = None):
    return _context_quiz_attempt_qs(user=user, dokuman=dokuman, gun=gun)


def context_boss_attempt_qs(*, user, dokuman=None, gun: int | None = None):
    return _context_quiz_attempt_qs(user=user, dokuman=dokuman, gun=gun)


def _primary_parca(*, parca=None, not_obj=None, portal_not=None):
    return parca or getattr(not_obj, "parca", None) or getattr(portal_not, "parca", None)


def _primary_text(*, parca=None, not_obj=None, portal_not=None) -> str:
    return (
        getattr(not_obj, "metin", "")
        or getattr(portal_not, "icerik", "")
        or getattr(parca, "metin", "")
        or ""
    )


def _primary_meta(*, parca=None, not_obj=None, portal_not=None) -> dict:
    active_parca = _primary_parca(parca=parca, not_obj=not_obj, portal_not=portal_not)
    return dict(getattr(active_parca, "meta", {}) or {})


def _technical_density(text: str) -> float:
    clean = str(text or "").strip()
    if not clean:
        return 0.0

    tokens = re.findall(r"[A-Za-z0-9_%=()/+\-*.]+", clean)
    if not tokens:
        return 0.0

    technical_hits = 0
    for token in tokens:
        if re.search(r"\d", token):
            technical_hits += 1
            continue
        if re.search(r"[=/%()<>+\-*]", token):
            technical_hits += 1
            continue
        if re.fullmatch(r"[A-Z0-9_]{2,}", token):
            technical_hits += 1

    return _clamp01(technical_hits / max(1, len(tokens)))


def _fact_density(text: str) -> float:
    clean = str(text or "").strip()
    if not clean:
        return 0.0

    tokens = re.findall(r"[A-Za-z0-9_%=()/+\-*.]+", clean)
    if not tokens:
        return 0.0

    fact_hits = 0
    for token in tokens:
        if re.search(r"\d", token):
            fact_hits += 1
            continue
        if re.fullmatch(r"[A-Z0-9_]{2,}", token):
            fact_hits += 1
            continue
        if len(token) >= 7:
            fact_hits += 0.5

    sentence_like_bonus = min(len(re.findall(r"[.!?;:]", clean)), 4) * 0.06
    return _clamp01((fact_hits / max(1, len(tokens))) + sentence_like_bonus)


def _length_bonus(text: str, *, sweet_min: int, sweet_max: int, hard_limit: int) -> float:
    length = len(str(text or "").strip())
    if length <= 0:
        return 0.0
    if sweet_min <= length <= sweet_max:
        return 1.0
    if length < sweet_min:
        return _clamp01(length / max(1, sweet_min))
    if length >= hard_limit:
        return 0.18
    remaining = max(1, hard_limit - sweet_max)
    return _clamp01(1.0 - ((length - sweet_max) / remaining) * 0.82)


def compute_confusion_map_score(*, user, dokuman=None, parca=None) -> dict:
    anlamadim_qs = AnlamadimKaydi.objects.filter(kullanici=user)
    if dokuman is not None:
        anlamadim_qs = anlamadim_qs.filter(dokuman=dokuman)
    if parca is not None:
        anlamadim_qs = anlamadim_qs.filter(parca=parca)
    anlamadim_qs = anlamadim_qs.filter(olusturuldu__gte=timezone.now() - timedelta(days=60))
    anlamadim_sayisi = anlamadim_qs.count()
    anlamadim_ratio = _normalized_count(anlamadim_sayisi, 3)

    anlamadim_metricleri = list(
        _context_metric_qs(
            user=user,
            dokuman=dokuman,
            parca=parca,
            olay_turu="ai2_anlamadim_degerlendirildi",
            gun=60,
        )[:24]
    )
    eksik_yanit_sayisi = sum(
        1
        for kayit in anlamadim_metricleri
        if _safe_metric_number(kayit.skor_ozeti, "completeness_score") < 0.55
        or _safe_metric_bool(kayit.skor_ozeti, "fallback_json_kullanildi")
    )
    incomplete_ratio = _bounded_ratio(eksik_yanit_sayisi, max(len(anlamadim_metricleri), 3), fallback=0.0)

    cevap_metricleri = list(
        _context_metric_qs(
            user=user,
            dokuman=dokuman,
            parca=parca,
            olay_turu="ai2_cevap_degerlendirildi",
            gun=60,
        )[:24]
    )
    riskli_cevap_sayisi = sum(
        1
        for kayit in cevap_metricleri
        if not bool((kayit.skor_ozeti or {}).get("supported", True))
        or _safe_metric_number(kayit.skor_ozeti, "hallucination_risk") >= 0.6
    )
    risky_answer_ratio = _bounded_ratio(riskli_cevap_sayisi, max(len(cevap_metricleri), 3), fallback=0.0)

    tekrar_bakma_sayisi = _context_metric_qs(
        user=user,
        dokuman=dokuman,
        parca=parca,
        gun=30,
    ).filter(
        olay_turu__in=["study_summary_uretildi", "cheatsheet_export_uretildi", "feedback_verildi"]
    ).count()
    revisit_ratio = _normalized_count(max(0, tekrar_bakma_sayisi - 1), 4)

    feedback_qs = _context_feedback_qs(
        user=user,
        dokuman=dokuman,
        parca=parca,
    )
    olumsuz_feedback_sayisi = feedback_qs.filter(feedback_turu__in=["eksik", "kotu", "alakasiz"]).count()
    negative_feedback_ratio = _bounded_ratio(olumsuz_feedback_sayisi, max(feedback_qs.count(), 2), fallback=0.0)

    feedback_metricleri = list(
        _context_metric_qs(
            user=user,
            dokuman=dokuman,
            parca=parca,
            olay_turu="feedback_verildi",
            gun=45,
        )[:16]
    )
    high_dwell_count = sum(
        1
        for kayit in feedback_metricleri
        if _safe_metric_number(kayit.skor_ozeti, "read_ratio") >= 1.15
        or _safe_metric_number(kayit.skor_ozeti, "observed_read_seconds") >= 20.0
    )
    high_dwell_ratio = _bounded_ratio(high_dwell_count, max(len(feedback_metricleri), 3), fallback=0.0)

    metric_result_events = list(
        _context_metric_qs(
            user=user,
            dokuman=dokuman,
            parca=parca,
            gun=90,
        ).filter(olay_turu__in=["mini_quiz_sonuclandi", "boss_deneme_tamamlandi"])[:16]
    )
    metric_result_ratios = []
    for kayit in metric_result_events:
        sonuc_orani = _safe_metric_number(kayit.skor_ozeti, "sonuc_orani")
        if sonuc_orani <= 0.0:
            sonuc_orani = _bounded_ratio(
                _safe_metric_number(kayit.skor_ozeti, "dogru_sayisi"),
                _safe_metric_number(kayit.skor_ozeti, "toplam_soru"),
            )
        metric_result_ratios.append(_clamp01(sonuc_orani))

    quiz_fail_ratio = 1.0 - _safe_avg(metric_result_ratios) if metric_result_ratios else 0.0
    quiz_attempt_qs = _context_quiz_attempt_qs(user=user, dokuman=dokuman, gun=90)
    if quiz_attempt_qs is not None:
        quiz_attempts = list(quiz_attempt_qs.order_by("-olusturuldu")[:12])
        if quiz_attempts:
            boss_fail_ratio = _bounded_ratio(
                sum(1 for deneme in quiz_attempts if not bool(getattr(deneme, "dogru_mu", False))),
                len(quiz_attempts),
            )
            quiz_fail_ratio = _safe_avg([quiz_fail_ratio, boss_fail_ratio] if metric_result_ratios else [boss_fail_ratio])

    skor = _clamp01(
        anlamadim_ratio * 0.32
        + incomplete_ratio * 0.14
        + risky_answer_ratio * 0.18
        + quiz_fail_ratio * 0.18
        + revisit_ratio * 0.10
        + high_dwell_ratio * 0.05
        + negative_feedback_ratio * 0.03
    )

    if quiz_fail_ratio >= 0.45:
        reason = "quiz_fail_yogunlugu"
    elif riskli_cevap_sayisi:
        reason = "riskli_cevap_yogunlugu"
    elif eksik_yanit_sayisi:
        reason = "eksik_aciklama_tekrari"
    elif anlamadim_sayisi >= 2:
        reason = "anlamadim_tekrari"
    elif tekrar_bakma_sayisi >= 3:
        reason = "tekrar_bakma_proxysi"
    else:
        reason = "dusuk_karisiklik"

    return {
        "confusion_map_score": round(skor, 4),
        "confusion_reason": reason,
        "confusion_incomplete_ratio": round(incomplete_ratio, 4),
        "confusion_quiz_fail_ratio": round(quiz_fail_ratio, 4),
        "confusion_revisit_ratio": round(revisit_ratio, 4),
        "confusion_high_dwell_ratio": round(high_dwell_ratio, 4),
    }


def compute_mastery_score(*, user, dokuman=None) -> dict:
    cevap_metricleri = list(
        _context_metric_qs(
            user=user,
            dokuman=dokuman,
            olay_turu="ai2_cevap_degerlendirildi",
            gun=90,
        )[:40]
    )
    anlamadim_metricleri = list(
        _context_metric_qs(
            user=user,
            dokuman=dokuman,
            olay_turu="ai2_anlamadim_degerlendirildi",
            gun=90,
        )[:40]
    )

    usefulness_ort = _safe_avg(
        _safe_metric_number(kayit.skor_ozeti, "usefulness_score_v2")
        for kayit in cevap_metricleri
    )
    completeness_ort = _safe_avg(
        _safe_metric_number(kayit.skor_ozeti, "completeness_score")
        for kayit in anlamadim_metricleri
    )
    confusion_meta = compute_confusion_map_score(user=user, dokuman=dokuman)
    confusion_score = confusion_meta["confusion_map_score"]
    tekrar_cezasi = min(
        _context_metric_qs(
            user=user,
            dokuman=dokuman,
            gun=30,
        ).filter(olay_turu__in=["study_summary_uretildi", "ai2_anlamadim_degerlendirildi"]).count(),
        8,
    ) * 0.018

    metric_quiz_attempts = list(
        _context_metric_qs(
            user=user,
            dokuman=dokuman,
            gun=120,
        ).filter(olay_turu__in=["mini_quiz_sonuclandi", "boss_deneme_tamamlandi"])[:20]
    )
    metric_quiz_ratios = []
    for kayit in metric_quiz_attempts:
        sonuc_orani = _safe_metric_number(kayit.skor_ozeti, "sonuc_orani")
        if sonuc_orani <= 0.0:
            toplam = _safe_metric_number(kayit.skor_ozeti, "toplam_soru")
            dogru = _safe_metric_number(kayit.skor_ozeti, "dogru_sayisi")
            sonuc_orani = _bounded_ratio(dogru, toplam)
        metric_quiz_ratios.append(_clamp01(sonuc_orani))

    quiz_success_ratio = _safe_avg(metric_quiz_ratios) if metric_quiz_ratios else 0.45
    quiz_attempt_qs = _context_quiz_attempt_qs(user=user, dokuman=dokuman, gun=120)
    if quiz_attempt_qs is not None:
        quiz_attempts = list(quiz_attempt_qs.order_by("-olusturuldu")[:16])
        if quiz_attempts:
            boss_quiz_ratio = _bounded_ratio(
                sum(1 for deneme in quiz_attempts if bool(getattr(deneme, "dogru_mu", False))),
                len(quiz_attempts),
                fallback=0.45,
            )
            quiz_success_ratio = _safe_avg([quiz_success_ratio, boss_quiz_ratio] if metric_quiz_ratios else [boss_quiz_ratio])

    skor = _clamp01(
        0.18
        + usefulness_ort * 0.22
        + completeness_ort * 0.18
        + quiz_success_ratio * 0.22
        + (1.0 - confusion_score) * 0.20
        - tekrar_cezasi
    )

    if skor >= 0.74:
        reason = "istikrarli_hakimiyet"
    elif confusion_score >= 0.45:
        reason = "karisiklik_masteryi_dusuruyor"
    elif quiz_success_ratio < 0.42:
        reason = "quiz_performansi_dusuk"
    elif usefulness_ort < 0.45:
        reason = "yanit_faydasi_dusuk"
    else:
        reason = "gelisen_hakimiyet"

    return {
        "mastery_score": round(skor, 4),
        "mastery_reason": reason,
        "mastery_quiz_success_ratio": round(quiz_success_ratio, 4),
        "mastery_usefulness_avg": round(usefulness_ort, 4),
        "mastery_repeat_penalty": round(tekrar_cezasi, 4),
    }


def compute_mastery_progress_delta(*, old_score: float, new_score: float) -> dict:
    delta = round(float(new_score or 0.0) - float(old_score or 0.0), 4)
    if delta > 0.15:
        reason = "strong_gain"
    elif delta > 0.03:
        reason = "steady_gain"
    elif delta < -0.08:
        reason = "regression"
    else:
        reason = "flat_progress"
    return {
        "mastery_progress_delta": delta,
        "mastery_delta_reason": reason,
        "micro_feedback": "Harika gidiyorsun." if delta > 0.15 else "",
    }


def compute_learning_momentum_score(*, user) -> dict:
    recent_qs = _context_metric_qs(user=user, gun=7)
    active_days = {
        timezone.localtime(item.created_at).date()
        for item in recent_qs.filter(
            olay_turu__in=[
                "mini_quiz_sonuclandi",
                "boss_deneme_tamamlandi",
                "mastery_delta_hesaplandi",
                "study_summary_uretildi",
                "feedback_verildi",
            ]
        )[:128]
    }
    today = timezone.localdate()
    streak_days = 0
    while (today - timedelta(days=streak_days)) in active_days:
        streak_days += 1

    positive_delta_sum = 0.0
    for kayit in _context_metric_qs(
        user=user,
        olay_turu="mastery_delta_hesaplandi",
        gun=3,
    )[:24]:
        positive_delta_sum += max(0.0, _safe_metric_number(kayit.skor_ozeti, "mastery_progress_delta"))

    score = _clamp01(
        0.3 * min(streak_days / 7.0, 1.0)
        + 0.7 * positive_delta_sum
    )
    if score >= 0.8:
        reason = "on_fire"
    elif positive_delta_sum >= 0.18:
        reason = "delta_driven"
    elif streak_days >= 3:
        reason = "streak_driven"
    else:
        reason = "low_momentum"
    return {
        "learning_momentum_score": round(score, 4),
        "momentum_reason": reason,
        "streak_days": int(streak_days),
        "positive_delta_sum": round(positive_delta_sum, 4),
    }


def compute_boss_difficulty_score(*, user, dokuman=None, retry_count: int | None = None) -> dict:
    mastery_meta = compute_mastery_score(user=user, dokuman=dokuman)
    momentum_meta = compute_learning_momentum_score(user=user)
    if retry_count is None:
        retry_events = _context_metric_qs(
            user=user,
            dokuman=dokuman,
            olay_turu="boss_deneme_tamamlandi",
            gun=180,
        )[:24]
        retry_count = sum(
            1
            for kayit in retry_events
            if max(
                _safe_metric_number(kayit.skor_ozeti, "boss_progress_score"),
                _safe_metric_number(kayit.skor_ozeti, "sonuc_orani"),
            ) < 0.85
        )
    retry_penalty = min(int(retry_count or 0), 4)
    score = _clamp01(
        mastery_meta["mastery_score"] * 0.6
        + momentum_meta["learning_momentum_score"] * 0.4
        - retry_penalty * 0.15
    )
    if score < 0.4:
        band = "easy"
        instruction = "Kolay mod: daha yuzeysel, secmeli ve guven verici sorular kullan."
    elif score < 0.7:
        band = "medium"
        instruction = "Orta mod: kavram eslestirme ve bosluk doldurma agirlikli ilerle."
    else:
        band = "hard"
        instruction = "Hardcore mod: yoruma dayali, acik uclu ve zorlayici sorular sor."
    return {
        "boss_difficulty_score": round(score, 4),
        "boss_difficulty_band": band,
        "boss_retry_count": retry_penalty,
        "boss_instruction": instruction,
        "mastery_score": mastery_meta["mastery_score"],
        "learning_momentum_score": momentum_meta["learning_momentum_score"],
    }


def compute_boss_progress_score(*, dogru_sayisi: int, toplam_soru: int, ipucu_sayisi: int = 0) -> dict:
    ratio = _bounded_ratio(dogru_sayisi, toplam_soru)
    score = _clamp01(ratio - (0.1 * max(int(ipucu_sayisi or 0), 0)))
    if score > 0.85:
        outcome = "boss_defeated"
        reason = "great_win"
    elif score < 0.40:
        outcome = "return_to_study"
        reason = "needs_more_study"
    else:
        outcome = "in_progress"
        reason = "partial_progress"
    return {
        "boss_progress_score": round(score, 4),
        "boss_outcome": outcome,
        "boss_progress_reason": reason,
        "sonuc_orani": round(ratio, 4),
        "ipucu_sayisi": int(ipucu_sayisi or 0),
    }


def compute_confusion_recovery_score(
    *,
    user,
    dokuman=None,
    parca=None,
    quiz_score: float,
    confusion_map_score: float | None = None,
) -> dict:
    confusion_score = _clamp01(
        confusion_map_score
        if confusion_map_score is not None
        else compute_confusion_map_score(user=user, dokuman=dokuman, parca=parca)["confusion_map_score"]
    )
    recovery_score = _clamp01(confusion_score * _clamp01(quiz_score))
    if recovery_score > 0.6:
        reason = "eureka"
    elif confusion_score >= 0.5 and quiz_score >= 0.5:
        reason = "recovering"
    else:
        reason = "limited_recovery"
    return {
        "confusion_recovery_score": round(recovery_score, 4),
        "recovery_reason": reason,
        "eureka_triggered": recovery_score > 0.6,
        "confusion_map_score": round(confusion_score, 4),
    }


def compute_reward_priority_score(
    *,
    recovery_score: float,
    momentum_score: float,
    boss_kill: bool,
) -> dict:
    score = _clamp01(
        (0.4 if boss_kill else 0.0)
        + 0.3 * _clamp01(recovery_score)
        + 0.3 * _clamp01(momentum_score)
    )
    if score > 0.8:
        reason = "rare_badge_ready"
    elif boss_kill:
        reason = "boss_reward_priority"
    elif recovery_score > momentum_score:
        reason = "recovery_reward_priority"
    else:
        reason = "momentum_reward_priority"
    return {
        "reward_priority_score": round(score, 4),
        "reward_priority_reason": reason,
    }


def compute_feedback_weight_score(
    *,
    user,
    dokuman=None,
    parca=None,
    feedback_turu: str = "",
    kisa_not_uzunlugu: int = 0,
    okuma_suresi_saniye: float | int | None = None,
    beklenen_okuma_suresi_saniye: float | int | None = None,
) -> dict:
    yakin_feedback_sayisi = _context_feedback_qs(
        user=user,
        dokuman=dokuman,
        parca=parca,
        son_dakika=10,
    ).count()
    mastery_meta = compute_mastery_score(user=user, dokuman=dokuman)
    mastery_score = mastery_meta["mastery_score"]
    recent_usefulness = _safe_avg(
        _safe_metric_number(kayit.skor_ozeti, "usefulness_score_v2")
        for kayit in _context_metric_qs(
            user=user,
            dokuman=dokuman,
            olay_turu="ai2_cevap_degerlendirildi",
            gun=90,
        )[:20]
    )

    speed_meta = compute_feedback_read_weight(
        text=("x " * max(int(kisa_not_uzunlugu or 0), 8)).strip(),
        dwell_seconds=okuma_suresi_saniye,
        user_reputation=0.5,
    )
    try:
        expected_seconds = max(float(beklenen_okuma_suresi_saniye or 0.0), 0.0)
    except Exception:
        expected_seconds = 0.0
    if expected_seconds > 0:
        observed_seconds = max(float(okuma_suresi_saniye or 0.0), 0.0)
        speed_score = _bounded_ratio(observed_seconds, max(expected_seconds * 0.8, 1.0), fallback=0.0)
    else:
        speed_score = float(speed_meta["feedback_weight_score"])

    baglam_bonus = 0.06 if (dokuman is not None or parca is not None) else 0.0
    not_bonus = 0.08 if kisa_not_uzunlugu >= 14 else (0.04 if kisa_not_uzunlugu >= 5 else 0.0)
    spam_cezasi = min(max(0, yakin_feedback_sayisi - 1), 6) * 0.10
    hiz_cezasi = 0.18 if speed_score < 0.25 else (0.08 if speed_score < 0.5 else 0.0)
    alakasiz_cezasi = 0.04 if str(feedback_turu or "").strip() == "alakasiz" and kisa_not_uzunlugu < 8 else 0.0

    skor = _clamp01(
        0.42
        + mastery_score * 0.15
        + recent_usefulness * 0.10
        + baglam_bonus
        + not_bonus
        + speed_score * 0.12
        - spam_cezasi
        - hiz_cezasi
        - alakasiz_cezasi
    )

    if yakin_feedback_sayisi >= 4:
        reason = "burst_feedback"
    elif speed_score < 0.25:
        reason = "too_fast_feedback"
    elif kisa_not_uzunlugu < 5:
        reason = "low_context_feedback"
    elif mastery_score >= 0.68:
        reason = "trusted_feedback"
    else:
        reason = "standard_feedback"

    return {
        "feedback_weight_score": round(skor, 4),
        "feedback_weight_reason": reason,
        "feedback_speed_score": round(speed_score, 4),
        "feedback_spam_penalty": round(spam_cezasi, 4),
        "feedback_context_bonus": round(baglam_bonus + not_bonus, 4),
    }


def compute_quiz_readiness_score(
    *,
    parca=None,
    text: str | None = None,
    quality_score: float | None = None,
    difficulty_score: float | None = None,
    weak_content: bool | None = None,
) -> dict:
    meta = _primary_meta(parca=parca)
    resolved_text = str(text if text is not None else _primary_text(parca=parca) or "").strip()
    resolved_quality = _clamp01(
        quality_score
        if quality_score is not None
        else max(
            _safe_metric_number(meta, "quality_score"),
            _safe_metric_number(meta, "ocr_quality_score"),
        )
    )
    resolved_difficulty = _clamp01(
        difficulty_score
        if difficulty_score is not None
        else max(
            _safe_metric_number(meta, "difficulty_score"),
            _safe_metric_number(meta, "zorluk_skoru"),
            float(getattr(parca, "zorluk_skoru", 0.0) or 0.0),
        )
    )
    weak = bool(meta.get("weak_content")) if weak_content is None else bool(weak_content)
    fact_density = _fact_density(resolved_text)
    length_fit = _length_bonus(resolved_text, sweet_min=80, sweet_max=420, hard_limit=900)
    if resolved_quality <= 0.0 and not weak and len(resolved_text) >= 60:
        resolved_quality = max(resolved_quality, 0.42 if fact_density >= 0.12 else 0.30)
    if resolved_difficulty <= 0.0 and len(resolved_text) >= 60:
        resolved_difficulty = max(resolved_difficulty, 0.28 if fact_density >= 0.12 else 0.18)
    short_penalty = 0.20 if 0 < len(resolved_text) < 24 else (0.08 if 24 <= len(resolved_text) < 48 else 0.0)
    weak_penalty = 0.22 if weak else 0.0
    score = _clamp01(
        resolved_quality * 0.30
        + resolved_difficulty * 0.16
        + fact_density * 0.30
        + length_fit * 0.16
        + (0.08 if not weak else 0.0)
        - short_penalty
        - weak_penalty
    )

    if weak:
        reason = "weak_content"
    elif len(resolved_text) < 48:
        reason = "too_short_for_quiz"
    elif fact_density < 0.18:
        reason = "low_fact_density"
    elif score >= 0.30:
        reason = "quiz_ready"
    else:
        reason = "borderline_quiz"

    return {
        "quiz_readiness_score": round(score, 4),
        "quiz_reason": reason,
        "quiz_eligible": score >= 0.30 and not weak and len(resolved_text) >= 24,
    }


def compute_study_summary_importance_score(
    *,
    user=None,
    dokuman=None,
    parca=None,
    not_obj=None,
    portal_not=None,
    confusion_map_score: float | None = None,
) -> dict:
    active_parca = _primary_parca(parca=parca, not_obj=not_obj, portal_not=portal_not)
    meta = _primary_meta(parca=parca, not_obj=not_obj, portal_not=portal_not)
    text = _primary_text(parca=parca, not_obj=not_obj, portal_not=portal_not)

    quality_score = max(
        _safe_metric_number(meta, "quality_score"),
        _safe_metric_number(meta, "ocr_quality_score"),
    )
    difficulty_score = max(
        _safe_metric_number(meta, "difficulty_score"),
        _safe_metric_number(meta, "zorluk_skoru"),
        float(getattr(active_parca, "zorluk_skoru", 0.0) or 0.0),
    )
    heading_score = _safe_metric_number(meta, "heading_score")
    confusion_score = _clamp01(confusion_map_score if confusion_map_score is not None else 0.0)
    rerank_score = max(
        _safe_metric_number(meta, "final_rerank"),
        _safe_metric_number(meta, "final_rerank_avg"),
    )
    source_count = len(getattr(not_obj, "kaynak_parca_idleri", []) or [])
    pinned_bonus = 0.10 if bool(getattr(not_obj, "pinned", False) or getattr(portal_not, "pinned", False)) else 0.0
    density_bonus = _technical_density(text) * 0.08
    weak_penalty = 0.10 if bool(meta.get("weak_content")) else 0.0
    usage_bonus = 0.0
    target_dokuman = dokuman or getattr(active_parca, "dokuman", None)
    if user is not None and target_dokuman is not None:
        usage_count = _context_metric_qs(
            user=user,
            dokuman=target_dokuman,
            parca=active_parca,
            gun=90,
        ).filter(
            olay_turu__in=[
                "ai2_anlamadim_degerlendirildi",
                "study_summary_uretildi",
                "cheatsheet_export_uretildi",
                "feedback_verildi",
            ]
        ).count()
        usage_bonus = _normalized_count(usage_count, 5) * 0.12

    skor = _clamp01(
        quality_score * 0.22
        + difficulty_score * 0.16
        + heading_score * 0.14
        + confusion_score * 0.18
        + rerank_score * 0.12
        + min(source_count, 3) * 0.04
        + pinned_bonus
        + density_bonus
        + usage_bonus
        - weak_penalty
    )

    if confusion_score >= 0.45:
        reason = "confusion_driven_priority"
    elif usage_bonus >= 0.08:
        reason = "historical_usage_priority"
    elif pinned_bonus or source_count >= 2:
        reason = "note_anchor_priority"
    elif quality_score + difficulty_score + rerank_score >= 1.2:
        reason = "quality_difficulty_priority"
    else:
        reason = "balanced_priority"

    return {
        "study_summary_importance_score": round(skor, 4),
        "study_summary_importance_reason": reason,
    }


def compute_cheatsheet_priority_score(*, parca=None, not_obj=None, portal_not=None) -> dict:
    meta = _primary_meta(parca=parca, not_obj=not_obj, portal_not=portal_not)
    text = _primary_text(parca=parca, not_obj=not_obj, portal_not=portal_not)

    quality_score = max(
        _safe_metric_number(meta, "quality_score"),
        _safe_metric_number(meta, "ocr_quality_score"),
    )
    tech_density = _technical_density(text)
    length_bonus = _length_bonus(text, sweet_min=24, sweet_max=180, hard_limit=520)
    formula_hits = len(re.findall(r"[=/%()<>]|\b[A-Z0-9_]{2,}\b", text or ""))
    number_hits = len(re.findall(r"\b\d+(?:[.,]\d+)?\b", text or ""))
    formula_bonus = _clamp01((formula_hits + min(number_hits, 3)) / 4.0) * 0.20
    weak_penalty = 0.18 if bool(meta.get("weak_content")) else 0.0

    skor = _clamp01(
        quality_score * 0.22
        + tech_density * 0.32
        + length_bonus * 0.22
        + formula_bonus
        - weak_penalty
    )

    if weak_penalty:
        reason = "weak_content_penalty"
    elif tech_density >= 0.35:
        reason = "technical_dense_priority"
    elif length_bonus >= 0.8:
        reason = "short_dense_priority"
    else:
        reason = "balanced_priority"

    return {
        "cheatsheet_priority_score": round(skor, 4),
        "cheatsheet_priority_reason": reason,
    }


def guvenli_metrik_kaydi_olustur(
    *,
    kullanici,
    olay_turu: str,
    kaynak_modul: str,
    dokuman=None,
    parca=None,
    ilgili_not_id: int | None = None,
    ilgili_portal_not_id: int | None = None,
    ilgili_feedback_id: int | None = None,
    skor_ozeti: dict | None = None,
    durum: str = "ok",
):
    if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
        return None

    # Uretim kaydina ham icerik sokmuyoruz; yalnizca guvenli ozet ve sayisal sinyal sakliyoruz.
    try:
        return MetrikKaydi.objects.create(
            kullanici=kullanici,
            dokuman=dokuman,
            parca=parca,
            ilgili_not_id=ilgili_not_id,
            ilgili_portal_not_id=ilgili_portal_not_id,
            ilgili_feedback_id=ilgili_feedback_id,
            olay_turu=str(olay_turu or "").strip()[:64],
            kaynak_modul=str(kaynak_modul or "").strip()[:64],
            skor_ozeti=_safe_metric_summary(skor_ozeti),
            durum=str(durum or "ok").strip()[:32] or "ok",
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "Metric store write skipped for olay_turu=%s kaynak_modul=%s error_type=%s",
            str(olay_turu or "").strip()[:64],
            str(kaynak_modul or "").strip()[:64],
            type(exc).__name__,
        )
        return None


def kaydet_skor_olayi(
    *,
    kullanici,
    olay_turu: str,
    kaynak_modul: str,
    dokuman=None,
    parca=None,
    score_map: dict | None = None,
    durum: str = "ok",
):
    return guvenli_metrik_kaydi_olustur(
        kullanici=kullanici,
        olay_turu=olay_turu,
        kaynak_modul=kaynak_modul,
        dokuman=dokuman,
        parca=parca,
        skor_ozeti=_safe_metric_summary(score_map),
        durum=durum,
    )
