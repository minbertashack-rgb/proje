from __future__ import annotations

from django.conf import settings


def modul_acik_mi(flag_adi: str, varsayilan: bool = False) -> bool:
    return bool(getattr(settings, flag_adi, varsayilan))
