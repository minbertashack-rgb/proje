import re
from typing import Tuple

TERM_RE = re.compile(r"\b[A-ZÇĞİÖŞÜ]{2,}\b")
NUM_RE = re.compile(r"\d")
FORMULA_RE = re.compile(r"[=<>+\-*/^]|->|=>|≤|≥")
CODE_HINT_RE = re.compile(r"[{}();]|def |class |import |SELECT |FROM |WHERE ", re.IGNORECASE)

def zorluk_hesapla(text: str, tur: str) -> Tuple[float, str]:
    t = (text or "").strip()
    if not t:
        return 0.0, "kolay"

    length = len(t)
    sentences = max(1, t.count(".") + t.count("?") + t.count("!"))
    avg_sent_len = length / sentences

    term_hits = len(TERM_RE.findall(t))
    num_hits = len(NUM_RE.findall(t))
    formula_hits = len(FORMULA_RE.findall(t))
    code_hits = 1 if CODE_HINT_RE.search(t) else 0

    term_density = term_hits / max(1, len(t.split()))
    num_density = num_hits / max(1, length)
    formula_density = formula_hits / max(1, length)

    score = 0.0
    score += min(0.35, length / 2000)
    score += min(0.25, avg_sent_len / 180)
    score += min(0.20, term_density * 2.5)
    score += min(0.10, num_density * 6.0)
    score += min(0.10, formula_density * 8.0)

    if tur in ["tablo", "formul", "kod"]:
        score += 0.08
    if code_hits:
        score += 0.06

    score = max(0.0, min(1.0, score))

    if score >= 0.66:
        return score, "zor"
    if score >= 0.33:
        return score, "orta"
    return score, "kolay"