from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.utils import timezone

from dokuman.models import Dokuman, DokumanNotu, KullaniciGeriBildirim, MetrikKaydi, Not, Parca
from dokuman.services.feature_flags import modul_acik_mi
from dokuman.services.metric_store import (
    compute_learning_momentum_score,
    compute_mastery_score,
    context_boss_attempt_qs,
)
from dokuman.services.product_panels import (
    build_achievement_progress_payload,
    build_boss_rush_panel_payload,
    build_export_readiness_payload,
    build_personalization_confidence_payload,
    build_weekly_progress_payload,
)

try:
    from oyun.models import KullaniciBasarim, OyunProfil
except Exception:
    KullaniciBasarim = None
    OyunProfil = None

USEFULNESS_EVENTS = [
    "ai2_cevap_degerlendirildi",
    "ai2_anlamadim_degerlendirildi",
]
CONFUSION_SCORE_EVENTS = [
    "ai2_cevap_degerlendirildi",
    "ai2_anlamadim_degerlendirildi",
    "study_summary_uretildi",
    "cheatsheet_export_uretildi",
    "feedback_verildi",
]
VALID_FEEDBACK_WEIGHT_MIN = 0.35
TRUSTED_FEEDBACK_WEIGHT_MIN = 0.40
LOW_USEFULNESS_THRESHOLD = 0.45
HIGH_CONFUSION_THRESHOLD = 0.55
LOW_MASTERY_THRESHOLD = 0.45
HIGH_MASTERY_THRESHOLD = 0.70
QUIZ_READY_THRESHOLD = 0.50
BOSS_ADAYI_ZORLUK_THRESHOLD = 0.70


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def _safe_ratio(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 4)


def _avg(values) -> float:
    clean = []
    for value in values or []:
        try:
            clean.append(float(value))
        except Exception:
            continue
    if not clean:
        return 0.0
    return round(sum(clean) / len(clean), 4)


def _last_n_days(days: int) -> list[str]:
    today = timezone.localdate()
    return [
        (today - timedelta(days=offset)).isoformat()
        for offset in range(max(days - 1, 0), -1, -1)
    ]


def _metric_qs(user, *, olay_turleri: list[str] | None = None, days: int | None = None):
    qs = MetrikKaydi.objects.filter(kullanici=user).select_related("dokuman", "parca").order_by(
        "-created_at",
        "-id",
    )
    if olay_turleri:
        qs = qs.filter(olay_turu__in=olay_turleri)
    if days:
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=max(days, 1)))
    return qs


def _global_metric_qs(*, olay_turleri: list[str] | None = None, days: int | None = None):
    qs = MetrikKaydi.objects.all().order_by("-created_at", "-id")
    if olay_turleri:
        qs = qs.filter(olay_turu__in=olay_turleri)
    if days:
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=max(days, 1)))
    return qs


def _safe_metric_number(score_map: dict | None, key: str) -> float:
    try:
        return float((score_map or {}).get(key) or 0.0)
    except Exception:
        return 0.0


def _doc_title(doc) -> str:
    if doc is None:
        return ""
    baslik = str(getattr(doc, "baslik", "") or "").strip()
    return baslik or f"Dokuman {doc.id}"


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


def _safe_title(value: str, *, fallback: str) -> str:
    clean = " ".join(str(value or "").split()).strip()
    if not clean:
        return fallback
    return clean[:80]


def _parca_safe_title(parca) -> str:
    meta = dict(getattr(parca, "meta", {}) or {})
    aday = (
        meta.get("heading")
        or meta.get("title")
        or meta.get("section_title")
        or meta.get("path")
        or meta.get("adres")
    )
    return _safe_title(aday, fallback=f"Parca {getattr(parca, 'id', 0)}")


def _empty_feedback_analytics(days: int) -> dict:
    return {
        "toplam_feedback": 0,
        "trusted_feedback": 0,
        "feedback_trust_ratio": 0.0,
        "feedback_turu_dagilimi": [],
        "kaynak_modul_dagilimi": [],
        "dokuman_dagilimi": [],
        "son_gun_trendi": [{"gun": gun, "adet": 0} for gun in _last_n_days(days)],
    }


def _empty_usage_summary(days: int) -> dict:
    return {
        "toplam": 0,
        "portal_not_bazli_kullanim": 0,
        "format_dagilimi": [],
        "son_gun_trendi": [{"gun": gun, "adet": 0} for gun in _last_n_days(min(days, 7))],
    }


def _metric_usage_summary(user, *, olay_turu: str, days: int = 30, enabled: bool = True) -> dict:
    if not enabled:
        return _empty_usage_summary(days)

    qs = _metric_qs(user, olay_turleri=[olay_turu], days=days)
    format_counter = Counter()
    portal_not_bazli_kullanim = 0
    gun_counter = Counter()

    for kayit in qs:
        skor_ozeti = kayit.skor_ozeti or {}
        format_value = str(skor_ozeti.get("format") or "").strip().lower()
        if format_value:
            format_counter[format_value] += 1
        if kayit.ilgili_portal_not_id is not None or bool(skor_ozeti.get("portal_not_var_mi")):
            portal_not_bazli_kullanim += 1
        gun_counter[timezone.localtime(kayit.created_at).date().isoformat()] += 1

    return {
        "toplam": qs.count(),
        "portal_not_bazli_kullanim": portal_not_bazli_kullanim,
        "format_dagilimi": [
            {"format": key, "adet": value}
            for key, value in sorted(format_counter.items())
        ],
        "son_gun_trendi": [
            {"gun": gun, "adet": gun_counter.get(gun, 0)}
            for gun in _last_n_days(min(days, 7))
        ],
    }


def _metric_average(
    user,
    *,
    olay_turleri: list[str],
    score_key: str,
    days: int = 30,
) -> float:
    values = []
    for kayit in _metric_qs(user, olay_turleri=olay_turleri, days=days):
        value = _safe_metric_number(kayit.skor_ozeti, score_key)
        if value > 0:
            values.append(value)
    return _avg(values)


def _metric_score_values(
    user,
    *,
    olay_turleri: list[str],
    score_key: str,
    days: int = 30,
) -> list[float]:
    values = []
    for kayit in _metric_qs(user, olay_turleri=olay_turleri, days=days):
        value = _safe_metric_number(kayit.skor_ozeti, score_key)
        if value > 0:
            values.append(value)
    return values


def _feedback_metric_summary(user, *, days: int = 30, enabled: bool = True) -> dict:
    if not enabled:
        return {
            "toplam": 0,
            "trusted": 0,
            "valid": 0,
            "ignored": 0,
            "quick_low_weight": 0,
            "feedback_trust_ratio": 0.0,
            "gecerli_feedback_orani": 0.0,
            "ignore_edilen_feedback_orani": 0.0,
            "hizli_oy_orani": 0.0,
        }

    total = 0
    trusted = 0
    valid = 0
    ignored = 0
    quick_low_weight = 0

    for kayit in _metric_qs(user, olay_turleri=["feedback_verildi"], days=days):
        total += 1
        skor_ozeti = kayit.skor_ozeti or {}
        weight = _safe_metric_number(skor_ozeti, "feedback_weight_score")
        ignored_flag = bool(skor_ozeti.get("feedback_ignored"))
        reason = str(skor_ozeti.get("feedback_reason") or "").strip().lower()

        if ignored_flag:
            ignored += 1
        if not ignored_flag and weight >= VALID_FEEDBACK_WEIGHT_MIN:
            valid += 1
        if not ignored_flag and weight >= TRUSTED_FEEDBACK_WEIGHT_MIN:
            trusted += 1
        if weight < VALID_FEEDBACK_WEIGHT_MIN or reason in {"burst_feedback", "low_context_feedback"}:
            quick_low_weight += 1

    return {
        "toplam": total,
        "trusted": trusted,
        "valid": valid,
        "ignored": ignored,
        "quick_low_weight": quick_low_weight,
        "feedback_trust_ratio": _safe_ratio(trusted, total),
        "gecerli_feedback_orani": _safe_ratio(valid, total),
        "ignore_edilen_feedback_orani": _safe_ratio(ignored, total),
        "hizli_oy_orani": _safe_ratio(quick_low_weight, total),
    }


def _cheatsheet_yield(user) -> float:
    qs = Parca.objects.filter(dokuman__owner=user).order_by("id")
    total = qs.count()
    if total <= 0:
        return 0.0
    cheat_count = 0
    for parca in qs:
        if bool((parca.meta or {}).get("is_cheatsheet")):
            cheat_count += 1
    return round(cheat_count / total, 4)


def _low_usefulness_ratio(user, *, days: int = 30) -> float:
    values = _metric_score_values(
        user,
        olay_turleri=USEFULNESS_EVENTS,
        score_key="usefulness_score_v2",
        days=days,
    )
    if not values:
        return 0.0
    low_count = sum(1 for value in values if value < LOW_USEFULNESS_THRESHOLD)
    return _safe_ratio(low_count, len(values))


def _build_parca_confusion_averages(user, *, days: int = 30) -> dict[int, dict]:
    parca_scores: dict[int, list[float]] = defaultdict(list)
    parca_objs: dict[int, Parca] = {}

    for kayit in _metric_qs(user, olay_turleri=CONFUSION_SCORE_EVENTS, days=days):
        if kayit.parca_id is None:
            continue
        score = _safe_metric_number(kayit.skor_ozeti, "confusion_map_score")
        if score <= 0:
            continue
        parca_scores[kayit.parca_id].append(score)
        if kayit.parca is not None:
            parca_objs[kayit.parca_id] = kayit.parca

    out = {}
    for parca_id, values in parca_scores.items():
        parca = parca_objs.get(parca_id)
        if parca is None:
            continue
        out[parca_id] = {
            "parca": parca,
            "ortalama_confusion": _avg(values),
        }
    return out


def _quiz_ready_counts(user) -> tuple[int, int]:
    total = 0
    ready = 0
    for parca in Parca.objects.filter(dokuman__owner=user).order_by("id"):
        total += 1
        meta = dict(parca.meta or {})
        if bool(meta.get("quiz_ready")) or _safe_metric_number(meta, "quiz_readiness_score") >= QUIZ_READY_THRESHOLD:
            ready += 1
    return ready, total


def build_feedback_analytics_v2(
    user,
    *,
    days: int = 7,
    dokuman_id=None,
    feedback_turu: str = "",
    kaynak_modul: str = "",
    enabled: bool = True,
) -> dict:
    if not enabled:
        return _empty_feedback_analytics(days)

    qs = KullaniciGeriBildirim.objects.filter(owner=user).order_by("-created_at", "-id")
    if dokuman_id:
        qs = qs.filter(dokuman_id=dokuman_id)
    if feedback_turu:
        qs = qs.filter(feedback_turu=feedback_turu)
    if kaynak_modul:
        qs = qs.filter(kaynak_modul=kaynak_modul)

    toplam_feedback = qs.count()
    feedback_counter = Counter(qs.values_list("feedback_turu", flat=True))
    kaynak_counter = Counter(qs.values_list("kaynak_modul", flat=True))
    dokuman_counter = Counter(
        doc_id for doc_id in qs.values_list("dokuman_id", flat=True) if doc_id is not None
    )

    since = timezone.now() - timedelta(days=max(days, 1))
    trend_qs = qs.filter(created_at__gte=since)
    trend_counter = Counter(
        timezone.localtime(created_at).date().isoformat()
        for created_at in trend_qs.values_list("created_at", flat=True)
    )
    feedback_metric = _feedback_metric_summary(user, days=max(days, 7), enabled=enabled)

    return {
        "toplam_feedback": toplam_feedback,
        "trusted_feedback": feedback_metric["trusted"],
        "feedback_trust_ratio": feedback_metric["feedback_trust_ratio"],
        "feedback_turu_dagilimi": [
            {
                "feedback_turu": key,
                "adet": value,
                "oran": _safe_ratio(value, toplam_feedback),
            }
            for key, value in sorted(feedback_counter.items())
        ],
        "kaynak_modul_dagilimi": [
            {
                "kaynak_modul": key,
                "adet": value,
                "oran": _safe_ratio(value, toplam_feedback),
            }
            for key, value in sorted(kaynak_counter.items())
        ],
        "dokuman_dagilimi": [
            {"dokuman_id": key, "adet": value}
            for key, value in sorted(dokuman_counter.items())
        ],
        "son_gun_trendi": [{"gun": gun, "adet": trend_counter.get(gun, 0)} for gun in _last_n_days(days)],
    }


def build_confusion_hotspot_analytics(
    user,
    *,
    days: int = 30,
    threshold: float = HIGH_CONFUSION_THRESHOLD,
    top_n: int = 5,
) -> dict:
    doc_stats: dict[int, dict] = {}
    parca_averages = _build_parca_confusion_averages(user, days=days)
    toplam_parca_haritasi = {
        item["dokuman_id"]: item["toplam_parca"]
        for item in Parca.objects.filter(dokuman__owner=user).values("dokuman_id").annotate(toplam_parca=Count("id"))
    }

    for data in parca_averages.values():
        parca = data["parca"]
        score = data["ortalama_confusion"]
        doc_entry = doc_stats.setdefault(
            parca.dokuman_id,
            {
                "dokuman_id": parca.dokuman_id,
                "baslik": _doc_title(parca.dokuman),
                "parca_skorlari": [],
                "yuksek_confusion_parca_sayisi": 0,
            },
        )
        doc_entry["parca_skorlari"].append(score)
        if score >= threshold:
            doc_entry["yuksek_confusion_parca_sayisi"] += 1

    dokuman_problem_yogunlugu = []
    toplam_yuksek_confusion = 0
    for dokuman_id, entry in doc_stats.items():
        toplam_parca = int(toplam_parca_haritasi.get(dokuman_id) or 0)
        yuksek_confusion = int(entry["yuksek_confusion_parca_sayisi"])
        toplam_yuksek_confusion += yuksek_confusion
        ortalama_confusion = _avg(entry["parca_skorlari"])
        problem_yogunlugu = _safe_ratio(yuksek_confusion, toplam_parca) if toplam_parca else 0.0
        problem_skoru = round(_clamp01(ortalama_confusion * 0.65 + problem_yogunlugu * 0.35), 4)
        dokuman_problem_yogunlugu.append(
            {
                "dokuman_id": dokuman_id,
                "baslik": entry["baslik"],
                "skor": problem_skoru,
                "ortalama_confusion": ortalama_confusion,
                "problem_yogunlugu": problem_yogunlugu,
                "yuksek_confusion_parca_sayisi": yuksek_confusion,
                "toplam_parca_sayisi": toplam_parca,
            }
        )

    dokuman_problem_yogunlugu.sort(key=lambda item: (-item["skor"], item["dokuman_id"]))
    return {
        "yuksek_confusion_parca_sayisi": toplam_yuksek_confusion,
        "dokuman_problem_yogunlugu": dokuman_problem_yogunlugu,
        "top_problemli_dokumanlar": [
            {
                "dokuman_id": item["dokuman_id"],
                "baslik": item["baslik"],
                "skor": item["skor"],
            }
            for item in dokuman_problem_yogunlugu[:top_n]
        ],
    }


def build_confusion_map_surface(
    user,
    *,
    days: int = 30,
    threshold: float = HIGH_CONFUSION_THRESHOLD,
    top_n: int = 5,
) -> dict:
    parca_averages = _build_parca_confusion_averages(user, days=days)
    dokuman_stats = defaultdict(lambda: {"skorlar": [], "problemli": 0, "baslik": ""})
    top_problemli = []

    for data in parca_averages.values():
        parca = data["parca"]
        score = data["ortalama_confusion"]
        dokuman_stats[parca.dokuman_id]["skorlar"].append(score)
        dokuman_stats[parca.dokuman_id]["baslik"] = _doc_title(parca.dokuman)
        if score >= threshold:
            dokuman_stats[parca.dokuman_id]["problemli"] += 1
            top_problemli.append(
                {
                    "id": parca.id,
                    "adres": getattr(parca, "adres", "") or "",
                    "baslik": _parca_safe_title(parca),
                    "kisa_skor": score,
                }
            )

    toplam_parca_haritasi = {
        item["dokuman_id"]: item["toplam_parca"]
        for item in Parca.objects.filter(dokuman__owner=user).values("dokuman_id").annotate(toplam_parca=Count("id"))
    }
    dokuman_bazli_confusion_yogunlugu = []
    for dokuman_id, stats in dokuman_stats.items():
        toplam_parca = int(toplam_parca_haritasi.get(dokuman_id) or 0)
        dokuman_bazli_confusion_yogunlugu.append(
            {
                "dokuman_id": dokuman_id,
                "baslik": stats["baslik"] or f"Dokuman {dokuman_id}",
                "confusion_yogunlugu": round(
                    _clamp01(_avg(stats["skorlar"]) * 0.7 + _safe_ratio(stats["problemli"], toplam_parca) * 0.3),
                    4,
                ),
                "problemli_parca_sayisi": int(stats["problemli"]),
            }
        )

    top_problemli.sort(key=lambda item: (-item["kisa_skor"], item["id"]))
    dokuman_bazli_confusion_yogunlugu.sort(
        key=lambda item: (-item["confusion_yogunlugu"], item["dokuman_id"])
    )
    return {
        "problemli_parca_sayisi": len(top_problemli),
        "top_problemli_parcalar": top_problemli[:top_n],
        "dokuman_bazli_confusion_yogunlugu": dokuman_bazli_confusion_yogunlugu,
    }


def build_mastery_feedback_trust_analytics(user, *, days: int = 30) -> dict:
    docs = Dokuman.objects.filter(owner=user).order_by("id")
    mastery_rows = []

    for doc in docs:
        mastery_meta = compute_mastery_score(user=user, dokuman=doc)
        mastery_rows.append(
            {
                "dokuman_id": doc.id,
                "baslik": _doc_title(doc),
                "ortalama_mastery": mastery_meta["mastery_score"],
            }
        )

    total_docs = len(mastery_rows)
    dusuk_mastery = sum(1 for item in mastery_rows if float(item["ortalama_mastery"]) < LOW_MASTERY_THRESHOLD)
    yuksek_mastery = sum(1 for item in mastery_rows if float(item["ortalama_mastery"]) >= HIGH_MASTERY_THRESHOLD)
    feedback_enabled = modul_acik_mi("DOCVERSE_FEEDBACK_ENABLED", True)
    feedback_metric = _feedback_metric_summary(user, days=days, enabled=feedback_enabled)

    return {
        "mastery_summary": {
            "ortalama_mastery": _avg(item["ortalama_mastery"] for item in mastery_rows),
            "dusuk_mastery_orani": _safe_ratio(dusuk_mastery, total_docs),
            "yuksek_mastery_orani": _safe_ratio(yuksek_mastery, total_docs),
            "dokuman_bazli_ortalama_mastery": mastery_rows,
        },
        "feedback_trust": {
            "gecerli_feedback_sayisi": feedback_metric["valid"],
            "ignore_edilen_feedback_orani": feedback_metric["ignore_edilen_feedback_orani"],
            "hizli_oy_orani": feedback_metric["hizli_oy_orani"],
            "feedback_trust_ratio": feedback_metric["feedback_trust_ratio"],
        },
    }


def build_kpi_panel(user, *, days: int = 30) -> dict:
    feedback_enabled = modul_acik_mi("DOCVERSE_FEEDBACK_ENABLED", True)
    feedback_metric = _feedback_metric_summary(user, days=days, enabled=feedback_enabled)

    return {
        "net_usefulness_score": _metric_average(
            user,
            olay_turleri=USEFULNESS_EVENTS,
            score_key="usefulness_score_v2",
            days=days,
        ),
        "global_confusion_index": _metric_average(
            user,
            olay_turleri=CONFUSION_SCORE_EVENTS,
            score_key="confusion_map_score",
            days=days,
        ),
        "feedback_trust_ratio": feedback_metric["feedback_trust_ratio"],
        "cheatsheet_yield": _cheatsheet_yield(user),
    }


def build_product_panels_kpi(user) -> dict:
    docs = list(Dokuman.objects.filter(owner=user).order_by("id")[:64])
    boss_scores = []
    export_scores = []

    for doc in docs:
        boss_payload = build_boss_rush_panel_payload(doc)
        export_payload = build_export_readiness_payload(doc)
        boss_scores.append(1.0 if bool(boss_payload.get("hazir_mi")) else 0.0)
        export_scores.append(_safe_metric_number(export_payload, "export_readiness_score"))

    weekly_payload = build_weekly_progress_payload(user)
    achievement_payload = build_achievement_progress_payload(user)
    personalization_payload = build_personalization_confidence_payload(user)

    return {
        "boss_rush_ready_ratio": _avg(boss_scores),
        "weekly_goal_completion_avg": _safe_metric_number(weekly_payload, "weekly_goal_progress_score"),
        "achievement_progress_avg": _safe_metric_number(achievement_payload, "achievement_progress_score"),
        "export_readiness_avg": _avg(export_scores),
        "personalization_confidence_avg": _safe_metric_number(
            personalization_payload,
            "personalization_confidence_score",
        ),
    }


def build_quiz_boss_surface(user, *, days: int = 30) -> dict:
    quiz_enabled = modul_acik_mi("DOCVERSE_QUIZ_ENABLED", True)
    boss_enabled = modul_acik_mi("DOCVERSE_BOSS_ENABLED", True)
    quiz_hazir_parca_sayisi, _ = _quiz_ready_counts(user) if quiz_enabled else (0, 0)

    boss_adayi_parca_sayisi = 0
    son_denemeler_ozeti = []
    basari_orani = 0.0

    if boss_enabled:
        parca_averages = _build_parca_confusion_averages(user, days=days)
        for parca in Parca.objects.filter(dokuman__owner=user).order_by("id"):
            meta = dict(parca.meta or {})
            confusion_score = float((parca_averages.get(parca.id) or {}).get("ortalama_confusion") or 0.0)
            difficulty_score = max(
                float(getattr(parca, "zorluk_skoru", 0.0) or 0.0),
                _safe_metric_number(meta, "difficulty_score"),
            )
            if difficulty_score >= BOSS_ADAYI_ZORLUK_THRESHOLD or confusion_score >= HIGH_CONFUSION_THRESHOLD:
                boss_adayi_parca_sayisi += 1

        denemeler_qs = context_boss_attempt_qs(user=user, gun=days)
        if denemeler_qs is not None:
            denemeler = list(denemeler_qs.select_related("soru", "boss").order_by("-olusturuldu")[:5])
            toplam_deneme = denemeler_qs.count()
            dogru_sayisi = denemeler_qs.filter(dogru_mu=True).count()
            basari_orani = _safe_ratio(dogru_sayisi, toplam_deneme)
            son_denemeler_ozeti = [
                {
                    "deneme_id": deneme.id,
                    "boss_id": deneme.boss_id,
                    "dokuman_id": getattr(deneme.soru, "context_doc_id", None),
                    "puan": int(getattr(deneme, "puan", 0) or 0),
                    "dogru_mu": bool(getattr(deneme, "dogru_mu", False)),
                    "olusturuldu": timezone.localtime(deneme.olusturuldu).isoformat(),
                }
                for deneme in denemeler
            ]

    return {
        "quiz_hazir_parca_sayisi": quiz_hazir_parca_sayisi,
        "boss_adayi_parca_sayisi": boss_adayi_parca_sayisi,
        "son_denemeler_ozeti": son_denemeler_ozeti,
        "basari_orani": basari_orani,
    }


def build_portal_note_study_panel(user, *, portal_not, days: int = 60) -> dict:
    metric_enabled = modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True)
    feedback_enabled = modul_acik_mi("DOCVERSE_FEEDBACK_ENABLED", True)
    study_summary_enabled = modul_acik_mi("DOCVERSE_STUDY_SUMMARY_ENABLED", True)
    cheatsheet_enabled = modul_acik_mi("DOCVERSE_CHEATSHEET_EXPORT_ENABLED", True)

    study_qs = MetrikKaydi.objects.none()
    cheatsheet_qs = MetrikKaydi.objects.none()
    feedback_qs = MetrikKaydi.objects.none()
    if metric_enabled:
        if study_summary_enabled:
            study_qs = _metric_qs(user, olay_turleri=["study_summary_uretildi"], days=days).filter(
                ilgili_portal_not_id=portal_not.id
            )
        if cheatsheet_enabled:
            cheatsheet_qs = _metric_qs(user, olay_turleri=["cheatsheet_export_uretildi"], days=days).filter(
                ilgili_portal_not_id=portal_not.id
            )
        if feedback_enabled:
            feedback_qs = _metric_qs(user, olay_turleri=["feedback_verildi"], days=days).filter(
                ilgili_portal_not_id=portal_not.id
            )

    feedback_metric = {
        "toplam_feedback": 0,
        "gecerli_feedback_orani": 0.0,
        "son_feedback_tarihi": None,
    }
    if feedback_qs.exists():
        toplam_feedback = feedback_qs.count()
        valid_feedback = sum(
            1
            for kayit in feedback_qs
            if _safe_metric_number(kayit.skor_ozeti, "feedback_weight_score") >= VALID_FEEDBACK_WEIGHT_MIN
            and not bool((kayit.skor_ozeti or {}).get("feedback_ignored"))
        )
        last_feedback = feedback_qs.first()
        feedback_metric = {
            "toplam_feedback": toplam_feedback,
            "gecerli_feedback_orani": _safe_ratio(valid_feedback, toplam_feedback),
            "son_feedback_tarihi": timezone.localtime(last_feedback.created_at).isoformat() if last_feedback else None,
        }

    son_kullanim = None
    adaylar = [item for item in [study_qs.first(), cheatsheet_qs.first()] if item is not None]
    if adaylar:
        adaylar.sort(key=lambda item: item.created_at, reverse=True)
        son_kullanim = timezone.localtime(adaylar[0].created_at).isoformat()

    return {
        "portal_not_id": portal_not.id,
        "bagli_not_sayisi": portal_not.bagli_notlar.count(),
        "kaynak_parca_sayisi": portal_not.kaynak_parcalar.count(),
        "summary_var_mi": bool(study_qs.exists()),
        "cheatsheet_var_mi": bool(cheatsheet_qs.exists()),
        "son_feedback_sinyali": feedback_metric,
        "son_kullanim_sinyali": {
            "study_summary_sayisi": int(study_qs.count()),
            "cheatsheet_export_sayisi": int(cheatsheet_qs.count()),
            "son_kullanim_tarihi": son_kullanim,
        },
    }


def build_learning_panel(user, *, days: int = 30) -> dict:
    feedback_enabled = modul_acik_mi("DOCVERSE_FEEDBACK_ENABLED", True)
    quiz_enabled = modul_acik_mi("DOCVERSE_QUIZ_ENABLED", True)
    feedback_metric = _feedback_metric_summary(user, days=days, enabled=feedback_enabled)
    quiz_ready_sayisi, toplam_parca = _quiz_ready_counts(user) if quiz_enabled else (0, 0)
    docs = Dokuman.objects.filter(owner=user).order_by("id")
    mastery_values = [compute_mastery_score(user=user, dokuman=doc)["mastery_score"] for doc in docs]

    return {
        "ortalama_confusion": _metric_average(
            user,
            olay_turleri=CONFUSION_SCORE_EVENTS,
            score_key="confusion_map_score",
            days=days,
        ),
        "ortalama_mastery": _avg(mastery_values),
        "quiz_ready_orani": _safe_ratio(quiz_ready_sayisi, toplam_parca),
        "gecerli_feedback_orani": feedback_metric["gecerli_feedback_orani"],
        "net_usefulness": _metric_average(
            user,
            olay_turleri=USEFULNESS_EVENTS,
            score_key="usefulness_score_v2",
            days=days,
        ),
    }


def build_learning_kpi(*, days: int = 30) -> dict:
    metric_qs = _global_metric_qs(days=days)
    boss_started = metric_qs.filter(olay_turu="boss_baslatildi").count()
    boss_completed_events = list(metric_qs.filter(olay_turu="boss_deneme_tamamlandi")[:400])
    boss_completed = len(boss_completed_events)
    boss_wins = sum(
        1
        for event in boss_completed_events
        if max(
            _safe_metric_number(event.skor_ozeti, "boss_progress_score"),
            _safe_metric_number(event.skor_ozeti, "sonuc_orani"),
        ) > 0.85
    )

    confusion_events = list(metric_qs.filter(olay_turu="confusion_recovery_hesaplandi")[:400])
    confusion_total = sum(
        1
        for event in confusion_events
        if _safe_metric_number(event.skor_ozeti, "confusion_map_score") > 0.5
    )
    recovered_total = sum(
        1
        for event in confusion_events
        if _safe_metric_number(event.skor_ozeti, "confusion_recovery_score") > 0.6
    )

    quiz_prompted = metric_qs.filter(olay_turu="quiz_prompted").count()
    quiz_accepted = metric_qs.filter(olay_turu="quiz_accepted").count()

    active_user_ids = list(
        metric_qs.values_list("kullanici_id", flat=True).distinct()[:120]
    )
    user_model = get_user_model()
    momentum_values = [
        compute_learning_momentum_score(user=user)["learning_momentum_score"]
        for user in user_model.objects.filter(id__in=active_user_ids)
    ]

    return {
        "boss_win_rate": _safe_ratio(boss_wins, boss_started),
        "confusion_recovery_rate": _safe_ratio(recovered_total, confusion_total),
        "quiz_engagement_ratio": _safe_ratio(quiz_accepted, quiz_prompted),
        "platform_momentum_index": _avg(momentum_values),
        "boss_started": boss_started,
        "boss_completed": boss_completed,
        "quiz_prompted": quiz_prompted,
        "quiz_accepted": quiz_accepted,
    }


def build_xp_visibility_panel(user) -> dict:
    if OyunProfil is None or KullaniciBasarim is None:
        return {
            "toplam_xp": 0,
            "seviye": 1,
            "unvan": _unvan_hesapla(1),
            "basari_sayisi": 0,
            "son_kazanilan_basari": None,
            "streak_bilgisi": {"streak_gun": 0, "son_giris_tarihi": None},
        }

    profil = OyunProfil.objects.filter(kullanici=user).first()
    toplam_xp = int(getattr(profil, "toplam_xp", 0) or 0)
    seviye = int(getattr(profil, "seviye", 0) or 0) or max(1, (toplam_xp // 100) + 1)
    basarim_qs = KullaniciBasarim.objects.filter(kullanici=user).select_related("basarim").order_by("-kazanildi", "-id")
    son_basari = basarim_qs.first()

    return {
        "toplam_xp": toplam_xp,
        "seviye": seviye,
        "unvan": _unvan_hesapla(seviye),
        "basari_sayisi": basarim_qs.count(),
        "son_kazanilan_basari": (
            {
                "kod": str(getattr(son_basari.basarim, "kod", "") or ""),
                "ad": str(getattr(son_basari.basarim, "ad", "") or ""),
                "kazanildi": timezone.localtime(son_basari.kazanildi).isoformat(),
            }
            if son_basari is not None
            else None
        ),
        "streak_bilgisi": {
            "streak_gun": int(getattr(profil, "streak_gun", 0) or 0),
            "son_giris_tarihi": (
                getattr(profil, "son_giris_tarihi", None).isoformat()
                if getattr(profil, "son_giris_tarihi", None) is not None
                else None
            ),
        },
    }


def build_dashboard_summary(user, *, days: int = 7) -> dict:
    feedback_enabled = modul_acik_mi("DOCVERSE_FEEDBACK_ENABLED", True)
    study_summary_enabled = modul_acik_mi("DOCVERSE_STUDY_SUMMARY_ENABLED", True)
    cheatsheet_enabled = modul_acik_mi("DOCVERSE_CHEATSHEET_EXPORT_ENABLED", True)

    feedback_summary = build_feedback_analytics_v2(user, days=days, enabled=feedback_enabled)
    feedback_metric = _feedback_metric_summary(user, days=max(days, 30), enabled=feedback_enabled)
    study_usage = _metric_usage_summary(
        user,
        olay_turu="study_summary_uretildi",
        days=30,
        enabled=study_summary_enabled,
    )
    cheatsheet_usage = _metric_usage_summary(
        user,
        olay_turu="cheatsheet_export_uretildi",
        days=30,
        enabled=cheatsheet_enabled,
    )
    confusion_hotspots = build_confusion_hotspot_analytics(user, days=30)
    kpi_panel = build_kpi_panel(user, days=30)

    return {
        "toplam_not_sayisi": Not.objects.filter(owner=user).count(),
        "toplam_portal_not_sayisi": DokumanNotu.objects.filter(owner=user).count(),
        "toplam_feedback": feedback_summary["toplam_feedback"],
        "son_7_gun_feedback": sum(item["adet"] for item in feedback_summary["son_gun_trendi"]),
        "study_summary_kullanimi": {
            "toplam_uretim": study_usage["toplam"],
            "portal_not_bazli_kullanim": study_usage["portal_not_bazli_kullanim"],
        },
        "cheatsheet_export_kullanimi": {
            "toplam_export": cheatsheet_usage["toplam"],
            "portal_not_bazli_kullanim": cheatsheet_usage["portal_not_bazli_kullanim"],
            "format_dagilimi": cheatsheet_usage["format_dagilimi"],
        },
        "feedback_turu_dagilimi": feedback_summary["feedback_turu_dagilimi"],
        "kaynak_modul_dagilimi": feedback_summary["kaynak_modul_dagilimi"],
        "gecerli_feedback_orani": feedback_metric["gecerli_feedback_orani"],
        "dusuk_fayda_orani": _low_usefulness_ratio(user, days=30),
        "yuksek_confusion_parca_sayisi": confusion_hotspots["yuksek_confusion_parca_sayisi"],
        "feedback_trust_ratio": kpi_panel["feedback_trust_ratio"],
        "net_usefulness_score": kpi_panel["net_usefulness_score"],
        "cheatsheet_yield": kpi_panel["cheatsheet_yield"],
    }
