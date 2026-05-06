from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from dokuman.models import Dokuman, MetrikKaydi
from dokuman.services.metric_store import compute_confusion_map_score, compute_mastery_score

try:
    from oyun.models import BossDeneme
except Exception:
    BossDeneme = None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def _safe_float(value) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _metric_qs(*, user, since, until=None):
    qs = MetrikKaydi.objects.filter(kullanici=user, created_at__gte=since)
    if until is not None:
        qs = qs.filter(created_at__lt=until)
    return qs.select_related("dokuman", "parca").order_by("-created_at", "-id")


def _latest_doc_score(*, user, doc, since, until, key: str, fallback_fn) -> float:
    for kayit in _metric_qs(user=user, since=since, until=until).filter(dokuman=doc)[:24]:
        value = _safe_float((kayit.skor_ozeti or {}).get(key))
        if value > 0.0:
            return value
    return _safe_float(fallback_fn())


def _doc_mastery_value(*, user, doc, since, until, fallback_to_current: bool) -> float:
    fallback = lambda: compute_mastery_score(user=user, dokuman=doc)["mastery_score"] if fallback_to_current else 0.0
    return _latest_doc_score(user=user, doc=doc, since=since, until=until, key="mastery_score", fallback_fn=fallback)


def _doc_confusion_value(*, user, doc, since, until, fallback_to_current: bool) -> float:
    fallback = lambda: compute_confusion_map_score(user=user, dokuman=doc)["confusion_map_score"] if fallback_to_current else 0.0
    return _latest_doc_score(user=user, doc=doc, since=since, until=until, key="confusion_map_score", fallback_fn=fallback)


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


def _topic_label(event) -> str:
    if getattr(event, "parca", None) is not None:
        doc_title = getattr(getattr(event.parca, "dokuman", None), "baslik", "") or f"Dokuman {event.parca.dokuman_id}"
        return f"{event.parca.adres} / {doc_title}"
    if getattr(event, "dokuman", None) is not None:
        return getattr(event.dokuman, "baslik", "") or f"Dokuman {event.dokuman_id}"
    return "Genel tekrar"


def _weighted_topic(event) -> float:
    skor_ozeti = event.skor_ozeti or {}
    return (
        1.0
        + (0.6 if event.olay_turu in {"mini_quiz_sonuclandi", "boss_deneme_tamamlandi", "self_check_calistirildi"} else 0.0)
        + (_safe_float(skor_ozeti.get("confusion_map_score")) * 0.8)
        + (_safe_float(skor_ozeti.get("mastery_score")) * 0.4)
        + (_safe_float(skor_ozeti.get("study_summary_importance_score")) * 0.3)
    )


def build_weekly_progress_report(user) -> dict:
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    prev_week = week_ago - timedelta(days=7)

    current_metrics = _metric_qs(user=user, since=week_ago)
    previous_metrics = _metric_qs(user=user, since=prev_week, until=week_ago)

    quiz_count = current_metrics.filter(olay_turu="mini_quiz_sonuclandi").count()
    boss_metric_count = current_metrics.filter(olay_turu="boss_deneme_tamamlandi").count()
    boss_count = boss_metric_count
    if boss_count <= 0 and BossDeneme is not None:
        boss_count = BossDeneme.objects.filter(kullanici=user, olusturuldu__gte=week_ago).count()

    docs = list(Dokuman.objects.filter(owner=user).order_by("id")[:24])
    mastery_now_values = []
    mastery_prev_values = []
    confusion_now_values = []
    confusion_prev_values = []
    for doc in docs:
        current_mastery = _doc_mastery_value(
            user=user,
            doc=doc,
            since=week_ago,
            until=None,
            fallback_to_current=True,
        )
        previous_mastery = _doc_mastery_value(
            user=user,
            doc=doc,
            since=prev_week,
            until=week_ago,
            fallback_to_current=False,
        )
        if previous_mastery <= 0.0:
            previous_mastery = current_mastery
        mastery_now_values.append(current_mastery)
        mastery_prev_values.append(previous_mastery)

        current_confusion = _doc_confusion_value(
            user=user,
            doc=doc,
            since=week_ago,
            until=None,
            fallback_to_current=True,
        )
        previous_confusion = _doc_confusion_value(
            user=user,
            doc=doc,
            since=prev_week,
            until=week_ago,
            fallback_to_current=False,
        )
        if previous_confusion <= 0.0:
            previous_confusion = current_confusion
        confusion_now_values.append(current_confusion)
        confusion_prev_values.append(previous_confusion)

    avg_mastery_now = _safe_avg(mastery_now_values)
    avg_mastery_prev = _safe_avg(mastery_prev_values)
    avg_confusion_now = _safe_avg(confusion_now_values)
    avg_confusion_prev = _safe_avg(confusion_prev_values)
    mastery_delta = round(avg_mastery_now - avg_mastery_prev, 4)
    confusion_azalisi = round(max(0.0, avg_confusion_prev - avg_confusion_now), 4)

    topic_scores = defaultdict(float)
    for event in current_metrics[:160]:
        topic_scores[_topic_label(event)] += _weighted_topic(event)
    if topic_scores:
        en_cok_konu = sorted(topic_scores.items(), key=lambda item: (-item[1], item[0]))[0][0]
    else:
        en_cok_konu = "Genel tekrar"

    if quiz_count <= 0 and avg_confusion_now >= 0.45:
        next_step = "Self-check ve reels ile karisik konulara hedefli tekrar yap."
    elif avg_confusion_now >= 0.55:
        next_step = "Confusion halen yuksek; once self-check sonra roulette onerilir."
    elif avg_mastery_now < 0.52:
        next_step = "Mastery orta bandin altinda; reels veya speedrun ile hizli tekrar yap."
    elif boss_count <= 0 and avg_mastery_now >= 0.58:
        next_step = "Boss veya escape room ile bir ust tura gecmek mantikli gorunuyor."
    else:
        next_step = "Roulette ya da speedrun ile haftalik ivmeyi sabitle."

    weekly_progress_score = _clamp01(
        min(quiz_count, 5) / 5.0 * 0.34
        + min(boss_count, 3) / 3.0 * 0.18
        + max(0.0, mastery_delta) * 1.8 * 0.26
        + min(confusion_azalisi / 0.35, 1.0) * 0.22
    )

    return {
        "bu_hafta_quiz_sayisi": quiz_count,
        "bu_hafta_boss_sayisi": boss_count,
        "mastery_delta": mastery_delta,
        "confusion_azalisi": confusion_azalisi,
        "en_cok_calistigi_konu": en_cok_konu,
        "onerilen_sonraki_adim": next_step,
        "_meta": {
            "weekly_progress_score": round(weekly_progress_score, 4),
            "mastery_progress_delta": mastery_delta,
            "confusion_map_score": round(avg_confusion_now, 4),
        },
    }
