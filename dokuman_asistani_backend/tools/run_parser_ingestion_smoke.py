from __future__ import annotations

import subprocess
import sys


def main() -> int:
    komut = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "dokuman/tests/test_heading_parser.py",
        "dokuman/tests/test_ingestion_quality.py",
        "dokuman/tests/test_golden_parser_ingestion.py",
    ]
    return subprocess.call(komut)


if __name__ == "__main__":
    raise SystemExit(main())
