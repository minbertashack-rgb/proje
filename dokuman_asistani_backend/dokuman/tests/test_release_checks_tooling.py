from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tools import release_checks


def _settings(**overrides):
    defaults = {
        "DEBUG": False,
        "SECRET_KEY": "super-secret",
        "DOCVERSE_UPLOAD_MIN_BYTES": 8,
        "DOCVERSE_UPLOAD_MAX_BYTES": 25 * 1024 * 1024,
        "REST_FRAMEWORK": {
            "DEFAULT_THROTTLE_RATES": {
                "token_obtain": "10/min",
                "token_refresh": "20/min",
                "upload": "20/min",
                "anlamadim": "30/min",
                "kanitli_cevap": "20/min",
                "notes_write": "40/min",
            }
        },
        "TESSERACT_CMD": "",
        "OCR_LANG": "tur+eng",
        "AI2_TABAN_ADRESI": "http://127.0.0.1:8002/v1",
        "AI2_MODEL_ADI": "qwen-docverse",
        "AI2_ZAMAN_ASIMI": 600,
        "YEREL_MODEL_ETKIN": True,
        "CORS_ALLOW_ALL_ORIGINS": False,
        "SIMPLE_JWT": {
            "ACCESS_TOKEN_LIFETIME": object(),
            "REFRESH_TOKEN_LIFETIME": object(),
        },
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_release_checks_report_becomes_no_ship_for_debug_and_default_secret(monkeypatch):
    monkeypatch.setattr(release_checks, "find_gguf_candidates", lambda repo_root: [])
    monkeypatch.setattr(release_checks, "settings_windows_path_warnings", lambda settings_path: [])
    monkeypatch.setattr(release_checks, "get_tesseract_probe", lambda env, settings_module: {"status": "missing", "candidate": "", "source": "none", "langs": []})

    report = release_checks.build_release_checks_report(
        repo_root=Path("."),
        env={},
        settings_module=_settings(DEBUG=True, SECRET_KEY="gecici-gelistirme-anahtari-degistir"),
    )

    assert report["config_recommendation"] == "no_ship"
    assert report["blocker_count"] >= 2
    assert any(item["key"] == "debug_mode" and item["status"] == "blocker" for item in report["checks"])
    assert any(item["key"] == "secret_key" and item["status"] == "blocker" for item in report["checks"])


def test_release_checks_report_marks_ship_with_ops_note_for_missing_tesseract(monkeypatch):
    monkeypatch.setattr(release_checks, "find_gguf_candidates", lambda repo_root: [Path("models/demo.gguf")])
    monkeypatch.setattr(release_checks, "settings_windows_path_warnings", lambda settings_path: [])
    monkeypatch.setattr(release_checks, "get_tesseract_probe", lambda env, settings_module: {"status": "missing", "candidate": "", "source": "none", "langs": []})

    report = release_checks.build_release_checks_report(
        repo_root=Path("."),
        env={"DJANGO_SECRET_KEY": "set"},
        settings_module=_settings(),
    )

    assert report["config_recommendation"] == "ship_with_ops_note"
    assert report["blocker_count"] == 0
    assert report["warning_count"] >= 1
    assert any(item["key"] == "tesseract" and item["status"] == "warning" for item in report["checks"])


def test_release_checks_report_flags_invalid_throttle_rate(monkeypatch):
    monkeypatch.setattr(release_checks, "find_gguf_candidates", lambda repo_root: [Path("models/demo.gguf")])
    monkeypatch.setattr(release_checks, "settings_windows_path_warnings", lambda settings_path: [])
    monkeypatch.setattr(
        release_checks,
        "get_tesseract_probe",
        lambda env, settings_module: {"status": "ready", "candidate": "tesseract", "source": "which:path", "langs": ["tur", "eng"]},
    )

    report = release_checks.build_release_checks_report(
        repo_root=Path("."),
        env={"DJANGO_SECRET_KEY": "set"},
        settings_module=_settings(
            REST_FRAMEWORK={
                "DEFAULT_THROTTLE_RATES": {
                    "token_obtain": "10/min",
                    "token_refresh": "broken-rate",
                    "upload": "20/min",
                    "anlamadim": "30/min",
                    "kanitli_cevap": "20/min",
                    "notes_write": "40/min",
                }
            }
        ),
    )

    assert report["config_recommendation"] == "no_ship"
    assert any(item["key"] == "throttle_rates" and item["status"] == "blocker" for item in report["checks"])
