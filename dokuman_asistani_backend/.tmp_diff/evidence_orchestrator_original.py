from __future__ import annotations

import math
import re
from typing import Any

from dokuman.services.rag import build_retrieval_ozeti, normalize_retrieval_hits
from dokuman.services.retrieval_terms import normalize_query_terms

WORD_RE = re.compile(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü_]+", re.UNICODE)
STOP = {
    "ve", "ile", "bir", "bu", "şu", "için", "gibi", "ama", "fakat", "çünkü", "da", "de",
    "the", "a", "an", "to", "of", "in", "on", "for", "is", "are",
}


def tokenize(text: str) -> list[str]:
    return normalize_query_terms(text)


def score_overlap(question_tokens: list[str], text: str) -> float:
    text_tokens = tokenize(text)
    if not question_tokens or not text_tokens:
        return 0.0
    text_token_set = set(text_tokens)
    hit_count = sum(1 for token in question_tokens if token in text_token_set)
    return hit_count / max(1, len(set(question_tokens)))


def snippet(text: str, n: int = 280) -> str:
    clean_text = " ".join((text or "").split())
    return clean_text[:n] + ("…" if len(clean_text) > n else "")


def _response_safe_hit(hit: dict[str, Any]) -> dict[str, Any]:
    """Gercek response'larda ham evidence metnini degil yalnizca guvenli ozet alanlarini tasir."""
    item = dict(hit or {})
    safe: dict[str, Any] = {}
    for key in (
        "parca_id",
        "dokuman_id",
        "adres",
        "baslik_yolu",
        "retrieval_kaynagi",
        "kanit_id",
        "cevapta_kullanildi",
        "kanit_gucu",
        "zayif_kaynak_mi",
        "weak_content",
        "weak_evidence",
        "chunk_kind",
        "format",
        "chunk_index",
        "code_language",
        "code_unit_kind",
        "code_unit_name",
        "parent_unit",
        "line_start",
        "line_end",
        "code_purpose_hints",
        "soru_terim_kapsama_orani",
        "evidence_strength",
    ):
        if item.get(key) is not None:
            safe[key] = item.get(key)
    for key in ("skor", "quality_score", "evidence_score"):
        if item.get(key) is not None:
            safe[key] = item.get(key)

    safe["weak_evidence"] = bool(
        item.get("weak_evidence")
        if item.get("weak_evidence") is not None
        else item.get("zayif_kaynak_mi")
    )
    safe["evidence_strength"] = (
        str(item.get("evidence_strength") or item.get("kanit_gucu") or "dusuk").strip()
        or "dusuk"
    )
    safe["snippet"] = snippet(item.get("snippet") or item.get("metin") or "", 280)
    return safe


def _infer_default_source(hits: list) -> str:
    for hit in hits or []:
        if isinstance(hit, dict):
            source = str(hit.get("retrieval_kaynagi") or "").strip()
            if source:
                return source
    return "rag.semantic"


def _dedupe_int_ids(values) -> list[int]:
    seen = set()
    out: list[int] = []
    for value in values or []:
        try:
            clean = int(value)
        except Exception:
            continue
        if clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _is_weak_evidence(hit: dict[str, Any], coverage_ratio: float) -> bool:
    if hit.get("weak_evidence") is not None:
        return bool(hit.get("weak_evidence"))
    if hit.get("zayif_kaynak_mi") is not None:
        return bool(hit.get("zayif_kaynak_mi"))
    if hit.get("weak_content") is not None:
        return bool(hit.get("weak_content"))

    text = " ".join(str(hit.get("metin") or "").split())
    tokens = tokenize(text)
    unique_token_count = len(set(tokens))
    char_count = len(text)
    score = _evidence_score(hit)
    quality_score = _safe_float(hit.get("quality_score"), default=0.0)
    rerank_meta = hit.get("_rerank") if isinstance(hit.get("_rerank"), dict) else {}
    if rerank_meta.get("dusuk_icerik_cezasi_var_mi"):
        return True

    if coverage_ratio <= 0.0:
        return True
    if coverage_ratio < 0.2 and unique_token_count < 12:
        return True
    if char_count < 35 and unique_token_count < 5:
        return True
    if char_count < 80 and unique_token_count < 8 and coverage_ratio < 0.3:
        return True
    if score < 0.15 and unique_token_count < 8:
        return True
    if quality_score > 0.0 and quality_score < 0.2 and coverage_ratio < 0.35:
        return True
    return False


def _evidence_strength_label(coverage_ratio: float, is_weak: bool, score: float) -> str:
    if is_weak:
        return "dusuk"
    if coverage_ratio >= 0.6 and score >= 0.45:
        return "yuksek"
    if coverage_ratio >= 0.3:
        return "orta"
    return "dusuk"


def _selection_sort_key(hit: dict[str, Any]):
    rerank_meta = hit.get("_rerank") if isinstance(hit.get("_rerank"), dict) else {}
    return (
        0 if hit.get("zayif_kaynak_mi") else 1,
        _evidence_score(hit),
        float(hit.get("soru_terim_kapsama_orani") or 0.0),
        1 if rerank_meta.get("tam_ifade_eslesmesi_var_mi") else 0,
        -int(hit.get("kanit_sirasi") or 0),
    )


def _evidence_score(hit: dict[str, Any]) -> float:
    rerank_meta = hit.get("_rerank") if isinstance(hit.get("_rerank"), dict) else {}
    try:
        if hit.get("_selection_score") is not None:
            return float(hit.get("_selection_score") or 0.0)
        if rerank_meta.get("final_rerank") is not None:
            return float(rerank_meta.get("final_rerank") or 0.0)
        return float(hit.get("skor") or 0.0)
    except Exception:
        return 0.0


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-float(value)))


def _derive_evidence_confidence(candidate_hits: list[dict[str, Any]]) -> dict[str, float | bool]:
    sirali = sorted(candidate_hits or [], key=_selection_sort_key, reverse=True)
    r1 = _evidence_score(sirali[0]) if sirali else 0.0
    r2 = _evidence_score(sirali[1]) if len(sirali) > 1 else 0.0
    margin = max(0.0, r1 - r2)
    confidence = (0.6 * r1) + (0.4 * _sigmoid((10 * margin) - 0.5))
    confidence = round(max(0.0, min(1.0, confidence)), 4)
    has_strong_candidate = any(
        (not bool(hit.get("zayif_kaynak_mi")))
        and float(hit.get("soru_terim_kapsama_orani") or 0.0) >= 0.4
        for hit in sirali[:2]
    )
    should_abstain = confidence < 0.45 or (r1 < 0.55 and not has_strong_candidate)
    abstain_reason = ""
    if not sirali:
        abstain_reason = "kanit_yok"
    elif should_abstain:
        if bool(sirali[0].get("zayif_kaynak_mi")):
            abstain_reason = "zayif_kanit"
        elif confidence < 0.45:
            abstain_reason = "dusuk_guven"
        elif r1 < 0.55:
            abstain_reason = "dusuk_skor"
        else:
            abstain_reason = "dusuk_kanit"
    return {
        "top1_score": round(r1, 4),
        "top2_score": round(r2, 4),
        "evidence_margin": round(margin, 4),
        "evidence_confidence": confidence,
        "should_abstain": should_abstain,
        "abstain_reason": abstain_reason,
    }


def _derive_source_confidence(
    secilen_kanitlar: list[dict[str, Any]],
    *,
    evidence_confidence: float = 0.0,
) -> str:
    if not secilen_kanitlar:
        return "dusuk"

    if evidence_confidence < 0.45:
        return "dusuk"

    avg_coverage = (
        sum(hit["soru_terim_kapsama_orani"] for hit in secilen_kanitlar)
        / len(secilen_kanitlar)
    )
    any_weak = any(hit["zayif_kaynak_mi"] for hit in secilen_kanitlar)
    if evidence_confidence >= 0.70 and avg_coverage >= 0.5 and not any_weak:
        return "yuksek"
    if avg_coverage >= 0.25 and len(secilen_kanitlar) >= 1:
        return "orta"
    return "dusuk"


def _derive_answer_decision(
    *,
    candidate_hits: list[dict[str, Any]],
    selected_hits: list[dict[str, Any]],
    confidence_meta: dict[str, Any],
    kaynak_guveni: str,
    forced_selection_istendi_mi: bool = False,
    abstention_uygulandi_mi: bool = False,
) -> dict[str, Any]:
    selected_hits = list(selected_hits or [])
    has_candidates = bool(candidate_hits)
    has_selected = bool(selected_hits)
    should_abstain = bool(confidence_meta.get("should_abstain"))
    evidence_confidence = _safe_float(confidence_meta.get("evidence_confidence"), default=0.0)
    top1_score = _safe_float(confidence_meta.get("top1_score"), default=0.0)
    weak_selected = any(bool(hit.get("zayif_kaynak_mi")) for hit in selected_hits)
    weak_evidence = (
        (not has_selected)
        or should_abstain
        or weak_selected
        or kaynak_guveni == "dusuk"
        or evidence_confidence < 0.55
    )
    answer_allowed = has_selected and not should_abstain
    if forced_selection_istendi_mi and has_selected:
        answer_allowed = True
    abstain_reason = ""
    if not has_candidates:
        abstain_reason = "kanit_yok"
    elif not has_selected:
        abstain_reason = "kanit_yok"
    elif not answer_allowed:
        abstain_reason = str(confidence_meta.get("abstain_reason") or "dusuk_kanit").strip() or "dusuk_kanit"

    if not answer_allowed:
        evidence_strength = "dusuk"
    elif not weak_evidence and kaynak_guveni == "yuksek" and evidence_confidence >= 0.7:
        evidence_strength = "yuksek"
    elif kaynak_guveni in {"orta", "yuksek"} and top1_score >= 0.45:
        evidence_strength = "orta"
    else:
        evidence_strength = "dusuk"

    return {
        "answer_allowed": bool(answer_allowed),
        "weak_evidence": bool(weak_evidence),
        "evidence_strength": evidence_strength,
        "abstain_reason": abstain_reason,
    }


def _read_decision_field(meta: dict[str, Any], key: str, default=None):
    if key in meta:
        return meta.get(key)
    selection_summary = dict(meta.get("evidence_secim_ozeti") or {})
    if key in selection_summary:
        return selection_summary.get(key)
    retrieval_ozeti = dict(meta.get("retrieval_ozeti") or {})
    if key in retrieval_ozeti:
        return retrieval_ozeti.get(key)
    nested_summary = dict(retrieval_ozeti.get("evidence_secim_ozeti") or {})
    if key in nested_summary:
        return nested_summary.get(key)
    return default


def prepare_answer_evidence(
    question: str,
    evidences: list[dict[str, Any]],
    *,
    answer_limit: int = 2,
    forced_parca_idleri: list[int] | None = None,
) -> dict[str, Any]:
    q_toks = tokenize(question)
    prepared: list[dict[str, Any]] = []
    forced_selection_istendi_mi = forced_parca_idleri is not None
    forced_ids = _dedupe_int_ids(forced_parca_idleri)

    for index, raw in enumerate(evidences, start=1):
        hit = dict(raw)
        pid = hit.get("parca_id")
        coverage_ratio = score_overlap(q_toks, hit.get("metin") or "")
        score = _evidence_score(hit)
        if score <= 0.0:
            hit["_selection_score"] = round(
                min(
                    0.99,
                    0.25
                    + (0.7 * coverage_ratio)
                    + (0.05 if coverage_ratio >= 0.25 else 0.0),
                ),
                4,
            )
            score = _evidence_score(hit)
        matched_terms = sorted(set(q_toks) & set(tokenize(hit.get("metin") or "")))
        weak = _is_weak_evidence(hit, coverage_ratio)
        hit["kanit_id"] = f"kanit:{pid}" if pid is not None else f"kanit:sira:{index}"
        hit["kanit_sirasi"] = index
        hit["snippet"] = hit.get("snippet") or snippet(hit.get("metin") or "", 280)
        hit["soru_terim_kapsama_orani"] = round(coverage_ratio, 3)
        hit["zayif_kaynak_mi"] = weak
        hit["weak_evidence"] = weak
        hit["eslesen_soru_terimleri"] = matched_terms
        hit["kanit_gucu"] = _evidence_strength_label(coverage_ratio, weak, score)
        hit["evidence_strength"] = hit["kanit_gucu"]
        hit["evidence_score"] = round(score, 4)
        prepared.append(hit)

    varsayilan_kanitlar = sorted(
        [hit for hit in prepared if not hit["zayif_kaynak_mi"]],
        key=_selection_sort_key,
        reverse=True,
    )[: max(1, answer_limit)]
    if not varsayilan_kanitlar:
        varsayilan_kanitlar = sorted(
            prepared,
            key=_selection_sort_key,
            reverse=True,
        )[: max(1, answer_limit)]

    if forced_selection_istendi_mi:
        hit_by_parca_id = {
            int(hit["parca_id"]): hit
            for hit in prepared
            if hit.get("parca_id") is not None
        }
        secilen_kanitlar = [
            hit_by_parca_id[parca_id]
            for parca_id in forced_ids
            if parca_id in hit_by_parca_id
        ]
    else:
        secilen_kanitlar = varsayilan_kanitlar

    confidence_meta = _derive_evidence_confidence(prepared)
    abstention_uygulandi_mi = bool(
        (not forced_selection_istendi_mi) and confidence_meta["should_abstain"]
    )
    if abstention_uygulandi_mi:
        secilen_kanitlar = []

    secilen_kanit_idleri = {hit["kanit_id"] for hit in secilen_kanitlar}
    for hit in prepared:
        hit["cevapta_kullanildi"] = hit["kanit_id"] in secilen_kanit_idleri

    kaynak_guveni = _derive_source_confidence(
        secilen_kanitlar,
        evidence_confidence=float(confidence_meta["evidence_confidence"] or 0.0),
    )
    decision_meta = _derive_answer_decision(
        candidate_hits=prepared,
        selected_hits=secilen_kanitlar,
        confidence_meta=confidence_meta,
        kaynak_guveni=kaynak_guveni,
        forced_selection_istendi_mi=forced_selection_istendi_mi,
        abstention_uygulandi_mi=abstention_uygulandi_mi,
    )

    return {
        "kanitlar": prepared,
        "secilen_kanitlar": secilen_kanitlar,
        "kullanilan_parca_idleri": [
            hit.get("parca_id")
            for hit in secilen_kanitlar
            if hit.get("parca_id") is not None
        ],
        "kullanilan_kanit_idleri": [hit["kanit_id"] for hit in secilen_kanitlar],
        "kullanilan_adresler": [
            str(hit.get("adres") or "").strip()
            for hit in secilen_kanitlar
            if str(hit.get("adres") or "").strip()
        ],
        "kaynak_guveni": kaynak_guveni,
        "kaynak_zayif_mi": bool(decision_meta["weak_evidence"]),
        "kaynak_zorlamasi_uygulandi_mi": forced_selection_istendi_mi,
        "evidence_confidence": confidence_meta["evidence_confidence"],
        "evidence_margin": confidence_meta["evidence_margin"],
        "top1_score": confidence_meta["top1_score"],
        "top2_score": confidence_meta["top2_score"],
        "abstention_uygulandi_mi": bool(`r`n            (not forced_selection_istendi_mi) and confidence_meta["should_abstain"]`r`n        ),
        "answer_allowed": bool(decision_meta["answer_allowed"]),
        "weak_evidence": bool(decision_meta["weak_evidence"]),
        "evidence_strength": str(decision_meta["evidence_strength"]),
        "abstain_reason": str(decision_meta["abstain_reason"]),
    }


def canonicalize_evidence_hits(
    hits: list,
    *,
    retrieval_kaynagi: str | None = None,
    varsayilan_dokuman_id=None,
    dokuman_filtreleri=None,
) -> dict[str, Any]:
    normalized_hits = normalize_retrieval_hits(
        hits or [],
        retrieval_kaynagi=retrieval_kaynagi or _infer_default_source(hits or []),
        varsayilan_dokuman_id=varsayilan_dokuman_id,
    )
    filtered_doc_ids = _dedupe_int_ids(dokuman_filtreleri)
    if not filtered_doc_ids:
        return {
            "ham_kanitlar": normalized_hits,
            "kanonik_kanitlar": normalized_hits,
            "dokuman_filtreleri": [],
            "dokuman_filtresi_uygulandi_mi": False,
            "filtrelenen_kanit_sayisi": 0,
        }

    canonical_hits = [
        hit
        for hit in normalized_hits
        if hit.get("dokuman_id") in filtered_doc_ids
    ]
    return {
        "ham_kanitlar": normalized_hits,
        "kanonik_kanitlar": canonical_hits,
        "dokuman_filtreleri": filtered_doc_ids,
        "dokuman_filtresi_uygulandi_mi": True,
        "filtrelenen_kanit_sayisi": max(0, len(normalized_hits) - len(canonical_hits)),
    }


def prepare_evidence_candidates(
    hits: list,
    *,
    retrieval_kaynagi: str | None = None,
    varsayilan_dokuman_id=None,
    dokuman_filtreleri=None,
) -> dict[str, Any]:
    canonicalization = canonicalize_evidence_hits(
        hits or [],
        retrieval_kaynagi=retrieval_kaynagi or _infer_default_source(hits or []),
        varsayilan_dokuman_id=varsayilan_dokuman_id,
        dokuman_filtreleri=dokuman_filtreleri,
    )

    aday_kanitlar: list[dict[str, Any]] = []
    for hit in canonicalization["kanonik_kanitlar"]:
        merged = dict(hit)
        merged["snippet"] = snippet(merged.get("snippet") or merged.get("metin") or "", 280)
        aday_kanitlar.append(merged)

    return {
        **canonicalization,
        "aday_kanitlar": aday_kanitlar,
    }


def _build_evidence_selection_summary(
    *,
    raw_hit_count: int,
    canonical_hits: list[dict[str, Any]],
    selected_hits: list[dict[str, Any]],
    forced_parca_idleri: list[int] | None = None,
    dokuman_filtreleri: list[int] | None = None,
    dokuman_filtresi_uygulandi_mi: bool = False,
    filtrelenen_kanit_sayisi: int = 0,
    kaynak_guveni: str = "dusuk",
    kaynak_zayif_mi: bool = True,
    evidence_confidence: float = 0.0,
    evidence_margin: float = 0.0,
    top1_score: float = 0.0,
    top2_score: float = 0.0,
    abstention_uygulandi_mi: bool = False,
    answer_allowed: bool = False,
    weak_evidence: bool = True,
    evidence_strength: str = "dusuk",
    abstain_reason: str = "",
) -> dict[str, Any]:
    return {
        "ham_kanit_sayisi": int(raw_hit_count or 0),
        "toplam_kanit_sayisi": len(canonical_hits),
        "secilen_kanit_sayisi": len(selected_hits),
        "secilen_parca_idleri": [
            hit.get("parca_id")
            for hit in selected_hits
            if hit.get("parca_id") is not None
        ],
        "secilen_kanit_idleri": [
            hit.get("kanit_id")
            for hit in selected_hits
            if hit.get("kanit_id")
        ],
        "forced_parca_idleri": _dedupe_int_ids(forced_parca_idleri),
        "dokuman_filtreleri": _dedupe_int_ids(dokuman_filtreleri),
        "dokuman_filtresi_uygulandi_mi": bool(dokuman_filtresi_uygulandi_mi),
        "filtrelenen_kanit_sayisi": max(0, int(filtrelenen_kanit_sayisi or 0)),
        "kaynak_guveni": str(kaynak_guveni or "dusuk"),
        "kaynak_zayif_mi": bool(kaynak_zayif_mi),
        "evidence_confidence": round(float(evidence_confidence or 0.0), 4),
        "evidence_margin": round(float(evidence_margin or 0.0), 4),
        "top1_score": round(float(top1_score or 0.0), 4),
        "top2_score": round(float(top2_score or 0.0), 4),
        "abstention_uygulandi_mi": bool(abstention_uygulandi_mi),
        "answer_allowed": bool(answer_allowed),
        "weak_evidence": bool(weak_evidence),
        "evidence_strength": str(evidence_strength or "dusuk"),
        "abstain_reason": str(abstain_reason or ""),
    }


def derive_answer_source_state(
    kanit_meta: dict[str, Any],
    *,
    citation_ids=None,
    citation_required: bool = False,
) -> dict[str, Any]:
    retrieval_ozeti = dict(kanit_meta.get("retrieval_ozeti") or {})
    secilen_kanitlar = list(kanit_meta.get("secilen_kanitlar") or [])
    clean_citation_ids = _dedupe_int_ids(citation_ids)

    answer_allowed = bool(_read_decision_field(kanit_meta, "answer_allowed", default=bool(secilen_kanitlar)))
    kaynak_zayif_mi = bool(
        _read_decision_field(
            kanit_meta,
            "weak_evidence",
            default=bool(kanit_meta.get("kaynak_zayif_mi")) or not secilen_kanitlar,
        )
    )
    evidence_strength = str(
        _read_decision_field(
            kanit_meta,
            "evidence_strength",
            default=str(kanit_meta.get("kaynak_guveni") or "dusuk"),
        )
        or "dusuk"
    ).strip()
    abstain_reason = str(_read_decision_field(kanit_meta, "abstain_reason", default="") or "").strip()

    if citation_required and not clean_citation_ids:
        answer_allowed = False
        kaynak_zayif_mi = True
        evidence_strength = "dusuk"
        abstain_reason = abstain_reason or "citation_gerekli"

    kaynak_guveni = str(kanit_meta.get("kaynak_guveni") or "dusuk")
    if not secilen_kanitlar or not answer_allowed:
        kaynak_guveni = "dusuk"
    elif kaynak_zayif_mi and kaynak_guveni == "yuksek":
        kaynak_guveni = "orta"
    if kaynak_guveni == "dusuk":
        evidence_strength = "dusuk"
    elif kaynak_zayif_mi and evidence_strength == "yuksek":
        evidence_strength = "orta"

    return {
        "kaynak_guveni": kaynak_guveni,
        "kaynak_zayif_mi": kaynak_zayif_mi,
        "citation_gerekli_miydi": bool(citation_required),
        "citation_var_mi": bool(clean_citation_ids),
        "answer_allowed": bool(answer_allowed),
        "weak_evidence": bool(kaynak_zayif_mi),
        "evidence_strength": evidence_strength,
        "abstain_reason": abstain_reason,
    }


def build_evidence_response_payload(
    kanit_meta: dict[str, Any],
    *,
    include_kanitlar: bool = True,
    include_kaynak_zorlamasi: bool = True,
) -> dict[str, Any]:
    selected_hits = list(kanit_meta.get("secilen_kanitlar") or [])
    safe_selected_hits = [_response_safe_hit(hit) for hit in selected_hits]
    answer_allowed = bool(_read_decision_field(kanit_meta, "answer_allowed", default=bool(selected_hits)))
    weak_evidence = bool(
        _read_decision_field(
            kanit_meta,
            "weak_evidence",
            default=bool(kanit_meta.get("kaynak_zayif_mi")) or not selected_hits,
        )
    )
    evidence_strength = str(
        _read_decision_field(
            kanit_meta,
            "evidence_strength",
            default=str(kanit_meta.get("kaynak_guveni") or "dusuk"),
        )
        or "dusuk"
    ).strip()
    abstain_reason = str(_read_decision_field(kanit_meta, "abstain_reason", default="") or "").strip()
    retrieval_ozeti = dict(kanit_meta.get("retrieval_ozeti") or {})
    evidence_secim_ozeti = dict(
        retrieval_ozeti.get("evidence_secim_ozeti")
        or kanit_meta.get("evidence_secim_ozeti")
        or {}
    )
    evidence_secim_ozeti.update(
        {
            "answer_allowed": answer_allowed,
            "weak_evidence": weak_evidence,
            "evidence_strength": evidence_strength,
            "abstain_reason": abstain_reason,
        }
    )
    retrieval_ozeti.update(
        {
            "evidence_secim_ozeti": evidence_secim_ozeti,
            "answer_allowed": answer_allowed,
            "weak_evidence": weak_evidence,
            "evidence_strength": evidence_strength,
            "abstain_reason": abstain_reason,
        }
    )
    kullanilan_parca_idleri = list(kanit_meta.get("kullanilan_parca_idleri") or [])
    if not kullanilan_parca_idleri:
        kullanilan_parca_idleri = [
            hit.get("parca_id")
            for hit in selected_hits
            if hit.get("parca_id") is not None
        ]
    kullanilan_kanit_idleri = list(kanit_meta.get("kullanilan_kanit_idleri") or [])
    if not kullanilan_kanit_idleri:
        kullanilan_kanit_idleri = [
            hit.get("kanit_id")
            for hit in selected_hits
            if hit.get("kanit_id")
        ]
    kullanilan_adresler = list(kanit_meta.get("kullanilan_adresler") or [])
    if not kullanilan_adresler:
        kullanilan_adresler = [
            str(hit.get("adres") or "").strip()
            for hit in selected_hits
            if str(hit.get("adres") or "").strip()
        ]
    payload = {
        "kullanilan_kanit_sayisi": int(kanit_meta.get("kullanilan_kanit_sayisi") or len(selected_hits)),
        "kullanilan_parca_idleri": kullanilan_parca_idleri,
        "kullanilan_kanit_idleri": kullanilan_kanit_idleri,
        "kullanilan_adresler": kullanilan_adresler,
        "kullanilan_kanitlar": safe_selected_hits,
        "kaynak_guveni": kanit_meta.get("kaynak_guveni"),
        "kaynak_zayif_mi": bool(weak_evidence),
        "evidence_confidence": float(kanit_meta.get("evidence_confidence") or 0.0),
        "evidence_margin": float(kanit_meta.get("evidence_margin") or 0.0),
        "answer_allowed": answer_allowed,
        "weak_evidence": weak_evidence,
        "evidence_strength": evidence_strength,
        "abstain_reason": abstain_reason,
        "retrieval_ozeti": retrieval_ozeti,
    }
    if include_kanitlar:
        payload["kanitlar"] = [_response_safe_hit(hit) for hit in list(kanit_meta.get("kanitlar") or [])]
    if include_kaynak_zorlamasi:
        payload["kaynak_zorlamasi_uygulandi_mi"] = bool(
            kanit_meta.get("kaynak_zorlamasi_uygulandi_mi")
        )
    return payload


def orchestrate_evidence_selection(
    question: str,
    hits: list,
    *,
    answer_limit: int = 2,
    dokuman_filtresi_var_mi: bool = False,
    dokuman_filtreleri=None,
    auto_index_denendi_mi: bool = False,
    forced_parca_idleri: list[int] | None = None,
    varsayilan_dokuman_id=None,
    retrieval_kaynagi: str | None = None,
) -> dict[str, Any]:
    candidate_meta = prepare_evidence_candidates(
        hits or [],
        retrieval_kaynagi=retrieval_kaynagi or _infer_default_source(hits or []),
        varsayilan_dokuman_id=varsayilan_dokuman_id,
        dokuman_filtreleri=dokuman_filtreleri,
    )
    canonical_hits = candidate_meta["kanonik_kanitlar"]
    annotated_hits = candidate_meta["aday_kanitlar"]

    kanit_meta = prepare_answer_evidence(
        question,
        annotated_hits,
        answer_limit=max(1, int(answer_limit or 1)),
        forced_parca_idleri=forced_parca_idleri,
    )
    secilen_kanitlar = kanit_meta["secilen_kanitlar"]
    retrieval_ozeti = build_retrieval_ozeti(
        question,
        kanit_meta["kanitlar"],
        kullanilan_hit=len(secilen_kanitlar),
        dokuman_filtresi_var_mi=bool(
            dokuman_filtresi_var_mi or candidate_meta["dokuman_filtresi_uygulandi_mi"]
        ),
        auto_index_denendi_mi=auto_index_denendi_mi,
    )
    evidence_secim_ozeti = _build_evidence_selection_summary(
        raw_hit_count=len(candidate_meta["ham_kanitlar"]),
        canonical_hits=canonical_hits,
        selected_hits=secilen_kanitlar,
        forced_parca_idleri=forced_parca_idleri,
        dokuman_filtreleri=candidate_meta["dokuman_filtreleri"],
        dokuman_filtresi_uygulandi_mi=candidate_meta["dokuman_filtresi_uygulandi_mi"],
        filtrelenen_kanit_sayisi=candidate_meta["filtrelenen_kanit_sayisi"],
        kaynak_guveni=kanit_meta["kaynak_guveni"],
        kaynak_zayif_mi=bool(kanit_meta["kaynak_zayif_mi"]),
        evidence_confidence=float(kanit_meta.get("evidence_confidence") or 0.0),
        evidence_margin=float(kanit_meta.get("evidence_margin") or 0.0),
        top1_score=float(kanit_meta.get("top1_score") or 0.0),
        top2_score=float(kanit_meta.get("top2_score") or 0.0),
        abstention_uygulandi_mi=bool(kanit_meta.get("abstention_uygulandi_mi")),
        answer_allowed=bool(kanit_meta.get("answer_allowed")),
        weak_evidence=bool(kanit_meta.get("weak_evidence")),
        evidence_strength=str(kanit_meta.get("evidence_strength") or "dusuk"),
        abstain_reason=str(kanit_meta.get("abstain_reason") or ""),
    )
    retrieval_ozeti = {
        **retrieval_ozeti,
        "evidence_secim_ozeti": evidence_secim_ozeti,
        "evidence_confidence": float(kanit_meta.get("evidence_confidence") or 0.0),
        "evidence_margin": float(kanit_meta.get("evidence_margin") or 0.0),
        "abstention_uygulandi_mi": bool(kanit_meta.get("abstention_uygulandi_mi")),
        "answer_allowed": bool(kanit_meta.get("answer_allowed")),
        "weak_evidence": bool(kanit_meta.get("weak_evidence")),
        "evidence_strength": str(kanit_meta.get("evidence_strength") or "dusuk"),
        "abstain_reason": str(kanit_meta.get("abstain_reason") or ""),
        "kaynak_guveni": str(kanit_meta.get("kaynak_guveni") or "dusuk"),
    }

    return {
        "ham_kanit_sayisi": len(candidate_meta["ham_kanitlar"]),
        "kanitlar": kanit_meta["kanitlar"],
        "secilen_kanitlar": secilen_kanitlar,
        "kullanilan_parca_idleri": list(kanit_meta["kullanilan_parca_idleri"]),
        "kullanilan_kanit_idleri": list(kanit_meta["kullanilan_kanit_idleri"]),
        "kullanilan_kanit_sayisi": len(secilen_kanitlar),
        "kullanilan_adresler": list(kanit_meta["kullanilan_adresler"]),
        "dokuman_filtreleri": list(candidate_meta["dokuman_filtreleri"]),
        "kaynak_guveni": kanit_meta["kaynak_guveni"],
        "kaynak_zayif_mi": bool(kanit_meta["kaynak_zayif_mi"]),
        "kaynak_zorlamasi_uygulandi_mi": bool(kanit_meta["kaynak_zorlamasi_uygulandi_mi"]),
        "evidence_confidence": float(kanit_meta.get("evidence_confidence") or 0.0),
        "evidence_margin": float(kanit_meta.get("evidence_margin") or 0.0),
        "top1_score": float(kanit_meta.get("top1_score") or 0.0),
        "top2_score": float(kanit_meta.get("top2_score") or 0.0),
        "abstention_uygulandi_mi": bool(kanit_meta.get("abstention_uygulandi_mi")),
        "answer_allowed": bool(kanit_meta.get("answer_allowed")),
        "weak_evidence": bool(kanit_meta.get("weak_evidence")),
        "evidence_strength": str(kanit_meta.get("evidence_strength") or "dusuk"),
        "abstain_reason": str(kanit_meta.get("abstain_reason") or ""),
        "evidence_secim_ozeti": evidence_secim_ozeti,
        "retrieval_ozeti": retrieval_ozeti,
    }

