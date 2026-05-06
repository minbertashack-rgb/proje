from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request


BASE_DIR = Path(__file__).resolve().parent.parent


def _arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI2 server operasyonel probe")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--istek-arasi-bekleme", type=float, default=0.0)
    parser.add_argument("--json-out", default=str(BASE_DIR / "ai2_server_probe_sonuc.json"))
    parser.add_argument("--text-out", default=str(BASE_DIR / "ai2_server_probe_ozet.txt"))
    return parser


def _powershell_json(command: str):
    tamam = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    text = (tamam.stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _port_ve_process_bilgisi(port: int) -> dict:
    baglanti = _powershell_json(
        f"Get-NetTCPConnection -LocalPort {int(port)} -ErrorAction SilentlyContinue | "
        'Sort-Object @{ Expression = { if ($_.State -eq "Listen") { 0 } else { 1 } } }, OwningProcess | '
        "Select-Object LocalAddress,LocalPort,State,OwningProcess | ConvertTo-Json -Compress"
    )
    kayit = baglanti[0] if isinstance(baglanti, list) and baglanti else baglanti
    if not isinstance(kayit, dict):
        return {
            "process_var_mi": False,
            "port_acik_mi": False,
            "pid": None,
            "state": "",
            "command_line": "",
        }

    pid = int(kayit.get("OwningProcess") or 0) or None
    process = None
    if pid:
        process = _powershell_json(
            f'Get-CimInstance Win32_Process -Filter "ProcessId = {pid}" | '
            "Select-Object ProcessId,Name,CommandLine,CreationDate | ConvertTo-Json -Compress"
        )

    return {
        "process_var_mi": bool(process),
        "port_acik_mi": True,
        "pid": pid,
        "state": str(kayit.get("State") or ""),
        "command_line": str((process or {}).get("CommandLine") or ""),
        "process_name": str((process or {}).get("Name") or ""),
        "creation_date": str((process or {}).get("CreationDate") or ""),
    }


def _models_probe(port: int, timeout_saniye: int) -> dict:
    adres = f"http://127.0.0.1:{int(port)}/v1/models"
    baslangic = time.perf_counter()
    try:
        with urllib.request.urlopen(adres, timeout=max(1, int(timeout_saniye or 5))) as yanit:
            govde = yanit.read().decode("utf-8", errors="replace")
            return {
                "ok": True,
                "adres": adres,
                "status": int(getattr(yanit, "status", 200) or 200),
                "sure_ms": round((time.perf_counter() - baslangic) * 1000, 1),
                "response_body_uzunlugu": len(govde),
            }
    except Exception as exc:
        return {
            "ok": False,
            "adres": adres,
            "status": None,
            "sure_ms": round((time.perf_counter() - baslangic) * 1000, 1),
            "hata": f"{type(exc).__name__}: {exc}",
        }


def _chat_probe(port: int, timeout_saniye: int, etiket: str, prompt_uzunlugu: int, max_tokens: int) -> dict:
    adres = f"http://127.0.0.1:{int(port)}/v1/chat/completions"
    govde = {
        "model": "qwen-docverse",
        "messages": [
            {"role": "system", "content": "Sadece kisa JSON don."},
            {"role": "user", "content": ("JWT token kimlik tasir. " * 200)[: max(80, prompt_uzunlugu)]},
        ],
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "stream": False,
    }

    istek = urllib.request.Request(
        adres,
        data=json.dumps(govde, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    baslangic = time.perf_counter()

    try:
        with urllib.request.urlopen(istek, timeout=max(1, int(timeout_saniye or 20))) as yanit:
            ham = yanit.read().decode("utf-8", errors="replace")
            sure = round((time.perf_counter() - baslangic) * 1000, 1)
            try:
                parsed = json.loads(ham)
            except Exception:
                parsed = {}

            content = ""
            try:
                content = str((((parsed.get("choices") or [{}])[0]).get("message") or {}).get("content") or "")
            except Exception:
                content = ""

            return {
                "etiket": etiket,
                "ok": True,
                "hata_nedeni": "",
                "status": int(getattr(yanit, "status", 200) or 200),
                "sure_ms": sure,
                "response_body_uzunlugu": len(ham),
                "content_uzunlugu": len(content),
                "prompt_uzunlugu": prompt_uzunlugu,
                "max_tokens": max_tokens,
            }
    except urllib.error.HTTPError as exc:
        return {
            "etiket": etiket,
            "ok": False,
            "hata_nedeni": "http_error",
            "status": int(getattr(exc, "code", 0) or 0),
            "sure_ms": round((time.perf_counter() - baslangic) * 1000, 1),
            "prompt_uzunlugu": prompt_uzunlugu,
            "max_tokens": max_tokens,
        }
    except urllib.error.URLError as exc:
        hata = str(getattr(exc, "reason", exc) or "")
        hata_nedeni = "connection_refused" if "10061" in hata else ("timeout" if "timed out" in hata.lower() else "connection_error")
        return {
            "etiket": etiket,
            "ok": False,
            "hata_nedeni": hata_nedeni,
            "status": None,
            "sure_ms": round((time.perf_counter() - baslangic) * 1000, 1),
            "prompt_uzunlugu": prompt_uzunlugu,
            "max_tokens": max_tokens,
        }
    except TimeoutError:
        return {
            "etiket": etiket,
            "ok": False,
            "hata_nedeni": "timeout",
            "status": None,
            "sure_ms": round((time.perf_counter() - baslangic) * 1000, 1),
            "prompt_uzunlugu": prompt_uzunlugu,
            "max_tokens": max_tokens,
        }
    except Exception as exc:
        return {
            "etiket": etiket,
            "ok": False,
            "hata_nedeni": f"{type(exc).__name__}",
            "status": None,
            "sure_ms": round((time.perf_counter() - baslangic) * 1000, 1),
            "prompt_uzunlugu": prompt_uzunlugu,
            "max_tokens": max_tokens,
        }


def _darbogaz_sinifi(baslangic: dict, models: dict, sonuclar: list[dict]) -> str:
    if baslangic.get("process_var_mi") and any(item.get("sonrasi", {}).get("process_var_mi") is False for item in sonuclar if not item.get("ok")):
        return "process_restart_suphesi"

    if any(item.get("hata_nedeni") == "connection_refused" for item in sonuclar[3:]):
        return "ard_isteklerde_baglanti_reddi"

    if sonuclar and sonuclar[2].get("hata_nedeni") == "timeout" and any(item.get("hata_nedeni") in {"connection_refused", "connection_error"} for item in sonuclar[3:]):
        return "uzun_istek_sonrasi_tikanma"

    if sonuclar and sonuclar[0].get("hata_nedeni") == "timeout":
        return "tek_istek_timeout"

    if baslangic.get("process_var_mi") and models.get("ok") and any(item.get("hata_nedeni") == "timeout" for item in sonuclar):
        return "worker_darbogazi_suphesi"

    if baslangic.get("process_var_mi") and not models.get("ok"):
        return "model_yukleme_gecikmesi"

    return "belirsiz_server_kararsizligi"


def _okunur_ozet(rapor: dict) -> str:
    satirlar = [
        "AI2 Server Probe Ozeti",
        "======================",
        f"process_var_mi: {rapor.get('process_var_mi')}",
        f"port_acik_mi: {rapor.get('port_acik_mi')}",
        f"models_ok_mu: {rapor.get('models_ok_mu')}",
        f"kisa_chat_ok_mu: {rapor.get('kisa_chat_ok_mu')}",
        f"orta_chat_ok_mu: {rapor.get('orta_chat_ok_mu')}",
        f"uzun_chat_ok_mu: {rapor.get('uzun_chat_ok_mu')}",
        f"ard_istek_sorunu_var_mi: {rapor.get('ard_istek_sorunu_var_mi')}",
        f"process_coktu_mu: {rapor.get('process_coktu_mu')}",
        f"olasi_darbogaz_sinifi: {rapor.get('olasi_darbogaz_sinifi')}",
        f"istek_arasi_bekleme_saniye: {rapor.get('istek_arasi_bekleme_saniye')}",
        "",
    ]
    for item in rapor.get("chat_sonuclari") or []:
        satirlar.append(
            f"- {item['etiket']}: ok={item['ok']} hata={item.get('hata_nedeni') or 'yok'} sure={item.get('sure_ms')}ms process_sonrasi={item.get('sonrasi', {}).get('process_var_mi')}"
        )
    return "\n".join(satirlar).strip() + "\n"


def main() -> int:
    args = _arg_parser().parse_args()
    json_out = Path(args.json_out)
    text_out = Path(args.text_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    text_out.parent.mkdir(parents=True, exist_ok=True)

    baslangic = _port_ve_process_bilgisi(args.port)
    models = _models_probe(args.port, min(8, args.timeout))

    senaryolar = [
        ("kisa_chat", 120, 32),
        ("orta_chat", 600, 64),
        ("uzun_chat", 1200, 96),
        ("ardisik_chat_1", 120, 32),
        ("ardisik_chat_2", 120, 32),
    ]

    chat_sonuclari = []
    for etiket, prompt_uzunlugu, max_tokens in senaryolar:
        sonuc = _chat_probe(args.port, args.timeout, etiket, prompt_uzunlugu, max_tokens)
        sonuc["sonrasi"] = _port_ve_process_bilgisi(args.port)
        chat_sonuclari.append(sonuc)
        if args.istek_arasi_bekleme > 0:
            time.sleep(args.istek_arasi_bekleme)

    refused_item = next((item for item in chat_sonuclari if item.get("hata_nedeni") == "connection_refused"), None)

    rapor = {
        **baslangic,
        "models_probe": models,
        "models_ok_mu": bool(models.get("ok")),
        "chat_sonuclari": chat_sonuclari,
        "kisa_chat_ok_mu": bool(chat_sonuclari[0].get("ok")) if chat_sonuclari else False,
        "orta_chat_ok_mu": bool(chat_sonuclari[1].get("ok")) if len(chat_sonuclari) > 1 else False,
        "uzun_chat_ok_mu": bool(chat_sonuclari[2].get("ok")) if len(chat_sonuclari) > 2 else False,
        "ard_istek_sorunu_var_mi": any(item.get("hata_nedeni") in {"connection_refused", "connection_error", "timeout"} for item in chat_sonuclari[3:]),
        "process_coktu_mu": bool(baslangic.get("process_var_mi")) and any(item.get("sonrasi", {}).get("process_var_mi") is False for item in chat_sonuclari if not item.get("ok")),
        "connection_refused_sonrasi_process_durumu": (refused_item or {}).get("sonrasi") or {},
        "istek_arasi_bekleme_saniye": args.istek_arasi_bekleme,
    }
    rapor["olasi_darbogaz_sinifi"] = _darbogaz_sinifi(baslangic, models, chat_sonuclari)

    json_out.write_text(json.dumps(rapor, ensure_ascii=False, indent=2), encoding="utf-8")
    text_out.write_text(_okunur_ozet(rapor), encoding="utf-8")
    print(_okunur_ozet(rapor))
    print(f"JSON rapor: {json_out}")
    print(f"Yazi ozeti: {text_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
