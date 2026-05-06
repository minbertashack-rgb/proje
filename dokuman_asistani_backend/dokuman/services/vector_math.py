"""
Yerel vektor yardimcilari.

Not: Bu moduldeki yardimcilar aktif DocVerse RAG / Chroma retrieval hattina
bagli degildir. Ana semantic akista L2 normalization,
SentenceTransformer.encode(..., normalize_embeddings=True) uzerinden
zaten uygulanir; index ve query embeddingleri aktif akista bu sekilde uretilir.
Bu dosya yalnizca izole vektor hesaplari, util ve testler icin tutulur.
Bu modul `rag.py` veya `vector_store.py` icindeki retrieval ana yoluna
entegre edilmemelidir.
Ek bir manuel normalize_l2 katmani retrieval skorlamasina yeni bilgi katmaz;
asil risk gereksiz bakim maliyeti ile zero-vector, dtype ve sekil (shape)
gibi edge-case ayrismalarini retrieval hattina tasimasidir.
"""

import math
from typing import List


def normalize_l2(vector: List[float]) -> List[float]:
    """
    Vektörü L2 normuna göre normalize eder: v / ||v||_2
    """
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm != 0 else vector


def cosine_similarity(v1: List[float], v2: List[float], pre_normalized: bool = False) -> float:
    """
    İki vektör arasındaki Kosinüs Benzerliğini hesaplar.
    Eğer vektörler zaten normalize edilmişse (pre_normalized=True),
    sadece Dot Product (nokta çarpımı) hesaplanarak ciddi bir CPU kazanımı sağlanır.
    """
    if not pre_normalized:
        v1 = normalize_l2(v1)
        v2 = normalize_l2(v2)
    return sum(x * y for x, y in zip(v1, v2))
