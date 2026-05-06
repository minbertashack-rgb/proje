#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


KNOWN_ACCEPTANCE_AREAS = (
    "parsing_ingestion",
    "ocr",
    "explain_anlamadim",
    "retrieval_evidence",
    "auth_api_contract",
    "security_no_leak",
    "notes_history",
)


def _parse_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def simple_load_release_yml(path: Path) -> list[dict]:
    items: list[dict] = []
    if not path.exists():
        return items
    current = None
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped == "release_gate:":
                continue
            if stripped.startswith("- path:"):
                if current:
                    items.append(_normalize_entry(current))
                current = {}
                _, rest = stripped.split(":", 1)
                current["path"] = rest.strip()
            elif stripped.startswith("path:"):
                _, rest = stripped.split(":", 1)
                if current is None:
                    current = {}
                current["path"] = rest.strip()
            elif stripped.startswith("critical:"):
                _, rest = stripped.split(":", 1)
                if current is None:
                    current = {}
                current["critical"] = _parse_bool(rest.strip(), default=True)
            elif stripped.startswith("must_pass:"):
                _, rest = stripped.split(":", 1)
                if current is None:
                    current = {}
                current["must_pass"] = _parse_bool(rest.strip(), default=False)
            elif stripped.startswith("reason:"):
                _, rest = stripped.split(":", 1)
                if current is None:
                    current = {}
                current["reason"] = rest.strip()
            elif stripped.startswith("acceptance_area:"):
                _, rest = stripped.split(":", 1)
                if current is None:
                    current = {}
                current["acceptance_area"] = rest.strip()
            elif stripped.startswith("category:"):
                _, rest = stripped.split(":", 1)
                if current is None:
                    current = {}
                current["category"] = rest.strip()
            elif stripped.startswith("requires:"):
                _, rest = stripped.split(":", 1)
                if current is None:
                    current = {}
                sval = rest.strip().strip("[]")
                reqs = [p.strip().upper() for p in sval.split(",") if p.strip()]
                current["requires"] = reqs
    if current:
        items.append(_normalize_entry(current))
    return items


def _normalize_entry(entry: dict) -> dict:
    critical = _parse_bool(entry.get("critical"), default=True)
    acceptance_area = str(entry.get("acceptance_area") or "").strip() or "uncategorized"
    return {
        "path": str(entry.get("path") or "").strip(),
        "critical": critical,
        "must_pass": _parse_bool(entry.get("must_pass"), default=critical),
        "reason": str(entry.get("reason") or "").strip(),
        "acceptance_area": acceptance_area,
        "category": str(entry.get("category") or "").strip(),
        "requires": list(entry.get("requires") or []),
    }


def _build_area_status(area_results: list[dict]) -> dict:
    status_counts = {"passed": 0, "failed": 0, "skipped": 0, "timed_out": 0}
    must_pass_total = 0
    must_pass_failed = 0
    for item in area_results:
        status = item.get("status") or "failed"
        if status in status_counts:
            status_counts[status] += 1
        else:
            status_counts["failed"] += 1
        if item.get("must_pass"):
            must_pass_total += 1
            if status != "passed":
                must_pass_failed += 1

    if must_pass_failed > 0 or status_counts["failed"] > 0 or status_counts["timed_out"] > 0:
        area_status = "failed"
    elif status_counts["skipped"] > 0:
        area_status = "needs_ops_note"
    else:
        area_status = "passed"

    return {
        "status": area_status,
        "total": len(area_results),
        "passed": status_counts["passed"],
        "failed": status_counts["failed"],
        "skipped": status_counts["skipped"],
        "timed_out": status_counts["timed_out"],
        "must_pass_total": must_pass_total,
        "must_pass_failed": must_pass_failed,
        "tests": [
            {
                "path": item.get("path"),
                "status": item.get("status"),
                "note": item.get("note"),
                "must_pass": bool(item.get("must_pass")),
            }
            for item in area_results
        ],
    }


def build_release_acceptance_summary(results: list[dict], release_checks: dict | None = None) -> dict:
    release_checks = release_checks or {}
    area_buckets: dict[str, list[dict]] = {}
    must_pass_total = 0
    must_pass_passed = 0
    must_pass_failed = 0
    must_pass_skipped = 0
    issues: list[dict] = []

    for item in results:
        area = str(item.get("acceptance_area") or "uncategorized")
        area_buckets.setdefault(area, []).append(item)
        status = str(item.get("status") or "failed")
        is_must_pass = bool(item.get("must_pass"))
        if is_must_pass:
            must_pass_total += 1
            if status == "passed":
                must_pass_passed += 1
            elif status == "skipped":
                must_pass_skipped += 1
                issues.append(
                    {
                        "path": item.get("path"),
                        "status": status,
                        "note": item.get("note"),
                        "acceptance_area": area,
                        "must_pass": True,
                    }
                )
            else:
                must_pass_failed += 1
                issues.append(
                    {
                        "path": item.get("path"),
                        "status": status,
                        "note": item.get("note"),
                        "acceptance_area": area,
                        "must_pass": True,
                    }
                )
        elif status != "passed":
            issues.append(
                {
                    "path": item.get("path"),
                    "status": status,
                    "note": item.get("note"),
                    "acceptance_area": area,
                    "must_pass": False,
                }
            )

    acceptance_areas = {
        area: _build_area_status(area_buckets.get(area, []))
        for area in KNOWN_ACCEPTANCE_AREAS
        if area in area_buckets
    }
    for area, area_results in area_buckets.items():
        if area not in acceptance_areas:
            acceptance_areas[area] = _build_area_status(area_results)

    critical_issues = list(release_checks.get("critical_issues") or [])
    warnings = list(release_checks.get("warnings") or [])
    has_failed_area = any(area["status"] == "failed" for area in acceptance_areas.values())
    has_ops_note = bool(warnings) or any(area["status"] == "needs_ops_note" for area in acceptance_areas.values())

    if critical_issues or must_pass_failed > 0 or must_pass_skipped > 0 or has_failed_area:
        ship_recommendation = "no_ship"
    elif has_ops_note or any(item.get("status") == "skipped" for item in results):
        ship_recommendation = "ship_with_ops_note"
    else:
        ship_recommendation = "ship"

    return {
        "ship_recommendation": ship_recommendation,
        "must_pass": {
            "total": must_pass_total,
            "passed": must_pass_passed,
            "failed": must_pass_failed,
            "skipped": must_pass_skipped,
        },
        "acceptance_areas": acceptance_areas,
        "release_checks": {
            "critical_issues": critical_issues,
            "warnings": warnings,
        },
        "issues": issues,
        "results": results,
    }


def render_release_acceptance_text(summary: dict) -> str:
    lines = [
        "Release Acceptance Summary",
        f"Ship recommendation: {summary.get('ship_recommendation', 'unknown')}",
    ]
    must_pass = summary.get("must_pass") or {}
    lines.append(
        "Must-pass: "
        f"{must_pass.get('passed', 0)}/{must_pass.get('total', 0)} passed, "
        f"failed={must_pass.get('failed', 0)}, skipped={must_pass.get('skipped', 0)}"
    )
    lines.append("")
    lines.append("Acceptance areas:")
    for area, area_summary in (summary.get("acceptance_areas") or {}).items():
        lines.append(
            f"- {area}: {area_summary.get('status')} "
            f"(passed={area_summary.get('passed', 0)}, "
            f"failed={area_summary.get('failed', 0)}, "
            f"skipped={area_summary.get('skipped', 0)}, "
            f"timed_out={area_summary.get('timed_out', 0)})"
        )
    critical_issues = list(((summary.get("release_checks") or {}).get("critical_issues")) or [])
    warnings = list(((summary.get("release_checks") or {}).get("warnings")) or [])
    issues = list(summary.get("issues") or [])
    if critical_issues or warnings or issues:
        lines.append("")
        lines.append("Issues:")
        for issue in critical_issues:
            lines.append(f"- release_check:blocker: {issue}")
        for warning in warnings:
            lines.append(f"- release_check:warning: {warning}")
        for item in issues:
            note = item.get("note")
            suffix = f" note={note}" if note else ""
            must_pass_tag = " must_pass" if item.get("must_pass") else ""
            lines.append(
                f"- {item.get('acceptance_area')} {item.get('path')} => {item.get('status')}{must_pass_tag}{suffix}"
            )
    return "\n".join(lines) + "\n"


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python tools/release_acceptance_summary.py <release_gate_summary.json>")
        return 2
    summary_path = Path(argv[1])
    if not summary_path.exists():
        print(f"Summary file not found: {summary_path}")
        return 2
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    acceptance_summary = payload.get("acceptance_summary") or build_release_acceptance_summary(
        list(payload.get("results") or []),
        dict(payload.get("release_checks") or {}),
    )
    print(render_release_acceptance_text(acceptance_summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
