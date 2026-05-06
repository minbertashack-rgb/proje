import os
from functools import lru_cache

from django.conf import settings

from dokuman.models import Parca
from dokuman.services.rag import normalize_retrieval_hits


def _persistent_client_cls():
    import chromadb

    return chromadb.PersistentClient


def _sentence_transformer_cls():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer


@lru_cache(maxsize=1)
def _embedder():
    model_name = getattr(
        settings,
        "EMBED_MODEL_NAME",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    return _sentence_transformer_cls()(model_name)


@lru_cache(maxsize=1)
def _client():
    db_path = str(getattr(settings, "CHROMA_DIR", settings.BASE_DIR / "chroma_db"))
    os.makedirs(db_path, exist_ok=True)
    return _persistent_client_cls()(path=db_path)


def _collection():
    client = _client()
    name = getattr(settings, "CHROMA_COLLECTION", "docverse_parcalar")
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"}
    )


def _embed_texts(texts: list[str]):
    texts = [str(t or "").strip() for t in texts]
    if not texts:
        return []
    # Chroma collection cosine uzayinda; normalization embedder seviyesinde tutulur.
    vecs = _embedder().encode(texts, normalize_embeddings=True)
    return vecs.tolist()


def chroma_upsert_parcalar(parcalar):
    parcalar = list(parcalar)
    if not parcalar:
        return 0

    ids = []
    docs = []
    metas = []

    for p in parcalar:
        text = (p.metin or "").strip()
        if not text:
            continue

        ids.append(f"parca:{p.id}")
        docs.append(text)
        metas.append({
            "parca_id": str(p.id),
            "dokuman_id": str(p.dokuman_id),
            "owner_id": str(getattr(p.dokuman, "owner_id", "")),
            "adres": getattr(p, "adres", "") or "",
            "owner_doc_key": f"{getattr(p.dokuman, 'owner_id', '')}:{p.dokuman_id}",
        })

    if not docs:
        return 0

    embeddings = _embed_texts(docs)

    _collection().upsert(
        ids=ids,
        documents=docs,
        metadatas=metas,
        embeddings=embeddings,
    )
    return len(ids)


def chroma_delete_doc(dokuman_id: int):
    col = _collection()
    try:
        old = col.get(where={"dokuman_id": str(dokuman_id)})
        ids = old.get("ids") or []
        if ids:
            col.delete(ids=ids)
    except Exception:
        pass


def chroma_search(query: str, owner_id: int, dokuman_id: int | None = None, top_k: int = 5):
    query = (query or "").strip()
    if not query:
        return []

    col = _collection()
    query_emb = _embed_texts([query])[0]

    if dokuman_id is not None:
        where = {"owner_doc_key": f"{owner_id}:{dokuman_id}"}
    else:
        where = {"owner_id": str(owner_id)}

    result = col.query(
        query_embeddings=[query_emb],
        n_results=max(1, min(int(top_k or 5), 10)),
        where=where,
    )

    raw_ids = (result.get("ids") or [[]])[0]
    parca_ids = []
    for rid in raw_ids:
        if isinstance(rid, str) and rid.startswith("parca:"):
            try:
                parca_ids.append(int(rid.split(":", 1)[1]))
            except Exception:
                pass

    if not parca_ids:
        return []

    qs = Parca.objects.filter(id__in=parca_ids).select_related("dokuman")
    parca_map = {p.id: p for p in qs}

    ordered = [parca_map[pid] for pid in parca_ids if pid in parca_map]
    return ordered


def chroma_search_standardized(
    query: str,
    owner_id: int,
    dokuman_id: int | None = None,
    top_k: int = 5,
):
    query = (query or "").strip()
    if not query:
        return []

    col = _collection()
    query_emb = _embed_texts([query])[0]

    if dokuman_id is not None:
        where = {"owner_doc_key": f"{owner_id}:{dokuman_id}"}
    else:
        where = {"owner_id": str(owner_id)}

    result = col.query(
        query_embeddings=[query_emb],
        n_results=max(1, min(int(top_k or 5), 10)),
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

    parca_ids = []
    for meta in metas:
        try:
            parca_id = int((meta or {}).get("parca_id"))
        except Exception:
            parca_id = None
        if parca_id is not None:
            parca_ids.append(parca_id)

    parca_map = {
        p.id: p
        for p in Parca.objects.filter(id__in=parca_ids).select_related("dokuman")
    }

    raw_hits = []
    for i, metin in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        dist = dists[i] if i < len(dists) else None
        try:
            parca_id = int((meta or {}).get("parca_id"))
        except Exception:
            parca_id = None
        parca = parca_map.get(parca_id)
        baslik_yolu = ""
        if parca is not None:
            baslik_yolu = str((parca.meta or {}).get("path") or (parca.meta or {}).get("baslik") or parca.adres or "").strip()

        raw_hits.append(
            {
                "parca_id": parca_id,
                "dokuman_id": (meta or {}).get("dokuman_id"),
                "skor": None if dist is None else round(1 - float(dist), 4),
                "metin": metin or getattr(parca, "metin", ""),
                "adres": (meta or {}).get("adres") or getattr(parca, "adres", ""),
                "baslik_yolu": baslik_yolu or (meta or {}).get("adres") or "",
            }
        )

    return normalize_retrieval_hits(raw_hits, retrieval_kaynagi="vector_store.chroma")
