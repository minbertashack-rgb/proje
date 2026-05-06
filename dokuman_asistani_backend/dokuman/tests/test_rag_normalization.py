from __future__ import annotations

"""Normalization invariant'larini retrieval ana yoluna dokunmadan kilitler."""

import ast
import math
from pathlib import Path

from django.core.files.base import ContentFile

from dokuman.models import Dokuman, Parca
from dokuman.services import rag as rag_service
from dokuman.services import vector_math, vector_store
from dokuman.services.rag import search_rag, upsert_dokuman_parcalari


def _fail_if_called(*_args, **_kwargs):
    raise AssertionError("normalize_l2 retrieval ana yolunda cagrilmamali")


class FakeArray(list):
    def tolist(self):
        return list(self)


def _module_ast(module) -> ast.AST:
    return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))


def test_search_rag_uses_normalized_query_embeddings_without_manual_helper(monkeypatch):
    captured = {}

    class FakeEmbedder:
        def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
            captured["texts"] = texts
            captured["normalize_embeddings"] = normalize_embeddings
            captured["show_progress_bar"] = show_progress_bar
            return FakeArray([[0.1, 0.2]])

    class FakeCollection:
        def query(self, **kwargs):
            captured["query_embeddings"] = kwargs["query_embeddings"]
            return {
                "documents": [["Normalize edilmis query semantic aramaya gider."]],
                "metadatas": [[
                    {
                        "parca_id": 7,
                        "dokuman_id": 3,
                        "adres": "RAG > Query",
                        "baslik_yolu": "RAG > Query",
                    }
                ]],
                "distances": [[0.09]],
            }

    monkeypatch.setattr("dokuman.services.rag._get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr("dokuman.services.rag._get_collection", lambda: FakeCollection())
    monkeypatch.setattr("dokuman.services.vector_math.normalize_l2", _fail_if_called)

    hits = search_rag("normalize query", owner_id=1, dokuman_id=3, n_results=1)

    assert len(hits) == 1
    assert captured["texts"] == ["normalize query"]
    assert captured["normalize_embeddings"] is True
    assert captured["show_progress_bar"] is False
    assert captured["query_embeddings"] == [[0.1, 0.2]]


def test_vector_store_embed_texts_uses_normalized_embeddings_without_manual_helper(monkeypatch):
    captured = {}

    class FakeEmbedder:
        def encode(self, texts, normalize_embeddings=True):
            captured["texts"] = texts
            captured["normalize_embeddings"] = normalize_embeddings
            return FakeArray([[0.3, 0.4]])

    monkeypatch.setattr("dokuman.services.vector_store._embedder", lambda: FakeEmbedder())
    monkeypatch.setattr("dokuman.services.vector_math.normalize_l2", _fail_if_called)

    vectors = vector_store._embed_texts(["test metni"])

    assert vectors == [[0.3, 0.4]]
    assert captured["texts"] == ["test metni"]
    assert captured["normalize_embeddings"] is True


def test_upsert_dokuman_parcalari_uses_normalized_index_embeddings(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Normalization Guard",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("normalization-guard.pdf", ContentFile(b"ornek"), save=True)

    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="RAG > Index",
        metin="Index embeddingleri normalize edilerek cosine aramaya yazilir.",
        meta={"path": "RAG > Index"},
    )

    captured = {}

    class FakeEmbedder:
        def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
            captured["texts"] = texts
            captured["normalize_embeddings"] = normalize_embeddings
            captured["show_progress_bar"] = show_progress_bar
            return FakeArray([[0.11, 0.22, 0.33]])

    class FakeCollection:
        def upsert(self, **kwargs):
            captured["upsert"] = kwargs

    monkeypatch.setattr("dokuman.services.rag._get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr("dokuman.services.rag._get_collection", lambda: FakeCollection())
    monkeypatch.setattr("dokuman.services.vector_math.normalize_l2", _fail_if_called)

    count = upsert_dokuman_parcalari(doc)

    assert count == 1
    assert captured["texts"] == ["Index embeddingleri normalize edilerek cosine aramaya yazilir."]
    assert captured["normalize_embeddings"] is True
    assert captured["show_progress_bar"] is False
    assert captured["upsert"]["ids"] == [f"parca_{parca.id}"]


def test_normalize_l2_is_idempotent_for_unit_vector():
    unit_vector = [0.6, 0.8]

    normalized_once = vector_math.normalize_l2(unit_vector)
    normalized_twice = vector_math.normalize_l2(normalized_once)

    assert normalized_once == normalized_twice
    assert math.isclose(sum(x * x for x in normalized_twice), 1.0, rel_tol=1e-9, abs_tol=1e-9)


def test_retrieval_modules_do_not_import_or_call_manual_normalize_helper():
    for module in (rag_service, vector_store):
        tree = _module_ast(module)

        imported_modules = []
        imported_names = []
        called_names = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.append(node.module or "")
                imported_names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    called_names.append(func.id)
                elif isinstance(func, ast.Attribute):
                    called_names.append(func.attr)

        assert "dokuman.services.vector_math" not in imported_modules
        assert "vector_math" not in imported_modules
        assert "normalize_l2" not in imported_names
        assert "normalize_l2" not in called_names
