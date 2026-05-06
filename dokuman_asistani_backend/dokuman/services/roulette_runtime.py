from __future__ import annotations

import re

from dokuman.services.concept_runtime import compute_concept_candidates
from dokuman.services.feature_flags import modul_acik_mi
from dokuman.services.metric_store import compute_quiz_readiness_score, kaydet_skor_olayi

_ORDER_RE = re.compile(r"\b(?:once|sonra|ilk|ikinci|ucuncu|adim|step|phase|faz)\b", re.IGNORECASE)


def roulette_runtime_enabled() -> bool:
    return modul_acik_mi("DOCVERSE_ROULETTE_ENABLED", True) and modul_acik_mi("DOCVERSE_QUIZ_ENABLED", True)


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _sequence_signal(text: str) -> float:
    clean = _clean_text(text)
    if not clean:
        return 0.0
    hits = len(_ORDER_RE.findall(clean))
    numeric_hits = len(re.findall(r"\b\d+[.)-]?", clean))
    return max(0.0, min(1.0, (hits * 0.22) + (numeric_hits * 0.16)))


def _eligible_modes(*, parca, user) -> tuple[list[str], dict, int]:
    text = _clean_text(getattr(parca, "metin", "") or "")
    concepts = compute_concept_candidates(doc=parca.dokuman, user=user, parca=parca, limit=6)
    concept_count = len(concepts)
    readiness = compute_quiz_readiness_score(parca=parca)
    weak = bool((getattr(parca, "meta", {}) or {}).get("weak_content"))
    sequence_score = _sequence_signal(text)

    modes: list[str] = []
    if not weak and len(text) >= 60 and concept_count >= 2:
        modes.append("eslestirme")
    if not weak and len(text) >= 72 and sequence_score >= 0.3:
        modes.append("siralama")
    if not weak and len(text) >= 48 and concept_count >= 1:
        modes.append("bosluk_doldurma")
    if readiness["quiz_eligible"]:
        modes.append("mini_test")
    if not modes:
        modes = ["mini_test"]
    return list(dict.fromkeys(modes)), readiness, concept_count


def build_quiz_roulette_payload(*, parca, user, requested_mode: str | None = None) -> dict:
    eligible_modes, readiness, concept_count = _eligible_modes(parca=parca, user=user)
    normalized_request = _clean_text(requested_mode).lower()
    if normalized_request and normalized_request in eligible_modes:
        selected_mode = normalized_request
        reason = "requested_mode_applied"
    else:
        deterministic_index = (
            int(getattr(parca, "id", 0) or 0)
            + len(_clean_text(getattr(parca, "metin", "") or ""))
            + concept_count
        ) % max(len(eligible_modes), 1)
        selected_mode = eligible_modes[deterministic_index]
        if normalized_request and normalized_request not in eligible_modes:
            reason = "requested_mode_filtered"
        elif selected_mode == "siralama":
            reason = "sequence_friendly_chunk"
        elif selected_mode == "eslestirme":
            reason = "concept_dense_chunk"
        elif selected_mode == "bosluk_doldurma":
            reason = "cloze_friendly_chunk"
        else:
            reason = "fallback_mini_test"

    return {
        "parca_id": parca.id,
        "mod": selected_mode,
        "uygun_modlar": eligible_modes,
        "gerekce": reason,
        "_meta": {
            "roulette_mode": selected_mode,
            "roulette_reason": reason,
            "roulette_option_count": len(eligible_modes),
            "quiz_readiness_score": readiness["quiz_readiness_score"],
            "critical_concept_count": concept_count,
        },
    }


def record_roulette_events(*, user, parca, payload: dict):
    meta = dict(payload.get("_meta") or {})
    for olay_turu in ("roulette_mod_secildi", "roulette_uretildi"):
        kaydet_skor_olayi(
            kullanici=user,
            olay_turu=olay_turu,
            kaynak_modul="roulette_runtime.api",
            dokuman=getattr(parca, "dokuman", None),
            parca=parca,
            score_map=meta,
            durum="ok",
        )
