from __future__ import annotations

import re


CONTRACT_VERSION = "1.0"
FIELD_ALLOWLIST = {
    "explanation": {
        "one_liner",
        "very_simple",
        "glossary",
        "steps",
        "examples",
        "trap",
        "mini_quiz",
        "tema_bazli_ornek",
        "alternatif_ornek",
    },
    "self_check": {
        "dogru_noktalar",
        "duzeltilecek_noktalar",
        "eksik_noktalar",
        "self_check_score",
    },
    "fusion": {
        "kavram_a",
        "kavram_b",
        "ortak_yonler",
        "farklar",
        "birlikte_kullanim_ornegi",
        "mini_soru",
    },
    "quiz_boss": {
        "dogru_sayisi",
        "toplam_soru",
        "sonuc_orani",
        "boss_progress_score",
        "boss_difficulty_score",
        "boss_difficulty_band",
        "boss_retry_count",
        "quiz_readiness_score",
    },
}
FIELD_DENYLIST = {
    "kullanici_mesaj",
    "note_text",
    "portal_note_text",
    "feedback_text",
    "ham_metin",
    "raw_text",
    "raw_payload",
}

EVAL_JSON_SCHEMAS = {
    "explanation": {
        "contract_version": CONTRACT_VERSION,
        "required": ["module", "source", "target", "metadata"],
        "target_fields": sorted(FIELD_ALLOWLIST["explanation"]),
    },
    "self_check": {
        "contract_version": CONTRACT_VERSION,
        "required": ["module", "source", "labels", "metadata"],
        "label_fields": sorted(FIELD_ALLOWLIST["self_check"]),
    },
    "fusion": {
        "contract_version": CONTRACT_VERSION,
        "required": ["module", "source", "target", "metadata"],
        "target_fields": sorted(FIELD_ALLOWLIST["fusion"]),
    },
    "quiz_boss": {
        "contract_version": CONTRACT_VERSION,
        "required": ["module", "source", "labels", "metadata"],
        "label_fields": sorted(FIELD_ALLOWLIST["quiz_boss"]),
    },
}

EVAL_EXTRACTION_POINTS = {
    "explanation": {
        "builder": "build_explanation_dataset_entry",
        "source_fields": ["dokuman_id", "parca_id", "chunk_kind", "format", "source_text"],
        "target_key": "target",
        "user_free_text_included": False,
    },
    "self_check": {
        "builder": "build_self_check_dataset_entry",
        "source_fields": ["dokuman_id", "parca_id", "chunk_kind", "format", "source_text", "user_free_text_included"],
        "target_key": "labels",
        "user_free_text_included": False,
    },
    "fusion": {
        "builder": "build_fusion_dataset_entry",
        "source_fields": ["dokuman_id", "baslik"],
        "target_key": "target",
        "user_free_text_included": False,
    },
    "quiz_boss": {
        "builder": "build_quiz_boss_eval_entry",
        "source_fields": ["dokuman_id", "baslik"],
        "target_key": "labels",
        "user_free_text_included": False,
    },
}

_SECRET_RE = re.compile(r"\b(?:HAM_[A-Z0-9_]+|secret|token|refresh_token)\b", re.IGNORECASE)


def _clean_text(value: str, *, limit: int = 320) -> str:
    clean = " ".join(str(value or "").split()).strip()
    clean = _SECRET_RE.sub("[redacted]", clean)
    if len(clean) <= limit:
        return clean
    short = clean[:limit].rsplit(" ", 1)[0].strip()
    return short or clean[:limit].strip()


def redact_docverse_eval_text(value: str, *, limit: int = 320) -> str:
    return _clean_text(value, limit=limit)


def _sanitize_value(value):
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value[:8]]
    if isinstance(value, dict):
        return {
            str(key)[:48]: _sanitize_value(item)
            for key, item in value.items()
            if str(key or "").strip() and str(key) not in FIELD_DENYLIST
        }
    return value


def _allowlist_payload(payload: dict | None, *, surface: str) -> dict:
    allowlist = FIELD_ALLOWLIST[surface]
    clean = {}
    for key, value in (payload or {}).items():
        if key not in allowlist or key in FIELD_DENYLIST:
            continue
        clean[key] = _sanitize_value(value)
    return clean


def sanitize_docverse_eval_payload(payload: dict | None, *, surface: str) -> dict:
    return _allowlist_payload(payload, surface=surface)


def _base_source(*, parca=None, doc=None) -> dict:
    active_doc = doc or getattr(parca, "dokuman", None)
    active_meta = dict(getattr(parca, "meta", {}) or {})
    return {
        "dokuman_id": getattr(active_doc, "id", None),
        "parca_id": getattr(parca, "id", None),
        "chunk_kind": str(active_meta.get("chunk_kind") or getattr(parca, "tur", "") or "genel"),
        "format": str(active_meta.get("format") or getattr(active_doc, "mime", "") or "genel"),
        "source_text": _clean_text(getattr(parca, "metin", "") or "", limit=480),
    }


def build_explanation_dataset_entry(*, parca, payload: dict | None, retrieval_ozeti: dict | None = None) -> dict:
    return {
        "module": "explanation",
        "contract_version": CONTRACT_VERSION,
        "source": _base_source(parca=parca),
        "target": sanitize_docverse_eval_payload(payload, surface="explanation"),
        "metadata": {
            "retrieval_ozeti": _sanitize_value(dict(retrieval_ozeti or {})),
            "field_allowlist": sorted(FIELD_ALLOWLIST["explanation"]),
            "field_denylist": sorted(FIELD_DENYLIST),
        },
    }


def build_self_check_dataset_entry(*, parca, result: dict | None) -> dict:
    return {
        "module": "self_check",
        "contract_version": CONTRACT_VERSION,
        "source": {
            **_base_source(parca=parca),
            "user_free_text_included": False,
        },
        "labels": sanitize_docverse_eval_payload(result, surface="self_check"),
        "metadata": {
            "field_allowlist": sorted(FIELD_ALLOWLIST["self_check"]),
            "field_denylist": sorted(FIELD_DENYLIST),
        },
    }


def build_fusion_dataset_entry(*, doc, payload: dict | None) -> dict:
    return {
        "module": "fusion",
        "contract_version": CONTRACT_VERSION,
        "source": {
            "dokuman_id": getattr(doc, "id", None),
            "baslik": _clean_text(getattr(doc, "baslik", "") or "", limit=120),
        },
        "target": sanitize_docverse_eval_payload(payload, surface="fusion"),
        "metadata": {
            "field_allowlist": sorted(FIELD_ALLOWLIST["fusion"]),
            "field_denylist": sorted(FIELD_DENYLIST),
        },
    }


def build_quiz_boss_eval_entry(*, doc, payload: dict | None) -> dict:
    return {
        "module": "quiz_boss",
        "contract_version": CONTRACT_VERSION,
        "source": {
            "dokuman_id": getattr(doc, "id", None),
            "baslik": _clean_text(getattr(doc, "baslik", "") or "", limit=120),
        },
        "labels": sanitize_docverse_eval_payload(payload, surface="quiz_boss"),
        "metadata": {
            "field_allowlist": sorted(FIELD_ALLOWLIST["quiz_boss"]),
            "field_denylist": sorted(FIELD_DENYLIST),
        },
    }


def build_docverse_eval_entry(
    module: str,
    *,
    parca=None,
    doc=None,
    payload: dict | None = None,
    result: dict | None = None,
    retrieval_ozeti: dict | None = None,
) -> dict:
    clean_module = str(module or "").strip()
    if clean_module == "explanation":
        return build_explanation_dataset_entry(parca=parca, payload=payload, retrieval_ozeti=retrieval_ozeti)
    if clean_module == "self_check":
        return build_self_check_dataset_entry(parca=parca, result=result if result is not None else payload)
    if clean_module == "fusion":
        active_doc = doc or getattr(parca, "dokuman", None)
        return build_fusion_dataset_entry(doc=active_doc, payload=payload)
    if clean_module == "quiz_boss":
        active_doc = doc or getattr(parca, "dokuman", None)
        return build_quiz_boss_eval_entry(doc=active_doc, payload=payload)
    raise ValueError(f"Unsupported DocVerse eval module: {clean_module}")


def get_docverse_eval_extractors() -> dict:
    return {
        key: {
            "builder": value["builder"],
            "source_fields": list(value["source_fields"]),
            "target_key": value["target_key"],
            "user_free_text_included": bool(value["user_free_text_included"]),
        }
        for key, value in EVAL_EXTRACTION_POINTS.items()
    }


def get_docverse_eval_contracts() -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "field_allowlist": {key: sorted(value) for key, value in FIELD_ALLOWLIST.items()},
        "field_denylist": sorted(FIELD_DENYLIST),
        "extraction_points": get_docverse_eval_extractors(),
        "no_leak_preprocessing": {
            "redaction_function": "redact_docverse_eval_text",
            "payload_sanitizer": "sanitize_docverse_eval_payload",
            "user_free_text_included": False,
        },
        "schemas": EVAL_JSON_SCHEMAS,
    }
