#!/usr/bin/env python3
"""Release preflight environment and portability checks.

Run: python tools/release_checks.py
Exits with 0 if no blockers are found, non-zero otherwise.
"""
from __future__ import annotations

import importlib
import re
import os
import platform
import shutil
import subprocess
import json
import sys
from pathlib import Path


def check_python_version(min_major=3, min_minor=10):
    v = sys.version_info
    ok = (v.major, v.minor) >= (min_major, min_minor)
    return ok, f"{v.major}.{v.minor}.{v.micro}"


def which_or_env(cmd_name: str, env_var: str | None = None) -> str | None:
    if env_var:
        candidate = os.getenv(env_var)
        if candidate:
            return candidate
    exe = shutil.which(cmd_name)
    return exe


def find_gguf_candidates(repo_root: Path) -> list[Path]:
    candidates = []
    env_paths = [os.getenv("DOCVERSE_GGUF_PATH"), os.getenv("ANA_GGUF_YOLU"), os.getenv("YEREL_MODEL_YOLU"), os.getenv("LLM_MODEL_PATH")]
    for p in env_paths:
        if p:
            candidates.append(Path(p))
    # search models dir for .gguf
    for p in (repo_root / "models").glob("*.gguf"):
        candidates.append(p)
    return [p for p in candidates if p]


def settings_windows_path_warnings(settings_path: Path) -> list[str]:
    warnings = []
    try:
        text = settings_path.read_text(encoding="utf-8")
    except Exception:
        return warnings
    # naive heuristics: absolute Windows drive letters or backslashes in default DB/TESSERACT
    # find and show offending lines (limited)
    lines = text.splitlines()
    hits = []
    for i, ln in enumerate(lines, start=1):
        if "\\\\" in ln or ":\\" in ln or "C:\\" in ln:
            snippet = ln.strip()
            if len(snippet) > 240:
                snippet = snippet[:240] + "..."
            hits.append(f"L{i}: {snippet}")
            if len(hits) >= 5:
                break
    if hits:
        warnings.append("settings.py appears to include Windows-style absolute paths (examples: %s)" % ("; ".join(hits)))
    return warnings


def load_project_settings():
    module_name = "dokuman_asistani.settings"
    if module_name in sys.modules:
        return sys.modules[module_name]
    return importlib.import_module(module_name)


def classify_check(key: str, status: str, summary: str, detail: str = "", recommendation: str = "") -> dict:
    return {
        "key": key,
        "status": status,
        "summary": summary,
        "detail": detail,
        "recommendation": recommendation,
    }


def get_tesseract_probe(env: dict, settings_module) -> dict:
    tesseract_env = env.get("TESSERACT_CMD")
    tesseract_which = which_or_env("tesseract")
    candidate = tesseract_env or tesseract_which or getattr(settings_module, "TESSERACT_CMD", "")
    if tesseract_env:
        source = "env:TESSERACT_CMD"
    elif tesseract_which:
        source = "which:path"
    elif candidate:
        source = "settings:TESSERACT_CMD"
    else:
        source = "none"

    langs: list[str] = []
    status = "missing"
    if candidate and Path(candidate).exists():
        try:
            subprocess.run([candidate, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            p = subprocess.run([candidate, "--list-langs"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            out = p.stdout.strip() or p.stderr.strip()
            langs = [ln.strip() for ln in out.splitlines() if ln.strip() and len(ln.strip()) <= 10]
            required_langs = set(str(getattr(settings_module, "OCR_LANG", "tur+eng")).split("+"))
            status = "ready" if required_langs.issubset(set(langs)) else "partial"
        except Exception:
            status = "partial"

    return {
        "status": status,
        "candidate": candidate,
        "source": source,
        "langs": langs,
    }


def _is_default_secret(secret_key: str, env: dict) -> bool:
    if not env.get("DJANGO_SECRET_KEY"):
        return True
    return str(secret_key or "").strip() == "gecici-gelistirme-anahtari-degistir"


def _valid_throttle_rate(value: str) -> bool:
    return bool(re.match(r"^\d+/(sec|second|s|min|minute|m|hour|h|day|d)$", str(value or "").strip(), re.IGNORECASE))


def build_release_checks_report(repo_root: Path, env: dict | None = None, settings_module=None) -> dict:
    env = dict(env or os.environ)
    settings_module = settings_module or load_project_settings()

    checks: list[dict] = []
    warnings: list[str] = []
    critical_issues: list[str] = []

    ok, pyver = check_python_version()
    checks.append(
        classify_check(
            "python_version",
            "ok" if ok else "blocker",
            f"Python version {pyver}",
            "Minimum required version is 3.10.",
            "Use Python 3.10+." if not ok else "",
        )
    )

    if getattr(settings_module, "DEBUG", False):
        checks.append(
            classify_check(
                "debug_mode",
                "blocker",
                "DEBUG acik gorunuyor.",
                "Production-safe release icin DEBUG=False olmali.",
                "DJANGO_DEBUG=0 kullanin.",
            )
        )
    else:
        checks.append(classify_check("debug_mode", "ok", "DEBUG kapali.", "Production debug gate temiz."))

    if _is_default_secret(str(getattr(settings_module, "SECRET_KEY", "")), env):
        checks.append(
            classify_check(
                "secret_key",
                "blocker",
                "Varsayilan veya eksik DJANGO_SECRET_KEY tespit edildi.",
                "Default gelistirme anahtari release icin uygun degil.",
                "DJANGO_SECRET_KEY ortam degiskeni ile guclu bir key verin.",
            )
        )
    else:
        checks.append(classify_check("secret_key", "ok", "DJANGO_SECRET_KEY override edilmis."))

    upload_min = int(getattr(settings_module, "DOCVERSE_UPLOAD_MIN_BYTES", 0) or 0)
    upload_max = int(getattr(settings_module, "DOCVERSE_UPLOAD_MAX_BYTES", 0) or 0)
    if upload_min < 0 or upload_max <= 0 or upload_min >= upload_max:
        checks.append(
            classify_check(
                "upload_limits",
                "blocker",
                "Upload byte limitleri gecersiz.",
                f"min={upload_min} max={upload_max}",
                "DOCVERSE_UPLOAD_MIN_BYTES ve DOCVERSE_UPLOAD_MAX_BYTES degerlerini duzeltin.",
            )
        )
    elif upload_max > 50 * 1024 * 1024:
        checks.append(
            classify_check(
                "upload_limits",
                "warning",
                "Upload max byte limiti oldukca yuksek.",
                f"min={upload_min} max={upload_max}",
                "Gereksiz buyuk upload'lar abuse riskini artirir.",
            )
        )
    else:
        checks.append(
            classify_check(
                "upload_limits",
                "ok",
                "Upload byte limitleri makul gorunuyor.",
                f"min={upload_min} max={upload_max}",
            )
        )

    throttle_rates = dict(((getattr(settings_module, "REST_FRAMEWORK", {}) or {}).get("DEFAULT_THROTTLE_RATES", {}) or {}))
    required_throttle_keys = (
        "token_obtain",
        "token_refresh",
        "upload",
        "anlamadim",
        "kanitli_cevap",
        "notes_write",
    )
    missing_keys = [key for key in required_throttle_keys if not throttle_rates.get(key)]
    invalid_rates = [f"{key}={throttle_rates.get(key)}" for key in required_throttle_keys if throttle_rates.get(key) and not _valid_throttle_rate(throttle_rates.get(key))]
    if missing_keys or invalid_rates:
        parts = []
        if missing_keys:
            parts.append("missing=" + ",".join(missing_keys))
        if invalid_rates:
            parts.append("invalid=" + ",".join(invalid_rates))
        checks.append(
            classify_check(
                "throttle_rates",
                "blocker",
                "Throttle ayarlari eksik veya gecersiz.",
                " ".join(parts),
                "Riskli yuzey throttle rate'lerini settings/env uzerinden tamamlayin.",
            )
        )
    else:
        checks.append(
            classify_check(
                "throttle_rates",
                "ok",
                "Riskli yuzey throttle rate'leri tanimli.",
                ", ".join(f"{key}={throttle_rates[key]}" for key in required_throttle_keys),
            )
        )

    tesseract_probe = get_tesseract_probe(env, settings_module)
    if tesseract_probe["status"] == "ready":
        checks.append(
            classify_check(
                "tesseract",
                "ok",
                "Tesseract hazir.",
                f"candidate={tesseract_probe['candidate']} langs={','.join(tesseract_probe['langs'])}",
            )
        )
    elif tesseract_probe["status"] == "partial":
        checks.append(
            classify_check(
                "tesseract",
                "warning",
                "Tesseract bulundu ama OCR kapsami kismi.",
                f"candidate={tesseract_probe['candidate']} langs={','.join(tesseract_probe['langs'])}",
                "OCR acceptance kosusundan once dil paketlerini ve binary erisimini dogrulayin.",
            )
        )
    else:
        checks.append(
            classify_check(
                "tesseract",
                "warning",
                "Tesseract bulunamadi.",
                "OCR acceptance ve smoke akislari skip veya ops note uretebilir.",
                "TESSERACT_CMD verin veya tesseract'i PATH'e ekleyin.",
            )
        )

    ggufs = find_gguf_candidates(repo_root)
    ai2_base_url = str(getattr(settings_module, "AI2_TABAN_ADRESI", "") or "").strip()
    ai2_model = str(getattr(settings_module, "AI2_MODEL_ADI", "") or "").strip()
    ai2_timeout = int(getattr(settings_module, "AI2_ZAMAN_ASIMI", 0) or 0)
    if ai2_timeout <= 0:
        checks.append(
            classify_check(
                "ai2_runtime",
                "blocker",
                "AI2 timeout gecersiz.",
                f"base_url={ai2_base_url} model={ai2_model} timeout={ai2_timeout}",
                "AI2_ZAMAN_ASIMI / AI2_TIMEOUT pozitif olmali.",
            )
        )
    elif not ai2_model:
        checks.append(
            classify_check(
                "ai2_runtime",
                "blocker",
                "AI2 model alias bos.",
                f"base_url={ai2_base_url} timeout={ai2_timeout}",
                "AI2_MODEL_ADI veya AI2_MODEL saglayin.",
            )
        )
    elif ai2_base_url.startswith("http://127.0.0.1:8002") and not (env.get("AI2_TABAN_ADRESI") or env.get("AI2_BASE_URL")):
        checks.append(
            classify_check(
                "ai2_runtime",
                "warning",
                "AI2 base URL implicit localhost varsayiminda.",
                f"base_url={ai2_base_url} model={ai2_model} timeout={ai2_timeout}",
                "Release ortami icin AI2_TABAN_ADRESI / AI2_BASE_URL acik verilmeli.",
            )
        )
    else:
        checks.append(
            classify_check(
                "ai2_runtime",
                "ok",
                "AI2 base URL / model / timeout tanimli.",
                f"base_url={ai2_base_url} model={ai2_model} timeout={ai2_timeout}",
            )
        )

    if ggufs:
        checks.append(
            classify_check(
                "local_model",
                "ok",
                "GGUF adaylari bulundu.",
                ", ".join(str(p) for p in ggufs[:3]),
            )
        )
    elif getattr(settings_module, "YEREL_MODEL_ETKIN", False):
        checks.append(
            classify_check(
                "local_model",
                "warning",
                "Yerel model etkin ama GGUF adayi bulunamadi.",
                "Local fallback smoke ve benchmark kosulari ops note uretebilir.",
                "DOCVERSE_GGUF_PATH veya ilgili env'leri ayarlayin.",
            )
        )
    else:
        checks.append(classify_check("local_model", "ok", "Yerel model fallback zorunlu degil veya devre disi."))

    if getattr(settings_module, "CORS_ALLOW_ALL_ORIGINS", False):
        checks.append(
            classify_check(
                "cors_policy",
                "warning",
                "CORS_ALLOW_ALL_ORIGINS=True.",
                "Bu ayar release oncesi bilincli gozden gecirilmeli.",
                "Mumkunse izin verilen originleri sinirlayin.",
            )
        )
    else:
        checks.append(classify_check("cors_policy", "ok", "CORS allow-all kapali."))

    access_lifetime = ((getattr(settings_module, "SIMPLE_JWT", {}) or {}).get("ACCESS_TOKEN_LIFETIME"))
    refresh_lifetime = ((getattr(settings_module, "SIMPLE_JWT", {}) or {}).get("REFRESH_TOKEN_LIFETIME"))
    if access_lifetime is None or refresh_lifetime is None:
        checks.append(
            classify_check(
                "jwt_policy",
                "warning",
                "SIMPLE_JWT lifetime ayarlari eksik gorunuyor.",
                "Auth release davranisi explicit olmayabilir.",
                "ACCESS_TOKEN_LIFETIME ve REFRESH_TOKEN_LIFETIME degerlerini teyit edin.",
            )
        )
    else:
        checks.append(classify_check("jwt_policy", "ok", "SIMPLE_JWT lifetime ayarlari tanimli."))

    settings_path = repo_root / "dokuman_asistani" / "settings.py"
    for warning in settings_windows_path_warnings(settings_path):
        checks.append(
            classify_check(
                "portability_paths",
                "warning",
                "Windows-style path heuristigi bulundu.",
                warning,
                "Explicit env path stratejisi tercih edilmeli.",
            )
        )

    # PyMuPDF / fitz
    try:
        import fitz  # type: ignore
        pymupdf_available = True
        pymupdf_note = getattr(fitz, "__doc__", "unknown")
    except Exception:
        pymupdf_available = False
        pymupdf_note = ""
        checks.append(
            classify_check(
                "pymupdf",
                "warning",
                "PyMuPDF (fitz) import edilemedi.",
                "PDF parsing fallback veya ops note uretebilir.",
                "pymupdf kurulumunu teyit edin.",
            )
        )

    for check in checks:
        if check["status"] == "blocker":
            critical_issues.append(f"{check['key']}: {check['summary']}")
        elif check["status"] == "warning":
            warnings.append(f"{check['key']}: {check['summary']}")

    blocker_count = sum(1 for item in checks if item["status"] == "blocker")
    warning_count = sum(1 for item in checks if item["status"] == "warning")
    ok_count = sum(1 for item in checks if item["status"] == "ok")
    if blocker_count > 0:
        config_recommendation = "no_ship"
        overall_status = "blocker"
    elif warning_count > 0:
        config_recommendation = "ship_with_ops_note"
        overall_status = "warning"
    else:
        config_recommendation = "ship"
        overall_status = "ok"

    report = {
        "python_version": pyver,
        "platform": platform.platform(),
        "tesseract": tesseract_probe["status"],
        "tesseract_candidate": tesseract_probe["candidate"],
        "tesseract_source": tesseract_probe["source"],
        "tesseract_langs": tesseract_probe["langs"],
        "pymupdf": pymupdf_available,
        "pymupdf_note": pymupdf_note,
        "gguf_candidates": [str(p) for p in ggufs],
        "ai2_candidate": ai2_base_url,
        "ai2_env": env.get("AI2_TABAN_ADRESI") or env.get("AI2_BASE_URL"),
        "ai2_model": ai2_model,
        "ai2_timeout": ai2_timeout,
        "debug": bool(getattr(settings_module, "DEBUG", False)),
        "upload_limits": {
            "min_bytes": upload_min,
            "max_bytes": upload_max,
        },
        "throttle_rates": throttle_rates,
        "warnings": warnings,
        "critical_issues": critical_issues,
        "checks": checks,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "ok_count": ok_count,
        "overall_status": overall_status,
        "config_recommendation": config_recommendation,
    }

    local_model_available = bool(ggufs)
    remote_ai_available = bool(ai2_base_url)
    if local_model_available and remote_ai_available:
        report["ai_model_mode"] = "both"
    elif local_model_available:
        report["ai_model_mode"] = "local"
    elif remote_ai_available:
        report["ai_model_mode"] = "remote"
    else:
        report["ai_model_mode"] = "none"
    report["local_model_enabled"] = getattr(settings_module, "YEREL_MODEL_ETKIN", None) or env.get("YEREL_MODEL_ETKIN") or env.get("LLM_ENABLED")
    return report


def render_release_checks_text(report: dict) -> str:
    lines = [
        "Release Config Summary",
        f"Config recommendation: {report.get('config_recommendation', 'unknown')}",
        f"Overall status: {report.get('overall_status', 'unknown')}",
        f"Checks: ok={report.get('ok_count', 0)} warning={report.get('warning_count', 0)} blocker={report.get('blocker_count', 0)}",
        "",
        "Checklist:",
    ]
    for check in report.get("checks", []):
        detail = f" | {check['detail']}" if check.get("detail") else ""
        recommendation = f" | action={check['recommendation']}" if check.get("recommendation") else ""
        lines.append(f"- [{check['status']}] {check['key']}: {check['summary']}{detail}{recommendation}")
    lines.append("")
    lines.append("Final decision glue:")
    lines.append("- Final release karari icin bu config recommendation sonucu, release gate acceptance summary ile birlikte okunur.")
    lines.append("- Taraflardan biri no_ship ise final karar no_ship olur.")
    lines.append("- Hic no_ship yok ama herhangi biri ship_with_ops_note ise final karar ship_with_ops_note olur.")
    lines.append("- Iki taraf da ship ise final karar ship olur.")
    return "\n".join(lines) + "\n"


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    print("Release preflight: environment and portability checks")
    print("Repository:", repo_root)

    report = build_release_checks_report(repo_root=repo_root)

    print("\nSummary:")
    print(f"Config recommendation: {report['config_recommendation']}")
    print(f"Overall status: {report['overall_status']}")
    if report["critical_issues"]:
        print("Blockers:")
        for c in report["critical_issues"]:
            print(" -", c)
    else:
        print("No blockers found.")

    if report["warnings"]:
        print("Warnings / ops notes:")
        for w in report["warnings"]:
            print(" -", w)
    else:
        print("No warnings.")

    try:
        out_path = repo_root / "release_checks_report.json"
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Wrote report:", out_path)
        text_path = repo_root / "release_checks_summary.txt"
        text_path.write_text(render_release_checks_text(report), encoding="utf-8")
        print("Wrote summary:", text_path)
    except Exception:
        print("Failed to write release checks artifacts")

    return 1 if report["critical_issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
