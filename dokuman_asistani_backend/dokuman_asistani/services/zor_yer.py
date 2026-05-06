import re
from bisect import bisect_right
from collections import Counter

_TR_WORD_RE = re.compile(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü]+")


def tokenize_tr(text: str):
    if not text:
        return []
    return [t for t in _TR_WORD_RE.findall(text.casefold()) if len(t) >= 2]


def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def sayfa_no_bul(sayfa_kirilimlari, char_index: int):
    """
    sayfa_kirilimlari: [0, 1820, 3655, ...]
    char_index hangi sayfada? => 1-index sayfa döndürür.
    """
    if not sayfa_kirilimlari:
        return None
    i = bisect_right(list(sayfa_kirilimlari), char_index) - 1
    return max(1, i + 1)


def parcala_metni(metin: str, chunk_char: int = 1200, overlap: int = 150):
    """
    Basit auto-chunk:
    - chunk_char: hedef chunk uzunluğu
    - overlap: bir sonraki chunk'a bindirme
    """
    metin = metin or ""
    n = len(metin)
    if n == 0:
        return []

    out = []
    start = 0
    sira = 1

    while start < n:
        end = min(n, start + chunk_char)

        # kelime ortasında kesme -> biraz geri sar
        if end < n:
            while end > start and metin[end - 1] not in (" ", "\n", "\t", ".", "!", "?", "…"):
                end -= 1
            if end <= start:
                end = min(n, start + chunk_char)  # geri sarma işe yaramadıysa

        out.append((sira, start, end))
        sira += 1

        if end >= n:
            break

        start = max(0, end - overlap)

    return out


def dokuman_global_freq(parca_icerikleri):
    c = Counter()
    for txt in parca_icerikleri:
        c.update(tokenize_tr(txt))
    return c


def zorluk_skoru_hesapla(chunk_text: str, global_freq: Counter):
    toks = tokenize_tr(chunk_text)
    n_words = len(toks)

    if n_words == 0:
        return 0, {
            "kelime_sayisi": 0,
            "nadir_oran": 0.0,
            "ort_kelime_uzunlugu": 0.0,
            "ort_cumle_uzunlugu": 0.0,
            "sent_count": 0,
        }

    rare_count = sum(1 for t in toks if global_freq.get(t, 0) <= 1)
    rare_ratio = rare_count / max(1, n_words)

    avg_word_len = sum(len(t) for t in toks) / n_words

    sent_count = len(re.findall(r"[.!?…]+", chunk_text)) or 1
    avg_sent_len = n_words / sent_count

    # normalize 0..1
    len_norm = clamp01(n_words / 200)                 # 200 kelime ≈ 1.0
    rare_norm = clamp01(rare_ratio / 0.25)            # %25+ nadir ≈ 1.0
    wordlen_norm = clamp01((avg_word_len - 4) / 4)    # 4->0, 8->1
    sent_norm = clamp01((avg_sent_len - 15) / 25)     # 15->0, 40->1

    score = round(100 * (0.25 * len_norm + 0.35 * rare_norm + 0.20 * wordlen_norm + 0.20 * sent_norm))
    score = max(0, min(100, int(score)))

    metrics = {
        "kelime_sayisi": n_words,
        "nadir_oran": round(rare_ratio, 4),
        "ort_kelime_uzunlugu": round(avg_word_len, 3),
        "ort_cumle_uzunlugu": round(avg_sent_len, 3),
        "sent_count": sent_count,
    }
    return score, metrics