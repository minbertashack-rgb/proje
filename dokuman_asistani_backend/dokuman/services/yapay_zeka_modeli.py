from django.apps import apps
from django.core.exceptions import AppRegistryNotReady
from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError


def _ayar_metnini_getir(*ayar_adlari, varsayilan=""):
    for ayar_adi in ayar_adlari:
        ayar_degeri = getattr(settings, ayar_adi, None)
        if ayar_degeri is None:
            continue
        ayar_metni = str(ayar_degeri).strip()
        if ayar_metni:
            return ayar_metni
    return varsayilan


def _yapay_zeka_modelini_al():
    try:
        return apps.get_model("dokuman", "YapayZekaModeli")
    except AppRegistryNotReady as hata:
        raise RuntimeError("Uygulama hazir degil.") from hata


def _ayar_tamsayisini_getir(*ayar_adlari, varsayilan=0):
    for ayar_adi in ayar_adlari:
        ayar_degeri = getattr(settings, ayar_adi, None)
        if ayar_degeri in (None, ""):
            continue
        try:
            return int(ayar_degeri)
        except (TypeError, ValueError):
            continue
    return varsayilan


def _ayar_ondaligini_getir(*ayar_adlari, varsayilan=0.0):
    for ayar_adi in ayar_adlari:
        ayar_degeri = getattr(settings, ayar_adi, None)
        if ayar_degeri in (None, ""):
            continue
        try:
            return float(ayar_degeri)
        except (TypeError, ValueError):
            continue
    return varsayilan


def _ayar_mantigini_getir(*ayar_adlari, varsayilan=False):
    for ayar_adi in ayar_adlari:
        ayar_degeri = getattr(settings, ayar_adi, None)
        if isinstance(ayar_degeri, bool):
            return ayar_degeri
        if ayar_degeri in (None, ""):
            continue
        return str(ayar_degeri).strip().lower() in {"1", "true", "evet", "on"}
    return varsayilan


def aktif_varsayilan_modeli_getir():
    yapay_zeka_modeli_sinifi = _yapay_zeka_modelini_al()

    try:
        yapay_zeka_modeli = (
            yapay_zeka_modeli_sinifi.objects.filter(aktif_mi=True, varsayilan_mi=True)
            .order_by("id")
            .first()
        )
    except (OperationalError, ProgrammingError) as hata:
        raise RuntimeError("Model tablosu hazir degil.") from hata

    if yapay_zeka_modeli is None:
        raise ValueError("Aktif varsayilan model yok.")

    return yapay_zeka_modeli


def aktif_model_bilgilerini_getir():
    yapay_zeka_modeli = aktif_varsayilan_modeli_getir()
    return {
        "kaynak": "veritabani",
        "ad": yapay_zeka_modeli.ad,
        "aciklama": yapay_zeka_modeli.aciklama,
        "model_kisa_adi": (yapay_zeka_modeli.model_kisa_adi or "").strip(),
        "gguf_dosya_adi": (yapay_zeka_modeli.gguf_dosya_adi or "").strip(),
        "gguf_dosya_yolu": (yapay_zeka_modeli.gguf_dosya_yolu or "").strip(),
        "kuantizasyon_turu": (yapay_zeka_modeli.kuantizasyon_turu or "").strip(),
        "aktif_mi": bool(yapay_zeka_modeli.aktif_mi),
        "varsayilan_mi": bool(yapay_zeka_modeli.varsayilan_mi),
    }


def model_yapilandirmasini_coz():
    veritabani_bilgisi = None
    veritabani_hatasi = None

    try:
        veritabani_bilgisi = aktif_model_bilgilerini_getir()
    except Exception as hata:
        veritabani_hatasi = hata

    ayar_model_kisa_adi = _ayar_metnini_getir("AI2_MODEL_ADI", varsayilan="qwen-docverse")
    ayar_gguf_yolu = _ayar_metnini_getir("ANA_GGUF_YOLU", varsayilan="")
    ayar_taban_adresi = _ayar_metnini_getir("AI2_TABAN_ADRESI", varsayilan="http://127.0.0.1:8002").rstrip("/")

    model_kisa_adi = ayar_model_kisa_adi
    gguf_dosya_yolu = ayar_gguf_yolu
    gguf_dosya_adi = ""
    kuantizasyon_turu = ""
    kaynak = "ayarlar"

    if veritabani_bilgisi:
        kaynak = "veritabani"
        model_kisa_adi = veritabani_bilgisi.get("model_kisa_adi") or ayar_model_kisa_adi
        gguf_dosya_yolu = veritabani_bilgisi.get("gguf_dosya_yolu") or ayar_gguf_yolu
        gguf_dosya_adi = veritabani_bilgisi.get("gguf_dosya_adi") or ""
        kuantizasyon_turu = veritabani_bilgisi.get("kuantizasyon_turu") or ""

    if not model_kisa_adi:
        raise RuntimeError("Model adi yok.")

    if not ayar_taban_adresi and not gguf_dosya_yolu:
        raise RuntimeError("Model ayari yok.")

    return {
        "kaynak": kaynak,
        "model_kisa_adi": model_kisa_adi,
        "gguf_dosya_yolu": gguf_dosya_yolu,
        "gguf_dosya_adi": gguf_dosya_adi,
        "kuantizasyon_turu": kuantizasyon_turu,
        "ai2_taban_adresi": ayar_taban_adresi,
        "ai2_sicaklik": _ayar_ondaligini_getir("AI2_SICAKLIK", varsayilan=0.0),
        "ai2_zaman_asimi": _ayar_tamsayisini_getir("AI2_ZAMAN_ASIMI", varsayilan=600),
        "ai2_azami_token": _ayar_tamsayisini_getir("AI2_AZAMI_TOKEN", varsayilan=1200),
        "ai2_api_anahtari": _ayar_metnini_getir("AI2_API_KEY", varsayilan=""),
        "yerel_model_etkin": _ayar_mantigini_getir("YEREL_MODEL_ETKIN", varsayilan=False),
        "yerel_baglam_boyu": _ayar_tamsayisini_getir("YEREL_BAGLAM_BOYU", varsayilan=4096),
        "yerel_is_parcacigi": _ayar_tamsayisini_getir("YEREL_IS_PARCACIGI", varsayilan=8),
        "yerel_gpu_katman_sayisi": _ayar_tamsayisini_getir("YEREL_GPU_KATMAN_SAYISI", varsayilan=0),
        "yerel_sicaklik": _ayar_ondaligini_getir("YEREL_SICAKLIK", varsayilan=0.0),
        "veritabani_hatasi": str(veritabani_hatasi) if veritabani_hatasi else "",
    }
