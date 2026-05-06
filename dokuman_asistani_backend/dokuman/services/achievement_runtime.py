from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.utils import timezone

from dokuman.models import MetrikKaydi

XP_EVENT_WEIGHTS = {
    "mini_quiz_sonuclandi": 22,
    "boss_deneme_tamamlandi": 38,
    "self_check_calistirildi": 14,
    "concept_fusion_uretildi": 10,
    "study_summary_uretildi": 8,
    "cheatsheet_export_uretildi": 8,
    "speedrun_tamamlandi": 16,
    "roulette_uretildi": 6,
    "reels_surface_uretildi": 4,
}
ACTIVE_EVENTS = tuple(XP_EVENT_WEIGHTS.keys())


def _safe_float(value) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


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


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def _metric_qs(user, *, days: int | None = None):
    qs = MetrikKaydi.objects.filter(kullanici=user).order_by("-created_at", "-id")
    if days:
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=max(1, int(days))))
    return qs


def _event_score(event: MetrikKaydi) -> int:
    base = int(XP_EVENT_WEIGHTS.get(event.olay_turu, 0) or 0)
    if base <= 0:
        return 0

    skor_ozeti = event.skor_ozeti or {}
    oran = max(
        _safe_float(skor_ozeti.get("sonuc_orani")),
        _safe_float(skor_ozeti.get("boss_progress_score")),
        _safe_float(skor_ozeti.get("self_check_score")),
    )
    if event.olay_turu in {"mini_quiz_sonuclandi", "boss_deneme_tamamlandi", "self_check_calistirildi", "speedrun_tamamlandi"}:
        multiplier = max(0.45, _clamp01(oran))
    elif event.olay_turu == "concept_fusion_uretildi":
        multiplier = 1.0 + min(0.25, _safe_float(skor_ozeti.get("concept_overlap_ratio")) * 0.25)
    else:
        multiplier = 1.0
    return int(round(base * multiplier))


def compute_metric_streak(user, *, days: int = 45) -> dict:
    active_days = {
        timezone.localtime(item.created_at).date()
        for item in _metric_qs(user, days=days).filter(olay_turu__in=ACTIVE_EVENTS)[:256]
    }
    if not active_days:
        return {"streak_gun": 0, "son_giris_tarihi": None}

    latest_day = max(active_days)
    streak_days = 0
    while latest_day - timedelta(days=streak_days) in active_days:
        streak_days += 1

    return {
        "streak_gun": int(streak_days),
        "son_giris_tarihi": latest_day.isoformat(),
    }


def build_metric_reward_snapshot(user) -> dict:
    qs = list(_metric_qs(user)[:400])
    event_counter = Counter(item.olay_turu for item in qs)
    quiz_events = [item for item in qs if item.olay_turu == "mini_quiz_sonuclandi"]
    boss_events = [item for item in qs if item.olay_turu == "boss_deneme_tamamlandi"]
    self_check_events = [item for item in qs if item.olay_turu == "self_check_calistirildi"]
    fusion_events = [item for item in qs if item.olay_turu == "concept_fusion_uretildi"]

    total_xp = sum(_event_score(item) for item in qs)
    quiz_avg = round(_safe_avg(_safe_float((item.skor_ozeti or {}).get("sonuc_orani")) for item in quiz_events), 4)
    boss_avg = round(
        _safe_avg(
            max(
                _safe_float((item.skor_ozeti or {}).get("boss_progress_score")),
                _safe_float((item.skor_ozeti or {}).get("sonuc_orani")),
            )
            for item in boss_events
        ),
        4,
    )
    self_check_avg = round(
        _safe_avg(_safe_float((item.skor_ozeti or {}).get("self_check_score")) for item in self_check_events),
        4,
    )
    fusion_overlap_avg = round(
        _safe_avg(_safe_float((item.skor_ozeti or {}).get("concept_overlap_ratio")) for item in fusion_events),
        4,
    )
    boss_wins = sum(
        1
        for item in boss_events
        if max(
            _safe_float((item.skor_ozeti or {}).get("boss_progress_score")),
            _safe_float((item.skor_ozeti or {}).get("sonuc_orani")),
        ) >= 0.85
    )
    streak = compute_metric_streak(user)
    level = max(1, (int(total_xp) // 100) + 1)

    if boss_wins >= 2:
        active_title = "Boss Avcisi"
    elif len(fusion_events) >= 2 and fusion_overlap_avg >= 0.45:
        active_title = "Kavram Dokuyucu"
    elif len(self_check_events) >= 3 and self_check_avg >= 0.68:
        active_title = "Oz-Kontrol Ustasi"
    elif len(quiz_events) >= 4 and quiz_avg >= 0.7:
        active_title = "Quiz Istikrarcisi"
    elif int(streak["streak_gun"] or 0) >= 4:
        active_title = "Ritim Koruyucu"
    elif total_xp >= 120:
        active_title = "Tekrar Toplayici"
    else:
        active_title = "Yeni Baslayan"

    basarilar = []

    def _append_achievement(*, kod: str, ad: str, event: MetrikKaydi | None):
        if event is None:
            return
        basarilar.append(
            {
                "kod": kod,
                "ad": ad,
                "kazanildi": timezone.localtime(event.created_at).isoformat(),
            }
        )

    if quiz_events:
        _append_achievement(
            kod="ilk_quiz",
            ad="Ilk Quiz Adimi",
            event=quiz_events[0],
        )
    if boss_wins >= 1:
        _append_achievement(
            kod="boss_esik",
            ad="Boss Esigi",
            event=next(
                (
                    item
                    for item in boss_events
                    if max(
                        _safe_float((item.skor_ozeti or {}).get("boss_progress_score")),
                        _safe_float((item.skor_ozeti or {}).get("sonuc_orani")),
                    ) >= 0.85
                ),
                None,
            ),
        )
    if len(self_check_events) >= 2 and self_check_avg >= 0.55:
        _append_achievement(
            kod="self_check_refleksi",
            ad="Self-Check Refleksi",
            event=self_check_events[0],
        )
    if fusion_events:
        _append_achievement(
            kod="kavram_baglayici",
            ad="Kavram Baglayici",
            event=fusion_events[0],
        )
    if int(streak["streak_gun"] or 0) >= 3:
        last_event = next((item for item in qs if item.olay_turu in ACTIVE_EVENTS), None)
        _append_achievement(
            kod="ritim_serisi",
            ad="Ritim Serisi",
            event=last_event,
        )

    if boss_wins <= 0 and quiz_avg >= 0.68:
        reward_hint = "Hazir gorunen bir dokumanda boss dene; siradaki rozet buna bagli."
    elif len(self_check_events) < 2:
        reward_hint = "Bir self-check tamamla; oz-kontrol basarisina yakinsin."
    elif not fusion_events and (len(quiz_events) + len(self_check_events)) >= 3:
        reward_hint = "Iki kavrami fusion modunda bagla; yeni basari acilacak."
    elif int(streak["streak_gun"] or 0) in {1, 2, 3}:
        reward_hint = "Bugun kisa bir quiz veya speedrun ile streak'i koru."
    elif quiz_avg < 0.55:
        reward_hint = "Roulette veya speedrun ile quiz oranini biraz daha yukari cek."
    else:
        reward_hint = "Bir boss veya speedrun daha yaparak XP ivmesini koruyabilirsin."

    return {
        "derived_xp": int(total_xp),
        "derived_level": int(level),
        "active_title": active_title,
        "achievements": sorted(basarilar, key=lambda item: item["kazanildi"], reverse=True)[:5],
        "streak": streak,
        "reward_hint": reward_hint,
        "quiz_count": int(event_counter.get("mini_quiz_sonuclandi", 0)),
        "boss_count": int(event_counter.get("boss_deneme_tamamlandi", 0)),
        "boss_wins": int(boss_wins),
        "self_check_count": int(event_counter.get("self_check_calistirildi", 0)),
        "quiz_avg": quiz_avg,
        "boss_avg": boss_avg,
        "self_check_avg": self_check_avg,
        "_meta": {
            "quiz_count": int(event_counter.get("mini_quiz_sonuclandi", 0)),
            "boss_count": int(event_counter.get("boss_deneme_tamamlandi", 0)),
            "boss_wins": int(boss_wins),
            "self_check_count": int(event_counter.get("self_check_calistirildi", 0)),
        },
    }
