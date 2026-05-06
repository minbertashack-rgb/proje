from pathlib import Path
from threading import Lock

from django.conf import settings

from ..models import Parca
from .rerank import (
    _deterministic_sort_key,
    build_rerank_debug_summary,
    debug_summary_enabled,
    extract_rerank_features,
    rerank_enabled,
    score_rerank_features,
)
from .retrieval_terms import normalize_query_terms


_CLIENT = None
_COLLECTION = None
_EMBEDDER = None
_LOCK = Lock()


def _persistent_client_cls():
    from chromadb import PersistentClient

    return PersistentClient


def _sentence_transformer_cls():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer


def _get_chroma_dir() -> str:
    base_dir = Path(getattr(settings, "BASE_DIR", Path.cwd()))
    chroma_dir = getattr(settings, "CHROMA_DIR", base_dir / "chroma_db")
    return str(chroma_dir)


def _get_client():
    global _CLIENT
    if _CLIENT is None:
        with _LOCK:
            if _CLIENT is None:
                _CLIENT = _persistent_client_cls()(path=_get_chroma_dir())
    return _CLIENT


def _get_collection():
    global _COLLECTION
    if _COLLECTION is None:
        with _LOCK:
            if _COLLECTION is None:
                _COLLECTION = _get_client().get_or_create_collection(
                    name=getattr(settings, "CHROMA_COLLECTION", "docverse_parcalar"),
                    metadata={"hnsw:space": "cosine"},
                )
    return _COLLECTION


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        with _LOCK:
            if _EMBEDDER is None:
                _EMBEDDER = _sentence_transformer_cls()(
                    getattr(
                        settings,
                        "RAG_EMBED_MODEL",
                        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                    )
                )
    return _EMBEDDER


def _parca_text(parca) -> str:
    return (
        getattr(parca, "metin", None)
        or getattr(parca, "icerik", None)
        or ""
    ).strip()


def _parca_adres(parca) -> str:
    if getattr(parca, "adres", None):
        return str(parca.adres)

    pieces = []

    sayfa_no = getattr(parca, "sayfa_no", None)
    if sayfa_no not in (None, ""):
        pieces.append(f"Sayfa {sayfa_no}")

    baslik = getattr(parca, "baslik", None)
    if baslik:
        pieces.append(str(baslik))

    if pieces:
        return " > ".join(pieces)

    return f"Parça {parca.id}"


def _parca_baslik_yolu(parca) -> str:
    meta = getattr(parca, "meta", None) or {}
    for key in ("path", "baslik_yolu", "baslik"):
        value = str(meta.get(key) or "").strip()
        if value:
            return value
    return _parca_adres(parca)


def _rag_tokens(text: str) -> list[str]:
    return normalize_query_terms(text)


def _hit_text(hit) -> str:
    if isinstance(hit, dict):
        return str(hit.get("metin") or hit.get("snippet") or "").strip()
    return str(getattr(hit, "metin", "") or getattr(hit, "icerik", "") or "").strip()


def _hit_addr(hit) -> str:
    if isinstance(hit, dict):
        return str(hit.get("adres") or "").strip()
    return str(getattr(hit, "adres", "") or "").strip()


def _hit_score(hit):
    if isinstance(hit, dict):
        return hit.get("skor")
    return None


def _hit_path(hit) -> str:
    if isinstance(hit, dict):
        return str(hit.get("baslik_yolu") or hit.get("adres") or "").strip()
    return str(getattr(hit, "baslik_yolu", "") or getattr(hit, "adres", "") or "").strip()


def _hit_doc_id(hit):
    if isinstance(hit, dict):
        return _coerce_int(hit.get("dokuman_id"))
    return _coerce_int(getattr(hit, "dokuman_id", None))


def _coerce_int(value):
    try:
        if value in (None, ""):
            return None
        return int(value)
    except Exception:
        return value


def _coerce_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)



def build_retrieval_hit(
    *,
    parca_id=None,
    dokuman_id=None,
    skor=None,
    metin: str = "",
    adres: str = "",
    baslik_yolu: str = "",
    retrieval_kaynagi: str = "rag.semantic",
    weak_content=None,
    quality_score=None,
    chunk_index=None,
    format_name: str = "",
    chunk_kind: str = "",
    code_language: str = "",
    code_unit_kind: str = "",
    code_unit_name: str = "",
    parent_unit: str = "",
    line_start=None,
    line_end=None,
    code_purpose_hints=None,
    komsu_var_mi=None,
    heading_path_uyumlu_mu=None,
):
    return {
        "parca_id": _coerce_int(parca_id),
        "dokuman_id": _coerce_int(dokuman_id),
        "skor": skor,
        "metin": "" if metin is None else str(metin),
        "adres": str(adres or "").strip(),
        "baslik_yolu": str(baslik_yolu or adres or "").strip(),
        "retrieval_kaynagi": str(retrieval_kaynagi or "rag.semantic"),
        "weak_content": bool(weak_content) if weak_content is not None else None,
        "quality_score": _coerce_float(quality_score) if quality_score is not None else None,
        "chunk_index": _coerce_int(chunk_index),
        "format": str(format_name or "").strip(),
        "chunk_kind": str(chunk_kind or "").strip(),
        "code_language": str(code_language or "").strip(),
        "code_unit_kind": str(code_unit_kind or "").strip(),
        "code_unit_name": str(code_unit_name or "").strip(),
        "parent_unit": str(parent_unit or "").strip(),
        "line_start": _coerce_int(line_start),
        "line_end": _coerce_int(line_end),
        "code_purpose_hints": [str(item).strip() for item in (code_purpose_hints or []) if str(item).strip()],
        "komsu_var_mi": bool(komsu_var_mi) if komsu_var_mi is not None else None,
        "heading_path_uyumlu_mu": bool(heading_path_uyumlu_mu) if heading_path_uyumlu_mu is not None else None,
    }


def normalize_retrieval_hit(hit, *, retrieval_kaynagi: str = "rag.semantic", varsayilan_dokuman_id=None):
    if isinstance(hit, dict):
        return build_retrieval_hit(
            parca_id=hit.get("parca_id") or hit.get("id"),
            dokuman_id=hit.get("dokuman_id", hit.get("doc_id", varsayilan_dokuman_id)),
            skor=hit.get("skor", hit.get("score")),
            metin=hit.get("metin") or hit.get("text") or hit.get("snippet") or "",
            adres=hit.get("adres") or hit.get("addr") or "",
            baslik_yolu=(
                hit.get("baslik_yolu")
                or hit.get("path")
                or hit.get("adres")
                or hit.get("addr")
                or ""
            ),
            retrieval_kaynagi=hit.get("retrieval_kaynagi") or retrieval_kaynagi,
            weak_content=hit.get("weak_content"),
            quality_score=hit.get("quality_score"),
            chunk_index=hit.get("chunk_index") or hit.get("sira"),
            format_name=hit.get("format"),
            chunk_kind=hit.get("chunk_kind"),
            code_language=hit.get("code_language"),
            code_unit_kind=hit.get("code_unit_kind"),
            code_unit_name=hit.get("code_unit_name"),
            parent_unit=hit.get("parent_unit"),
            line_start=hit.get("line_start"),
            line_end=hit.get("line_end"),
            code_purpose_hints=hit.get("code_purpose_hints"),
            komsu_var_mi=hit.get("komsu_var_mi"),
            heading_path_uyumlu_mu=hit.get("heading_path_uyumlu_mu"),
        )

    return build_retrieval_hit(
        parca_id=getattr(hit, "id", None),
        dokuman_id=getattr(hit, "dokuman_id", varsayilan_dokuman_id),
        skor=getattr(hit, "skor", None),
        metin=_parca_text(hit),
        adres=_parca_adres(hit),
        baslik_yolu=_parca_baslik_yolu(hit),
        retrieval_kaynagi=retrieval_kaynagi,
        weak_content=(getattr(hit, "meta", None) or {}).get("weak_content"),
        quality_score=(getattr(hit, "meta", None) or {}).get("quality_score"),
        chunk_index=getattr(hit, "sira", None),
        format_name=(getattr(hit, "meta", None) or {}).get("format"),
        chunk_kind=(getattr(hit, "meta", None) or {}).get("chunk_kind"),
        code_language=(getattr(hit, "meta", None) or {}).get("code_language"),
        code_unit_kind=(getattr(hit, "meta", None) or {}).get("code_unit_kind"),
        code_unit_name=(getattr(hit, "meta", None) or {}).get("code_unit_name"),
        parent_unit=(getattr(hit, "meta", None) or {}).get("parent_unit"),
        line_start=(getattr(hit, "meta", None) or {}).get("line_start"),
        line_end=(getattr(hit, "meta", None) or {}).get("line_end"),
        code_purpose_hints=(getattr(hit, "meta", None) or {}).get("code_purpose_hints") or [],
    )


def normalize_retrieval_hits(hits: list, *, retrieval_kaynagi: str = "rag.semantic", varsayilan_dokuman_id=None):
    return [
        normalize_retrieval_hit(
            hit,
            retrieval_kaynagi=retrieval_kaynagi,
            varsayilan_dokuman_id=varsayilan_dokuman_id,
        )
        for hit in (hits or [])
    ]


def lightweight_rerank_hits(query: str, hits: list) -> list:
    query_tokens = _rag_tokens(query)
    if not hits:
        return []
    if not query_tokens:
        return list(hits)
    if not rerank_enabled():
        disabled_hits = []
        for index, hit in enumerate(hits, start=1):
            if isinstance(hit, dict):
                reranked = dict(hit)
                reranked["_rerank"] = {
                    "uygulandi": False,
                    "skor": _coerce_float(hit.get("skor")),
                    "final_rerank": _coerce_float(hit.get("skor")),
                    "onceki_sira": index,
                    "yeni_sira": index,
                    "sira_degisti_mi": False,
                    "dusuk_icerik_cezasi_var_mi": False,
                    "soru_terim_kapsama_orani": 0.0,
                    "adres_terim_kapsama_orani": 0.0,
                    "metin_terim_yogunlugu": 0.0,
                    "tam_ifade_eslesmesi_var_mi": False,
                    "tam_adres_eslesmesi_var_mi": False,
                    "tum_soru_terimleri_eslesti_mi": False,
                    "ayni_dokuman_destegi_var_mi": False,
                    "ayni_dokuman_destek_hit_sayisi": 0,
                    "eslesen_soru_terimleri": [],
                }
                disabled_hits.append(reranked)
                continue
            disabled_hits.append(hit)
        return disabled_hits

    doc_density = {}
    prepared = []

    for index, hit in enumerate(hits):
        doc_id = _hit_doc_id(hit)
        features = extract_rerank_features(
            query_tokens,
            hit,
            doc_support_hits=0,
            onceki_sira=index + 1,
        )

        prepared.append(
            {
                "index": index,
                "hit": hit,
                "doc_id": doc_id,
                "features": features,
            }
        )

    scored = []
    for row in prepared:
        features = dict(row["features"])
        doc_id = row["doc_id"]
        chunk_index = int(features.get("chunk_index") or 0)
        doc_support_hits = sum(
            1
            for candidate in prepared
            if candidate is not row
            and candidate["doc_id"] == doc_id
            and abs(int(candidate["features"].get("chunk_index") or 0) - chunk_index) == 1
        )
        if doc_id is not None and features["matched_terms"]:
            doc_density[doc_id] = doc_density.get(doc_id, 0) + 1
        # Ardışık parça desteği varsa küçük locality bonusu ekliyoruz.
        features["locality_bonus"] = round(0.05 if doc_support_hits > 0 else 0.0, 3)
        features["doc_support_hits"] = int(doc_support_hits)
        features["final_rerank"] = score_rerank_features(features)

        scored.append(
            {
                **row,
                "features": features,
            }
        )

    scored.sort(key=_deterministic_sort_key, reverse=True)

    reranked_hits = []
    for new_index, item in enumerate(scored, start=1):
        hit = item["hit"]
        features = item["features"]
        if isinstance(hit, dict):
            reranked = dict(hit)
            reranked["_rerank"] = {
                "uygulandi": True,
                "skor": features["final_rerank"],
                "final_rerank": features["final_rerank"],
                "semantic_score": features["semantic_score"],
                "lexical_overlap": features["lexical_overlap"],
                "path_match": features["path_match"],
                "locality_bonus": features["locality_bonus"],
                "weak_penalty": features["weak_penalty"],
                "weak_content": bool(features.get("weak_content")),
                "chunk_index": int(features.get("chunk_index") or 0),
                "onceki_sira": item["index"] + 1,
                "yeni_sira": new_index,
                "sira_degisti_mi": item["index"] + 1 != new_index,
                "dusuk_icerik_cezasi_var_mi": features["weak_penalty"] > 0,
                "soru_terim_kapsama_orani": features["lexical_overlap"],
                "adres_terim_kapsama_orani": features["path_match"],
                "metin_terim_yogunlugu": features["text_density"],
                "tam_ifade_eslesmesi_var_mi": bool(features["phrase_match"]),
                "tam_adres_eslesmesi_var_mi": bool(features["exact_path_match"]),
                "tum_soru_terimleri_eslesti_mi": bool(features["full_query_match"]),
                "ayni_dokuman_destegi_var_mi": item["doc_id"] is not None and doc_density.get(item["doc_id"], 0) > 1,
                "ayni_dokuman_destek_hit_sayisi": features["doc_support_hits"],
                "eslesen_soru_terimleri": list(features["matched_terms"]),
            }
            reranked.update(derive_hit_observability(reranked, query=query))
            reranked_hits.append(reranked)
            continue
        reranked_hits.append(hit)

    return reranked_hits


def summarize_rag_hits(query: str, hits: list) -> dict:
    query_tokens = set(_rag_tokens(query))
    hit_texts = [_hit_text(hit) for hit in hits if _hit_text(hit)]
    hit_addrs = {_hit_addr(hit) for hit in hits if _hit_addr(hit)}
    numeric_scores = []

    for hit in hits:
        try:
            score = _hit_score(hit)
            if score is not None:
                numeric_scores.append(float(score))
        except Exception:
            continue

    coverage_tokens = set()
    for text in hit_texts:
        coverage_tokens.update(set(_rag_tokens(text)) & query_tokens)

    coverage_ratio = round(len(coverage_tokens) / max(1, len(query_tokens)), 3) if query_tokens else 0.0
    avg_score = round(sum(numeric_scores) / max(1, len(numeric_scores)), 4) if numeric_scores else None
    top_score = round(max(numeric_scores), 4) if numeric_scores else None

    quality = "zayif"
    if len(hit_texts) >= 3 and coverage_ratio >= 0.5:
        quality = "guclu"
    elif len(hit_texts) >= 1 and coverage_ratio >= 0.2:
        quality = "orta"

    return {
        "toplam_sonuc": len(hits),
        "metinli_sonuc": len(hit_texts),
        "tekil_adres_sayisi": len(hit_addrs),
        "ortalama_skor": avg_score,
        "en_yuksek_skor": top_score,
        "soru_terim_kapsama_orani": coverage_ratio,
        "kapsanan_soru_terimleri": sorted(coverage_tokens),
        "retrieval_kalitesi": quality,
    }


def _retrieval_kaynagi_ozeti(hits: list) -> dict:
    ozet = {}
    for hit in hits:
        if isinstance(hit, dict):
            kaynak = str(hit.get("retrieval_kaynagi") or "bilinmiyor").strip() or "bilinmiyor"
        else:
            kaynak = "bilinmiyor"
        ozet[kaynak] = ozet.get(kaynak, 0) + 1
    return ozet


def build_retrieval_ozeti(
    query: str,
    hits: list,
    *,
    kullanilan_hit: int | None = None,
    dokuman_filtresi_var_mi: bool = False,
    auto_index_denendi_mi: bool = False,
) -> dict:
    base = summarize_rag_hits(query, hits)
    numeric_scores = []
    for hit in hits:
        try:
            score = _hit_score(hit)
            if score is not None:
                numeric_scores.append(float(score))
        except Exception:
            continue

    rerank_meta = [
        hit.get("_rerank")
        for hit in hits
        if isinstance(hit, dict) and isinstance(hit.get("_rerank"), dict)
    ]
    rerank_scores = [
        _coerce_float(meta.get("skor"))
        for meta in rerank_meta
        if meta.get("skor") is not None
    ]
    weak_evidence_flags = [
        bool(hit.get("zayif_kaynak_mi"))
        for hit in hits
        if isinstance(hit, dict) and "zayif_kaynak_mi" in hit
    ]
    observability_flags = [derive_hit_observability(hit, query=query) for hit in hits]
    base.update(
        {
            "toplam_hit": len(hits),
            "kullanilan_hit": int(kullanilan_hit if kullanilan_hit is not None else len(hits)),
            "en_dusuk_skor": round(min(numeric_scores), 4) if numeric_scores else None,
            "dokuman_filtresi_var_mi": bool(dokuman_filtresi_var_mi),
            "auto_index_denendi_mi": bool(auto_index_denendi_mi),
            "retrieval_kaynagi_ozeti": _retrieval_kaynagi_ozeti(hits),
            "rerank_uygulandi_mi": any(meta.get("uygulandi") for meta in rerank_meta),
            "rerank_ilk_hit_degisti_mi": bool(rerank_meta and rerank_meta[0].get("onceki_sira") != 1),
            "rerank_sirasi_degisti_mi": any(meta.get("sira_degisti_mi") for meta in rerank_meta),
            "rerank_sirasi_degisen_hit_sayisi": sum(1 for meta in rerank_meta if meta.get("sira_degisti_mi")),
            "ortalama_rerank_skoru": round(sum(rerank_scores) / len(rerank_scores), 4) if rerank_scores else None,
            "zayif_icerik_hit_sayisi": sum(
                1 for meta in rerank_meta if meta.get("dusuk_icerik_cezasi_var_mi")
            ),
            "zayif_kaynak_hit_sayisi": sum(1 for is_weak in weak_evidence_flags if is_weak),
            "komsu_destekli_hit_sayisi": sum(1 for item in observability_flags if item["komsu_var_mi"]),
            "heading_uyumlu_hit_sayisi": sum(1 for item in observability_flags if item["heading_path_uyumlu_mu"]),
            "komsu_destegi_var_mi": any(item["komsu_var_mi"] for item in observability_flags),
        }
    )
    if debug_summary_enabled():
        base["hit_debug_ozeti"] = [
            build_rerank_debug_summary(
                {
                    "parca_id": hit.get("parca_id"),
                    "onceki_sira": meta.get("onceki_sira"),
                    "semantic_score": meta.get("semantic_score", hit.get("skor")),
                    "lexical_overlap": meta.get("lexical_overlap", meta.get("soru_terim_kapsama_orani")),
                    "path_match": meta.get("path_match", meta.get("adres_terim_kapsama_orani")),
                    "locality_bonus": meta.get("locality_bonus", 0.0),
                    "weak_penalty": meta.get("weak_penalty", 0.0),
                    "final_rerank": meta.get("final_rerank", meta.get("skor")),
                },
                yeni_sira=meta.get("yeni_sira") or index,
                selected=index == 1,
            )
            for index, (hit, meta) in enumerate(
                [
                    (hit, hit.get("_rerank"))
                    for hit in hits
                    if isinstance(hit, dict) and isinstance(hit.get("_rerank"), dict)
                ],
                start=1,
            )
        ]
    return base


def upsert_dokuman_parcalari(dokuman) -> int:
    parcalar = list(Parca.objects.filter(dokuman=dokuman).order_by("id"))

    ids = []
    texts = []
    metas = []

    for parca in parcalar:
        metin = _parca_text(parca)
        if not metin:
            continue

        ids.append(f"parca_{parca.id}")
        texts.append(metin)
        metas.append(
            {
                "parca_id": int(parca.id),
                "dokuman_id": int(dokuman.id),
                "owner_id": int(dokuman.owner_id),
                "adres": _parca_adres(parca),
                "baslik_yolu": _parca_baslik_yolu(parca),
                # Retrieval tarafinda weak penalty ve deterministik tie-break icin gerekli metadata.
                "weak_content": bool((parca.meta or {}).get("weak_content")),
                "quality_score": float((parca.meta or {}).get("quality_score") or 0.0),
                "chunk_index": int(getattr(parca, "sira", 0) or 0),
                "format": str((parca.meta or {}).get("format") or "").strip(),
                "chunk_kind": str((parca.meta or {}).get("chunk_kind") or "").strip(),
                "code_language": str((parca.meta or {}).get("code_language") or "").strip(),
                "code_unit_kind": str((parca.meta or {}).get("code_unit_kind") or "").strip(),
                "code_unit_name": str((parca.meta or {}).get("code_unit_name") or "").strip(),
                "parent_unit": str((parca.meta or {}).get("parent_unit") or "").strip(),
                "line_start": _coerce_int((parca.meta or {}).get("line_start")),
                "line_end": _coerce_int((parca.meta or {}).get("line_end")),
                "code_purpose_hints": [str(item).strip() for item in ((parca.meta or {}).get("code_purpose_hints") or []) if str(item).strip()],
            }
        )

    if not texts:
        return 0

    # Cosine retrieval icin L2 normalization embedder seviyesinde uygulanir.
    # Buraya ek bir manuel normalize_l2 katmani eklemiyoruz.
    embeddings = _get_embedder().encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).tolist()

    _get_collection().upsert(
        ids=ids,
        documents=texts,
        embeddings=embeddings,
        metadatas=metas,
    )

    return len(ids)


def sil_dokuman_indexi(dokuman_id: int):
    try:
        _get_collection().delete(where={"dokuman_id": int(dokuman_id)})
    except Exception:
        pass


def search_rag(query: str, owner_id: int, dokuman_id=None, n_results: int = 5):
    query = (query or "").strip()
    if not query:
        return []

    where = {"owner_id": int(owner_id)}
    if dokuman_id is not None:
        where["dokuman_id"] = int(dokuman_id)

    try:
        # Query tarafi da indexleme ile ayni normalize akisini kullanir.
        query_embedding = _get_embedder().encode(
            [query],
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

        result = _get_collection().query(
            query_embeddings=query_embedding,
            n_results=max(1, int(n_results)),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

    out = []
    for i, metin in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        dist = dists[i] if i < len(dists) else None
        skor = None if dist is None else round(1 - float(dist), 4)

        out.append(
            build_retrieval_hit(
                parca_id=meta.get("parca_id"),
                dokuman_id=meta.get("dokuman_id"),
                skor=skor,
                metin=metin,
                adres=meta.get("adres"),
                baslik_yolu=meta.get("baslik_yolu") or meta.get("adres"),
                retrieval_kaynagi="rag.semantic",
                weak_content=meta.get("weak_content"),
                quality_score=meta.get("quality_score"),
                chunk_index=meta.get("chunk_index"),
                format_name=meta.get("format"),
                chunk_kind=meta.get("chunk_kind"),
                code_language=meta.get("code_language"),
                code_unit_kind=meta.get("code_unit_kind"),
                code_unit_name=meta.get("code_unit_name"),
                parent_unit=meta.get("parent_unit"),
                line_start=meta.get("line_start"),
                line_end=meta.get("line_end"),
                code_purpose_hints=meta.get("code_purpose_hints"),
            )
        )

    return lightweight_rerank_hits(query, out)


def search_rag_with_auto_index(query: str, owner_id: int, dokuman=None, n_results: int = 5):
    sonuclar, _meta = search_rag_with_auto_index_meta(
        query=query,
        owner_id=owner_id,
        dokuman=dokuman,
        n_results=n_results,
    )
    return sonuclar


def search_rag_with_auto_index_meta(query: str, owner_id: int, dokuman=None, n_results: int = 5):
    meta = {
        "dokuman_filtresi_var_mi": dokuman is not None,
        "auto_index_denendi_mi": False,
    }
    dokuman_id = getattr(dokuman, "id", None)
    sonuclar = search_rag(
        query=query,
        owner_id=owner_id,
        dokuman_id=dokuman_id,
        n_results=n_results,
    )
    if sonuclar or dokuman is None:
        return sonuclar, meta

    if not Parca.objects.filter(dokuman=dokuman).exists():
        return sonuclar, meta

    try:
        meta["auto_index_denendi_mi"] = True
        upsert_dokuman_parcalari(dokuman)
    except Exception:
        return sonuclar, meta

    return search_rag(
        query=query,
        owner_id=owner_id,
        dokuman_id=dokuman_id,
        n_results=n_results,
    ), meta


def sync_dokuman_indexi_if_enabled(dokuman):
    if not getattr(settings, "RAG_ENABLED", True):
        return {"denendi": False, "basarili": False, "neden": "rag_disabled"}
    if not getattr(settings, "RAG_AUTO_INDEX_ON_INGEST", False):
        return {"denendi": False, "basarili": False, "neden": "auto_index_disabled"}
    if dokuman is None or getattr(dokuman, "durum", "") != "parcalandi":
        return {"denendi": False, "basarili": False, "neden": "dokuman_hazir_degil"}

    try:
        adet = upsert_dokuman_parcalari(dokuman)
        return {"denendi": True, "basarili": True, "indexlenen_parca_sayisi": adet}
    except Exception as exc:
        return {
            "denendi": True,
            "basarili": False,
            "neden": "upsert_hatasi",
            "hata": str(exc),
        }

