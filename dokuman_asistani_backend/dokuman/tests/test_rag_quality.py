from __future__ import annotations

from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import Dokuman, Parca
from dokuman.services.evidence_orchestrator import (
    build_evidence_response_payload,
    canonicalize_evidence_hits,
    derive_answer_source_state,
    orchestrate_evidence_selection,
    prepare_evidence_candidates,
)
from dokuman.services.kanitli_qa import (
    build_answer_from_evidence,
    ground_answer_text,
    prepare_answer_evidence,
    retrieve_evidence_standardized,
)
from dokuman.services.rag import (
    build_retrieval_hit,
    build_retrieval_ozeti,
    lightweight_rerank_hits,
    normalize_retrieval_hits,
    search_rag,
    search_rag_with_auto_index,
    search_rag_with_auto_index_meta,
    summarize_rag_hits,
    upsert_dokuman_parcalari,
)
from dokuman.services import vector_store
from dokuman.services.vector_store import chroma_search_standardized
from dokuman.services import ingestion


def test_normalize_retrieval_hits_fills_standard_fields(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Standart Hit",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("standart-hit.pdf", ContentFile(b"ornek"), save=True)

    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Bolum 1",
        metin="RAG ilgili parcayi bularak cevap uretir.",
        meta={"path": "Giris > RAG"},
    )

    hits = normalize_retrieval_hits(
        [
            parca,
            {
                "parca_id": 99,
                "dokuman_id": 77,
                "skor": 0.61,
                "metin": "Ek retrieval kaydi",
                "adres": "Ek",
            },
        ],
        retrieval_kaynagi="test.adapter",
    )

    assert hits[0]["parca_id"] == parca.id
    assert hits[0]["dokuman_id"] == doc.id
    assert hits[0]["baslik_yolu"] == "Giris > RAG"
    assert hits[0]["retrieval_kaynagi"] == "test.adapter"
    assert hits[1]["adres"] == "Ek"
    assert hits[1]["retrieval_kaynagi"] == "test.adapter"


def test_normalize_retrieval_hits_accepts_legacy_text_addr_aliases():
    hits = normalize_retrieval_hits(
        [
            {
                "id": 15,
                "doc_id": 42,
                "score": 0.73,
                "text": "Legacy lexical hit ortak evidence katmanina girebilir.",
                "addr": "Legacy > Lexical",
                "path": "Legacy > Lexical",
            }
        ],
        retrieval_kaynagi="legacy.adapter",
    )

    assert len(hits) == 1
    assert hits[0]["parca_id"] == 15
    assert hits[0]["dokuman_id"] == 42
    assert hits[0]["skor"] == 0.73
    assert hits[0]["metin"] == "Legacy lexical hit ortak evidence katmanina girebilir."
    assert hits[0]["adres"] == "Legacy > Lexical"
    assert hits[0]["baslik_yolu"] == "Legacy > Lexical"
    assert hits[0]["retrieval_kaynagi"] == "legacy.adapter"
    assert hits[0]["weak_content"] is None
    assert hits[0]["quality_score"] is None
    assert hits[0]["chunk_index"] is None
    assert hits[0]["format"] == ""
    assert hits[0]["chunk_kind"] == ""
    assert hits[0]["code_language"] == ""
    assert hits[0]["code_unit_kind"] == ""
    assert hits[0]["code_unit_name"] == ""
    assert hits[0]["parent_unit"] == ""
    assert hits[0]["line_start"] is None
    assert hits[0]["line_end"] is None
    assert hits[0]["code_purpose_hints"] == []


def test_build_retrieval_hit_preserves_raw_metin_whitespace():
    raw_text = "\n  Ilk satir\nIkinci satir  \n"

    hit = build_retrieval_hit(
        parca_id=15,
        dokuman_id=42,
        metin=raw_text,
        adres=" Legacy > Lexical ",
        baslik_yolu=" Legacy > Lexical ",
    )

    assert hit["metin"] == raw_text
    assert hit["adres"] == "Legacy > Lexical"
    assert hit["baslik_yolu"] == "Legacy > Lexical"


def test_summarize_rag_hits_reports_coverage_and_quality():
    hits = [
        {
            "parca_id": 1,
            "adres": "1",
            "metin": "RAG once ilgili parcayi bulur sonra kanitli cevap uretir.",
            "skor": 0.82,
        },
        {
            "parca_id": 2,
            "adres": "2",
            "metin": "Retrieval ve citation sinyalleri kaliteyi arttirir.",
            "skor": 0.74,
        },
    ]

    summary = summarize_rag_hits("RAG retrieval citation nasil calisir?", hits)

    assert summary["toplam_sonuc"] == 2
    assert summary["tekil_adres_sayisi"] == 2
    assert summary["en_yuksek_skor"] == 0.82
    assert summary["ortalama_skor"] == 0.78
    assert summary["soru_terim_kapsama_orani"] > 0
    assert summary["retrieval_kalitesi"] in {"orta", "guclu"}


def test_build_retrieval_ozeti_adds_operational_fields():
    hits = [
        {
            "parca_id": 1,
            "dokuman_id": 10,
            "adres": "A",
            "metin": "SQL retrieval notu",
            "skor": 0.91,
            "retrieval_kaynagi": "rag.semantic",
        },
        {
            "parca_id": 2,
            "dokuman_id": 10,
            "adres": "B",
            "metin": "Ek retrieval notu",
            "skor": 0.52,
            "retrieval_kaynagi": "lexical_overlap",
        },
    ]

    summary = build_retrieval_ozeti(
        "sql retrieval nasil calisir",
        hits,
        kullanilan_hit=1,
        dokuman_filtresi_var_mi=True,
        auto_index_denendi_mi=True,
    )

    assert summary["toplam_hit"] == 2
    assert summary["kullanilan_hit"] == 1
    assert summary["en_yuksek_skor"] == 0.91
    assert summary["en_dusuk_skor"] == 0.52
    assert summary["dokuman_filtresi_var_mi"] is True
    assert summary["auto_index_denendi_mi"] is True
    assert summary["rerank_uygulandi_mi"] is False
    assert summary["rerank_ilk_hit_degisti_mi"] is False
    assert summary["rerank_sirasi_degisti_mi"] is False
    assert summary["rerank_sirasi_degisen_hit_sayisi"] == 0
    assert summary["ortalama_rerank_skoru"] is None
    assert summary["zayif_icerik_hit_sayisi"] == 0
    assert summary["zayif_kaynak_hit_sayisi"] == 0
    assert summary["retrieval_kaynagi_ozeti"] == {
        "rag.semantic": 1,
        "lexical_overlap": 1,
    }
    assert "hit_debug_ozeti" not in summary


def test_build_retrieval_ozeti_adds_safe_observability_counts():
    hits = lightweight_rerank_hits(
        "jwt amaci",
        [
            {
                "parca_id": 101,
                "dokuman_id": 44,
                "adres": "Guvenlik > JWT > Amac",
                "baslik_yolu": "Guvenlik > JWT > Amac",
                "metin": "JWT amaci istemci kimligini tasimak ve yetki bilgisini iletmektir.",
                "skor": 0.84,
                "retrieval_kaynagi": "rag.semantic",
                "chunk_index": 10,
            },
            {
                "parca_id": 102,
                "dokuman_id": 44,
                "adres": "Guvenlik > JWT > Yapi",
                "baslik_yolu": "Guvenlik > JWT > Yapi",
                "metin": "JWT yapisi header, payload ve signature katmanlarindan olusur.",
                "skor": 0.79,
                "retrieval_kaynagi": "rag.semantic",
                "chunk_index": 11,
            },
        ],
    )

    summary = build_retrieval_ozeti("jwt amaci", hits, kullanilan_hit=1)

    assert summary["komsu_destegi_var_mi"] is True
    assert summary["komsu_destekli_hit_sayisi"] == 2
    assert summary["heading_uyumlu_hit_sayisi"] >= 1


def test_build_retrieval_ozeti_adds_safe_hit_debug_summary_when_flag_enabled(settings):
    settings.DOCVERSE_DEBUG_SUMMARY_ENABLED = True
    hits = lightweight_rerank_hits(
        "jwt amaci",
        [
            {
                "parca_id": 11,
                "dokuman_id": 1,
                "skor": 0.81,
                "metin": "JWT amaci istemci kimligini tasimak ve yetki bilgisini iletmektir.",
                "adres": "Guvenlik > JWT > Amac",
                "baslik_yolu": "Guvenlik > JWT > Amac",
                "retrieval_kaynagi": "rag.semantic",
            },
            {
                "parca_id": 12,
                "dokuman_id": 1,
                "skor": 0.74,
                "metin": "JWT genel notu.",
                "adres": "Ek",
                "baslik_yolu": "Ek",
                "retrieval_kaynagi": "rag.semantic",
            },
        ],
    )

    summary = build_retrieval_ozeti("jwt amaci", hits)

    assert "hit_debug_ozeti" in summary
    assert summary["hit_debug_ozeti"][0]["parca_id"] == 11
    assert summary["hit_debug_ozeti"][0]["why_selected"] != ""
    assert summary["hit_debug_ozeti"][1]["dropped_reason"] != ""
    assert "metin" not in summary["hit_debug_ozeti"][0]
    assert "snippet" not in summary["hit_debug_ozeti"][0]
    assert "raw_tokens" not in summary["hit_debug_ozeti"][0]


def test_lightweight_rerank_promotes_hit_with_stronger_query_and_path_match():
    hits = [
        {
            "parca_id": 40,
            "dokuman_id": 5,
            "skor": 0.91,
            "metin": "Genel giris notu.",
            "adres": "Genel",
            "baslik_yolu": "Genel",
            "retrieval_kaynagi": "rag.semantic",
        },
        {
            "parca_id": 41,
            "dokuman_id": 5,
            "skor": 0.82,
            "metin": "Embedding retrieval rerank kaliteyi ve ilgili parcayi secmeyi iyilestirir.",
            "adres": "RAG > Kalite",
            "baslik_yolu": "RAG > Embedding > Rerank",
            "retrieval_kaynagi": "rag.semantic",
        },
    ]

    reranked = lightweight_rerank_hits("embedding rerank kalite", hits)

    assert reranked[0]["parca_id"] == 41
    assert reranked[0]["_rerank"]["uygulandi"] is True
    assert reranked[0]["_rerank"]["onceki_sira"] == 2
    assert reranked[0]["_rerank"]["yeni_sira"] == 1
    assert reranked[0]["_rerank"]["sira_degisti_mi"] is True
    assert reranked[0]["_rerank"]["soru_terim_kapsama_orani"] > 0.6
    assert reranked[0]["_rerank"]["adres_terim_kapsama_orani"] > 0.3
    assert reranked[0]["_rerank"]["metin_terim_yogunlugu"] > 0.2
    assert reranked[0]["_rerank"]["ayni_dokuman_destek_hit_sayisi"] >= 0


def test_lightweight_rerank_demotes_low_information_chunk_and_surfaces_summary():
    hits = lightweight_rerank_hits(
        "embedding retrieval rerank",
        [
            {
                "parca_id": 50,
                "dokuman_id": 9,
                "skor": 0.89,
                "metin": "Rerank notu",
                "adres": "Ek",
                "baslik_yolu": "Ek",
                "retrieval_kaynagi": "rag.semantic",
                "weak_content": True,
            },
            {
                "parca_id": 51,
                "dokuman_id": 9,
                "skor": 0.81,
                "metin": "Embedding retrieval ve rerank birlikte ilk hitlerin daha anlamli siralanmasini saglar.",
                "adres": "RAG > Kalite",
                "baslik_yolu": "RAG > Kalite",
                "retrieval_kaynagi": "rag.semantic",
            },
        ],
    )

    summary = build_retrieval_ozeti("embedding retrieval rerank", hits)

    assert hits[0]["parca_id"] == 51
    assert hits[-1]["parca_id"] == 50
    assert hits[-1]["_rerank"]["dusuk_icerik_cezasi_var_mi"] is True
    assert summary["rerank_uygulandi_mi"] is True
    assert summary["rerank_ilk_hit_degisti_mi"] is True
    assert summary["rerank_sirasi_degisti_mi"] is True
    assert summary["rerank_sirasi_degisen_hit_sayisi"] == 2
    assert summary["ortalama_rerank_skoru"] is not None
    assert summary["zayif_icerik_hit_sayisi"] >= 1


def test_lightweight_rerank_can_be_disabled_without_changing_hit_order(settings):
    settings.DOCVERSE_RERANK_ENABLED = False
    hits = lightweight_rerank_hits(
        "embedding rerank kalite",
        [
            {
                "parca_id": 70,
                "dokuman_id": 8,
                "skor": 0.93,
                "metin": "Genel not.",
                "adres": "Genel",
                "baslik_yolu": "Genel",
                "retrieval_kaynagi": "rag.semantic",
            },
            {
                "parca_id": 71,
                "dokuman_id": 8,
                "skor": 0.74,
                "metin": "Embedding rerank kalite icin daha ilgili aciklama.",
                "adres": "RAG > Kalite",
                "baslik_yolu": "RAG > Kalite",
                "retrieval_kaynagi": "rag.semantic",
            },
        ],
    )
    summary = build_retrieval_ozeti("embedding rerank kalite", hits)

    assert [hit["parca_id"] for hit in hits] == [70, 71]
    assert hits[0]["_rerank"]["uygulandi"] is False
    assert hits[1]["_rerank"]["uygulandi"] is False
    assert summary["rerank_uygulandi_mi"] is False


def test_lightweight_rerank_grounding_regression_demotes_keyword_only_wrong_context():
    hits = lightweight_rerank_hits(
        "jwt amaci",
        [
            {
                "parca_id": 81,
                "dokuman_id": 5,
                "skor": 0.88,
                "metin": "JWT token jwt jwt kimlik notu ve daginik anahtarlar.",
                "adres": "Genel > Token",
                "baslik_yolu": "Genel > Token",
                "retrieval_kaynagi": "rag.semantic",
            },
            {
                "parca_id": 82,
                "dokuman_id": 5,
                "skor": 0.79,
                "metin": "JWT amaci istemci kimligini tasimak ve yetki bilgisini iletmektir.",
                "adres": "Guvenlik > JWT > Amac",
                "baslik_yolu": "Guvenlik > JWT > Amac",
                "retrieval_kaynagi": "rag.semantic",
            },
        ],
    )

    assert [hit["parca_id"] for hit in hits] == [82, 81]
    assert hits[0]["_rerank"]["adres_terim_kapsama_orani"] >= hits[1]["_rerank"]["adres_terim_kapsama_orani"]
    assert hits[0]["_rerank"]["final_rerank"] > hits[1]["_rerank"]["final_rerank"]


def test_search_rag_returns_standard_fields_and_scoped_where(monkeypatch):
    captured = {}

    class FakeArray(list):
        def tolist(self):
            return list(self)

    class FakeEmbedder:
        def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
            assert texts == ["sql retrieval"]
            captured["normalize_embeddings"] = normalize_embeddings
            captured["show_progress_bar"] = show_progress_bar
            return FakeArray([[0.1, 0.2, 0.3]])

    class FakeCollection:
        def query(self, **kwargs):
            captured["where"] = kwargs["where"]
            return {
                "documents": [[
                    "SELECT ile filtre uygulanir.",
                    "Retrieval ilgili SQL parcasi getirir.",
                ]],
                "metadatas": [[
                    {
                        "parca_id": 3,
                        "dokuman_id": 11,
                        "adres": "SQL > Giris",
                        "baslik_yolu": "SQL > Giris",
                    },
                    {
                        "parca_id": 4,
                        "dokuman_id": 11,
                        "adres": "SQL > Ornek",
                        "baslik_yolu": "SQL > Ornek",
                    },
                ]],
                "distances": [[0.12, 0.33]],
            }

    monkeypatch.setattr("dokuman.services.rag._get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr("dokuman.services.rag._get_collection", lambda: FakeCollection())

    hits = search_rag("sql retrieval", owner_id=9, dokuman_id=11, n_results=2)

    assert captured["where"] == {"owner_id": 9, "dokuman_id": 11}
    assert captured["normalize_embeddings"] is True
    assert captured["show_progress_bar"] is False
    assert len(hits) == 2
    assert [hit["parca_id"] for hit in hits] == [4, 3]
    assert all(hit["dokuman_id"] == 11 for hit in hits)
    assert all(hit["retrieval_kaynagi"] == "rag.semantic" for hit in hits)
    assert all(hit["_rerank"]["uygulandi"] is True for hit in hits)
    assert hits[0]["adres"] == "SQL > Ornek"


def test_search_rag_lightweight_rerank_prioritizes_query_coverage(monkeypatch):
    class FakeArray(list):
        def tolist(self):
            return list(self)

    class FakeEmbedder:
        def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
            assert texts == ["sql join"]
            return FakeArray([[0.1, 0.2]])

    class FakeCollection:
        def query(self, **kwargs):
            return {
                "documents": [[
                    "Genel veri notu ve baglamsiz kisa aciklama.",
                    "SQL join iki tabloyu ortak alan uzerinden birlestirir.",
                ]],
                "metadatas": [[
                    {
                        "parca_id": 21,
                        "dokuman_id": 5,
                        "adres": "Genel",
                        "baslik_yolu": "Genel",
                    },
                    {
                        "parca_id": 22,
                        "dokuman_id": 5,
                        "adres": "SQL > Join",
                        "baslik_yolu": "SQL > Join",
                    },
                ]],
                "distances": [[0.15, 0.2]],
            }

    monkeypatch.setattr("dokuman.services.rag._get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr("dokuman.services.rag._get_collection", lambda: FakeCollection())

    hits = search_rag("sql join", owner_id=9, dokuman_id=5, n_results=2)
    summary = build_retrieval_ozeti("sql join", hits, kullanilan_hit=1, dokuman_filtresi_var_mi=True)

    assert [hit["parca_id"] for hit in hits] == [22, 21]
    assert summary["rerank_uygulandi_mi"] is True
    assert summary["rerank_sirasi_degisti_mi"] is True


def test_search_rag_rerank_demotes_low_content_chunk(monkeypatch):
    class FakeArray(list):
        def tolist(self):
            return list(self)

    class FakeEmbedder:
        def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
            assert texts == ["vektor arama"]
            return FakeArray([[0.1, 0.2]])

    class FakeCollection:
        def query(self, **kwargs):
            return {
                "documents": [[
                    "Vektor arama;",
                    "Vektor arama benzer parcayi skorlayip ust siraya tasir.",
                ]],
                "metadatas": [[
                    {
                        "parca_id": 31,
                        "dokuman_id": 12,
                        "adres": "Kisa",
                        "baslik_yolu": "Kisa",
                    },
                    {
                        "parca_id": 32,
                        "dokuman_id": 12,
                        "adres": "Arama > Mantik",
                        "baslik_yolu": "Arama > Mantik",
                    },
                ]],
                "distances": [[0.08, 0.18]],
            }

    monkeypatch.setattr("dokuman.services.rag._get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr("dokuman.services.rag._get_collection", lambda: FakeCollection())

    hits = search_rag("vektor arama", owner_id=9, dokuman_id=12, n_results=2)

    assert [hit["parca_id"] for hit in hits] == [32, 31]
    assert hits[1]["_rerank"]["dusuk_icerik_cezasi_var_mi"] is True


def test_search_rag_with_auto_index_retries_for_specific_doc(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Retry Doc",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("retry-doc.pdf", ContentFile(b"ornek"), save=True)
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1",
        metin="RAG parcasi veritabaninda var ama index geriden geliyor.",
        meta={"path": "1"},
    )

    calls = []

    def fake_search_rag(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return []
        return [
            {
                "parca_id": 1,
                "dokuman_id": doc.id,
                "skor": 0.91,
                "metin": "RAG parcasi veritabaninda var ama index geriden geliyor.",
                "adres": "1",
                "baslik_yolu": "1",
                "retrieval_kaynagi": "rag.semantic",
            }
        ]

    upsert_calls = []
    monkeypatch.setattr("dokuman.services.rag.search_rag", fake_search_rag)
    monkeypatch.setattr("dokuman.services.rag.upsert_dokuman_parcalari", lambda d: upsert_calls.append(d.id) or 1)

    hits = search_rag_with_auto_index(
        query="index neden bos",
        owner_id=test_kullanicisi.id,
        dokuman=doc,
        n_results=3,
    )

    assert len(calls) == 2
    assert upsert_calls == [doc.id]
    assert hits[0]["dokuman_id"] == doc.id


def test_search_rag_with_auto_index_meta_marks_retry_when_self_heal_runs(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Retry Meta Doc",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("retry-meta.pdf", ContentFile(b"ornek"), save=True)
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1",
        metin="Index yoksa ikinci deneme ile sonuc gelebilir.",
        meta={"path": "1"},
    )

    calls = []

    def fake_search_rag(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return []
        return [
            {
                "parca_id": 5,
                "dokuman_id": doc.id,
                "skor": 0.77,
                "metin": "Index yoksa ikinci deneme ile sonuc gelebilir.",
                "adres": "1",
                "baslik_yolu": "1",
                "retrieval_kaynagi": "rag.semantic",
            }
        ]

    monkeypatch.setattr("dokuman.services.rag.search_rag", fake_search_rag)
    monkeypatch.setattr("dokuman.services.rag.upsert_dokuman_parcalari", lambda d: 1)

    hits, meta = search_rag_with_auto_index_meta(
        query="ikinci deneme",
        owner_id=test_kullanicisi.id,
        dokuman=doc,
        n_results=3,
    )

    assert len(hits) == 1
    assert meta["dokuman_filtresi_var_mi"] is True
    assert meta["auto_index_denendi_mi"] is True


def test_chroma_search_standardized_returns_canonical_fields(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Vector Store Doc",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("vector-doc.pdf", ContentFile(b"ornek"), save=True)

    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Veri > Giris",
        metin="Vector store retrieval parcayi skorla birlikte dondurur.",
        meta={"path": "Veri > Giris"},
    )

    monkeypatch.setattr("dokuman.services.vector_store._embed_texts", lambda texts: [[0.2, 0.3]])

    class FakeCollection:
        def query(self, **kwargs):
            return {
                "documents": [[parca.metin]],
                "metadatas": [[
                    {
                        "parca_id": str(parca.id),
                        "dokuman_id": str(doc.id),
                        "adres": parca.adres,
                    }
                ]],
                "distances": [[0.18]],
            }

    monkeypatch.setattr("dokuman.services.vector_store._collection", lambda: FakeCollection())

    hits = chroma_search_standardized(
        query="vector retrieval",
        owner_id=test_kullanicisi.id,
        dokuman_id=doc.id,
        top_k=3,
    )

    assert len(hits) == 1
    assert hits[0]["parca_id"] == parca.id
    assert hits[0]["dokuman_id"] == doc.id
    assert hits[0]["baslik_yolu"] == "Veri > Giris"
    assert hits[0]["retrieval_kaynagi"] == "vector_store.chroma"


def test_chroma_search_standardized_query_uses_normalized_embeddings(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Vector Query Normalize",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("vector-query-normalize.pdf", ContentFile(b"ornek"), save=True)

    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Normalize > Query",
        metin="Query embedding normalize edilerek cosine aramaya gider.",
        meta={"path": "Normalize > Query"},
    )

    captured = {}

    class FakeArray(list):
        def tolist(self):
            return list(self)

    class FakeEmbedder:
        def encode(self, texts, normalize_embeddings=True):
            captured["texts"] = texts
            captured["normalize_embeddings"] = normalize_embeddings
            return FakeArray([[0.7, 0.1]])

    class FakeCollection:
        def query(self, **kwargs):
            captured["query_embeddings"] = kwargs["query_embeddings"]
            return {
                "documents": [[parca.metin]],
                "metadatas": [[
                    {
                        "parca_id": str(parca.id),
                        "dokuman_id": str(doc.id),
                        "adres": parca.adres,
                    }
                ]],
                "distances": [[0.09]],
            }

    monkeypatch.setattr("dokuman.services.vector_store._embedder", lambda: FakeEmbedder())
    monkeypatch.setattr("dokuman.services.vector_store._collection", lambda: FakeCollection())

    hits = chroma_search_standardized(
        query="normalize query",
        owner_id=test_kullanicisi.id,
        dokuman_id=doc.id,
        top_k=3,
    )

    assert len(hits) == 1
    assert captured["texts"] == ["normalize query"]
    assert captured["normalize_embeddings"] is True
    assert captured["query_embeddings"] == [[0.7, 0.1]]


def test_upsert_dokuman_parcalari_uses_normalized_embeddings(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Normalize Doc",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("normalize-doc.pdf", ContentFile(b"ornek"), save=True)

    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Giris",
        metin="Normalize edilmis embeddingler cosine aramayi kararli tutar.",
        meta={"path": "Giris"},
    )

    captured = {}

    class FakeArray(list):
        def tolist(self):
            return list(self)

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

    count = upsert_dokuman_parcalari(doc)

    assert count == 1
    assert captured["texts"] == ["Normalize edilmis embeddingler cosine aramayi kararli tutar."]
    assert captured["normalize_embeddings"] is True
    assert captured["show_progress_bar"] is False
    assert captured["upsert"]["ids"] == [f"parca_{doc.parcalar.first().id}"]
    assert captured["upsert"]["metadatas"][0]["weak_content"] is False
    assert captured["upsert"]["metadatas"][0]["chunk_index"] == 1


def test_vector_store_embed_texts_uses_normalized_embeddings(monkeypatch):
    captured = {}

    class FakeArray(list):
        def tolist(self):
            return list(self)

    class FakeEmbedder:
        def encode(self, texts, normalize_embeddings=True):
            captured["texts"] = texts
            captured["normalize_embeddings"] = normalize_embeddings
            return FakeArray([[0.4, 0.5]])

    monkeypatch.setattr("dokuman.services.vector_store._embedder", lambda: FakeEmbedder())

    vectors = vector_store._embed_texts(["vektor kalite"])

    assert vectors == [[0.4, 0.5]]
    assert captured["texts"] == ["vektor kalite"]
    assert captured["normalize_embeddings"] is True


def test_retrieve_evidence_standardized_preserves_canonical_fields():
    hits = retrieve_evidence_standardized(
        "sql filtre nasil olur",
        [
            (10, "SQL > Giris", "SELECT ifadesiyle filtre uygulanir."),
            (11, "Yetkisiz", "Baska bir not"),
        ],
        dokuman_id=55,
        limit=2,
    )

    assert hits
    assert hits[0]["parca_id"] == 10
    assert hits[0]["dokuman_id"] == 55
    assert hits[0]["adres"] == "SQL > Giris"
    assert hits[0]["baslik_yolu"] == "SQL > Giris"
    assert hits[0]["retrieval_kaynagi"] == "lexical_overlap"
    assert hits[0]["snippet"]
    assert "SELECT" in hits[0]["metin"]


def test_canonicalize_evidence_hits_supports_optional_doc_filter():
    meta = canonicalize_evidence_hits(
        [
            {
                "parca_id": 201,
                "dokuman_id": 91,
                "adres": "Doc 91 > Giris",
                "metin": "Semantic retrieval ilk dokumandan kanit getirir.",
                "skor": 0.72,
                "retrieval_kaynagi": "rag.semantic",
            },
            {
                "parca_id": 202,
                "dokuman_id": 92,
                "adres": "Doc 92 > Giris",
                "metin": "Semantic retrieval ikinci dokumandan kanit getirir.",
                "skor": 0.74,
                "retrieval_kaynagi": "rag.semantic",
            },
        ],
        dokuman_filtreleri=[92],
    )

    assert [hit["parca_id"] for hit in meta["ham_kanitlar"]] == [201, 202]
    assert [hit["parca_id"] for hit in meta["kanonik_kanitlar"]] == [202]
    assert meta["dokuman_filtreleri"] == [92]
    assert meta["dokuman_filtresi_uygulandi_mi"] is True
    assert meta["filtrelenen_kanit_sayisi"] == 1


def test_prepare_evidence_candidates_normalizes_legacy_hits_before_selection(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Legacy Candidates",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("legacy-candidates.pdf", ContentFile(b"ornek"), save=True)

    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Legacy > Giris",
        metin="Legacy object retrieval de once kanonik candidate listesine donusmelidir.",
        meta={"path": "Legacy > Giris"},
    )

    meta = prepare_evidence_candidates(
        [parca],
        retrieval_kaynagi="legacy.object_retrieval",
        varsayilan_dokuman_id=doc.id,
        dokuman_filtreleri=[doc.id],
    )

    assert meta["ham_kanitlar"][0]["parca_id"] == parca.id
    assert meta["aday_kanitlar"][0]["parca_id"] == parca.id
    assert meta["aday_kanitlar"][0]["dokuman_id"] == doc.id
    assert meta["aday_kanitlar"][0]["retrieval_kaynagi"] == "legacy.object_retrieval"
    assert meta["aday_kanitlar"][0]["snippet"]
    assert meta["dokuman_filtreleri"] == [doc.id]
    assert meta["dokuman_filtresi_uygulandi_mi"] is True


def test_orchestrate_evidence_selection_works_for_semantic_hits():
    meta = orchestrate_evidence_selection(
        "sql join nasil calisir",
        [
            {
                "parca_id": 41,
                "dokuman_id": 8,
                "adres": "SQL > Join",
                "baslik_yolu": "SQL > Join",
                "metin": "SQL join iki tabloyu ortak alan uzerinden birlestirir.",
                "skor": 0.82,
                "retrieval_kaynagi": "rag.semantic",
            },
            {
                "parca_id": 42,
                "dokuman_id": 8,
                "adres": "Ek",
                "baslik_yolu": "Ek",
                "metin": "Kisa not",
                "skor": 0.2,
                "retrieval_kaynagi": "rag.semantic",
            },
        ],
        answer_limit=1,
        dokuman_filtresi_var_mi=True,
    )

    assert meta["kullanilan_kanit_sayisi"] == 1
    assert meta["kullanilan_parca_idleri"] == [41]
    assert meta["kullanilan_kanit_idleri"] == ["kanit:41"]
    assert meta["kaynak_guveni"] in {"orta", "yuksek"}
    assert meta["evidence_confidence"] >= 0.45
    assert meta["abstention_uygulandi_mi"] is False
    assert meta["evidence_secim_ozeti"]["secilen_parca_idleri"] == [41]
    assert meta["retrieval_ozeti"]["evidence_secim_ozeti"]["secilen_parca_idleri"] == [41]
    assert meta["retrieval_ozeti"]["kullanilan_hit"] == 1
    assert meta["retrieval_ozeti"]["retrieval_kaynagi_ozeti"] == {"rag.semantic": 2}
    assert meta["retrieval_ozeti"]["evidence_confidence"] >= 0.45


def test_orchestrate_evidence_selection_abstains_when_margin_and_top_score_are_low():
    meta = orchestrate_evidence_selection(
        "jwt neden kullanilir",
        [
            {
                "parca_id": 611,
                "dokuman_id": 90,
                "adres": "Genel",
                "baslik_yolu": "Genel",
                "metin": "JWT notu.",
                "skor": 0.50,
                "retrieval_kaynagi": "rag.semantic",
                "weak_content": True,
            },
            {
                "parca_id": 612,
                "dokuman_id": 90,
                "adres": "Ek",
                "baslik_yolu": "Ek",
                "metin": "JWT kisa not.",
                "skor": 0.48,
                "retrieval_kaynagi": "rag.semantic",
                "weak_content": True,
            },
        ],
        answer_limit=1,
        dokuman_filtresi_var_mi=True,
    )

    assert meta["kullanilan_kanit_sayisi"] == 0
    assert meta["kaynak_guveni"] == "dusuk"
    assert meta["abstention_uygulandi_mi"] is True
    assert meta["top1_score"] < 0.55
    assert meta["evidence_confidence"] <= 0.6
    assert meta["retrieval_ozeti"]["abstention_uygulandi_mi"] is True


def test_orchestrate_evidence_selection_applies_doc_filter_before_selection():
    meta = orchestrate_evidence_selection(
        "retrieval neden izlenebilir olmali",
        [
            {
                "parca_id": 211,
                "dokuman_id": 70,
                "adres": "Doc 70 > Kaynak",
                "metin": "Izlenebilirlik cevapta kullanilan parcayi gosterir.",
                "skor": 0.81,
                "retrieval_kaynagi": "rag.semantic",
            },
            {
                "parca_id": 212,
                "dokuman_id": 71,
                "adres": "Doc 71 > Kaynak",
                "metin": "Izlenebilirlik cevapta kullanilan parcayi gosterir.",
                "skor": 0.83,
                "retrieval_kaynagi": "rag.semantic",
            },
        ],
        answer_limit=1,
        dokuman_filtreleri=[71],
    )

    assert meta["ham_kanit_sayisi"] == 2
    assert meta["kullanilan_parca_idleri"] == [212]
    assert meta["dokuman_filtreleri"] == [71]
    assert meta["evidence_secim_ozeti"]["ham_kanit_sayisi"] == 2
    assert meta["evidence_secim_ozeti"]["toplam_kanit_sayisi"] == 1
    assert meta["evidence_secim_ozeti"]["filtrelenen_kanit_sayisi"] == 1
    assert meta["retrieval_ozeti"]["dokuman_filtresi_var_mi"] is True


def test_orchestrate_evidence_selection_works_for_lexical_hits_and_forced_ids():
    hits = retrieve_evidence_standardized(
        "kanit id neden onemli",
        [
            (51, "RAG > Kaynak", "Kanit id cevabin hangi parcaya dayandigini gorunur kilar."),
            (52, "Ek", "Ilgisiz ek not."),
        ],
        dokuman_id=55,
        limit=2,
    )

    meta = orchestrate_evidence_selection(
        "kanit id neden onemli",
        hits,
        answer_limit=2,
        dokuman_filtresi_var_mi=True,
        forced_parca_idleri=[51],
    )

    assert meta["kaynak_zorlamasi_uygulandi_mi"] is True
    assert meta["kullanilan_parca_idleri"] == [51]
    assert meta["kullanilan_kanit_idleri"] == ["kanit:51"]
    assert meta["retrieval_ozeti"]["evidence_secim_ozeti"]["forced_parca_idleri"] == [51]
    assert meta["retrieval_ozeti"]["kullanilan_hit"] == 1
    assert meta["retrieval_ozeti"]["retrieval_kaynagi_ozeti"]["lexical_overlap"] >= 1


def test_orchestrate_evidence_selection_supports_mixed_semantic_and_lexical_hits():
    meta = orchestrate_evidence_selection(
        "kaynak secimi nasil ortaklasir",
        [
            {
                "parca_id": 301,
                "dokuman_id": 81,
                "adres": "RAG > Semantik",
                "baslik_yolu": "RAG > Semantik",
                "metin": "Semantik retrieval ortak evidence secim katmanina kanonik hit uretir.",
                "skor": 0.84,
                "retrieval_kaynagi": "rag.semantic",
            },
            {
                "parca_id": 302,
                "dokuman_id": 81,
                "adres": "RAG > Lexical",
                "baslik_yolu": "RAG > Lexical",
                "metin": "Lexical overlap de ayni orchestrator uzerinden kanit secimine katilir.",
                "skor": 0.62,
                "retrieval_kaynagi": "lexical_overlap",
            },
        ],
        answer_limit=2,
        dokuman_filtresi_var_mi=True,
    )

    assert meta["kullanilan_kanit_sayisi"] >= 1
    assert set(meta["kullanilan_parca_idleri"]).issubset({301, 302})
    assert meta["retrieval_ozeti"]["retrieval_kaynagi_ozeti"] == {
        "rag.semantic": 1,
        "lexical_overlap": 1,
    }
    assert meta["retrieval_ozeti"]["evidence_secim_ozeti"]["secilen_kanit_sayisi"] == meta["kullanilan_kanit_sayisi"]


def test_build_evidence_response_payload_aligns_common_fields():
    meta = orchestrate_evidence_selection(
        "kaynak neden izlenebilir olmali",
        [
            {
                "parca_id": 88,
                "dokuman_id": 9,
                "adres": "Kaynak > Izlenebilirlik",
                "metin": "Kaynak izlenebilirligi cevapta hangi kanitin kullanildigini aciklar.",
                "skor": 0.77,
                "retrieval_kaynagi": "rag.semantic",
            }
        ],
        answer_limit=1,
        dokuman_filtresi_var_mi=True,
    )

    payload = build_evidence_response_payload(
        meta,
        include_kanitlar=False,
        include_kaynak_zorlamasi=False,
    )

    assert "kanitlar" not in payload
    assert "kaynak_zorlamasi_uygulandi_mi" not in payload
    assert payload["kullanilan_kanit_sayisi"] == 1
    assert payload["kullanilan_parca_idleri"] == [88]
    assert payload["kullanilan_kanitlar"][0]["parca_id"] == 88
    assert payload["evidence_confidence"] >= 0.45
    assert payload["retrieval_ozeti"]["evidence_secim_ozeti"]["secilen_kanit_sayisi"] == 1


def test_build_evidence_response_payload_redacts_internal_rerank_fields():
    meta = prepare_answer_evidence(
        "jwt neden kullanilir",
        [
            {
                "parca_id": 901,
                "dokuman_id": 9,
                "adres": "JWT > Giris",
                "metin": "JWT istemci ile sunucu arasinda kimlik ve yetki bilgisini tasimaya yardim eder.",
                "skor": 0.81,
                "_rerank": {
                    "final_rerank": 0.93,
                    "dusuk_icerik_cezasi_var_mi": False,
                    "raw_tokens": ["jwt", "secret"],
                },
            }
        ],
        answer_limit=1,
    )

    payload = build_evidence_response_payload(meta)

    assert payload["answer_allowed"] is True
    assert payload["kullanilan_kanitlar"][0]["parca_id"] == 901
    assert "_rerank" not in payload["kullanilan_kanitlar"][0]
    assert "metin" not in payload["kullanilan_kanitlar"][0]
    assert payload["kanitlar"][0]["snippet"]
    assert "_rerank" not in payload["kanitlar"][0]


def test_build_evidence_response_payload_includes_safe_observability_flags():
    meta = orchestrate_evidence_selection(
        "jwt amaci nedir",
        [
            {
                "parca_id": 951,
                "dokuman_id": 61,
                "adres": "Guvenlik > JWT > Amac",
                "baslik_yolu": "Guvenlik > JWT > Amac",
                "metin": "JWT amaci istemci kimligini tasimak ve yetki bilgisini iletmektir.",
                "skor": 0.86,
                "retrieval_kaynagi": "rag.semantic",
                "chunk_index": 20,
            },
            {
                "parca_id": 952,
                "dokuman_id": 61,
                "adres": "Guvenlik > JWT > Yapi",
                "baslik_yolu": "Guvenlik > JWT > Yapi",
                "metin": "JWT yapisi header, payload ve signature bolumlerinden olusur.",
                "skor": 0.8,
                "retrieval_kaynagi": "rag.semantic",
                "chunk_index": 21,
            },
        ],
        answer_limit=1,
        dokuman_filtresi_var_mi=True,
    )

    payload = build_evidence_response_payload(meta)

    assert payload["kullanilan_kanitlar"][0]["komsu_var_mi"] is True
    assert payload["kullanilan_kanitlar"][0]["heading_path_uyumlu_mu"] is True
    assert payload["retrieval_ozeti"]["komsu_destegi_var_mi"] is True
    assert payload["retrieval_ozeti"]["komsu_destekli_hit_sayisi"] == 2
    assert payload["retrieval_ozeti"]["heading_uyumlu_hit_sayisi"] >= 1
    assert payload["retrieval_ozeti"]["evidence_secim_ozeti"]["komsu_destekli_hit_sayisi"] == 2
    assert payload["retrieval_ozeti"]["evidence_secim_ozeti"]["heading_uyumlu_hit_sayisi"] >= 1
    assert "_rerank" not in payload["kullanilan_kanitlar"][0]
    assert "metin" not in payload["kullanilan_kanitlar"][0]


def test_prepare_answer_evidence_marks_selected_and_weak_sources():
    meta = prepare_answer_evidence(
        "rerank nasil calisir",
        [
            {
                "parca_id": 61,
                "dokuman_id": 12,
                "adres": "Giris",
                "metin": "Rerank, query ile daha cok ortusen parcayi ust siraya alir.",
                "snippet": "Rerank, query ile daha cok ortusen parcayi ust siraya alir.",
                "skor": 0.66,
            },
            {
                "parca_id": 62,
                "dokuman_id": 12,
                "adres": "Ek",
                "metin": "Not",
                "snippet": "Not",
                "skor": 0.12,
            },
        ],
    )

    assert meta["kullanilan_parca_idleri"] == [61]
    assert meta["kullanilan_kanit_idleri"] == ["kanit:61"]
    assert meta["kullanilan_adresler"] == ["Giris"]
    assert meta["kaynak_guveni"] in {"orta", "yuksek"}
    assert meta["kanitlar"][0]["cevapta_kullanildi"] is True
    assert meta["kanitlar"][0]["kanit_gucu"] in {"orta", "yuksek"}
    assert meta["kanitlar"][1]["zayif_kaynak_mi"] is True
    assert meta["kanitlar"][1]["kanit_gucu"] == "dusuk"


def test_prepare_answer_evidence_respects_forced_selected_ids_without_fallback():
    meta = prepare_answer_evidence(
        "rerank nasil calisir",
        [
            {
                "parca_id": 71,
                "dokuman_id": 12,
                "adres": "Giris",
                "metin": "Rerank, query ile ortusen parcayi ust siraya alir.",
                "snippet": "Rerank, query ile ortusen parcayi ust siraya alir.",
                "skor": 0.66,
            },
            {
                "parca_id": 72,
                "dokuman_id": 12,
                "adres": "Ek",
                "metin": "Kisa not",
                "snippet": "Kisa not",
                "skor": 0.11,
            },
        ],
        forced_parca_idleri=[999],
    )

    assert meta["kaynak_zorlamasi_uygulandi_mi"] is True
    assert meta["secilen_kanitlar"] == []
    assert meta["kullanilan_parca_idleri"] == []
    assert meta["kaynak_guveni"] == "dusuk"


def test_prepare_answer_evidence_forced_selection_keeps_answer_allowed_aligned_for_weak_hit():
    meta = prepare_answer_evidence(
        "jwt neden kullanilir",
        [
            {
                "parca_id": 801,
                "dokuman_id": 41,
                "adres": "JWT > Kisa Not",
                "metin": "JWT notu.",
                "skor": 0.18,
                "weak_content": True,
            }
        ],
        forced_parca_idleri=[801],
    )

    assert meta["kaynak_zorlamasi_uygulandi_mi"] is True
    assert meta["kullanilan_parca_idleri"] == [801]
    assert meta["abstention_uygulandi_mi"] is False
    assert meta["answer_allowed"] is True
    assert meta["weak_evidence"] is True
    assert meta["evidence_strength"] == "dusuk"
    assert meta["abstain_reason"] == ""


def test_build_evidence_response_payload_keeps_forced_selection_flags_consistent():
    meta = orchestrate_evidence_selection(
        "jwt neden kullanilir",
        [
            {
                "parca_id": 811,
                "dokuman_id": 51,
                "adres": "JWT > Zayif Kaynak",
                "metin": "JWT kisa not.",
                "skor": 0.16,
                "retrieval_kaynagi": "rag.semantic",
                "weak_content": True,
            }
        ],
        answer_limit=1,
        forced_parca_idleri=[811],
    )

    payload = build_evidence_response_payload(meta, include_kanitlar=False)
    kaynak_durumu = derive_answer_source_state(meta)

    assert meta["abstention_uygulandi_mi"] is False
    assert meta["answer_allowed"] is True
    assert meta["weak_evidence"] is True
    assert meta["abstain_reason"] == ""
    assert payload["answer_allowed"] is True
    assert payload["weak_evidence"] is True
    assert payload["abstain_reason"] == ""
    assert payload["retrieval_ozeti"]["answer_allowed"] is True
    assert payload["retrieval_ozeti"]["evidence_secim_ozeti"]["answer_allowed"] is True
    assert kaynak_durumu["answer_allowed"] is True
    assert kaynak_durumu["weak_evidence"] is True


def test_build_answer_from_evidence_references_selected_sources_cautiously_when_weak():
    answer = build_answer_from_evidence(
        "RAG neden bazen zayif kalir?",
        [
            {
                "parca_id": 91,
                "kanit_id": "kanit:91",
                "adres": "RAG > Sinir",
                "snippet": "Kaynak parcasi kisa oldugunda cevap daha temkinli olmalidir.",
            }
        ],
        kaynak_zayif_mi=True,
    )

    assert "Kaynaklar sınırlı" in answer
    assert "RAG > Sinir" in answer
    assert "kanit_sayisi: 1" in answer
    assert "[kanit:91]" in answer


def test_build_answer_from_evidence_does_not_overclaim_when_answer_not_allowed():
    answer = build_answer_from_evidence(
        "JWT neden kullanilir?",
        [
            {
                "parca_id": 191,
                "kanit_id": "kanit:191",
                "adres": "JWT > Kisa Not",
                "snippet": "JWT kisa not.",
                "weak_evidence": True,
                "evidence_strength": "dusuk",
            }
        ],
        answer_allowed=False,
        weak_evidence=True,
        evidence_strength="dusuk",
        abstain_reason="zayif_kanit",
    )

    assert "güvenli bir yanıt vermek için yeterli değil" in answer
    assert "Seçili kanıtlara göre" not in answer
    assert "[kanit:191]" in answer


def test_ground_answer_text_uses_common_decision_fields_for_cautious_grounding():
    grounded = ground_answer_text(
        "JWT istemci kimligini tasimaya yardim eder.",
        [
            {
                "kanit_id": "kanit:211",
                "adres": "JWT > Amac",
                "weak_evidence": True,
                "evidence_strength": "dusuk",
            }
        ],
        answer_allowed=True,
        weak_evidence=True,
        evidence_strength="dusuk",
    )

    assert grounded.startswith("Kaynaklar sınırlı; seçili parçalara dayanarak:")
    assert "Kaynaklar: [kanit:211] JWT > Amac" in grounded


def test_derive_answer_source_state_can_require_citations_for_ai2():
    kanit_meta = orchestrate_evidence_selection(
        "rerank neden faydali",
        [
            {
                "parca_id": 401,
                "dokuman_id": 21,
                "adres": "RAG > Rerank",
                "metin": "Rerank daha ilgili parcayi ust siraya tasiyarak cevap kalitesini artirir.",
                "skor": 0.88,
                "retrieval_kaynagi": "rag.semantic",
            }
        ],
        answer_limit=1,
        dokuman_filtresi_var_mi=True,
    )

    normal = derive_answer_source_state(kanit_meta)
    ai2_weak = derive_answer_source_state(
        kanit_meta,
        citation_ids=[],
        citation_required=True,
    )
    ai2_supported = derive_answer_source_state(
        kanit_meta,
        citation_ids=[401],
        citation_required=True,
    )

    assert normal["kaynak_zayif_mi"] is False
    assert ai2_weak["kaynak_zayif_mi"] is True
    assert ai2_weak["kaynak_guveni"] == "dusuk"
    assert ai2_supported["kaynak_zayif_mi"] is False


def test_rag_ara_endpoint_returns_standardized_results_and_retrieval_ozeti(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="RAG Test",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("rag-test.pdf", ContentFile(b"ornek"), save=True)

    monkeypatch.setattr(
        "dokuman.views.search_rag_with_auto_index_meta",
        lambda **kwargs: (
            [
                {
                    "parca_id": 7,
                    "dokuman_id": doc.id,
                    "skor": 0.84,
                    "metin": "RAG once ilgili parcayi bulur sonra bu parcaya dayali cevap uretir.",
                    "adres": "1",
                    "baslik_yolu": "1",
                    "retrieval_kaynagi": "rag.semantic",
                }
            ],
            {
                "dokuman_filtresi_var_mi": True,
                "auto_index_denendi_mi": True,
            },
        ),
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        f"/api/dokuman-asistani/dokumanlar/{doc.id}/rag-ara/",
        {"query": "RAG nasil calisir?"},
        format="json",
    )

    assert response.status_code == 200
    data = response.data
    assert data["count"] == 1
    assert data["retrieval_ozeti"]["toplam_sonuc"] == 1
    assert data["retrieval_ozeti"]["toplam_hit"] == 1
    assert data["retrieval_ozeti"]["kullanilan_hit"] == 1
    assert data["retrieval_ozeti"]["dokuman_filtresi_var_mi"] is True
    assert data["retrieval_ozeti"]["auto_index_denendi_mi"] is True
    assert data["retrieval_ozeti"]["rerank_uygulandi_mi"] is False
    assert data["retrieval_ozeti"]["rerank_ilk_hit_degisti_mi"] is False
    assert data["retrieval_ozeti"]["zayif_icerik_hit_sayisi"] == 0
    assert data["retrieval_ozeti"]["zayif_kaynak_hit_sayisi"] == 0
    assert data["retrieval_ozeti"]["retrieval_kaynagi_ozeti"] == {"rag.semantic": 1}
    assert data["sonuclar"][0]["parca_id"] == 7
    assert data["sonuclar"][0]["dokuman_id"] == doc.id
    assert data["sonuclar"][0]["retrieval_kaynagi"] == "rag.semantic"
    assert data["sonuclar"][0]["baslik_yolu"] == "1"
    assert "metin" not in data["sonuclar"][0]
    assert data["sonuclar"][0]["snippet"]


def test_kanitli_sor_endpoint_returns_standardized_hits_and_ozet(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Lexical QA",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("lexical-qa.pdf", ContentFile(b"ornek"), save=True)

    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Giris",
        metin="RAG once ilgili parcayi bulur sonra kaynakli cevap uretir.",
        meta={"path": "Giris"},
    )
    Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="Ek",
        metin="Baska bir teknik not.",
        meta={"path": "Ek"},
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        f"/api/dokuman-asistani/dokumanlar/{doc.id}/sor/",
        {"soru": "RAG once ne yapar?", "limit": 2},
        format="json",
    )

    assert response.status_code == 200
    data = response.data
    assert data["kanitlar"]
    assert data["kanitlar"][0]["dokuman_id"] == doc.id
    assert data["kanitlar"][0]["retrieval_kaynagi"] == "lexical_overlap"
    assert data["kanitlar"][0]["kanit_id"] == f"kanit:{data['kanitlar'][0]['parca_id']}"
    assert "snippet" in data["kanitlar"][0]
    assert data["kullanilan_kanit_sayisi"] >= 1
    assert data["kullanilan_parca_idleri"]
    assert data["kullanilan_kanit_idleri"]
    assert data["kullanilan_adresler"]
    assert data["kullanilan_kanitlar"]
    assert data["kaynak_guveni"] in {"orta", "yuksek"}
    assert data["retrieval_ozeti"]["kullanilan_hit"] == data["kullanilan_kanit_sayisi"]
    assert data["retrieval_ozeti"]["toplam_sonuc"] >= 1
    assert data["retrieval_ozeti"]["dokuman_filtresi_var_mi"] is True
    assert data["retrieval_ozeti"]["auto_index_denendi_mi"] is False
    assert data["retrieval_ozeti"]["rerank_uygulandi_mi"] is False
    assert data["retrieval_ozeti"]["zayif_kaynak_hit_sayisi"] >= 0
    assert data["retrieval_ozeti"]["retrieval_kaynagi_ozeti"]["lexical_overlap"] >= 1


def test_kanitli_sor_endpoint_keeps_answer_and_used_evidence_aligned(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Aligned QA",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("aligned-qa.pdf", ContentFile(b"ornek"), save=True)

    first = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="RAG > Giris",
        metin="RAG once ilgili parcayi bulur ve sonra cevap icin kanit kullanir.",
        meta={"path": "RAG > Giris"},
    )
    second = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="RAG > Kaynak",
        metin="Kaynakli cevapta parca_id izlenebilirligi cevap kalitesini gorunur kilar.",
        meta={"path": "RAG > Kaynak"},
    )
    Parca.objects.create(
        dokuman=doc,
        sira=3,
        tur="bolum",
        adres="Ek",
        metin="Bagimsiz ek not.",
        meta={"path": "Ek"},
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        f"/api/dokuman-asistani/dokumanlar/{doc.id}/sor/",
        {"soru": "Kaynakli cevapta parca_id neden onemli?", "limit": 3},
        format="json",
    )

    assert response.status_code == 200
    data = response.data
    used_hits = [hit for hit in data["kanitlar"] if hit["cevapta_kullanildi"] is True]

    assert data["kullanilan_kanit_sayisi"] == len(used_hits)
    assert set(data["kullanilan_parca_idleri"]) == {hit["parca_id"] for hit in used_hits}
    assert set(data["kullanilan_kanit_idleri"]) == {hit["kanit_id"] for hit in used_hits}
    assert set(data["kullanilan_adresler"]) == {hit["adres"] for hit in used_hits}
    assert set(data["kullanilan_parca_idleri"]).issubset({first.id, second.id})
    assert f"[{data['kullanilan_kanit_idleri'][0]}]" in data["cevap"]


def test_ai2_kanitli_cevap_endpoint_aligns_citations_with_used_evidence(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="AI2 QA",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("ai2-qa.pdf", ContentFile(b"ornek"), save=True)

    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="RAG > Giris",
        metin="RAG once ilgili parcayi bulur ve cevap icin bu parcayi kullanir.",
        meta={"path": "RAG > Giris"},
    )
    second = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="RAG > Kaynak",
        metin="Kaynakli cevapta parca_id ve kanit_id izlenebilirligi kritik onemdedir.",
        meta={"path": "RAG > Kaynak"},
    )

    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: (
            '{"answer":"Parca kimligini gostermek cevabin hangi kanita dayandigini izlenebilir kilar.",'
            f'"supported":true,"citations":[{second.id},{second.id}],"missing":[],"followups":[]}}'
        ),
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/ai2/kanitli-cevap/",
        {"question": "Kaynakli cevapta parca_id neden onemli?", "doc_id": doc.id, "top_k": 2},
        format="json",
    )

    assert response.status_code == 200
    data = response.data
    assert data["supported"] is True
    assert data["citations"] == [second.id]
    assert data["kullanilan_parca_idleri"] == [second.id]
    assert data["kullanilan_kanit_idleri"] == [f"kanit:{second.id}"]
    assert data["kullanilan_kanit_sayisi"] == 1
    assert data["kullanilan_kanitlar"][0]["parca_id"] == second.id
    assert data["kullanilan_kanitlar"][0]["cevapta_kullanildi"] is True
    assert data["kaynak_zorlamasi_uygulandi_mi"] is True
    assert "[kanit:" in data["answer"]
    assert "Kaynaklar:" in data["answer"]
    assert data["retrieval_ozeti"]["kullanilan_hit"] == 1
    assert data["retrieval_ozeti"]["evidence_secim_ozeti"]["forced_parca_idleri"] == [second.id]
    assert data["retrieval_ozeti"]["retrieval_kaynagi_ozeti"]["lexical_overlap"] >= 1
    assert "metin" not in data["kullanilan_kanitlar"][0]
    assert "_evidence_used" not in data


def test_ai2_kanitli_cevap_endpoint_routes_manual_evidence_through_common_orchestrator(
    db,
    test_kullanicisi,
    monkeypatch,
):
    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: (
            '{"answer":"Elle verilen kanit da ortak orchestrator ile secilir.",'
            '"supported":true,"citations":[501],"missing":[],"followups":[]}'
        ),
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/ai2/kanitli-cevap/",
        {
            "question": "Elle verilen kanit nasil seciliyor?",
            "evidence": [
                {
                    "parca_id": 501,
                    "addr": "Manual > Evidence",
                    "text": "Elle verilen evidence de ortak evidence orchestrator uzerinden secilir.",
                },
                {
                    "parca_id": 502,
                    "addr": "Manual > Ek",
                    "text": "Kisa ek not.",
                },
            ],
        },
        format="json",
    )

    assert response.status_code == 200
    data = response.data
    assert data["supported"] is True
    assert data["citations"] == [501]
    assert data["kullanilan_parca_idleri"] == [501]
    assert data["kullanilan_kanit_idleri"] == ["kanit:501"]
    assert data["kullanilan_kanit_sayisi"] == 1
    assert data["kullanilan_kanitlar"][0]["adres"] == "Manual > Evidence"
    assert "metin" not in data["kullanilan_kanitlar"][0]
    assert data["retrieval_ozeti"]["retrieval_kaynagi_ozeti"] == {"ai2.request_evidence": 2}
    assert data["retrieval_ozeti"]["evidence_secim_ozeti"]["forced_parca_idleri"] == [501]


def test_ai2_kanitli_cevap_endpoint_rejects_answer_without_citation(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="AI2 QA Weak",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("ai2-qa-weak.pdf", ContentFile(b"ornek"), save=True)

    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="RAG > Giris",
        metin="RAG ilgili parcayi bulur.",
        meta={"path": "RAG > Giris"},
    )

    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: '{"answer":"Bence cevap bu.","supported":true,"citations":[],"missing":[],"followups":[]}',
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/ai2/kanitli-cevap/",
        {"question": "RAG ne yapar?", "doc_id": doc.id, "top_k": 1},
        format="json",
    )

    assert response.status_code == 200
    data = response.data
    assert data["supported"] is False
    assert data["answer"] == "Dokümanda geçmiyor."
    assert data["citations"] == []
    assert data["kullanilan_kanit_sayisi"] == 0
    assert data["kullanilan_kanit_idleri"] == []
    assert data["kaynak_guveni"] == "dusuk"


def test_legacy_kanitli_sor_endpoint_routes_legacy_hits_through_common_orchestrator(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Legacy QA",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("legacy-qa.pdf", ContentFile(b"ornek"), save=True)

    first = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Legacy > Kaynak",
        metin="Ortak evidence orchestrator legacy retrieval sonucunu da secili kanita donusturur.",
        meta={"path": "Legacy > Kaynak"},
    )
    Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="Legacy > Ek",
        metin="Kisa ek not.",
        meta={"path": "Legacy > Ek"},
    )

    monkeypatch.setattr("dokuman.views.en_alakali", lambda soru, texts, top_k=5: [0, 1])
    monkeypatch.setattr("dokuman.views.yerel_modeli_al", lambda: None)

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/sor/",
        {"doc_id": doc.id, "soru": "legacy retrieval nasil seciliyor", "skip_gate": True},
        format="json",
    )

    assert response.status_code == 200
    data = response.data
    assert data["kullanilan_kanit_sayisi"] >= 1
    assert first.id in data["kullanilan_parca_idleri"]
    assert data["retrieval_ozeti"]["retrieval_kaynagi_ozeti"]["legacy.object_retrieval"] == 2
    assert data["retrieval_ozeti"]["evidence_secim_ozeti"]["secilen_kanit_sayisi"] == data["kullanilan_kanit_sayisi"]
    assert data["kullanilan_kanitlar"][0]["kanit_id"].startswith("kanit:")


def test_ingestion_optionally_syncs_rag_index_after_success(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
    settings,
):
    settings.RAG_AUTO_INDEX_ON_INGEST = True

    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Ingest Sync",
        mime="application/pdf",
        durum="yuklendi",
    )
    doc.dosya.save("ingest-sync.pdf", ContentFile(b"ornek"), save=True)

    monkeypatch.setattr(
        "dokuman.services.ingestion.parse_document_structure",
        lambda path: {
            "section_count": 1,
            "sections": [
                    {
                        "title": "Giris",
                        "content": (
                            "Retrieval parcasi ingestion sonunda indexe de girebilir. "
                            "Bu bolum bilerek daha uzun tutuldu ve kalite filtresini gecmesi beklenir."
                        ),
                        "path": "Giris",
                        "level": 1,
                        "page_start": 1,
                    }
            ],
        },
    )

    sync_calls = []
    monkeypatch.setattr(
        "dokuman.services.rag.sync_dokuman_indexi_if_enabled",
        lambda d: sync_calls.append(d.id) or {"denendi": True, "basarili": True, "indexlenen_parca_sayisi": 1},
    )

    ingestion.dokumani_parcala_ve_kaydet(doc)
    doc.refresh_from_db()

    assert doc.durum == "parcalandi"
    assert sync_calls == [doc.id]
