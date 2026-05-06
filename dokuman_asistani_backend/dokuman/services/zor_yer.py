# dokuman/services/zor_yer.py
import math
import re
from collections import Counter
from typing import Dict, List

from dokuman.models import AnlamadimKaydi, Parca
from dokuman.services.metric_store import compute_confusion_map_score

_WORD_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]+", re.UNICODE)

# mini stopword set (çok basit)
_STOP = {
    "ve", "veya", "ile", "ama", "fakat", "ancak", "bu", "şu", "o", "bir", "de", "da",
    "mi", "mı", "mu", "mü", "için", "gibi", "daha", "çok", "az", "en"
}


def parcala_metni(metin: str) -> List[str]:
    # compat için: şimdilik tek parça dön
    return [metin or ""]


def dokuman_global_freq(parca_metinleri: List[str]) -> Dict[str, int]:
    words = []
    for t in parca_metinleri:
        for w in _WORD_RE.findall((t or "").lower()):
            if w in _STOP:
                continue
            words.append(w)
    return dict(Counter(words))


def zorluk_skoru_hesapla(metin: str, global_freq: Dict[str, int]) -> float:
    """
    0.0 - 1.0 arası basit zorluk skoru:
    - çok uzun metin biraz zor
    - nadir kelimeler (düşük freq) zor
    """
    text = metin or ""
    tokens = [w.lower() for w in _WORD_RE.findall(text) if w.lower() not in _STOP]
    if not tokens:
        return 0.0

    # nadirlik puanı: 1/(freq+1) ortalaması
    rarities = []
    for w in tokens:
        f = global_freq.get(w, 0)
        rarities.append(1.0 / (f + 1.0))
    rare_score = sum(rarities) / len(rarities)  # 0..1 civarı

    # uzunluk puanı
    length = len(text)
    len_score = min(1.0, math.log(1 + length) / math.log(1 + 2000))  # ~2000 char'da 1'e yakın

    # birleşim (ağırlık)
    score = 0.65 * rare_score + 0.35 * len_score

    # clamp
    if score < 0.0:
        score = 0.0
    if score > 1.0:
        score = 1.0
    return float(score)


def sayfa_no_bul(*args, **kwargs):
    # compat placeholder
    return None


def _safe_score(value) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0.0)))
    except Exception:
        return 0.0


def _quality_gap(parca) -> float:
    meta = getattr(parca, "meta", {}) or {}
    quality = max(_safe_score(meta.get("quality_score")), _safe_score(meta.get("ocr_quality_score")))
    weak_bonus = 0.10 if bool(meta.get("weak_content")) else 0.0
    return min(1.0, (1.0 - quality) + weak_bonus)


def _difficulty_signal(parca) -> float:
    meta = getattr(parca, "meta", {}) or {}
    return max(
        _safe_score(meta.get("difficulty_score")),
        _safe_score(getattr(parca, "zorluk_skoru", 0.0)),
    )


def _short_title(parca) -> str:
    meta = getattr(parca, "meta", {}) or {}
    for key in ("chunk_title", "baslik", "slide_title", "symbol"):
        value = str(meta.get(key) or "").strip()
        if value:
            return value[:80]
    adres = str(getattr(parca, "adres", "") or "").strip()
    if not adres:
        return f"Parca {getattr(parca, 'id', 0)}"
    parts = [piece for piece in re.split(r"[:>#/]", adres) if piece.strip()]
    return " / ".join(parts[-2:])[:80] or adres[:80]


def _reason_text(*, confusion: float, difficulty: float, quality_gap: float, confusion_count: int) -> str:
    reasons = []
    if confusion >= 0.55 or confusion_count >= 2:
        reasons.append("karisiklik sinyali yuksek")
    if difficulty >= 0.60:
        reasons.append("yapisal zorluk yuksek")
    if quality_gap >= 0.45:
        reasons.append("anlatim yogunlugu yuksek")
    if not reasons:
        reasons.append("mevcut sinyallerde diger parcalardan daha zor")
    return ", ".join(reasons)[:120]


def build_hardest_parts_payload(*, doc, user=None, limit: int = 3) -> list[dict]:
    parcalar = list(Parca.objects.filter(dokuman=doc).order_by("id"))
    if not parcalar:
        return []

    pre_ranked = sorted(
        parcalar,
        key=lambda parca: (
            0.7 * _difficulty_signal(parca)
            + 0.3 * _quality_gap(parca)
        ),
        reverse=True,
    )[: min(max(limit * 4, 6), len(parcalar))]

    items = []
    for parca in pre_ranked:
        confusion = 0.0
        confusion_count = 0
        if user is not None:
            confusion = _safe_score(
                compute_confusion_map_score(user=user, dokuman=doc, parca=parca)["confusion_map_score"]
            )
            confusion_count = AnlamadimKaydi.objects.filter(kullanici=user, dokuman=doc, parca=parca).count()
        difficulty = _difficulty_signal(parca)
        quality_gap = _quality_gap(parca)
        hardness = (0.45 * difficulty) + (0.35 * confusion) + (0.20 * quality_gap)
        items.append(
            {
                "parca_id": parca.id,
                "adres": getattr(parca, "adres", ""),
                "kisa_baslik": _short_title(parca),
                "neden_zor": _reason_text(
                    confusion=confusion,
                    difficulty=difficulty,
                    quality_gap=quality_gap,
                    confusion_count=confusion_count,
                ),
                "_hardness": round(hardness, 4),
                "_confusion": round(confusion, 4),
                "_difficulty": round(difficulty, 4),
                "_quality_gap": round(quality_gap, 4),
            }
        )

    items.sort(key=lambda item: (item["_hardness"], item["_difficulty"], item["_confusion"]), reverse=True)
    return [
        {
            "parca_id": item["parca_id"],
            "adres": item["adres"],
            "neden_zor": item["neden_zor"],
            "kisa_baslik": item["kisa_baslik"],
        }
        for item in items[: max(1, int(limit or 3))]
    ]
