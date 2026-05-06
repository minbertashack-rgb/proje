# dokuman/services/kanitli_qa.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple

from dokuman.services.evidence_orchestrator import (
    prepare_evidence_candidates,
    prepare_answer_evidence,
    score_overlap,
    snippet,
    tokenize,
)
from dokuman.services.rag import normalize_retrieval_hits


def _normalize_evidence_strength(value: Any, *, default: str = "dusuk") -> str:
    clean = str(value or default).strip().lower()
    if clean in {"yuksek", "orta", "dusuk"}:
        return clean
    return default


def _merge_answer_decision(
    evidences: List[Dict[str, Any]],
    *,
    kaynak_zayif_mi: bool = False,
    answer_allowed: bool | None = None,
    weak_evidence: bool | None = None,
    evidence_strength: str | None = None,
    abstain_reason: str = "",
) -> Dict[str, Any]:
    safe_evidences = list(evidences or [])
    derived_weak = any(
        bool(ev.get("weak_evidence"))
        or bool(ev.get("zayif_kaynak_mi"))
        or bool(ev.get("weak_content"))
        for ev in safe_evidences
    )
    strongest_rank = {"dusuk": 0, "orta": 1, "yuksek": 2}
    derived_strength = "dusuk"
    for ev in safe_evidences:
        current = _normalize_evidence_strength(
            ev.get("evidence_strength") or ev.get("kanit_gucu"),
            default="dusuk",
        )
        if strongest_rank[current] > strongest_rank[derived_strength]:
            derived_strength = current

    has_evidence = bool(safe_evidences)
    if weak_evidence is None:
        weak_evidence = bool(kaynak_zayif_mi or derived_weak or not has_evidence)
    else:
        weak_evidence = bool(weak_evidence)

    normalized_strength = _normalize_evidence_strength(
        evidence_strength or derived_strength,
        default="dusuk" if weak_evidence or not has_evidence else "orta",
    )
    if weak_evidence and normalized_strength == "yuksek":
        normalized_strength = "orta"
    if not has_evidence:
        normalized_strength = "dusuk"

    if answer_allowed is None:
        answer_allowed = has_evidence
    else:
        answer_allowed = bool(answer_allowed)

    clean_reason = str(abstain_reason or "").strip()
    if not has_evidence:
        answer_allowed = False
        weak_evidence = True
        normalized_strength = "dusuk"
        clean_reason = clean_reason or "kanit_yok"
    elif not answer_allowed:
        weak_evidence = True
        normalized_strength = "dusuk"
        clean_reason = clean_reason or "dusuk_kanit"

    return {
        "answer_allowed": bool(answer_allowed),
        "weak_evidence": bool(weak_evidence),
        "evidence_strength": normalized_strength,
        "abstain_reason": clean_reason,
    }


def _safe_answer_snippet(ev: Dict[str, Any]) -> str:
    return snippet(str(ev.get("snippet") or ev.get("metin") or ""), 280)


def _source_refs(evidences: List[Dict[str, Any]]) -> List[str]:
    source_refs = []
    for ev in evidences:
        kanit_id = str(ev.get("kanit_id") or "").strip()
        adres = str(ev.get("adres") or "").strip()
        ref = f"[{kanit_id}]" if kanit_id else "[kanit:yok]"
        if adres:
            ref = f"{ref} {adres}"
        source_refs.append(ref)
    return source_refs


def _abstention_text(evidences: List[Dict[str, Any]], decision: Dict[str, Any]) -> str:
    if not evidences:
        return "Dokümanda bu soruya doğrudan kanıt bulamadım."
    if decision["abstain_reason"] == "kanit_yok":
        return "Dokümanda bu soruya doğrudan kanıt bulamadım."
    return "Seçili kaynaklarla bu soruya güvenle yanıt verecek kadar güçlü kanıt bulamadım."


def ground_answer_text(
    answer_text: str,
    evidences: List[Dict[str, Any]],
    *,
    kaynak_zayif_mi: bool = False,
    answer_allowed: bool | None = None,
    weak_evidence: bool | None = None,
    evidence_strength: str | None = None,
    abstain_reason: str = "",
) -> str:
    decision = _merge_answer_decision(
        evidences,
        kaynak_zayif_mi=kaynak_zayif_mi,
        answer_allowed=answer_allowed,
        weak_evidence=weak_evidence,
        evidence_strength=evidence_strength,
        abstain_reason=abstain_reason,
    )
    if not evidences:
        return "Dokümanda geçmiyor."

    clean_answer = " ".join(str(answer_text or "").split()).strip()
    if not decision["answer_allowed"]:
        clean_answer = _abstention_text(evidences, decision)
    elif not clean_answer or clean_answer == "Dokümanda geçmiyor.":
        return "Dokümanda geçmiyor."

    if (
        decision["answer_allowed"]
        and decision["weak_evidence"]
        and not clean_answer.lower().startswith("kaynaklar sınırlı")
    ):
        clean_answer = f"Kaynaklar sınırlı; seçili parçalara dayanarak: {clean_answer}"

    source_refs = _source_refs(evidences)
    footer = "Kaynaklar: " + ", ".join(source_refs[:3])
    return f"{clean_answer}\n{footer}"


def build_answer_from_evidence(
    question: str,
    evidences: List[Dict[str, Any]],
    *,
    kaynak_zayif_mi: bool = False,
    answer_allowed: bool | None = None,
    weak_evidence: bool | None = None,
    evidence_strength: str | None = None,
    abstain_reason: str = "",
) -> str:
    # Cevabı seçili kanıtlara sıkı bağlı tutuyoruz; karar alanları zayıf/abstain tonunu belirliyor.
    decision = _merge_answer_decision(
        evidences,
        kaynak_zayif_mi=kaynak_zayif_mi,
        answer_allowed=answer_allowed,
        weak_evidence=weak_evidence,
        evidence_strength=evidence_strength,
        abstain_reason=abstain_reason,
    )
    if not evidences:
        return "Dokümanda bu soruya doğrudan kanıt bulamadım."
    kullanilan_ids = [ev.get("parca_id") for ev in evidences if ev.get("parca_id") is not None]
    kullanilan_kanit_idleri = [ev.get("kanit_id") for ev in evidences if ev.get("kanit_id")]
    kullanilan_adresler = [str(ev.get("adres") or "").strip() for ev in evidences if str(ev.get("adres") or "").strip()]
    id_metin = ", ".join(str(pid) for pid in kullanilan_ids[:3]) or "yok"
    kanit_id_metin = ", ".join(str(kid) for kid in kullanilan_kanit_idleri[:3]) or "yok"
    adres_metin = ", ".join(kullanilan_adresler[:2]) or "yok"
    kanit_sayisi = len(kullanilan_kanit_idleri) or len(evidences)
    if not decision["answer_allowed"]:
        giris = "Seçili kaynaklar bu soruya güvenli bir yanıt vermek için yeterli değil; yalnız ilgili parçaları paylaşıyorum:"
    elif decision["weak_evidence"]:
        giris = "Kaynaklar sınırlı; seçili parçalarda açıkça görünen kısmı temkinli biçimde paylaşabiliyorum:"
    else:
        giris = "Seçili kanıtlara göre:"
    lines = []
    for ev in evidences:
        etiket = ev.get("kanit_id") or ev.get("parca_id")
        adres = str(ev.get("adres") or "").strip()
        kaynak_suffix = f" ({adres})" if adres else ""
        lines.append(f"- {_safe_answer_snippet(ev)}{kaynak_suffix} [{etiket}]")
    answer = (
        f"{giris} (kanit_sayisi: {kanit_sayisi}; parca_id: {id_metin}; kanit_id: {kanit_id_metin}; adres: {adres_metin})\n"
        + "\n".join(lines)
    )
    if not decision["answer_allowed"]:
        answer += "\nNot: Daha net bir cevap için daha güçlü veya daha kapsamlı kanıt gerekiyor."
    elif decision["weak_evidence"]:
        answer += "\nNot: Daha güçlü ve kesin bir cevap için daha kapsamlı kanıt gerekiyor."
    return answer


def retrieve_evidence(question: str, parcalar: List[Tuple[int, str, str]], limit: int = 3) -> List[Dict[str, Any]]:
    """
    parcalar: [(parca_id, adres, metin), ...]
    """
    q_toks = tokenize(question)
    raw_hits = [
        {
            "parca_id": pid,
            "adres": adres,
            "baslik_yolu": adres,
            "metin": metin,
            "retrieval_kaynagi": "lexical_overlap",
        }
        for pid, adres, metin in (parcalar or [])
    ]
    canonical_hits = normalize_retrieval_hits(raw_hits, retrieval_kaynagi="lexical_overlap")
    scored = []
    for hit in canonical_hits:
        s = score_overlap(q_toks, str(hit.get("metin") or ""))
        if s > 0:
            scored.append((s, hit))
    scored.sort(reverse=True, key=lambda x: x[0])
    out = []
    for s, hit in scored[:limit]:
        item = dict(hit)
        item["skor"] = float(s)
        item["snippet"] = snippet(str(hit.get("metin") or ""), 280)
        out.append(item)
    return out


def retrieve_evidence_standardized(
    question: str,
    parcalar: List[Tuple[int, str, str]],
    *,
    dokuman_id=None,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    evidences = retrieve_evidence(question, parcalar, limit=limit)
    candidate_meta = prepare_evidence_candidates(
        evidences,
        retrieval_kaynagi="lexical_overlap",
        varsayilan_dokuman_id=dokuman_id,
    )
    return candidate_meta["aday_kanitlar"]
