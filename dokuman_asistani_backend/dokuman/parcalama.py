# dokuman/parcalama.py
from __future__ import annotations
from typing import List, Tuple

_BOUNDARY_SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", ": ", ", "]
_BOUNDARY_WINDOW = 220


def _find_semantic_boundary(text: str, start: int, target_end: int) -> int:
    text_len = len(text)
    search_back_start = max(start, target_end - _BOUNDARY_WINDOW)
    search_forward_end = min(text_len, target_end + _BOUNDARY_WINDOW)

    for sep in _BOUNDARY_SEPARATORS:
        pos = text.rfind(sep, search_back_start, min(target_end, text_len))
        if pos != -1 and pos > start + int((target_end - start) * 0.6):
            return pos + len(sep)

    for sep in _BOUNDARY_SEPARATORS:
        pos = text.find(sep, target_end, search_forward_end)
        if pos != -1:
            return pos + len(sep)

    return target_end


def chunk_text(text: str, chunk_char: int = 1200, overlap: int = 150) -> List[Tuple[int, int]]:
    """
    Basit karakter bazlı chunk + overlap. Cümle/ satır sonuna yakın kırmaya çalışır.
    Dönen: [(start, end), ...]
    """
    t = (text or "").strip()
    if not t:
        return []

    chunk_char = max(200, int(chunk_char))
    overlap = max(0, int(overlap))
    if overlap >= chunk_char:
        overlap = max(0, chunk_char // 5)

    n = len(t)
    spans = []
    start = 0

    while start < n:
        end = min(n, start + chunk_char)

        end = _find_semantic_boundary(t, start, end)
        if end <= start:
            end = min(n, start + chunk_char)

        spans.append((start, end))
        if end >= n:
            break
        next_start = max(0, end - overlap)
        start = end if next_start <= start else next_start

    return spans
