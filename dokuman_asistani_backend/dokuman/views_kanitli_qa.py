# dokuman/views_kanitli_qa.py
from __future__ import annotations
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from dokuman.models import Dokuman
from dokuman.services.evidence_orchestrator import (
    build_evidence_response_payload,
    derive_answer_source_state,
    orchestrate_evidence_selection,
)
from dokuman.services.kanitli_qa import (
    retrieve_evidence_standardized,
    build_answer_from_evidence,
)
from dokuman.throttles import EvidenceThrottle


def _api_error_payload(*, detail: str, error_code: str = "", field_errors: dict | None = None) -> dict:
    payload = {
        "detail": str(detail or "").strip(),
        "status_text": str(detail or "").strip(),
    }
    if str(error_code or "").strip():
        payload["error_code"] = str(error_code).strip()
    if field_errors:
        payload["field_errors"] = dict(field_errors)
    return payload


def _answer_status_text(answer_state: str) -> str:
    state = str(answer_state or "").strip()
    if state == "answered":
        return "Kanitli cevap hazir."
    if state == "answered_with_weak_evidence":
        return "Kanitli cevap hazir, ancak kanit zayif."
    if state == "insufficient_evidence":
        return "Yeterli kanit bulunamadi."
    if state == "not_in_document":
        return "Dokumanda gecmiyor."
    return "Kanitli cevap hazir."


def _augment_answer_payload(payload: dict) -> dict:
    out = dict(payload or {})
    dokumanda_yok = bool(out.get("dokumanda_yok"))
    answer_allowed = bool(out.get("answer_allowed")) if "answer_allowed" in out else not dokumanda_yok
    weak_evidence = bool(out.get("weak_evidence")) if "weak_evidence" in out else bool(out.get("kaynak_zayif_mi"))
    evidence_strength = str(out.get("evidence_strength") or ("dusuk" if weak_evidence or not answer_allowed else "yuksek")).strip() or "dusuk"
    abstain_reason = str(out.get("abstain_reason") or "").strip()
    kaynak_guveni = str(out.get("kaynak_guveni") or ("dusuk" if weak_evidence or not answer_allowed else "yuksek")).strip() or "dusuk"

    if dokumanda_yok:
        answer_state = "not_in_document"
    elif not answer_allowed:
        answer_state = "insufficient_evidence"
    elif weak_evidence:
        answer_state = "answered_with_weak_evidence"
    else:
        answer_state = "answered"

    warning_code = str(out.get("warning_code") or "").strip()
    if not warning_code:
        if answer_state == "not_in_document":
            warning_code = "document_missing_answer"
        elif answer_state in {"insufficient_evidence", "answered_with_weak_evidence"} or weak_evidence:
            warning_code = "weak_evidence"
        else:
            warning_code = ""

    out["dokumanda_yok"] = dokumanda_yok
    out["answer_allowed"] = answer_allowed
    out["weak_evidence"] = weak_evidence
    out["evidence_strength"] = evidence_strength
    out["abstain_reason"] = abstain_reason
    out["kaynak_guveni"] = kaynak_guveni
    out["answer_state"] = answer_state
    out["status_text"] = str(out.get("status_text") or _answer_status_text(answer_state)).strip()
    out["warning_code"] = warning_code
    return out

class KanitliSorAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EvidenceThrottle]

    def post(self, request, doc_id: int, *args, **kwargs):
        soru = (request.data.get("soru") or "").strip()
        limit = int(request.data.get("limit", 3))

        if not soru:
            return Response(
                _api_error_payload(
                    detail="soru zorunlu",
                    error_code="validation_error",
                    field_errors={"soru": ["Bu alan zorunludur."]},
                ),
                status=400,
            )

        doc = Dokuman.objects.filter(id=doc_id, owner_id=request.user.id).first()
        if not doc:
            return Response(
                _api_error_payload(detail="Doküman yok", error_code="resource_not_found"),
                status=404,
            )

        # parcalar
        parcalar = [(p.id, p.adres, p.metin or "") for p in doc.parcalar.all()]
        standardized = retrieve_evidence_standardized(
            soru,
            parcalar,
            dokuman_id=doc.id,
            limit=max(1, min(limit, 8)),
        )
        kanit_meta = orchestrate_evidence_selection(
            soru,
            standardized,
            answer_limit=min(2, len(standardized) or 1),
            dokuman_filtresi_var_mi=True,
            varsayilan_dokuman_id=doc.id,
        )
        evidence_payload = build_evidence_response_payload(kanit_meta)
        cevap_kanitlari = evidence_payload["kullanilan_kanitlar"]
        kaynak_durumu = derive_answer_source_state(kanit_meta)
        kaynak_zayif_mi = bool(kaynak_durumu["kaynak_zayif_mi"])
        cevap = build_answer_from_evidence(
            soru,
            cevap_kanitlari,
            kaynak_zayif_mi=kaynak_zayif_mi,
        )

        return Response(
            _augment_answer_payload(
                {
                    "doc_id": doc.id,
                    "soru": soru,
                    "cevap": cevap,
                    "dokumanda_yok": not bool(kaynak_durumu["answer_allowed"]),
                    **{
                        **evidence_payload,
                        "kaynak_guveni": kaynak_durumu["kaynak_guveni"],
                        "kaynak_zayif_mi": kaynak_zayif_mi,
                    },
                }
            )
        )
