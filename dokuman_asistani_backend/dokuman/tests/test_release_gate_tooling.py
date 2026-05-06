from __future__ import annotations

import json
from pathlib import Path

from tools.release_acceptance_summary import (
    build_release_acceptance_summary,
    render_release_acceptance_text,
    simple_load_release_yml,
)


def test_simple_load_release_yml_parses_must_pass_and_acceptance_area(tmp_path: Path):
    manifest = tmp_path / "release_gate.yml"
    manifest.write_text(
        "\n".join(
            [
                "release_gate:",
                "  - path: dokuman/tests/test_upload_fields.py",
                "    critical: true",
                "    must_pass: true",
                "    acceptance_area: parsing_ingestion",
                "    reason: upload contract",
                "  - path: dokuman/tests/test_rag_quality.py",
                "    critical: true",
                "    acceptance_area: retrieval_evidence",
                "    requires: [AI2]",
            ]
        ),
        encoding="utf-8",
    )

    items = simple_load_release_yml(manifest)

    assert len(items) == 2
    assert items[0]["path"] == "dokuman/tests/test_upload_fields.py"
    assert items[0]["must_pass"] is True
    assert items[0]["acceptance_area"] == "parsing_ingestion"
    assert items[1]["acceptance_area"] == "retrieval_evidence"
    assert items[1]["must_pass"] is True
    assert items[1]["requires"] == ["AI2"]


def test_release_acceptance_summary_marks_no_ship_for_must_pass_failure():
    results = [
        {
            "path": "dokuman/tests/test_upload_fields.py",
            "status": "passed",
            "exit_code": 0,
            "note": None,
            "critical": True,
            "must_pass": True,
            "acceptance_area": "parsing_ingestion",
            "reason": "upload contract",
        },
        {
            "path": "dokuman/tests/test_patch6_throttle_shapes.py",
            "status": "failed",
            "exit_code": 1,
            "note": None,
            "critical": True,
            "must_pass": True,
            "acceptance_area": "security_no_leak",
            "reason": "throttle shapes",
        },
    ]

    summary = build_release_acceptance_summary(results, {"warnings": [], "critical_issues": []})

    assert summary["ship_recommendation"] == "no_ship"
    assert summary["must_pass"]["failed"] == 1
    assert summary["acceptance_areas"]["security_no_leak"]["status"] == "failed"


def test_release_acceptance_summary_marks_ship_with_ops_note_for_warning_and_skip():
    results = [
        {
            "path": "dokuman/tests/test_upload_fields.py",
            "status": "passed",
            "exit_code": 0,
            "note": None,
            "critical": True,
            "must_pass": True,
            "acceptance_area": "parsing_ingestion",
            "reason": "upload contract",
        },
        {
            "path": "dokuman/tests/test_ai2_runtime_tools.py",
            "status": "skipped",
            "exit_code": None,
            "note": "AI2",
            "critical": True,
            "must_pass": False,
            "acceptance_area": "retrieval_evidence",
            "reason": "ai2 tooling",
        },
    ]

    summary = build_release_acceptance_summary(
        results,
        {"warnings": ["No AI2_TABAN_ADRESI set"], "critical_issues": []},
    )

    assert summary["ship_recommendation"] == "ship_with_ops_note"
    assert summary["must_pass"]["failed"] == 0
    assert summary["must_pass"]["skipped"] == 0
    assert summary["acceptance_areas"]["retrieval_evidence"]["status"] == "needs_ops_note"

    text = render_release_acceptance_text(summary)
    assert "Ship recommendation: ship_with_ops_note" in text
    assert "Must-pass" in text
    assert "retrieval_evidence" in text


def test_release_acceptance_summary_json_is_serializable():
    results = [
        {
            "path": "dokuman/tests/test_patch2_auth_error_shapes.py",
            "status": "passed",
            "exit_code": 0,
            "note": None,
            "critical": True,
            "must_pass": True,
            "acceptance_area": "auth_api_contract",
            "reason": "auth contract",
        }
    ]

    summary = build_release_acceptance_summary(results, {"warnings": [], "critical_issues": []})

    rendered = json.dumps(summary, ensure_ascii=False)
    assert "auth_api_contract" in rendered
    assert '"ship_recommendation": "ship"' in rendered
