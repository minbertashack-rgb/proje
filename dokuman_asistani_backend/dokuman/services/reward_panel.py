from __future__ import annotations

from django.utils import timezone

from dokuman.services.achievement_runtime import build_metric_reward_snapshot
from dokuman.services.metric_store import (
    compute_confusion_recovery_score,
    compute_learning_momentum_score,
    compute_reward_priority_score,
)
from dokuman.services.product_analytics import build_xp_visibility_panel

try:
    from oyun.models import KullaniciBasarim
except Exception:
    KullaniciBasarim = None


def _merge_achievements(*, stored: list[dict], derived: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for item in stored + derived:
        kod = str(item.get("kod") or "").strip()
        if not kod or kod in seen:
            continue
        seen.add(kod)
        merged.append(item)
    merged.sort(key=lambda item: str(item.get("kazanildi") or ""), reverse=True)
    return merged[:5]


def build_reward_panel(user) -> dict:
    xp_panel = build_xp_visibility_panel(user)
    metric_reward = build_metric_reward_snapshot(user)

    stored_achievements = []
    if KullaniciBasarim is not None:
        for item in KullaniciBasarim.objects.filter(kullanici=user).select_related("basarim").order_by("-kazanildi", "-id")[:5]:
            stored_achievements.append(
                {
                    "kod": str(getattr(item.basarim, "kod", "") or ""),
                    "ad": str(getattr(item.basarim, "ad", "") or ""),
                    "kazanildi": timezone.localtime(item.kazanildi).isoformat(),
                }
            )

    recent_quiz_signal = max(
        float(metric_reward.get("quiz_avg") or 0.0),
        float(metric_reward.get("self_check_avg") or 0.0),
        0.35,
    )
    momentum = compute_learning_momentum_score(user=user)
    recovery_meta = compute_confusion_recovery_score(user=user, quiz_score=recent_quiz_signal)
    reward_priority = compute_reward_priority_score(
        recovery_score=recovery_meta["confusion_recovery_score"],
        momentum_score=momentum["learning_momentum_score"],
        boss_kill=bool(metric_reward.get("boss_wins")),
    )

    total_xp = max(int(xp_panel.get("toplam_xp") or 0), int(metric_reward.get("derived_xp") or 0))
    seviye = max(
        int(xp_panel.get("seviye") or 1),
        int(metric_reward.get("derived_level") or 1),
        max(1, (int(total_xp) // 100) + 1),
    )
    metric_title = str(metric_reward.get("active_title") or "").strip()
    stored_title = str(xp_panel.get("unvan") or "").strip()
    aktif_unvan = metric_title or stored_title or "Yeni Baslayan"
    if stored_title and stored_title != "Yeni Başlayan" and total_xp == int(xp_panel.get("toplam_xp") or 0):
        aktif_unvan = stored_title

    metric_streak = dict(metric_reward.get("streak") or {})
    stored_streak = dict(xp_panel.get("streak_bilgisi") or {})
    streak = metric_streak if int(metric_streak.get("streak_gun") or 0) >= int(stored_streak.get("streak_gun") or 0) else stored_streak

    return {
        "toplam_xp": total_xp,
        "seviye": seviye,
        "aktif_unvan": aktif_unvan,
        "basarilar": _merge_achievements(stored=stored_achievements, derived=list(metric_reward.get("achievements") or [])),
        "streak": streak,
        "reward_priority": reward_priority["reward_priority_score"],
        "reward_hint": str(metric_reward.get("reward_hint") or reward_priority["reward_priority_reason"]),
        "_meta": {
            "reward_priority_score": reward_priority["reward_priority_score"],
            "reward_priority_reason": reward_priority["reward_priority_reason"],
            "learning_momentum_score": momentum["learning_momentum_score"],
            "confusion_recovery_score": recovery_meta["confusion_recovery_score"],
        },
    }
