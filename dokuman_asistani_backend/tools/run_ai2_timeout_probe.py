from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dokuman_asistani.settings")

import django

django.setup()

from django.test.utils import override_settings

from dokuman.ai2.llm import ai2_istemcisini_hazirla, chat, son_chat_debug_bilgisi_al


def _arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI2 timeout profil araci")
    parser.add_argument("--mode", choices=("smoke", "detailed"), default="smoke")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--long-timeout", type=int, default=45)
    parser.add_argument("--json-out", default=str(BASE_DIR / "ai2_timeout_probe_sonuc.json"))
    parser.add_argument("--text-out", default=str(BASE_DIR / "ai2_timeout_probe_ozet.txt"))
    return parser


def _user_icerigi(parca_uzunlugu: int) -> str:
    govde = (
        "Bu metni sadece JSON olarak kisaca ozetle. "
        "Yanitta 'one_liner' ve 'very_simple' anahtarlarini kullan. "
        "Metin: "
        + ("JWT token kimlik tasir ve sure bitince refresh token ile yenilenir. " * max(1, parca_uzunlugu // 70))
    )
    return govde[: max(120, parca_uzunlugu)]


def _mesajlar(parca_uzunlugu: int) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "Sadece JSON don. "
                '{"one_liner":"string","very_simple":"string"}'
            ),
        },
        {
            "role": "user",
            "content": _user_icerigi(parca_uzunlugu),
        },
    ]


def _preflight(timeout_saniye: int) -> dict:
    istemci = ai2_istemcisini_hazirla()
    aday_adres = str((istemci.get("aday_adresler") or [""])[0] or "")
    parsed = urlparse(aday_adres)
    host = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or (443 if parsed.scheme == "https" else 80))
    models_adresi = f"{parsed.scheme or 'http'}://{host}:{port}/v1/models"
    baslangic = time.perf_counter()
    try:
        with urllib.request.urlopen(models_adresi, timeout=max(1, int(timeout_saniye or 5))) as yanit:
            status = int(getattr(yanit, "status", 200) or 200)
            govde = yanit.read().decode("utf-8", errors="replace")
        return {
            "ok": True,
            "adres": models_adresi,
            "status": status,
            "preflight_suresi_ms": round((time.perf_counter() - baslangic) * 1000, 1),
            "response_body_uzunlugu": len(govde),
        }
    except Exception as exc:
        return {
            "ok": False,
            "adres": models_adresi,
            "status": None,
            "preflight_suresi_ms": round((time.perf_counter() - baslangic) * 1000, 1),
            "hata": f"{type(exc).__name__}: {exc}",
        }


def _tek_chat_deneme(
    *,
    senaryo_adi: str,
    parca_uzunlugu: int,
    max_tokens: int,
    timeout_saniye: int,
    ai2_test_modu: bool,
) -> dict:
    mesajlar = _mesajlar(parca_uzunlugu)
    baslangic = time.perf_counter()
    with override_settings(
        AI2_ZAMAN_ASIMI=max(1, int(timeout_saniye or 20)),
        AI2_TEST_MODU=bool(ai2_test_modu),
        YEREL_MODEL_ETKIN=False,
    ):
        try:
            yanit = chat(mesajlar, max_tokens=max_tokens)
            durum = "basarili"
            hata = ""
        except Exception as exc:
            yanit = ""
            durum = "hata"
            hata = f"{type(exc).__name__}: {exc}"
        debug = son_chat_debug_bilgisi_al()

    toplam_sure = round((time.perf_counter() - baslangic) * 1000, 1)
    return {
        "senaryo": senaryo_adi,
        "durum": durum,
        "hata": hata,
        "yanit_uzunlugu": len(yanit or ""),
        "toplam_olcum_suresi_ms": toplam_sure,
        "debug_ai2": debug,
    }


def _warmup_ve_asil_deneme(timeout_saniye: int) -> dict:
    warmup = _tek_chat_deneme(
        senaryo_adi="warmup",
        parca_uzunlugu=80,
        max_tokens=24,
        timeout_saniye=min(12, max(6, timeout_saniye)),
        ai2_test_modu=False,
    )
    asil = _tek_chat_deneme(
        senaryo_adi="warmup_sonrasi_orta",
        parca_uzunlugu=700,
        max_tokens=96,
        timeout_saniye=timeout_saniye,
        ai2_test_modu=False,
    )
    return {"warmup": warmup, "asil": asil}


def _profil_sinifi(sonuclar: list[dict], warmup: dict, timeout_saniye: int, long_timeout_saniye: int) -> list[str]:
    etiketler: list[str] = []
    sonuclar_map = {item["senaryo"]: item for item in sonuclar}

    kisa_20 = sonuclar_map.get(f"normal_kisa_{timeout_saniye}", {})
    orta_20 = sonuclar_map.get(f"normal_orta_{timeout_saniye}", {})
    uzun_20 = sonuclar_map.get(f"normal_uzun_{timeout_saniye}", {})
    kisa_45 = sonuclar_map.get(f"normal_kisa_{long_timeout_saniye}", {})
    test_kisa = sonuclar_map.get(f"test_kisa_{timeout_saniye}", {})
    seri_1 = sonuclar_map.get("seri_kisa_1", {})
    seri_2 = sonuclar_map.get("seri_kisa_2", {})
    seri_3 = sonuclar_map.get("seri_kisa_3", {})

    if kisa_20.get("debug_ai2", {}).get("hata_nedeni") == "ai2_timeout":
        if kisa_45.get("durum") == "basarili":
            etiketler.append("timeout_degeri_yetersiz")
        if warmup.get("asil", {}).get("durum") == "basarili":
            etiketler.append("cold_start_suphesi")

    hizli_baglanti_hatasi = any(
        item.get("debug_ai2", {}).get("hata_nedeni") == "ai2_connection_error"
        and float(item.get("debug_ai2", {}).get("toplam_cevap_suresi_ms") or 0) <= 5000
        for item in sonuclar
    )
    if kisa_20.get("debug_ai2", {}).get("hata_nedeni") == "ai2_timeout" and hizli_baglanti_hatasi:
        etiketler.append("kuyruklanma_suphesi")

    if orta_20.get("debug_ai2", {}).get("hata_nedeni") == "ai2_timeout" and kisa_20.get("durum") == "basarili":
        etiketler.append("prompt_agirligi_suphesi")

    if uzun_20.get("debug_ai2", {}).get("hata_nedeni") == "ai2_timeout" and orta_20.get("durum") == "basarili":
        etiketler.append("token_butcesi_suphesi")

    if (
        seri_1.get("durum") == "basarili"
        and (
            seri_2.get("debug_ai2", {}).get("hata_nedeni") == "ai2_timeout"
            or seri_3.get("debug_ai2", {}).get("hata_nedeni") == "ai2_timeout"
        )
    ):
        etiketler.append("kuyruklanma_suphesi")

    if test_kisa.get("durum") == "basarili" and kisa_20.get("debug_ai2", {}).get("hata_nedeni") == "ai2_timeout":
        etiketler.append("ai2_test_modu_farki")

    if not etiketler and any(item.get("debug_ai2", {}).get("hata_nedeni") == "ai2_timeout" for item in sonuclar):
        etiketler.append("belirsiz_timeout")

    return etiketler


def _okunur_ozet(rapor: dict) -> str:
    satirlar = [
        "AI2 Timeout Probe Ozeti",
        "=======================",
        "",
        f"Preflight: {'OK' if rapor['preflight'].get('ok') else 'HATA'}",
        f"Preflight sure: {rapor['preflight'].get('preflight_suresi_ms')} ms",
        f"Timeout siniflari: {', '.join(rapor.get('timeout_siniflari') or ['yok'])}",
        "",
        "Senaryolar:",
    ]

    for item in rapor.get("sonuclar") or []:
        debug = item.get("debug_ai2") or {}
        satirlar.append(
            "- {senaryo}: {durum} | hata_nedeni={hata_nedeni} | ilk={ilk} ms | toplam={toplam} ms | prompt={prompt} | token={token}".format(
                senaryo=item.get("senaryo"),
                durum=item.get("durum"),
                hata_nedeni=debug.get("hata_nedeni") or "yok",
                ilk=debug.get("ilk_cevap_suresi_ms"),
                toplam=debug.get("toplam_cevap_suresi_ms"),
                prompt=debug.get("prompt_tahmini_uzunluk"),
                token=debug.get("max_tokens"),
            )
        )

    satirlar.append("")
    satirlar.append("Warm-up Karsilastirmasi:")
    warmup = rapor.get("warmup") or {}
    satirlar.append(
        f"- warmup: {warmup.get('warmup', {}).get('durum')} / {warmup.get('warmup', {}).get('debug_ai2', {}).get('hata_nedeni') or 'yok'}"
    )
    satirlar.append(
        f"- warmup_sonrasi_orta: {warmup.get('asil', {}).get('durum')} / {warmup.get('asil', {}).get('debug_ai2', {}).get('hata_nedeni') or 'yok'}"
    )
    return "\n".join(satirlar).strip() + "\n"


def main() -> int:
    args = _arg_parser().parse_args()
    json_out = Path(args.json_out)
    text_out = Path(args.text_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    text_out.parent.mkdir(parents=True, exist_ok=True)

    preflight = _preflight(args.timeout)

    senaryolar = [
        (f"normal_kisa_{args.timeout}", 140, 48, args.timeout, False),
        (f"normal_orta_{args.timeout}", 700, 96, args.timeout, False),
        (f"normal_uzun_{args.timeout}", 1350, 160 if args.mode == "detailed" else 128, args.timeout, False),
        (f"normal_kisa_{args.long_timeout}", 140, 48, args.long_timeout, False),
        ("seri_kisa_1", 140, 48, args.timeout, False),
        ("seri_kisa_2", 140, 48, args.timeout, False),
    ]
    if args.mode == "detailed":
        senaryolar.extend(
            [
                (f"test_kisa_{args.timeout}", 140, 48, args.timeout, True),
                ("seri_kisa_3", 140, 48, args.timeout, False),
            ]
        )

    sonuclar = [
        _tek_chat_deneme(
            senaryo_adi=senaryo_adi,
            parca_uzunlugu=parca_uzunlugu,
            max_tokens=max_tokens,
            timeout_saniye=timeout_saniye,
            ai2_test_modu=ai2_test_modu,
        )
        for senaryo_adi, parca_uzunlugu, max_tokens, timeout_saniye, ai2_test_modu in senaryolar
    ]

    warmup = _warmup_ve_asil_deneme(args.timeout)
    timeout_siniflari = _profil_sinifi(sonuclar, warmup, args.timeout, args.long_timeout)

    rapor = {
        "preflight": preflight,
        "sonuclar": sonuclar,
        "warmup": warmup,
        "timeout_siniflari": timeout_siniflari,
    }

    json_out.write_text(json.dumps(rapor, ensure_ascii=False, indent=2), encoding="utf-8")
    text_out.write_text(_okunur_ozet(rapor), encoding="utf-8")
    print(_okunur_ozet(rapor))
    print(f"JSON rapor: {json_out}")
    print(f"Yazi ozeti: {text_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
