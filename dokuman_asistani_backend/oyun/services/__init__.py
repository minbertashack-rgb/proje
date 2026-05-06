# oyun/services/__init__.py
"""
Bu paket, oyun/views.py içinden yapılan:
from .services import profil_getir, odul_ver, ...
importlarını karşılamak için "public API" sağlar.

Önce eski services_legacy.py'den gerçek implementasyonu çekmeyi dener.
Bulamazsa veya import sırasında hata olursa, server düşmesin diye stub fonksiyonlar üretir.
"""

from __future__ import annotations
from typing import Any, Dict

# Yeni modüler yapıdan (bizim oluşturduğumuz) görev hazırlama:
from .gorevler import gorevleri_hazirla


def _stub(name: str):
    def _fn(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        # Server ayakta kalsın diye güvenli fallback
        return {
            "ok": False,
            "stub": True,
            "fonksiyon": name,
            "detail": f"{name} henüz implement edilmedi veya services_legacy import edilemedi.",
        }
    return _fn


# Varsayılan: stub'lar
profil_getir = _stub("profil_getir")
odul_ver = _stub("odul_ver")
gunluk_giris = _stub("gunluk_giris")
gorev_event = _stub("gorev_event")
gorev_odul_al = _stub("gorev_odul_al")
basarim_kontrol = _stub("basarim_kontrol")
market_satin_al = _stub("market_satin_al")
booster_kullan = _stub("booster_kullan")

# Eğer eski dosyada gerçek fonksiyonlar varsa onları kullan
try:
    from ..services_legacy import (  # type: ignore
        profil_getir as _profil_getir,
        odul_ver as _odul_ver,
        gunluk_giris as _gunluk_giris,
        gorev_event as _gorev_event,
        gorev_odul_al as _gorev_odul_al,
        basarim_kontrol as _basarim_kontrol,
        market_satin_al as _market_satin_al,
        booster_kullan as _booster_kullan,
    )

    profil_getir = _profil_getir
    odul_ver = _odul_ver
    gunluk_giris = _gunluk_giris
    gorev_event = _gorev_event
    gorev_odul_al = _gorev_odul_al
    basarim_kontrol = _basarim_kontrol
    market_satin_al = _market_satin_al
    booster_kullan = _booster_kullan
except Exception:
    # Kasıtlı: import patlarsa stub'larla devam etsin
    pass


__all__ = [
    "profil_getir",
    "odul_ver",
    "gunluk_giris",
    "gorev_event",
    "gorev_odul_al",
    "basarim_kontrol",
    "market_satin_al",
    "booster_kullan",
    "gorevleri_hazirla",
]