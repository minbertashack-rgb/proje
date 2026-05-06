from __future__ import annotations
from typing import Any, List

def kanitli_cevap_uret(*args, **kwargs):
    # TODO: gerçek implementasyonu sonra
    return {"durum": "ok", "mesaj": "placeholder kanitli_cevap_uret"}
# dokuman/services/answerer.py

class CevapSonuc(dict):
    """
    Hem dict gibi: sonuc["cevap"], sonuc["kanitlar"]
    Hem de tuple gibi: cevap, kanitlar = sonuc
    """
    def __iter__(self):
        yield self.get("cevap")
        yield self.get("kanitlar")


def tanim_var_mi(soru, kanitlar=None, *args, **kwargs) -> bool:
    s = str(soru).lower()
    # Soru tanım sorusu değilse gate'i PAS geç
    is_def = any(k in s for k in ["tanım", "nedir", "ne demek"])
    if not is_def:
        return True

    # Tanım sorusuysa: kanıtlarda tanım işareti arayalım
    joined = " ".join([(k.get("metin") or "") for k in (kanitlar or [])]).lower()
    return any(p in joined for p in [
        "anlamına gelir", "olarak tanımlan", "denir", "ifade eder"
    ])


def kanitli_cevap_uret(*args, **kwargs) -> CevapSonuc:
    """
    Placeholder: Sistem ayağa kalksın diye.
    Gerçek kanıtlı cevap motorunu sonra buraya bağlarız.
    """
    return CevapSonuc(
        durum="ok",
        cevap="(placeholder) Kanıtlı cevap motoru henüz bağlanmadı.",
        kanitlar=[],
    )