#!/usr/bin/env python3
"""Simple audit for code explanation benchmark cases.

Run: python tools/benchmark_audit.py
Prints duplicates, missing tags, and weak cases summary.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module_from_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    bench_path = repo_root / "dokuman" / "tests" / "code_explanation_benchmark_data.py"
    if not bench_path.exists():
        print("Benchmark data file not found:", bench_path)
        return 2

    mod = load_module_from_path(bench_path, "bench_data")
    cases = getattr(mod, "CODE_EXPLANATION_BENCHMARK_CASES", [])
    axis_matrix = getattr(mod, "CODE_EXPLANATION_AXIS_MATRIX", {})
    required_tags = getattr(mod, "CODE_EXPLANATION_REQUIRED_COVERAGE_TAGS", set())

    print(f"Loaded {len(cases)} benchmark cases")

    # duplicates
    slugs = [c.get("slug") for c in cases]
    dup_slugs = {s for s in slugs if slugs.count(s) > 1}
    if dup_slugs:
        print("Duplicate slugs found:")
        for s in dup_slugs:
            print(" -", s)
    else:
        print("No duplicate slugs.")

    # coverage tags union
    all_tags = {t for c in cases for t in (c.get("coverage_tags") or [])}
    missing_required = set(required_tags) - all_tags
    if missing_required:
        print("Missing required coverage tags in cases:")
        for t in missing_required:
            print(" -", t)
    else:
        print("All required coverage tags present across cases.")

    # weak cases: min_counts thresholds
    weak = []
    for c in cases:
        mc = c.get("min_counts") or {}
        if mc.get("line_comments", 0) < 2 or mc.get("block_comments", 0) < 1:
            weak.append(c.get("slug"))

    if weak:
        print("Cases with low min_counts (possible weak cases):")
        for s in weak:
            print(" -", s)
    else:
        print("All cases meet min_counts thresholds.")

    # Check axis coverage
    axes = {c.get("axis") for c in cases}
    missing_axes = set(axis_matrix.keys()) - axes
    if missing_axes:
        print("Missing axes coverage for:")
        for a in missing_axes:
            print(" -", a)
    else:
        print("Axes coverage looks aligned with axis matrix.")

    print("\nAudit complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
