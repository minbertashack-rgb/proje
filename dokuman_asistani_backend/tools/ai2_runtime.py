from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8002"
DEFAULT_ALIAS = "qwen-docverse"
PREFERRED_QWEN_Q5_MODEL = REPO_ROOT / "models" / "Qwen2.5-7B-Instruct-Q5_K_M.gguf"
LEGACY_QWEN_Q4_MODEL = REPO_ROOT / "models" / "Qwen2.5-7B-Instruct-Q4_K_S.gguf"
FALLBACK_DEEPSEEK_MODEL = REPO_ROOT / "models" / "DeepSeek-R1-Distill-Qwen-7B-Q6_K_L.gguf"
DEFAULT_STDOUT = REPO_ROOT / "ai2_server_runtime.out.log"
DEFAULT_STDERR = REPO_ROOT / "ai2_server_runtime.err.log"


def _default_model_candidates() -> list[Path]:
    return [
        PREFERRED_QWEN_Q5_MODEL,
        LEGACY_QWEN_Q4_MODEL,
        FALLBACK_DEEPSEEK_MODEL,
    ]


def resolve_default_model_path() -> Path:
    for candidate in _default_model_candidates():
        if candidate.exists():
            return candidate
    return _default_model_candidates()[0]


DEFAULT_MODEL = resolve_default_model_path()


def _tail_text(path: Path, line_count: int = 40) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-line_count:])


def _models_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/v1/models"


def _last_nonempty_line(text: str) -> str:
    for line in reversed((text or "").splitlines()):
        line = str(line).strip()
        if line:
            return line
    return ""


def _infer_load_stage(stderr_text: str, stdout_text: str) -> str:
    haystack = f"{stderr_text}\n{stdout_text}".lower()
    if "model path does not exist" in haystack:
        return "model_path_validation"
    if "error loading model" in haystack or "failed to load model" in haystack:
        return "model_open_failed"
    if "uvicorn running on" in haystack:
        return "uvicorn_ready"
    if "application startup complete" in haystack:
        return "uvicorn_startup_complete"
    if "started server process" in haystack:
        return "uvicorn_boot"
    if "repack:" in haystack:
        return "model_repack"
    if "load_tensors:" in haystack:
        return "load_tensors"
    if "llama_model_loader" in haystack or "llm_load_print_meta" in haystack:
        return "model_metadata"
    return "unknown"


def _classify_exit_code(exit_code: int | None) -> str:
    if exit_code is None:
        return "still_running"
    common = {
        0: "clean_exit",
        1: "generic_error",
        -9: "killed",
        3221225477: "access_violation",
        3221225781: "ctrl_c_or_close",
        3221226505: "stack_buffer_overrun",
    }
    return common.get(int(exit_code), "unknown_exit")


def probe_ai2_ready(base_url: str = DEFAULT_BASE_URL, *, timeout_sec: int = 10, expected_alias: str = DEFAULT_ALIAS) -> dict:
    models_url = _models_url(base_url)
    status = {
        "ready": False,
        "base_url": base_url,
        "models_url": models_url,
        "expected_alias": expected_alias,
        "http_status": None,
        "attempted_at": round(time.time(), 3),
        "message": "",
    }

    try:
        req = urllib.request.Request(models_url, headers={"Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(req, timeout=max(1, int(timeout_sec or 1))) as resp:
            status["http_status"] = int(getattr(resp, "status", 200) or 200)
            body = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(body or "{}")
        models = payload.get("data") if isinstance(payload, dict) else []
        ids = [str(item.get("id") or "").strip() for item in models if isinstance(item, dict)]
        status["model_ids"] = ids
        status["ready"] = expected_alias in ids if expected_alias else bool(ids)
        status["message"] = (
            f"AI2 hazir: {expected_alias} bulundu."
            if status["ready"]
            else f"/v1/models dondu ama beklenen alias bulunamadi: {ids}"
        )
        return status
    except urllib.error.HTTPError as exc:
        status["http_status"] = int(exc.code)
        status["message"] = f"/v1/models HTTP {exc.code}"
        return status
    except Exception as exc:
        status["message"] = f"/v1/models erisilemedi: {type(exc).__name__}: {exc}"
        return status


def wait_for_ai2_ready(
    base_url: str = DEFAULT_BASE_URL,
    *,
    timeout_sec: int = 240,
    poll_interval_sec: int = 5,
    expected_alias: str = DEFAULT_ALIAS,
) -> dict:
    started = time.perf_counter()
    last_status = {}

    while time.perf_counter() - started < max(1, int(timeout_sec or 1)):
        last_status = probe_ai2_ready(base_url, timeout_sec=max(2, poll_interval_sec), expected_alias=expected_alias)
        if last_status.get("ready"):
            last_status["waited_sec"] = round(time.perf_counter() - started, 2)
            return last_status
        time.sleep(max(1, int(poll_interval_sec or 1)))

    last_status = dict(last_status or {})
    last_status["ready"] = False
    last_status["waited_sec"] = round(time.perf_counter() - started, 2)
    last_status["message"] = last_status.get("message") or "AI2 hazir olmadi."
    return last_status


def start_ai2_server(
    *,
    python_exe: str | None = None,
    model_path: str | Path = DEFAULT_MODEL,
    host: str = "127.0.0.1",
    port: int = 8002,
    alias: str = DEFAULT_ALIAS,
    stdout_path: str | Path = DEFAULT_STDOUT,
    stderr_path: str | Path = DEFAULT_STDERR,
) -> dict:
    python_path = str(python_exe or sys.executable)
    model_path = Path(model_path)
    if not model_path.exists():
        searched = ", ".join(str(item) for item in _default_model_candidates())
        raise FileNotFoundError(
            f"AI2 model bulunamadi: {model_path}. "
            f"Yeni varsayilan Q5_K_M modelidir; denenen varsayilan adaylar: {searched}"
        )
    stdout_path = Path(stdout_path)
    stderr_path = Path(stderr_path)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)

    stdout_fh = stdout_path.open("w", encoding="utf-8")
    stderr_fh = stderr_path.open("w", encoding="utf-8")
    command = [
        python_path,
        "-m",
        "llama_cpp.server",
        "--host",
        host,
        "--port",
        str(port),
        "--model",
        str(model_path),
        "--model_alias",
        alias,
    ]
    process = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        stdout=stdout_fh,
        stderr=stderr_fh,
    )
    stdout_fh.close()
    stderr_fh.close()
    return {
        "pid": int(process.pid),
        "process": process,
        "command": command,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def ensure_ai2_ready(
    *,
    base_url: str = DEFAULT_BASE_URL,
    python_exe: str | None = None,
    model_path: str | Path = DEFAULT_MODEL,
    alias: str = DEFAULT_ALIAS,
    port: int = 8002,
    ready_timeout_sec: int = 360,
    poll_interval_sec: int = 5,
    auto_start: bool = True,
    stdout_path: str | Path = DEFAULT_STDOUT,
    stderr_path: str | Path = DEFAULT_STDERR,
) -> dict:
    precheck = probe_ai2_ready(base_url, timeout_sec=max(2, poll_interval_sec), expected_alias=alias)
    if precheck.get("ready"):
        precheck["startup_action"] = "already_running"
        return precheck

    if not auto_start:
        precheck["startup_action"] = "not_started"
        return precheck

    started = start_ai2_server(
        python_exe=python_exe,
        model_path=model_path,
        host="127.0.0.1",
        port=port,
        alias=alias,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    process = started["process"]
    begun = time.perf_counter()
    probe_attempt_count = 0
    last_probe = {}

    while time.perf_counter() - begun < max(5, int(ready_timeout_sec or 5)):
        current = probe_ai2_ready(base_url, timeout_sec=max(2, poll_interval_sec), expected_alias=alias)
        probe_attempt_count += 1
        last_probe = dict(current or {})
        if current.get("ready"):
            current.update(
                {
                    "startup_action": "started_now",
                    "pid": started["pid"],
                    "startup_wait_sec": round(time.perf_counter() - begun, 2),
                    "probe_attempt_count": probe_attempt_count,
                    "last_probe_message": last_probe.get("message") or "",
                    "stdout_path": started["stdout_path"],
                    "stderr_path": started["stderr_path"],
                }
            )
            return current

        exit_code = process.poll()
        if exit_code is not None:
            stderr_tail = _tail_text(Path(started["stderr_path"]))
            stdout_tail = _tail_text(Path(started["stdout_path"]))
            load_stage = _infer_load_stage(stderr_tail, stdout_tail)
            current.update(
                {
                    "ready": False,
                    "startup_action": "process_exited_early",
                    "pid": started["pid"],
                    "exit_code": int(exit_code),
                    "exit_label": _classify_exit_code(exit_code),
                    "startup_wait_sec": round(time.perf_counter() - begun, 2),
                    "probe_attempt_count": probe_attempt_count,
                    "last_probe_message": last_probe.get("message") or "",
                    "stdout_path": started["stdout_path"],
                    "stderr_path": started["stderr_path"],
                    "stderr_tail": stderr_tail,
                    "stdout_tail": stdout_tail,
                    "last_log_line": _last_nonempty_line(stderr_tail or stdout_tail),
                    "load_stage": load_stage,
                }
            )
            if load_stage == "model_path_validation":
                current["message"] = "AI2 prosesinin model dosya yolu dogrulamasinda sonlandigi goruldu."
            elif not current.get("message"):
                current["message"] = "AI2 prosesinin port bind etmeden once sonlandigi goruldu."
            return current

        time.sleep(max(1, int(poll_interval_sec or 1)))

    status = probe_ai2_ready(base_url, timeout_sec=max(2, poll_interval_sec), expected_alias=alias)
    stderr_tail = _tail_text(Path(started["stderr_path"]))
    stdout_tail = _tail_text(Path(started["stdout_path"]))
    load_stage = _infer_load_stage(stderr_tail, stdout_tail)
    status.update(
        {
            "ready": False,
            "startup_action": "timeout_waiting_ready",
            "pid": started["pid"],
            "startup_wait_sec": round(time.perf_counter() - begun, 2),
            "probe_attempt_count": probe_attempt_count,
            "last_probe_message": last_probe.get("message") or "",
            "stdout_path": started["stdout_path"],
            "stderr_path": started["stderr_path"],
            "stderr_tail": stderr_tail,
            "stdout_tail": stdout_tail,
            "last_log_line": _last_nonempty_line(stderr_tail or stdout_tail),
            "load_stage": load_stage,
        }
    )
    return status


__all__ = [
    "DEFAULT_ALIAS",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "ensure_ai2_ready",
    "probe_ai2_ready",
    "resolve_default_model_path",
    "start_ai2_server",
    "wait_for_ai2_ready",
]
