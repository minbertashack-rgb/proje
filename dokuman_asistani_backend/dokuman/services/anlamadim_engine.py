# dokuman/services/anlamadim_engine.py
from __future__ import annotations
import re
from typing import List, Dict, Any

from dokuman.services.metric_store import compute_confusion_map_score

WORD_RE = re.compile(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü_]+", re.UNICODE)
ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")

DOMAIN_TERMS = {
    "rls","cdc","oltp","etl","jwt","rbac","oauth","api","gateway",
    "sql","select","join","where","group","xlookup","vlookup","if"
}
THEME_EXAMPLES = {
    "genel": "Bunu, bir gorevi tekrar etmeden once adimlari netlestirmek gibi dusun.",
    "teknoloji": "Bunu, uygulamada dogru modulu secip veri akisini izlemek gibi dusun.",
    "yazilim": "Bunu, fonksiyonun girdisini ve ciktisini okuyup hata ayiklamak gibi dusun.",
    "oyun": "Bunu, oyunda hangi esyanin hangi gorevi actigini anlamak gibi dusun.",
    "spor": "Bunu, mac istatistiginde kritik satiri once okumak gibi dusun.",
    "yemek": "Bunu, tarifte malzeme ile adim eslesmesini kurmak gibi dusun.",
    "film": "Bunu, sahneler arasinda ana baglanti noktasini yakalamak gibi dusun.",
}

def one_sentence_summary(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    # ilk cümle ya da ilk 25 kelime
    parts = re.split(r"[.!?…]\s+", t, maxsplit=1)
    first = parts[0].strip()
    if len(first) >= 10:
        return first
    words = WORD_RE.findall(t)
    return " ".join(words[:25]) + ("…" if len(words) > 25 else "")

def extract_terms(text: str, limit: int = 10) -> List[Dict[str, str]]:
    t = (text or "")
    lower = t.lower()
    found = set()

    for a in ACRONYM_RE.findall(t):
        found.add(a)

    for term in DOMAIN_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", lower):
            found.add(term.upper() if len(term) <= 4 else term)

    out = []
    for x in list(found)[:limit]:
        out.append({"terim": x, "aciklama": "—"})
    return out

def step_by_step(text: str, limit: int = 6) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    # satır/cümle bazlı parçala
    chunks = []
    for line in t.splitlines():
        line = line.strip()
        if not line:
            continue
        chunks.extend([p.strip() for p in re.split(r"[.!?…]+", line) if p.strip()])
    # en fazla limit
    return [f"{i+1}) {c}" for i, c in enumerate(chunks[:limit])]

def simple_explain(text: str) -> str:
    # LLM yoksa: metni “madde”ye çevirip sadeleştirilmiş bir özet gibi ver
    steps = step_by_step(text, limit=4)
    if not steps:
        return ""
    return "Şöyle düşün:\n" + "\n".join(f"- {s[3:]}" for s in steps)

def traps(text: str) -> str:
    lower = (text or "").lower()
    if "join" in lower or "where" in lower:
        return "SQL’de en sık tuzak: JOIN koşulu ile WHERE filtresini karıştırmak."
    if "jwt" in lower or "oauth" in lower:
        return "Auth’ta en sık tuzak: access token süresi bitince refresh akışını unutmak."
    return "En sık tuzak: terimleri ezberleyip ‘neden-sonuç’ bağını kaçırmak."

def mini_quiz(text: str) -> List[Dict[str, Any]]:
    # LLM yoksa: basit 3 soru üret (tanım/ana fikir/uygulama)
    summ = one_sentence_summary(text)
    terms = extract_terms(text, limit=5)
    tnames = [x["terim"] for x in terms] or ["Kavram"]
    return [
        {"soru": f"Bu bölümün ana fikri nedir?", "cevap": summ},
        {"soru": f"{tnames[0]} neyle ilişkilidir? (1 cümle)", "cevap": "—"},
        {"soru": "Bu bilgiyi gerçek hayatta nerede kullanırsın? (1 örnek)", "cevap": "—"},
    ]

def build_anlamadim_payload(text: str, tema: str = "", seviye: str = "orta") -> Dict[str, Any]:
    safe_tema = (tema or "genel").strip().lower() or "genel"
    terms = extract_terms(text)
    summary = one_sentence_summary(text)
    return {
        "ozet_1cumle": summary,
        "cok_basit": simple_explain(text),
        "tema_bazli_ornek": f"{THEME_EXAMPLES.get(safe_tema, THEME_EXAMPLES['genel'])} Ana fikir: {summary}",
        "alternatif_ornek": f"Alternatif aci: once {(terms[0]['terim'] if terms else 'ana kavrami')} bul, sonra bunun ne ise yaradigini tek cumlede soyle.",
        "terimler": terms,
        "adim_adim": step_by_step(text),
        "tuzak": traps(text),
        "mini_test": mini_quiz(text),
        "tema": safe_tema,
        "seviye": seviye,
    }


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clean_short_text(value: str, limit: int = 72) -> str:
    clean = " ".join(str(value or "").split()).strip()
    if len(clean) <= limit:
        return clean
    short = clean[:limit].rsplit(" ", 1)[0].strip()
    return f"{short or clean[:limit].strip()}..."


def _part_short_title(parca) -> str:
    meta = dict(getattr(parca, "meta", {}) or {})
    for candidate in [
        meta.get("baslik"),
        meta.get("office_unit_title"),
        meta.get("symbol"),
        meta.get("sheet"),
        meta.get("slide_title"),
        meta.get("path"),
        getattr(parca, "adres", ""),
    ]:
        title = _clean_short_text(candidate, 64)
        if title:
            return title
    return f"Parca {getattr(parca, 'id', '')}".strip()


def _part_kind(parca) -> str:
    meta = dict(getattr(parca, "meta", {}) or {})
    return (
        str(meta.get("chunk_kind") or "")
        or str(meta.get("format") or "")
        or str(getattr(parca, "tur", "") or "")
        or "genel"
    ).strip().lower()


def _hard_reason(*, confusion_score: float, difficulty_score: float, quality_score: float, part_kind: str) -> str:
    quality_gap = max(0.0, 1.0 - quality_score)
    if confusion_score >= max(difficulty_score, quality_gap) and confusion_score >= 0.30:
        return "Kullanici bu bolume tekrar takiliyor."
    if difficulty_score >= max(confusion_score, quality_gap) and difficulty_score >= 0.55:
        return "Kavram yogunlugu ve yapisal zorluk yuksek."
    if quality_gap >= max(confusion_score, difficulty_score) and quality_gap >= 0.30:
        return "Parca kisa veya yogun oldugu icin yorumlamak zor."
    if "table" in part_kind or "tablo" in part_kind:
        return "Tabloyu okumak icin satir ve sutun iliskisini birlikte takip etmek gerekiyor."
    if "code" in part_kind or "kod" in part_kind:
        return "Kod akisi giris-cikis ve yan etkileri birlikte okumayi gerektiriyor."
    if "ocr" in part_kind or "visual" in part_kind or "gorsel" in part_kind:
        return "Gorsel parcada metin ipuclari parcali geldigi icin yorum daha zor."
    return "Bu bolum orta-yuksek zorluk sinyali tasiyor."


def build_hardest_parts_payload(*, doc, user, limit: int = 3, feature_enabled: bool = True) -> dict:
    scored = []
    for parca in doc.parcalar.all().order_by("id"):
        meta = dict(getattr(parca, "meta", {}) or {})
        difficulty_score = max(
            _safe_float(getattr(parca, "zorluk_skoru", 0.0)),
            _safe_float(meta.get("difficulty_score")),
        )
        quality_score = _safe_float(meta.get("quality_score"), 0.55)
        confusion_score = 0.0
        if feature_enabled:
            confusion_meta = compute_confusion_map_score(user=user, dokuman=doc, parca=parca)
            confusion_score = _safe_float(confusion_meta.get("confusion_map_score"))
        hardest_score = (
            (0.45 * confusion_score) + (0.35 * difficulty_score) + (0.20 * max(0.0, 1.0 - quality_score))
            if feature_enabled
            else max(difficulty_score, _safe_float(getattr(parca, "zorluk_skoru", 0.0)))
        )
        part_kind = _part_kind(parca)
        scored.append(
            {
                "parca_id": int(getattr(parca, "id", 0) or 0),
                "adres": str(getattr(parca, "adres", "") or ""),
                "neden_zor": _hard_reason(
                    confusion_score=confusion_score,
                    difficulty_score=difficulty_score,
                    quality_score=quality_score,
                    part_kind=part_kind,
                ),
                "kisa_baslik": _part_short_title(parca),
                "_score": round(hardest_score, 4),
            }
        )

    scored.sort(key=lambda item: (-item["_score"], item["parca_id"]))
    return {
        "oneriler": [
            {
                "parca_id": item["parca_id"],
                "adres": item["adres"],
                "neden_zor": item["neden_zor"],
                "kisa_baslik": item["kisa_baslik"],
            }
            for item in scored[: max(1, int(limit or 3))]
        ]
    }
