import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from threading import Lock, local
from typing import Optional

from django.conf import settings

from dokuman.services.yapay_zeka_modeli import model_yapilandirmasini_coz


_yerel_model = None
_yerel_model_yolu = ""
_yerel_model_kilidi = Lock()
_son_chat_debug = local()
_DUSUNCE_KALIBI = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class AI2IstekHatasi(RuntimeError):
    def __init__(self, mesaj: str, hata_nedeni: str, debug_bilgisi: Optional[dict] = None):
        super().__init__(mesaj)
        self.hata_nedeni = str(hata_nedeni or "ai2_exception")
        self.debug_bilgisi = dict(debug_bilgisi or {})
        self.debug_bilgisi["hata_nedeni"] = self.hata_nedeni
        self.debug_bilgisi["hata_mesaji"] = str(mesaj or "")


def _debug_bilgisi_yaz(debug_bilgisi: dict):
    _son_chat_debug.veri = dict(debug_bilgisi or {})


def son_chat_debug_bilgisi_al() -> dict:
    return dict(getattr(_son_chat_debug, "veri", {}) or {})


def _metin_ozeti(metin: str, limit: int = 160) -> str:
    text = dusunce_etiketlerini_temizle(str(metin or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _model_aliasi_uyusuyor_mu(istenen_model: str, yanit_modeli: str) -> bool | None:
    istenen = str(istenen_model or "").strip().lower()
    yanit = str(yanit_modeli or "").strip().lower()
    if not istenen or not yanit:
        return None
    return istenen == yanit or istenen in yanit or yanit in istenen


def _chat_istek_zamani() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _prompt_tahmini_uzunluk(messages: list[dict]) -> int:
    toplam = 0
    for message in list(messages or []):
        if isinstance(message, dict):
            toplam += len(str(message.get("content") or ""))
        elif message:
            toplam += len(str(message))
    return toplam


def _ayar_tamsayisini_oku(ayar_adi: str, varsayilan: int) -> int:
    try:
        return int(getattr(settings, ayar_adi, varsayilan))
    except (TypeError, ValueError):
        return int(varsayilan)


def ai2_test_modu_aktif() -> bool:
    deger = getattr(settings, "AI2_TEST_MODU", False)
    if isinstance(deger, bool):
        return deger
    return str(deger).strip().lower() in {"1", "true", "evet", "on", "yes"}


def ai2_scope_icin_max_token(scope: str, istenen_token=None, minimum: int = 64) -> int:
    scope_adi = str(scope or "DEFAULT").strip().upper()
    ayar_onyeki = "AI2_TEST" if ai2_test_modu_aktif() else "AI2_NORMAL"
    scope_varsayilani = _ayar_tamsayisini_oku(
        f"{ayar_onyeki}_{scope_adi}_MAX_TOKENS",
        _ayar_tamsayisini_oku(
            f"{ayar_onyeki}_DEFAULT_MAX_TOKENS",
            _ayar_tamsayisini_oku("AI2_AZAMI_TOKEN", 1200),
        ),
    )

    try:
        hedef_token = int(istenen_token) if istenen_token not in (None, "") else scope_varsayilani
    except (TypeError, ValueError):
        hedef_token = scope_varsayilani

    return _azami_tokeni_uygula(
        max_tokens=hedef_token,
        azami_token=_ayar_tamsayisini_oku("AI2_AZAMI_TOKEN", 1200),
        varsayilan=max(minimum, scope_varsayilani),
    )


def ai2_istemcisini_hazirla():
    model_yapilandirmasi = model_yapilandirmasini_coz()
    ai2_taban_adresi = str(model_yapilandirmasi.get("ai2_taban_adresi", "") or "").rstrip("/")

    if not ai2_taban_adresi:
        raise RuntimeError("AI2 adresi yok.")

    if ai2_taban_adresi.endswith("/v1"):
        aday_adresler = [f"{ai2_taban_adresi}/chat/completions"]
    else:
        aday_adresler = [
            f"{ai2_taban_adresi}/v1/chat/completions",
            f"{ai2_taban_adresi}/chat/completions",
        ]

    basliklar = {"Content-Type": "application/json; charset=utf-8"}
    ai2_api_anahtari = str(model_yapilandirmasi.get("ai2_api_anahtari", "") or "").strip()
    if ai2_api_anahtari:
        basliklar["Authorization"] = f"Bearer {ai2_api_anahtari}"

    return {
        "aday_adresler": aday_adresler,
        "basliklar": basliklar,
        "model_kisa_adi": model_yapilandirmasi["model_kisa_adi"],
        "gguf_dosya_yolu": model_yapilandirmasi.get("gguf_dosya_yolu", ""),
        "ai2_sicaklik": float(model_yapilandirmasi.get("ai2_sicaklik", 0.0)),
        "ai2_zaman_asimi": int(model_yapilandirmasi.get("ai2_zaman_asimi", 600)),
        "ai2_azami_token": int(model_yapilandirmasi.get("ai2_azami_token", 1200)),
        "yerel_model_etkin": bool(model_yapilandirmasi.get("yerel_model_etkin", False)),
        "yerel_baglam_boyu": int(model_yapilandirmasi.get("yerel_baglam_boyu", 4096)),
        "yerel_is_parcacigi": int(model_yapilandirmasi.get("yerel_is_parcacigi", 8)),
        "yerel_gpu_katman_sayisi": int(model_yapilandirmasi.get("yerel_gpu_katman_sayisi", 0)),
        "yerel_sicaklik": float(model_yapilandirmasi.get("yerel_sicaklik", 0.0)),
    }


def dusunce_etiketlerini_temizle(metin: str) -> str:
    if not metin:
        return metin
    metin = re.sub(_DUSUNCE_KALIBI, "", metin)
    metin = metin.replace("</think>", "").replace("<think>", "")
    return metin.strip()


def _icerikten_metin_cikar(icerik) -> str:
    if isinstance(icerik, str):
        return dusunce_etiketlerini_temizle(icerik.strip())

    if isinstance(icerik, list):
        metin_parcalari = []
        for oge in icerik:
            if isinstance(oge, dict):
                metin_parcasi = oge.get("text")
                if metin_parcasi:
                    metin_parcalari.append(str(metin_parcasi))
            elif oge:
                metin_parcalari.append(str(oge))
        return dusunce_etiketlerini_temizle("\n".join(metin_parcalari).strip())

    if icerik:
        return dusunce_etiketlerini_temizle(str(icerik).strip())

    return ""


def _openai_yanitindan_icerik_cikar(sunucu_cevabi: dict) -> str:
    try:
        secim = sunucu_cevabi.get("choices", [{}])[0]
    except Exception:
        return ""

    mesaj_icerigi = secim.get("message", {}).get("content")
    if mesaj_icerigi not in (None, ""):
        return _icerikten_metin_cikar(mesaj_icerigi)

    if "text" in secim:
        return _icerikten_metin_cikar(secim.get("text"))

    return ""


def _azami_tokeni_uygula(max_tokens: int, azami_token: int, varsayilan: int) -> int:
    izinli_ust_sinir = max(64, int(azami_token or 1200))
    istenen_token = int(max_tokens or varsayilan)
    return max(64, min(istenen_token, izinli_ust_sinir))


def yerel_modeli_al(ai2_istemcisi: Optional[dict] = None):
    global _yerel_model, _yerel_model_yolu

    ai2_istemcisi = ai2_istemcisi or ai2_istemcisini_hazirla()

    if not ai2_istemcisi.get("yerel_model_etkin"):
        return None

    gguf_dosya_yolu = str(ai2_istemcisi.get("gguf_dosya_yolu", "") or "").strip()
    if not gguf_dosya_yolu:
        raise RuntimeError("GGUF yolu yok.")
    if not os.path.exists(gguf_dosya_yolu):
        raise FileNotFoundError(f"GGUF bulunamadi: {gguf_dosya_yolu}")

    if _yerel_model is not None and _yerel_model_yolu == gguf_dosya_yolu:
        return _yerel_model

    with _yerel_model_kilidi:
        if _yerel_model is not None and _yerel_model_yolu == gguf_dosya_yolu:
            return _yerel_model

        try:
            from llama_cpp import Llama
        except ModuleNotFoundError as hata:
            raise RuntimeError("llama_cpp yok.") from hata

        _yerel_model = Llama(
            model_path=gguf_dosya_yolu,
            n_ctx=int(ai2_istemcisi.get("yerel_baglam_boyu", 4096)),
            n_threads=int(ai2_istemcisi.get("yerel_is_parcacigi", 8)),
            n_gpu_layers=int(ai2_istemcisi.get("yerel_gpu_katman_sayisi", 0)),
            verbose=False,
        )
        _yerel_model_yolu = gguf_dosya_yolu
        return _yerel_model


def _json_gonder(adres: str, istek_govdesi: dict, basliklar: dict, zaman_asimi: int, debug_bilgisi: Optional[dict] = None) -> dict:
    debug_bilgisi = dict(debug_bilgisi or {})
    debug_bilgisi["kullanilan_url"] = adres
    istek_verisi = json.dumps(istek_govdesi, ensure_ascii=False).encode("utf-8")
    istek = urllib.request.Request(adres, data=istek_verisi, headers=basliklar, method="POST")
    zaman_asimi = max(1, int(zaman_asimi or 1))
    istek_baslangici = time.perf_counter()
    timeout_onceki_asama = "baglanti_kuruluyor"
    yanit = None

    try:
        yanit = urllib.request.urlopen(istek, timeout=zaman_asimi)
        debug_bilgisi["ilk_cevap_suresi_ms"] = round((time.perf_counter() - istek_baslangici) * 1000, 1)
        timeout_onceki_asama = "govde_okunuyor"
        debug_bilgisi["response_status"] = int(getattr(yanit, "status", 200) or 200)
        ham_yanit = yanit.read().decode("utf-8", errors="replace")
        debug_bilgisi["response_body_uzunlugu"] = len(ham_yanit)
        debug_bilgisi["toplam_cevap_suresi_ms"] = round((time.perf_counter() - istek_baslangici) * 1000, 1)
    except urllib.error.HTTPError as hata:
        ham_hata = hata.read().decode("utf-8", errors="replace")
        debug_bilgisi["response_status"] = int(getattr(hata, "code", 0) or 0)
        debug_bilgisi["response_body_uzunlugu"] = len(ham_hata)
        debug_bilgisi["response_onizleme"] = _metin_ozeti(ham_hata)
        debug_bilgisi["timeout_onceki_asama"] = timeout_onceki_asama
        debug_bilgisi["toplam_cevap_suresi_ms"] = round((time.perf_counter() - istek_baslangici) * 1000, 1)
        raise AI2IstekHatasi(f"AI2 HTTP hatasi: {hata.code}", "ai2_http_error", debug_bilgisi) from hata
    except urllib.error.URLError as hata:
        reason = getattr(hata, "reason", None)
        hata_metni = str(reason or hata or "").strip()
        debug_bilgisi["timeout_onceki_asama"] = timeout_onceki_asama
        debug_bilgisi["toplam_cevap_suresi_ms"] = round((time.perf_counter() - istek_baslangici) * 1000, 1)
        if isinstance(reason, socket.timeout) or "timed out" in hata_metni.lower():
            raise AI2IstekHatasi("AI2 zaman asimi.", "ai2_timeout", debug_bilgisi) from hata
        raise AI2IstekHatasi("AI2 baglanti hatasi.", "ai2_connection_error", debug_bilgisi) from hata
    except (TimeoutError, socket.timeout) as hata:
        debug_bilgisi["timeout_onceki_asama"] = timeout_onceki_asama
        debug_bilgisi["toplam_cevap_suresi_ms"] = round((time.perf_counter() - istek_baslangici) * 1000, 1)
        raise AI2IstekHatasi("AI2 zaman asimi.", "ai2_timeout", debug_bilgisi) from hata
    except Exception as hata:
        debug_bilgisi["timeout_onceki_asama"] = timeout_onceki_asama
        debug_bilgisi["toplam_cevap_suresi_ms"] = round((time.perf_counter() - istek_baslangici) * 1000, 1)
        raise AI2IstekHatasi("AI2 istek hatasi.", "ai2_exception", debug_bilgisi) from hata
    finally:
        try:
            if yanit is not None:
                yanit.close()
        except Exception:
            pass

    debug_bilgisi["response_onizleme"] = _metin_ozeti(ham_yanit)
    debug_bilgisi["timeout_onceki_asama"] = "tamamlandi"

    try:
        return json.loads(ham_yanit)
    except Exception as hata:
        debug_bilgisi["timeout_onceki_asama"] = "json_cozumleniyor"
        raise AI2IstekHatasi("AI2 gecersiz cevap verdi.", "ai2_invalid_response_json", debug_bilgisi) from hata


def llm_tamamla(istem: str, max_tokens: int = 512) -> str:
    ai2_istemcisi = ai2_istemcisini_hazirla()
    yerel_model = yerel_modeli_al(ai2_istemcisi)

    if yerel_model is None:
        raise RuntimeError("Yerel model kapali. (YEREL_MODEL_ETKIN=0)")

    sunucu_cevabi = yerel_model(
        istem,
        max_tokens=_azami_tokeni_uygula(max_tokens, ai2_istemcisi["ai2_azami_token"], 512),
        temperature=ai2_istemcisi["yerel_sicaklik"],
        stop=["</s>"],
    )
    yanit_metin = _openai_yanitindan_icerik_cikar(sunucu_cevabi)
    if yanit_metin:
        return yanit_metin

    raise RuntimeError("Yerel tamamlama bos cevap verdi.")


def chat(
    messages: list[dict],
    max_tokens: int = 256,
    *,
    timeout_seconds: int | None = None,
    max_attempts_per_url: int = 2,
) -> str:
    ai2_istemcisi = ai2_istemcisini_hazirla()
    mesajlar = messages
    max_tokens = _azami_tokeni_uygula(max_tokens, ai2_istemcisi["ai2_azami_token"], 256)
    zaman_asimi = max(1, int(timeout_seconds or ai2_istemcisi["ai2_zaman_asimi"]))
    max_attempts_per_url = max(1, int(max_attempts_per_url or 1))
    aday_adresler = list(ai2_istemcisi["aday_adresler"])

    istek_govdesi = {
        "model": ai2_istemcisi["model_kisa_adi"],
        "messages": mesajlar,
        "temperature": ai2_istemcisi["ai2_sicaklik"],
        "max_tokens": max_tokens,
        "stream": False,
    }

    temel_debug = {
        "chat_istek_baslama": _chat_istek_zamani(),
        "kullanilan_url": "",
        "model_alias": ai2_istemcisi["model_kisa_adi"],
        "yanit_modeli": "",
        "model_alias_uyusuyor_mu": None,
        "max_tokens": max_tokens,
        "timeout_saniye": zaman_asimi,
        "ilk_cevap_suresi_ms": None,
        "toplam_cevap_suresi_ms": None,
        "timeout_onceki_asama": "",
        "response_status": None,
        "response_body_uzunlugu": 0,
        "response_onizleme": "",
        "content_bos_mu": True,
        "content_uzunlugu": 0,
        "ai2_cevap_ozeti": "",
        "prompt_tahmini_uzunluk": _prompt_tahmini_uzunluk(mesajlar),
        "ai2_test_modu_aktif_mi": ai2_test_modu_aktif(),
        "retry_devreye_girdi_mi": False,
        "retry_bekleme_suresi_ms": 0,
        "deneme_sayisi": 0,
        "tekil_deneme_no": 0,
        "hata_nedeni": "",
        "hata_mesaji": "",
    }
    _debug_bilgisi_yaz(temel_debug)

    uzak_hata_ozeti = ""
    son_hata_nedeni = ""
    toplam_deneme = 0
    for aday_adres in aday_adresler:
        for tekil_deneme_no in range(1, max_attempts_per_url + 1):
            toplam_deneme += 1
            debug_bilgisi = dict(temel_debug)
            debug_bilgisi["kullanilan_url"] = aday_adres
            debug_bilgisi["deneme_sayisi"] = toplam_deneme
            debug_bilgisi["tekil_deneme_no"] = tekil_deneme_no
            debug_bilgisi["retry_devreye_girdi_mi"] = toplam_deneme > 1
            try:
                sunucu_cevabi = _json_gonder(
                    aday_adres,
                    istek_govdesi,
                    ai2_istemcisi["basliklar"],
                    zaman_asimi,
                    debug_bilgisi=debug_bilgisi,
                )
                yanit_modeli = str((sunucu_cevabi or {}).get("model") or "").strip()
                debug_bilgisi["yanit_modeli"] = yanit_modeli
                debug_bilgisi["model_alias_uyusuyor_mu"] = _model_aliasi_uyusuyor_mu(
                    ai2_istemcisi["model_kisa_adi"],
                    yanit_modeli,
                )

                yanit_metin = _openai_yanitindan_icerik_cikar(sunucu_cevabi)
                debug_bilgisi["content_bos_mu"] = not bool(yanit_metin)
                debug_bilgisi["content_uzunlugu"] = len(yanit_metin or "")
                debug_bilgisi["ai2_cevap_ozeti"] = _metin_ozeti(yanit_metin)

                if yanit_metin:
                    _debug_bilgisi_yaz(debug_bilgisi)
                    return yanit_metin

                son_hata_nedeni = "ai2_empty_content"
                uzak_hata_ozeti = "AI2 bos cevap verdi."
                debug_bilgisi["hata_nedeni"] = son_hata_nedeni
                debug_bilgisi["hata_mesaji"] = uzak_hata_ozeti
                _debug_bilgisi_yaz(debug_bilgisi)
                break
            except AI2IstekHatasi as hata:
                son_hata_nedeni = hata.hata_nedeni
                uzak_hata_ozeti = str(hata) or "AI2 hatasi."
                hata_debug = dict(hata.debug_bilgisi or debug_bilgisi)
                hata_debug["deneme_sayisi"] = toplam_deneme
                hata_debug["tekil_deneme_no"] = tekil_deneme_no
                _debug_bilgisi_yaz(hata_debug)
                if hata.hata_nedeni == "ai2_timeout" and tekil_deneme_no < max_attempts_per_url:
                    bekleme_suresi = 1.5
                    hata_debug["retry_bekleme_suresi_ms"] = int(bekleme_suresi * 1000)
                    _debug_bilgisi_yaz(hata_debug)
                    time.sleep(bekleme_suresi)
                    continue
                break

    if not ai2_istemcisi["yerel_model_etkin"]:
        final_debug = son_chat_debug_bilgisi_al()
        if son_hata_nedeni and not final_debug.get("hata_nedeni"):
            final_debug["hata_nedeni"] = son_hata_nedeni
            final_debug["hata_mesaji"] = uzak_hata_ozeti
            _debug_bilgisi_yaz(final_debug)
        raise RuntimeError(uzak_hata_ozeti or "AI2 hatasi.")

    try:
        yerel_model = yerel_modeli_al(ai2_istemcisi)
        sunucu_cevabi = yerel_model.create_chat_completion(
            messages=mesajlar,
            temperature=ai2_istemcisi["yerel_sicaklik"],
            max_tokens=max_tokens,
        )
        yanit_metin = _openai_yanitindan_icerik_cikar(sunucu_cevabi)
        if yanit_metin:
            final_debug = son_chat_debug_bilgisi_al()
            final_debug["yerel_model_kullanildi"] = True
            final_debug["content_bos_mu"] = False
            final_debug["content_uzunlugu"] = len(yanit_metin)
            final_debug["ai2_cevap_ozeti"] = _metin_ozeti(yanit_metin)
            _debug_bilgisi_yaz(final_debug)
            return yanit_metin
        raise RuntimeError("Yerel model bos cevap verdi.")
    except Exception as hata:
        final_debug = son_chat_debug_bilgisi_al()
        final_debug["yerel_model_kullanildi"] = True
        final_debug["hata_nedeni"] = final_debug.get("hata_nedeni") or "yerel_model_hatasi"
        final_debug["hata_mesaji"] = str(hata)
        _debug_bilgisi_yaz(final_debug)
        if uzak_hata_ozeti:
            raise RuntimeError(f"{uzak_hata_ozeti} Yerel hata: {hata}") from hata
        raise RuntimeError(f"Yerel hata: {hata}") from hata


__all__ = [
    "ai2_scope_icin_max_token",
    "son_chat_debug_bilgisi_al",
    "ai2_test_modu_aktif",
    "ai2_istemcisini_hazirla",
    "chat",
    "dusunce_etiketlerini_temizle",
    "llm_tamamla",
    "yerel_modeli_al",
]
