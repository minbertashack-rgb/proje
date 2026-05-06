#!/usr/bin/env python3
"""Run the release gate: env checks, quick compiles and the selected critical tests.

Usage: python tools/run_release_gate.py

This is intentionally dependency-light and works on Windows/Linux.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import shlex

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.release_acceptance_summary import (
    build_release_acceptance_summary,
    render_release_acceptance_text,
    simple_load_release_yml,
)

RELEASE_YML = REPO_ROOT / "release_gate.yml"
LOG_ROOT = REPO_ROOT / "release_logs"


def run_cmd(cmd: list[str], cwd: Path, timeout: int | None = None):
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    return p.returncode, p.stdout, p.stderr


def main() -> int:
    print("Release gate runner (non-interactive)")
    # per-test timeout in seconds; configurable by env var RELEASE_GATE_TEST_TIMEOUT
    try:
        DEFAULT_TEST_TIMEOUT = int(os.getenv("RELEASE_GATE_TEST_TIMEOUT", "1200"))
    except Exception:
        DEFAULT_TEST_TIMEOUT = 1200
    # 1) run release_checks
    rc_script = REPO_ROOT / "tools" / "release_checks.py"
    if rc_script.exists():
        print("Running release_checks...")
        try:
            env = os.environ.copy()
            env.setdefault("CI", "true")
            p = subprocess.run([sys.executable, str(rc_script)], cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300, stdin=subprocess.DEVNULL, env=env)
            print(p.stdout)
            if p.returncode != 0:
                print("release_checks reported issues (exit code", p.returncode, ")")
            else:
                print("release_checks OK")
        except subprocess.TimeoutExpired:
            print("release_checks timed out")

    # 2) quick compiles (as in TESTING.md)
    print("Quick byte-compile checks...")
    for target in ["manage.py", "dokuman/views.py", "dokuman/views_ai2.py", "dokuman/views_ingestion.py"]:
        tgt = REPO_ROOT / target
        if tgt.exists():
            try:
                subprocess.check_call([sys.executable, "-m", "py_compile", str(tgt)])
                print("Compiled:", target)
            except subprocess.CalledProcessError:
                print("Compile failed for:", target)
                # continue; pytest will show real errors

    items = simple_load_release_yml(RELEASE_YML)
    if not items:
        print("No release_gate.yml found or empty — nothing to run.")
        return 2

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    outdir = LOG_ROOT / timestamp
    outdir.mkdir(parents=True, exist_ok=True)

    # load release_checks report if present to inform skips
    report_path = REPO_ROOT / "release_checks_report.json"
    release_report = {}
    if report_path.exists():
        try:
            release_report = json.loads(report_path.read_text(encoding="utf-8"))
            print("Loaded release_checks_report.json")
        except Exception:
            print("Failed to parse release_checks_report.json")

    any_failed = False
    results = []
    for entry in items:
        path = entry.get("path")
        critical = bool(entry.get("critical", True))
        must_pass = bool(entry.get("must_pass", critical))
        reason = entry.get("reason", "")
        requires = entry.get("requires", []) or []
        acceptance_area = entry.get("acceptance_area", "uncategorized")
        category = entry.get("category", "")
        display = f"{path} (critical={critical})"
        print("Running test:", display, "-", reason)
        # check requirements
        if requires:
            unmet = []
            for r in requires:
                r = r.upper()
                if r == "TESSERACT":
                    if release_report.get("tesseract") != "ready":
                        unmet.append(r)
                elif r == "GGUF":
                    if not release_report.get("gguf_candidates"):
                        unmet.append(r)
                elif r == "AI2":
                    if not release_report.get("ai2_candidate"):
                        unmet.append(r)
                elif r == "LOCAL_MODEL":
                    if not release_report.get("gguf_candidates"):
                        unmet.append(r)
                else:
                    # unknown requirement: conservatively mark unmet if not in report
                    if r not in release_report:
                        unmet.append(r)
            if unmet:
                print(f" -> SKIPPED due to unmet requirements: {', '.join(unmet)}")
                results.append(
                    {
                        "path": path,
                        "status": "skipped",
                        "exit_code": None,
                        "note": ", ".join(unmet),
                        "critical": critical,
                        "must_pass": must_pass,
                        "acceptance_area": acceptance_area,
                        "category": category,
                        "reason": reason,
                    }
                )
                # do not mark as failure; caller should inspect skipped tests
                continue
        stdout_file = outdir / (Path(path).name + ".stdout.txt")
        stderr_file = outdir / (Path(path).name + ".stderr.txt")
        try:
            cmd = [sys.executable, "-m", "pytest", "-q", path]
            child_env = os.environ.copy()
            child_env.setdefault("CI", "true")
            child_env.setdefault("PYTHONUNBUFFERED", "1")
            # run pytest with a reasonable per-test timeout
            timeout = int(os.getenv("RELEASE_GATE_TEST_TIMEOUT", DEFAULT_TEST_TIMEOUT))
            p = subprocess.run(cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, stdin=subprocess.DEVNULL, env=child_env)
            stdout_file.write_text(p.stdout, encoding="utf-8")
            stderr_file.write_text(p.stderr, encoding="utf-8")
            passed = p.returncode == 0
            results.append(
                {
                    "path": path,
                    "status": "passed" if passed else "failed",
                    "exit_code": p.returncode,
                    "note": None,
                    "critical": critical,
                    "must_pass": must_pass,
                    "acceptance_area": acceptance_area,
                    "category": category,
                    "reason": reason,
                }
            )
            if not passed:
                any_failed = any_failed or critical
                print(f" -> FAILED (exit={p.returncode})")
            else:
                print(" -> PASSED")
        except subprocess.TimeoutExpired:
            any_failed = any_failed or critical
            print(" -> TIMED OUT")
            results.append(
                {
                    "path": path,
                    "status": "timed_out",
                    "exit_code": None,
                    "note": None,
                    "critical": critical,
                    "must_pass": must_pass,
                    "acceptance_area": acceptance_area,
                    "category": category,
                    "reason": reason,
                }
            )

    # Summarize
    print("\n=== Release Gate Summary ===")
    for item in results:
        print(
            f"{item['path']} | status={item['status']} | exit={item['exit_code']} | "
            f"must_pass={item['must_pass']} | area={item['acceptance_area']} | note={item['note']}"
        )

    acceptance_summary = build_release_acceptance_summary(results, release_report)
    acceptance_text = render_release_acceptance_text(acceptance_summary)
    print("\n=== Acceptance Summary ===")
    print(acceptance_text)

    # write JSON summary
    summary = {
        "timestamp": timestamp,
        "results": results,
        "any_failed": any_failed,
        "release_checks": release_report,
        "acceptance_summary": acceptance_summary,
    }
    try:
        sum_path = outdir / "release_gate_summary.json"
        sum_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("Wrote summary:", sum_path)
        acceptance_json_path = outdir / "release_acceptance_summary.json"
        acceptance_json_path.write_text(json.dumps(acceptance_summary, indent=2), encoding="utf-8")
        print("Wrote acceptance summary:", acceptance_json_path)
        acceptance_txt_path = outdir / "release_acceptance_summary.txt"
        acceptance_txt_path.write_text(acceptance_text, encoding="utf-8")
        print("Wrote acceptance text summary:", acceptance_txt_path)
    except Exception:
        print("Failed to write release gate summary")

    print("Logs written to:", outdir)
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
