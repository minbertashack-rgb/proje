from __future__ import annotations

import re

from dokuman.services.concept_runtime import compute_concept_candidates
from dokuman.services.feature_flags import modul_acik_mi
from dokuman.services.metric_store import compute_quiz_readiness_score, kaydet_skor_olayi

_TERM_RE = re.compile(r"\b[A-Za-zÇĞİÖŞÜçğıöşü0-9_-]{3,}\b")


def puzzle_runtime_enabled() -> bool:
    return modul_acik_mi("DOCVERSE_ROULETTE_ENABLED", True) and modul_acik_mi("DOCVERSE_QUIZ_ENABLED", True)


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _choose_terms(*, parca, user, limit: int = 3) -> list[str]:
    text = _clean_text(getattr(parca, "metin", "") or "")
    concepts = compute_concept_candidates(doc=parca.dokuman, user=user, parca=parca, limit=8)
    seen = set()
    out = []
    for item in concepts:
        term = _clean_text(item.get("kavram"))
        if len(term) < 3:
            continue
        if term.lower() not in text.lower():
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
        if len(out) >= limit:
            return out
    for raw in _TERM_RE.findall(text):
        clean = _clean_text(raw)
        if len(clean) < 4 or clean.lower() in seen:
            continue
        if not (any(ch.isdigit() for ch in clean) or clean.isupper()):
            continue
        seen.add(clean.lower())
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def _mask_context(text: str, term: str, index: int) -> str:
    placeholder = f"[BOSLUK_{index}]"
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    masked = pattern.sub(placeholder, text, count=1)
    return masked[:180]


def build_puzzle_payload(*, parca, user) -> dict:
    text = _clean_text(getattr(parca, "metin", "") or "")
    readiness = compute_quiz_readiness_score(parca=parca)
    weak = bool((getattr(parca, "meta", {}) or {}).get("weak_content"))
    terms = [] if weak or len(text) < 40 or not readiness["quiz_eligible"] else _choose_terms(parca=parca, user=user, limit=3)
    blanks = [
        {
            "sira": index,
            "yer_tutucu": f"[BOSLUK_{index}]",
            "maskeli_baglam": _mask_context(text, term, index),
        }
        for index, term in enumerate(terms, start=1)
    ]
    reason = "weak_or_short_content" if not terms else "cloze_ready"
    return {
        "orijinal_parca_id": parca.id,
        "bosluklar": blanks,
        "beklenen_kelimeler": terms,
        "ipucu_var_mi": bool(terms),
        "_meta": {
            "puzzle_blank_count": len(terms),
            "quiz_readiness_score": readiness["quiz_readiness_score"],
            "puzzle_status": reason,
        },
    }


def record_puzzle_event(*, user, parca, payload: dict):
    return kaydet_skor_olayi(
        kullanici=user,
        olay_turu="puzzle_uretildi",
        kaynak_modul="puzzle_runtime.api",
        dokuman=getattr(parca, "dokuman", None),
        parca=parca,
        score_map=dict(payload.get("_meta") or {}),
        durum="ok" if payload.get("beklenen_kelimeler") else "skipped",
    )
