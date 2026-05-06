from __future__ import annotations

from dokuman.services.rag import lightweight_rerank_hits
from dokuman.services.retrieval_terms import normalize_query_terms


def _hit(
    parca_id: int,
    skor: float,
    metin: str,
    path: str,
    dokuman_id: int = 1,
    *,
    weak_content: bool | None = None,
    chunk_index: int | None = None,
) -> dict:
    return {
        "parca_id": parca_id,
        "dokuman_id": dokuman_id,
        "skor": skor,
        "metin": metin,
        "adres": path,
        "baslik_yolu": path,
        "retrieval_kaynagi": "rag.semantic",
        "weak_content": weak_content,
        "chunk_index": chunk_index,
    }


def _sirala(query: str, hits: list[dict]) -> list[dict]:
    return lightweight_rerank_hits(query, hits)


def test_normalize_query_terms_cleans_case_and_stopwords():
    assert normalize_query_terms("Ve JWT, Icin amac nedir?") == ["jwt", "amac", "nedir"]


def test_deterministic_rerank_prefers_semantic_when_gap_is_clear():
    hits = _sirala(
        "jwt amac",
        [
            _hit(
                101,
                0.96,
                "JWT guvenlik yapisidir ve servisler arasi kimlik aktariminda kullanilan standart bir token yapisi sunar.",
                "Guvenlik > Giris",
            ),
            _hit(
                102,
                0.55,
                "Token yapisi burada genel guvenlik notu olarak anilir.",
                "Guvenlik > Notlar",
            ),
        ],
    )

    assert [hit["parca_id"] for hit in hits] == [101, 102]
    assert 0.48 <= hits[0]["_rerank"]["final_rerank"] <= 0.70
    assert hits[0]["_rerank"]["final_rerank"] > hits[1]["_rerank"]["final_rerank"]


def test_deterministic_rerank_prefers_lexical_strength_when_semantic_is_close():
    hits = _sirala(
        "embedding rerank kalite",
        [
            _hit(201, 0.84, "Genel sistem notu ve baglamsiz bir aciklama.", "Genel"),
            _hit(202, 0.71, "Embedding rerank kalite artirir ve ilgili parcayi one cikarir.", "RAG > Kalite"),
        ],
    )

    assert [hit["parca_id"] for hit in hits] == [202, 201]
    assert hits[0]["_rerank"]["soru_terim_kapsama_orani"] > hits[1]["_rerank"]["soru_terim_kapsama_orani"]
    assert hits[0]["_rerank"]["final_rerank"] > 0.55


def test_deterministic_rerank_path_match_can_break_close_candidates():
    hits = _sirala(
        "jwt amac",
        [
            _hit(301, 0.79, "JWT ile ilgili kisa ama dogru not.", "Guvenlik > JWT", chunk_index=8),
            _hit(302, 0.74, "JWT ile ilgili kisa ama dogru not.", "Guvenlik > JWT > Amac", chunk_index=9),
        ],
    )

    assert [hit["parca_id"] for hit in hits] == [302, 301]
    assert hits[0]["_rerank"]["adres_terim_kapsama_orani"] > hits[1]["_rerank"]["adres_terim_kapsama_orani"]


def test_deterministic_rerank_weak_penalty_demotes_thin_chunk():
    hits = _sirala(
        "vektor arama",
        [
            _hit(401, 0.90, "Vektor notu", "Ek", weak_content=True),
            _hit(402, 0.78, "Vektor arama benzer parcayi semantik olarak bulup ust siraya tasir.", "Arama > Mantik"),
        ],
    )

    assert [hit["parca_id"] for hit in hits] == [402, 401]
    assert hits[1]["_rerank"]["weak_penalty"] == 0.15
    assert hits[0]["_rerank"]["final_rerank"] > hits[1]["_rerank"]["final_rerank"]


def test_deterministic_rerank_uses_chunk_index_asc_for_stable_tie_break():
    query = "sql join"
    candidates = [
        _hit(501, 0.77, "SQL join iki tabloyu ortak alan uzerinden birlestirir.", "SQL > Join", chunk_index=5),
        _hit(502, 0.77, "SQL join iki tabloyu ortak alan uzerinden birlestirir.", "SQL > Join", chunk_index=3),
    ]

    first = _sirala(query, candidates)
    second = _sirala(query, candidates)

    assert [hit["parca_id"] for hit in first] == [502, 501]
    assert [hit["parca_id"] for hit in second] == [502, 501]
    assert first[0]["_rerank"]["final_rerank"] == first[1]["_rerank"]["final_rerank"]
