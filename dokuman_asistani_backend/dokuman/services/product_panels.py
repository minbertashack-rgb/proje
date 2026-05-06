from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from dokuman.models import DokumanNotu, KullaniciTercih, MetrikKaydi, Not
from dokuman.services.achievement_runtime import build_metric_reward_snapshot, compute_metric_streak
from dokuman.services.personalization_hints import build_personalization_hints_payload

SAFE_TEMALAR = {choice[0] for choice in getattr(KullaniciTercih, "TEMA_CHOICES", [])}
SAFE_TONLAR = {choice[0] for choice in getattr(KullaniciTercih, "TON_CHOICES", [])}
PANEL_SCORE_HOOK_CONTRACTS = {
    "boss_rush_readiness_score": {
        "context_fields": ["doc_id", "boss_adayi_sayisi", "ortalama_zorluk", "legacy_score"],
        "fallback_mode": "legacy_payload_score",
        "response_fields": ["hazirlik_skoru", "boss_rush_readiness_score"],
    },
    "weekly_goal_progress_score": {
        "context_fields": ["quiz_sayisi", "boss_sayisi", "ozet_sayisi", "tamamlanan_gorev_sayisi", "legacy_score"],
        "fallback_mode": "legacy_payload_score",
        "response_fields": ["tamamlanma_orani", "haftalik_ilerleme_skoru", "weekly_goal_progress_score"],
    },
    "achievement_progress_score": {
        "context_fields": ["derived_xp", "derived_level", "quiz_count", "boss_count", "boss_wins", "self_check_count", "legacy_score"],
        "fallback_mode": "latest_metric_score",
        "response_fields": ["achievement_progress_score"],
    },
    "export_readiness_score": {
        "context_fields": ["doc_id", "chunk_count", "avg_quality", "avg_heading", "table_count", "code_count", "legacy_score", "onerilen_format"],
        "fallback_mode": "legacy_payload_score",
        "response_fields": ["export_readiness_score"],
    },
    "personalization_confidence_score": {
        "context_fields": ["aktif_tema", "aktif_ton", "is_default", "legacy_score"],
        "fallback_mode": "legacy_payload_score",
        "response_fields": ["personalization_confidence", "personalization_confidence_score"],
    },
}


def clamp(val: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    return max(min_val, min(float(val or 0.0), max_val))


def _safe_div(numerator: Any, denominator: Any, *, default: float = 0.0) -> float:
    try:
        den = float(denominator or 0.0)
        if den == 0.0:
            return float(default)
        return float(numerator or 0.0) / den
    except Exception:
        return float(default)


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return float(default)


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return int(default)


def _safe_choice(value: Any, *, allowed: set[str], default: str) -> str:
    clean = str(value or "").strip()
    return clean if clean in allowed else default


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


def _safe_state(value: Any, *, default: str) -> str:
    clean = "_".join(str(value or "").strip().lower().split())
    return clean[:24] or default


def _ratio(numerator: Any, denominator: Any, *, default: float = 0.0) -> float:
    try:
        den = float(denominator or 0.0)
        if den <= 0:
            return clamp(default)
        return clamp(float(numerator or 0.0) / den)
    except Exception:
        return clamp(default)


def _norm_delta(delta: Any, *, scale: float) -> float:
    try:
        scale_val = max(float(scale or 0.0), 1e-6)
        return clamp(0.5 + (float(delta or 0.0) / (2.0 * scale_val)))
    except Exception:
        return 0.5


def _age_decay(days: Any, *, half_life_days: float, default: float = 0.5) -> float:
    try:
        day_val = max(float(days), 0.0)
    except Exception:
        return clamp(default)
    return clamp(1.0 / (1.0 + (day_val / max(float(half_life_days or 1.0), 1e-6))))


def _decay(age: Any, *, half_life: float, default: float = 1.0) -> float:
    try:
        age_val = max(float(age or 0.0), 0.0)
        half_life_val = max(float(half_life or 0.0), 1e-6)
    except Exception:
        return clamp(default)
    return clamp(2.0 ** (-(age_val / half_life_val)))


def _age_decay_seconds(seconds: Any, *, horizon_seconds: float, default: float = 0.0) -> float:
    try:
        second_val = max(float(seconds), 0.0)
    except Exception:
        return clamp(default)
    if second_val >= float(horizon_seconds or 0.0):
        return 0.0
    return clamp(1.0 - (second_val / max(float(horizon_seconds or 1.0), 1.0)))


def _score_hooks() -> dict:
    hooks = getattr(settings, "DOCVERSE_PANEL_SCORE_HOOKS", {}) or {}
    return hooks if isinstance(hooks, dict) else {}


def _score_overrides() -> dict:
    overrides = getattr(settings, "DOCVERSE_PANEL_SCORE_OVERRIDES", {}) or {}
    return overrides if isinstance(overrides, dict) else {}


def _resolve_configurable_score(score_key: str, *, fallback: float, context: dict | None = None) -> tuple[float, str]:
    safe_fallback = round(clamp(fallback), 4)
    overrides = _score_overrides()
    if score_key in overrides:
        return round(clamp(_safe_float(overrides.get(score_key), default=safe_fallback)), 4), "override"

    hook = _score_hooks().get(score_key)
    if callable(hook):
        try:
            value = hook(score_key=score_key, fallback=safe_fallback, context=dict(context or {}))
        except TypeError:
            try:
                value = hook(dict(context or {}))
            except Exception:
                value = safe_fallback
        except Exception:
            value = safe_fallback
        return round(clamp(_safe_float(value, default=safe_fallback)), 4), "hook"

    return safe_fallback, "fallback"


def _build_score_meta(
    score_key: str,
    score_value: float,
    *,
    score_status: str,
    extra_numeric: dict | None = None,
    extra_state: dict | None = None,
) -> dict:
    meta = {
        score_key: round(clamp(score_value), 4),
        "selection_state": str(score_status or "fallback")[:24],
    }
    for key, value in (extra_numeric or {}).items():
        meta[str(key)] = round(_safe_float(value), 4)
    for key, value in (extra_state or {}).items():
        meta[str(key)] = value
    return meta


def get_panel_score_hook_contracts() -> dict:
    return {
        key: {
            "context_fields": list(value["context_fields"]),
            "fallback_mode": str(value["fallback_mode"]),
            "response_fields": list(value["response_fields"]),
        }
        for key, value in PANEL_SCORE_HOOK_CONTRACTS.items()
    }


def _recent_metric_count(user, *, olay_turu: str, days: int = 7) -> int:
    since = timezone.now() - timedelta(days=max(1, int(days)))
    return MetrikKaydi.objects.filter(
        kullanici=user,
        olay_turu=olay_turu,
        created_at__gte=since,
    ).count()


def _latest_known_score(user, score_key: str, *, limit: int = 48) -> float:
    for kayit in MetrikKaydi.objects.filter(kullanici=user).order_by("-created_at", "-id")[: max(1, int(limit))]:
        value = _safe_float((kayit.skor_ozeti or {}).get(score_key), default=-1.0)
        if value >= 0.0:
            return clamp(value)
    return 0.0


def _metric_qs(*, user=None, doc=None, days: int | None = None, olay_turleri: list[str] | tuple[str, ...] | None = None):
    qs = MetrikKaydi.objects.all()
    if user is not None:
        qs = qs.filter(kullanici=user)
    if doc is not None:
        qs = qs.filter(dokuman=doc)
    if days:
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=max(1, int(days))))
    if olay_turleri:
        qs = qs.filter(olay_turu__in=list(olay_turleri))
    return qs.order_by("-created_at", "-id")


def _metric_count(*, user=None, doc=None, days: int | None = None, olay_turleri: list[str] | tuple[str, ...] | None = None) -> int:
    return int(_metric_qs(user=user, doc=doc, days=days, olay_turleri=olay_turleri).count())


def _metric_avg(*, user=None, doc=None, days: int | None = None, olay_turleri: list[str] | tuple[str, ...] | None = None, score_key: str, default: float = 0.0) -> float:
    values = []
    for kayit in _metric_qs(user=user, doc=doc, days=days, olay_turleri=olay_turleri)[:48]:
        value = _safe_float((kayit.skor_ozeti or {}).get(score_key), default=-1.0)
        if value >= 0.0:
            values.append(value)
    return round(_safe_avg(values), 4) if values else round(clamp(default), 4)


def _latest_metric_event(*, user=None, doc=None, olay_turleri: list[str] | tuple[str, ...] | None = None):
    return _metric_qs(user=user, doc=doc, olay_turleri=olay_turleri).first()


def _latest_metric_value(*, user=None, doc=None, olay_turleri: list[str] | tuple[str, ...] | None = None, score_key: str, default: float = 0.0) -> float:
    kayit = _latest_metric_event(user=user, doc=doc, olay_turleri=olay_turleri)
    if kayit is None:
        return round(clamp(default), 4)
    value = _safe_float((kayit.skor_ozeti or {}).get(score_key), default=default)
    return round(clamp(value), 4)


def _latest_event_age_days(*, user=None, doc=None, olay_turleri: list[str] | tuple[str, ...] | None = None) -> float | None:
    kayit = _latest_metric_event(user=user, doc=doc, olay_turleri=olay_turleri)
    if kayit is None:
        return None
    delta = timezone.now() - kayit.created_at
    return max(delta.total_seconds(), 0.0) / 86400.0


def _latest_event_age_seconds(*, user=None, doc=None, olay_turleri: list[str] | tuple[str, ...] | None = None) -> float | None:
    kayit = _latest_metric_event(user=user, doc=doc, olay_turleri=olay_turleri)
    if kayit is None:
        return None
    delta = timezone.now() - kayit.created_at
    return max(delta.total_seconds(), 0.0)


def _event_counter(*, user=None, days: int = 30) -> Counter[str]:
    return Counter(item.olay_turu for item in _metric_qs(user=user, days=days)[:240])


def _active_day_ratio(user, *, days: int) -> float:
    active_days = {
        timezone.localtime(item.created_at).date()
        for item in _metric_qs(user=user, days=days)[:240]
    }
    return _ratio(len(active_days), days)


def _learning_variety_ratio(user, *, days: int, event_names: tuple[str, ...]) -> float:
    active = 0
    for event_name in event_names:
        if _metric_count(user=user, days=days, olay_turleri=[event_name]) > 0:
            active += 1
    return _ratio(active, len(event_names))


def _average_metric_window(user, *, start_days_ago: int, end_days_ago: int, score_key: str) -> float:
    now = timezone.now()
    start = now - timedelta(days=max(start_days_ago, end_days_ago))
    end = now - timedelta(days=min(start_days_ago, end_days_ago))
    values = []
    for kayit in MetrikKaydi.objects.filter(
        kullanici=user,
        created_at__gte=start,
        created_at__lt=end,
    ).order_by("-created_at", "-id")[:96]:
        value = _safe_float((kayit.skor_ozeti or {}).get(score_key), default=-1.0)
        if value >= 0.0:
            values.append(value)
    return round(_safe_avg(values), 4) if values else 0.0


def _average_confusion_window(user, *, start_days_ago: int, end_days_ago: int) -> float:
    return _average_metric_window(
        user,
        start_days_ago=start_days_ago,
        end_days_ago=end_days_ago,
        score_key="confusion_map_score",
    )


def _note_activity_ratio(user, *, days: int) -> float:
    since = timezone.now() - timedelta(days=max(1, int(days)))
    note_count = Not.objects.filter(owner=user, created_at__gte=since).count()
    portal_count = DokumanNotu.objects.filter(owner=user, created_at__gte=since).count()
    export_count = _metric_count(
        user=user,
        days=days,
        olay_turleri=[
            "study_summary_uretildi",
            "cheatsheet_export_uretildi",
            "export_plan_uretildi",
            "export_manifest_v2_uretildi",
        ],
    )
    return _ratio(note_count + portal_count + export_count, 6)


def build_boss_rush_panel_payload(doc) -> dict:
    user = getattr(doc, "owner", None)
    parcalar = list(doc.parcalar.only("zorluk_skoru", "meta"))
    chunk_count = len(parcalar)
    aday_parcalar = [parca for parca in parcalar if _safe_float(getattr(parca, "zorluk_skoru", 0.0)) >= 0.60]
    aday_sayisi = len(aday_parcalar)
    ortalama_zorluk = _safe_avg(getattr(parca, "zorluk_skoru", 0.0) for parca in aday_parcalar)
    en_yuksek_zorluk = max((_safe_float(getattr(parca, "zorluk_skoru", 0.0)) for parca in parcalar), default=0.0)
    yuksek_confusion_orani = _ratio(
        sum(1 for parca in parcalar if _safe_float((getattr(parca, "meta", {}) or {}).get("confusion_map_score")) >= 0.6),
        chunk_count,
    )
    yogun_parca_orani = _ratio(
        sum(
            1
            for parca in parcalar
            if len(str(getattr(parca, "metin", "") or "").split()) >= 80
            and _safe_float((getattr(parca, "meta", {}) or {}).get("heading_score")) < 0.35
        ),
        chunk_count,
    )
    son_boss_saniye = _latest_event_age_seconds(user=user, doc=doc, olay_turleri=["boss_deneme_tamamlandi"])
    cooldown_dakika = max(_safe_float(son_boss_saniye, default=3600.0) / 60.0, 0.0) if son_boss_saniye is not None else 10_000.0
    cooldown_carpani = clamp(cooldown_dakika / 60.0) if cooldown_dakika < 60.0 else 1.0
    aday_skoru = clamp(_safe_div(aday_sayisi, 5.0))
    zorluk_skoru = clamp((0.6 * ortalama_zorluk) + (0.4 * en_yuksek_zorluk))
    ihtiyac_sinyali = clamp(yuksek_confusion_orani + (0.5 * yogun_parca_orani))
    ham_readiness = clamp((0.4 * aday_skoru) + (0.3 * zorluk_skoru) + (0.3 * ihtiyac_sinyali))
    legacy_score = 0.0 if aday_sayisi <= 0 or chunk_count <= 0 else clamp(ham_readiness * cooldown_carpani)
    resolved_score, score_status = _resolve_configurable_score(
        "boss_rush_readiness_score",
        fallback=round(legacy_score, 4),
        context={
            "doc_id": getattr(doc, "id", None),
            "boss_adayi_sayisi": aday_sayisi,
            "ortalama_zorluk": round(ortalama_zorluk, 4),
            "legacy_score": round(legacy_score, 4),
        },
    )

    zorluk_indeksi = zorluk_skoru
    zorluk_bandi = "kolay"
    if zorluk_indeksi >= 0.70:
        zorluk_bandi = "zor"
    elif zorluk_indeksi >= 0.40:
        zorluk_bandi = "orta"

    hazir_mi = resolved_score >= 0.65 and aday_sayisi >= 3
    boss_state = "ready" if hazir_mi else ("empty" if aday_sayisi <= 0 else ("cooldown" if cooldown_dakika < 60.0 else "needs_more_coverage"))
    tahmini_sure = 0 if aday_sayisi <= 0 else max(1, int(round(aday_sayisi * 2.5)))
    return {
        "hazir_mi": hazir_mi,
        "hazirlik_skoru": resolved_score,
        "boss_rush_readiness_score": resolved_score,
        "boss_adayi_sayisi": aday_sayisi,
        "tahmini_boss_rush_suresi_dk": tahmini_sure,
        "zorluk_bandi": zorluk_bandi,
        "onerilen_baslangic": "simdi" if hazir_mi else "daha_fazla_oku",
        "_meta": _build_score_meta(
            "boss_rush_readiness_score",
            resolved_score,
            score_status=score_status,
            extra_numeric={
                "arena_sayisi": aday_sayisi,
                "boss_adayi_sayisi": aday_sayisi,
                "candidate_chunk_count": aday_sayisi,
                "avg_difficulty": ortalama_zorluk,
                "peak_difficulty": en_yuksek_zorluk,
                "high_confusion_ratio": yuksek_confusion_orani,
                "short_dense_hard_ratio": yogun_parca_orani,
                "recent_boss_recency": cooldown_carpani,
                "cooldown_factor": 1.0 - cooldown_carpani if cooldown_dakika < 60.0 else 0.0,
                "cooldown_minutes": cooldown_dakika if cooldown_dakika < 10_000 else 0.0,
                "boss_difficulty_score": zorluk_skoru,
                "boss_candidate_score": aday_skoru,
                "boss_progress_score": ham_readiness,
            },
            extra_state={
                "boss_difficulty_band": _safe_state(zorluk_bandi, default="kolay"),
                "boss_rush_state": _safe_state(boss_state, default="empty"),
            },
        ),
    }


def build_weekly_progress_payload(user) -> dict:
    quiz_sayisi = _recent_metric_count(user, olay_turu="mini_quiz_sonuclandi")
    boss_sayisi = _recent_metric_count(user, olay_turu="boss_deneme_tamamlandi")
    ozet_sayisi = _recent_metric_count(user, olay_turu="study_summary_uretildi")
    self_check_sayisi = _recent_metric_count(user, olay_turu="self_check_calistirildi")
    fusion_sayisi = _recent_metric_count(user, olay_turu="concept_fusion_uretildi")
    reels_sayisi = _recent_metric_count(user, olay_turu="reels_surface_uretildi")
    streak_info = compute_metric_streak(user, days=21)
    current_streak = _safe_int((streak_info or {}).get("streak_gun"))
    streak_norm = _ratio(current_streak, 7, default=0.0)
    mastery_now = _average_metric_window(user, start_days_ago=0, end_days_ago=7, score_key="mastery_score")
    mastery_prev = _average_metric_window(user, start_days_ago=7, end_days_ago=14, score_key="mastery_score")
    mastery_delta = max(mastery_now - mastery_prev, 0.0)
    mastery_delta_norm = clamp(2.0 * mastery_delta)
    aktif_modul_sayisi = sum(
        1
        for value in (
            quiz_sayisi > 0,
            boss_sayisi > 0,
            self_check_sayisi > 0,
            ozet_sayisi > 0,
            fusion_sayisi > 0,
            reels_sayisi > 0,
        )
        if value
    )
    learning_variety = clamp(_safe_div(aktif_modul_sayisi, 4.0))
    mod_variety_ratio = _learning_variety_ratio(
        user,
        days=7,
        event_names=(
            "mini_quiz_sonuclandi",
            "boss_deneme_tamamlandi",
            "study_summary_uretildi",
            "self_check_calistirildi",
            "concept_fusion_uretildi",
            "reels_surface_uretildi",
        ),
    )
    total_events = quiz_sayisi + boss_sayisi + ozet_sayisi + self_check_sayisi + fusion_sayisi + reels_sayisi
    volume_score = clamp(_safe_div(quiz_sayisi + (2 * boss_sayisi) + (1.5 * self_check_sayisi) + (1.5 * ozet_sayisi), 10.0))

    hedefler = [
        {"kod": "quiz_hedefi", "hedef": 3, "mevcut": quiz_sayisi, "isim": "3 Mini Quiz Coz"},
        {"kod": "boss_hedefi", "hedef": 1, "mevcut": boss_sayisi, "isim": "1 Boss Yen"},
        {"kod": "ozet_hedefi", "hedef": 1, "mevcut": ozet_sayisi, "isim": "1 Ozet Cikar"},
        {"kod": "self_check_hedefi", "hedef": 1, "mevcut": self_check_sayisi, "isim": "1 Self-Check Yap"},
        {"kod": "cesitlilik_hedefi", "hedef": 2, "mevcut": aktif_modul_sayisi, "isim": "Farkli bir modul dene"},
    ]

    tamamlananlar = 0
    toplam_oran = 0.0
    eksikler = []
    for hedef in hedefler:
        oran = clamp(_safe_float(hedef["mevcut"]) / max(_safe_float(hedef["hedef"]), 1.0))
        toplam_oran += oran
        if oran >= 1.0:
            tamamlananlar += 1
        else:
            eksikler.append(hedef["isim"])

    task_completion = clamp(toplam_oran / max(len(hedefler), 1))
    legacy_score = 0.0 if total_events <= 0 else clamp((0.5 * volume_score) + (0.3 * mastery_delta_norm) + (0.2 * learning_variety))
    resolved_score, score_status = _resolve_configurable_score(
        "weekly_goal_progress_score",
        fallback=round(legacy_score, 4),
        context={
            "quiz_sayisi": quiz_sayisi,
            "boss_sayisi": boss_sayisi,
            "ozet_sayisi": ozet_sayisi,
            "tamamlanan_gorev_sayisi": tamamlananlar,
            "legacy_score": round(legacy_score, 4),
        },
    )
    weekly_state = "complete" if resolved_score >= 0.80 else ("new_user" if total_events <= 0 else "in_progress")
    if quiz_sayisi < 3:
        eksikler = ["2 Mini Quiz daha cozmelisin." if quiz_sayisi == 1 else "3 Mini Quiz hedefine ulas."]
    else:
        eksikler = []
    if aktif_modul_sayisi < 2:
        eksikler.append("Self-Check veya Fusion gibi farkli bir modul dene.")
    if ozet_sayisi < 1:
        eksikler.append("Bir calisma ozeti cikarmayi dene.")

    return {
        "haftalik_gorevler": hedefler,
        "tamamlanan_gorev_sayisi": tamamlananlar,
        "tamamlanma_orani": resolved_score,
        "sonraki_rozet": "Haftanin Bilgesi" if weekly_state == "complete" else "Ogrenci",
        "ne_eksik": eksikler,
        "haftalik_ilerleme_skoru": resolved_score,
        "weekly_goal_progress_score": resolved_score,
        "_meta": _build_score_meta(
            "weekly_goal_progress_score",
            resolved_score,
            score_status=score_status,
            extra_numeric={
                "weekly_progress_score": resolved_score,
                "quiz_count": quiz_sayisi,
                "boss_count": boss_sayisi,
                "summary_count": ozet_sayisi,
                "self_check_count": self_check_sayisi,
                "fusion_count": fusion_sayisi,
                "reels_count": reels_sayisi,
                "completed_goals": tamamlananlar,
                "task_completion": task_completion,
                "goal_volume_score": volume_score,
                "development_score": mastery_delta_norm,
                "variety_score": learning_variety,
                "current_streak_days": current_streak,
                "streak_norm": streak_norm,
                "mastery_delta_norm": mastery_delta_norm,
                "learning_variety": mod_variety_ratio,
            },
            extra_state={"weekly_goal_state": _safe_state(weekly_state, default="new_user")},
        ),
    }


def build_export_readiness_payload(doc) -> dict:
    parcalar = list(doc.parcalar.all())
    chunk_count = len(parcalar)
    if chunk_count == 0:
        resolved_score, score_status = _resolve_configurable_score(
            "export_readiness_score",
            fallback=0.0,
            context={"doc_id": getattr(doc, "id", None), "chunk_count": 0},
        )
        return {
            "pdf_hazirlik": 0.0,
            "docx_hazirlik": 0.0,
            "pptx_hazirlik": 0.0,
            "readme_hazirlik": 0.0,
            "export_readiness_score": resolved_score,
            "onerilen_format": "yok",
            "eksik_bilesenler": ["icerik"],
            "_meta": _build_score_meta(
                "export_readiness_score",
                resolved_score,
                score_status=score_status,
                extra_numeric={
                    "chunk_norm": 0.0,
                    "quality_avg": 0.0,
                    "heading_avg": 0.0,
                },
                extra_state={
                    "export_readiness_state": "missing_content",
                    "hedef_format": "yok",
                },
            ),
        }

    quality_sum = sum(_safe_float((p.meta or {}).get("quality_score")) for p in parcalar if isinstance(p.meta, dict))
    heading_sum = sum(_safe_float((p.meta or {}).get("heading_score")) for p in parcalar if isinstance(p.meta, dict))
    table_count = sum(1 for p in parcalar if p.tur == "tablo")
    code_count = sum(1 for p in parcalar if p.tur == "kod")
    image_count = sum(1 for p in parcalar if p.tur in {"gorsel", "image", "resim"})
    summary_count = _metric_count(user=getattr(doc, "owner", None), doc=doc, olay_turleri=["study_summary_uretildi"])
    export_plan_count = _metric_count(user=getattr(doc, "owner", None), doc=doc, olay_turleri=["export_plan_uretildi"])
    chunk_norm = _ratio(chunk_count, 8.0)
    avg_quality = quality_sum / chunk_count
    avg_heading = heading_sum / chunk_count
    density_score = clamp(_safe_div(_safe_avg(len(str(getattr(parca, "metin", "") or "").split()) for parca in parcalar), 80.0))
    table_flag = 1.0 if table_count > 0 else 0.0
    code_flag = 1.0 if code_count > 0 else 0.0
    image_flag = 1.0 if image_count > 0 else 0.0
    summary_flag = 1.0 if summary_count > 0 else 0.0
    presentation_plan_flag = 1.0 if export_plan_count > 0 else 0.0
    structural_variety = _ratio(len({str(getattr(parca, "tur", "") or "bolum") for parca in parcalar}), 4)
    yapi_skoru = clamp((0.6 * avg_heading) + (0.4 * avg_quality))
    hacim_skoru = chunk_norm
    temel_readiness = clamp(yapi_skoru * hacim_skoru)

    pdf_score = clamp(temel_readiness + (0.15 * summary_flag))
    docx_score = clamp(temel_readiness + (0.10 * density_score))
    pptx_score = clamp((temel_readiness * 0.8) + (0.4 * presentation_plan_flag))
    readme_score = clamp(temel_readiness + (0.4 * code_flag))

    skorlar = {
        "docx": round(docx_score, 4),
        "pptx": round(pptx_score, 4),
        "pdf": round(pdf_score, 4),
        "readme": round(readme_score, 4),
    }
    onerilen = max(skorlar, key=skorlar.get)
    if max(skorlar.values()) < 0.2:
        onerilen = "yok"
    elif len(skorlar) > 1:
        sorted_scores = sorted(skorlar.items(), key=lambda item: (-item[1], item[0]))
        if len(sorted_scores) > 1 and abs(sorted_scores[0][1] - sorted_scores[1][1]) < 0.03:
            if code_flag:
                onerilen = "readme"
            elif presentation_plan_flag:
                onerilen = "pptx"
            else:
                onerilen = "docx"
    legacy_score = round(_safe_avg(skorlar.values()), 4) if chunk_count > 0 else 0.0
    resolved_score, score_status = _resolve_configurable_score(
        "export_readiness_score",
        fallback=legacy_score,
        context={
            "doc_id": getattr(doc, "id", None),
            "chunk_count": chunk_count,
            "avg_quality": round(avg_quality, 4),
            "avg_heading": round(avg_heading, 4),
            "table_count": table_count,
            "code_count": code_count,
            "legacy_score": legacy_score,
            "onerilen_format": onerilen,
        },
    )

    eksikler = []
    if not summary_flag:
        eksikler.append("study_summary_eksik")
    if avg_heading < 0.3:
        eksikler.append("baslik_hiyerarsisi")
    if chunk_count < 3:
        eksikler.append("icerik_yetersiz")
    if pptx_score < 0.50 and not presentation_plan_flag:
        eksikler.append("sunum_yuzeyi_eksik")
    if readme_score < 0.50 and not code_flag:
        eksikler.append("readme_kaynagi_eksik")
    export_state = "ready" if resolved_score >= 0.7 and not eksikler else ("missing_content" if chunk_count <= 0 else "partial")

    return {
        "pdf_hazirlik": skorlar["pdf"],
        "docx_hazirlik": skorlar["docx"],
        "pptx_hazirlik": skorlar["pptx"],
        "readme_hazirlik": skorlar["readme"],
        "export_readiness_score": resolved_score,
        "onerilen_format": onerilen,
        "eksik_bilesenler": eksikler,
        "_meta": _build_score_meta(
            "export_readiness_score",
            resolved_score,
            score_status=score_status,
            extra_numeric={
                "chunk_norm": chunk_norm,
                "quality_avg": avg_quality,
                "heading_avg": avg_heading,
                "table_flag": table_flag,
                "code_flag": code_flag,
                "image_flag": image_flag,
                "summary_flag": summary_flag,
                "density_score": density_score,
                "presentation_plan_flag": presentation_plan_flag,
                "structural_variety": structural_variety,
                "has_presentation_plan": presentation_plan_flag,
            },
            extra_state={
                "hedef_format": _safe_state(onerilen, default="yok"),
                "export_readiness_state": _safe_state(export_state, default="partial"),
            },
        ),
    }


def build_personalization_confidence_payload(user) -> dict:
    tercih = KullaniciTercih.objects.filter(kullanici=user).first()
    aktif_tema = _safe_choice(getattr(tercih, "tema", ""), allowed=SAFE_TEMALAR, default="genel")
    aktif_ton = _safe_choice(getattr(tercih, "ton", ""), allowed=SAFE_TONLAR, default="teknik")
    metric_store_enabled = bool(getattr(settings, "DOCVERSE_METRIC_STORE_ENABLED", True))
    hints = build_personalization_hints_payload(
        user=user,
        tercih=tercih or KullaniciTercih(tema=aktif_tema, ton=aktif_ton),
        metric_store_enabled=metric_store_enabled,
    )
    olaylar = _event_counter(user=user, days=14)
    total_personalization_events = sum(
        olaylar.get(name, 0)
        for name in (
            "style_console_uretildi",
            "directors_cut_uretildi",
            "reels_surface_uretildi",
            "study_summary_uretildi",
            "self_check_calistirildi",
            "concept_fusion_uretildi",
            "mini_quiz_sonuclandi",
            "boss_deneme_tamamlandi",
            "personalization_hint_uretildi",
            "personalization_guncellendi",
        )
    )
    style_remix_usage = _ratio(olaylar.get("style_console_uretildi", 0) + olaylar.get("directors_cut_uretildi", 0), 6)
    usage_volume = _ratio(total_personalization_events, 30.0)
    is_default = aktif_tema == "genel" and aktif_ton == "teknik"
    pref_defined = 0.0 if tercih is None else 1.0
    default_flag = 1.0 if is_default else 0.0
    onerilen_tema = _safe_choice(hints.get("onerilen_tema"), allowed=SAFE_TEMALAR, default=aktif_tema)
    onerilen_ton = _safe_choice(hints.get("onerilen_ton"), allowed=SAFE_TONLAR, default=aktif_ton)
    mode_consistency = clamp(
        _safe_div(
            max(
                olaylar.get("study_summary_uretildi", 0),
                olaylar.get("self_check_calistirildi", 0),
                olaylar.get("concept_fusion_uretildi", 0),
                olaylar.get("reels_surface_uretildi", 0),
                olaylar.get("mini_quiz_sonuclandi", 0),
                olaylar.get("boss_deneme_tamamlandi", 0),
            ),
            max(total_personalization_events, 1),
        )
    )
    inferred_match = 0.0
    if onerilen_tema == aktif_tema:
        inferred_match += 0.5
    if onerilen_ton == aktif_ton:
        inferred_match += 0.5
    drift_score = clamp(1.0 - inferred_match)
    if inferred_match == 0.0:
        drift_score = 0.8
    hint_count = olaylar.get("personalization_hint_uretildi", 0)
    accepted_count = olaylar.get("personalization_guncellendi", 0)
    rejection_ratio = clamp(_safe_div(max(hint_count - accepted_count, 0), max(hint_count, 1))) if hint_count > 0 else 0.0
    behavior_alignment = clamp(1.0 - drift_score)
    accepted_suggestion_ratio = clamp(_safe_div(accepted_count, max(hint_count, 1))) if hint_count > 0 else 0.0
    override_instability = drift_score
    repeat_rejection_ratio = rejection_ratio
    if total_personalization_events < 5:
        legacy_score = clamp(_safe_div(total_personalization_events, 60.0))
    else:
        legacy_score = clamp((0.5 * usage_volume) + (0.5 * behavior_alignment) - (0.6 * rejection_ratio))
    if rejection_ratio >= 0.6:
        legacy_score = 0.0
    resolved_score, score_status = _resolve_configurable_score(
        "personalization_confidence_score",
        fallback=legacy_score,
        context={
            "aktif_tema": aktif_tema,
            "aktif_ton": aktif_ton,
            "is_default": is_default,
            "legacy_score": legacy_score,
        },
    )
    theme_margin = 0.2 if onerilen_tema != aktif_tema else 0.05
    tone_margin = 0.2 if onerilen_ton != aktif_ton else 0.05
    spam_koruma = rejection_ratio >= 0.6 or resolved_score < 0.4
    personalization_state = (
        "spam_cooldown"
        if rejection_ratio >= 0.6
        else ("default_profile" if is_default else ("low_data" if total_personalization_events < 5 else "custom_profile"))
    )

    return {
        "aktif_tema": aktif_tema,
        "aktif_ton": aktif_ton,
        "onerilen_tema": aktif_tema if spam_koruma else onerilen_tema,
        "onerilen_ton": aktif_ton if spam_koruma else onerilen_ton,
        "personalization_confidence": resolved_score,
        "personalization_confidence_score": resolved_score,
        "neden_bu_oneri": "spam_shield" if rejection_ratio >= 0.6 else ("dusuk_veri_koruma" if total_personalization_events < 5 else ("davranis_kaymasi" if drift_score >= 0.5 else "mevcut_secim_korundu")),
        "_meta": _build_score_meta(
            "personalization_confidence_score",
            resolved_score,
            score_status=score_status,
            extra_numeric={
                "pref_defined": pref_defined,
                "default_flag": default_flag,
                "data_volume": float(total_personalization_events),
                "usage_volume": usage_volume,
                "mode_consistency": mode_consistency,
                "style_remix_usage": style_remix_usage,
                "accepted_suggestion_ratio": accepted_suggestion_ratio,
                "override_instability": override_instability,
                "repeat_rejection_ratio": repeat_rejection_ratio,
                "behavior_alignment": behavior_alignment,
                "drift_score": drift_score,
                "rejection_ratio": rejection_ratio,
                "theme_margin": theme_margin,
                "tone_margin": tone_margin,
            },
            extra_state={
                "tema": aktif_tema,
                "ton": aktif_ton,
                "secondary_theme": _safe_state(onerilen_tema, default=aktif_tema),
                "personalization_state": _safe_state(personalization_state, default="default_profile"),
            },
        ),
    }


def build_achievement_progress_payload(user) -> dict:
    payload = dict(build_metric_reward_snapshot(user))
    olaylar = _event_counter(user=user, days=30)
    summary_count = int(olaylar.get("study_summary_uretildi", 0))
    fusion_count = int(olaylar.get("concept_fusion_uretildi", 0))
    current_streak = _safe_int((payload.get("streak") or {}).get("streak_gun"))
    total_learning_events = sum(
        olaylar.get(name, 0)
        for name in (
            "mini_quiz_sonuclandi",
            "boss_deneme_tamamlandi",
            "self_check_calistirildi",
            "concept_fusion_uretildi",
            "study_summary_uretildi",
            "reels_surface_uretildi",
        )
    )
    badge_targets = {
        "ilk_adim": {"summary_count": 1, "quiz_count": 1},
        "ritim_serisi": {"current_streak_days": 7},
        "quiz_istikrari": {"quiz_count": 5},
        "boss_esigi": {"boss_wins": 1},
        "master": {"boss_wins": 10, "current_streak_days": 7},
        "kavram_baglayici": {"fusion_count": 2},
    }
    current_values = {
        "summary_count": summary_count,
        "quiz_count": _safe_int(payload.get("quiz_count")),
        "boss_wins": _safe_int(payload.get("boss_wins")),
        "current_streak_days": current_streak,
        "fusion_count": fusion_count,
    }

    def _badge_progress(targets: dict) -> float:
        progresses = [clamp(_safe_div(current_values.get(key, 0), value)) for key, value in targets.items()]
        return round(_safe_avg(progresses), 4) if progresses else 0.0

    badge_progress = {badge: _badge_progress(targets) for badge, targets in badge_targets.items()}
    if total_learning_events <= 0:
        sonraki_rozet = "ilk_adim"
    else:
        incomplete = {badge: progress for badge, progress in badge_progress.items() if progress < 1.0}
        sonraki_rozet = max(sorted(incomplete), key=lambda badge: incomplete[badge]) if incomplete else "master"
    legacy_score = badge_progress.get(sonraki_rozet, 0.0)
    resolved_score, score_status = _resolve_configurable_score(
        "achievement_progress_score",
        fallback=legacy_score,
        context={
            "derived_xp": _safe_int(payload.get("derived_xp")),
            "derived_level": _safe_int(payload.get("derived_level"), default=1),
            "quiz_count": _safe_int(payload.get("quiz_count")),
            "boss_count": _safe_int(payload.get("boss_count")),
            "boss_wins": _safe_int(payload.get("boss_wins")),
            "self_check_count": _safe_int(payload.get("self_check_count")),
            "legacy_score": legacy_score,
        },
    )
    achievement_state = "new_user" if _safe_int(payload.get("derived_xp")) <= 0 else ("boss_ready" if _safe_int(payload.get("boss_wins")) > 0 else "in_progress")
    if current_streak >= 3:
        payload["reward_hint"] = "Serini bozma, yarin XP bonusun artacak."
    elif sonraki_rozet == "boss_esigi":
        payload["reward_hint"] = "Hedefe ulasmak icin 1 Boss daha yenmelisin."
    elif sonraki_rozet == "master":
        payload["reward_hint"] = "Master rozeti icin Boss ve streak hedeflerini birlikte ilerlet."
    elif sonraki_rozet == "kavram_baglayici":
        payload["reward_hint"] = "Bir fusion karti daha ureterek yeni rozete yaklas."
    elif sonraki_rozet == "ilk_adim":
        payload["reward_hint"] = "Ilk rozet icin bir ozet cikar ve mini quiz coz."
    payload["achievement_progress_score"] = resolved_score
    payload["_meta"] = _build_score_meta(
        "achievement_progress_score",
        resolved_score,
        score_status=score_status,
        extra_numeric={
            "quiz_count": _safe_int(payload.get("quiz_count")),
            "boss_count": _safe_int(payload.get("boss_count")),
            "boss_wins": _safe_int(payload.get("boss_wins")),
            "self_check_count": _safe_int(payload.get("self_check_count")),
            "current_streak_days": current_streak,
            "fusion_count": fusion_count,
            "summary_count": summary_count,
            "target_badge_progress": legacy_score,
        },
        extra_state={
            "achievement_state": _safe_state(achievement_state, default="new_user"),
            "unlock_reason_code": _safe_state(sonraki_rozet, default="ritim_serisi"),
        },
    )
    return payload
