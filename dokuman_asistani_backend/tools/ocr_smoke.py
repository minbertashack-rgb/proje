#!/usr/bin/env python3
"""Simple OCR smoke test.

Creates a tiny image with the text TEST and runs tesseract to verify basic OCR pipeline.

Exits:
  0 -> success (tesseract returned non-empty output)
  2 -> tesseract binary missing
  3 -> Pillow not installed (skipped)
  4 -> OCR failed or returned empty
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    print("Pillow not installed — install pillow to run OCR smoke (skipping)")
    sys.exit(3)


def which_or_env(var: str | None = None):
    # prefer explicit env var, then PATH, then common Windows default
    if var and os.getenv(var):
        return os.getenv(var)
    from shutil import which

    candidate = which("tesseract")
    if candidate:
        return candidate
    # common Windows default
    default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if Path(default).exists():
        return default
    return None


def main():
    tess = which_or_env("TESSERACT_CMD")
    if not tess:
        print("Tesseract binary not found on PATH and TESSERACT_CMD not set")
        return 2

    # make a small image with clear text
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "smoke.png"
        img = Image.new("L", (160, 48), color=255)
        draw = ImageDraw.Draw(img)
        try:
            # try default font
            f = ImageFont.load_default()
        except Exception:
            f = None
        draw.text((8, 8), "TEST", fill=0, font=f)
        img.save(p)

        # call tesseract
        try:
            proc = subprocess.run([tess, str(p), "stdout", "-l", os.getenv("OCR_LANG", "eng"), "--psm", "6"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            out = (proc.stdout or proc.stderr or "").strip()
            print("tesseract stdout/stderr:\n", out)
            if out:
                return 0
            else:
                print("OCR returned empty output")
                return 4
        except Exception as e:
            print("Failed to run tesseract:", e)
            return 4


if __name__ == "__main__":
    sys.exit(main())
