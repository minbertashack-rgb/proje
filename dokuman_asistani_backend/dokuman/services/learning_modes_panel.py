from __future__ import annotations

from dokuman.services.learning_unlocks import build_learning_unlock_snapshot


def build_learning_modes_panel(user, doc=None) -> dict:
    return build_learning_unlock_snapshot(user=user, doc=doc)
