from typing import List
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

def en_alakali(question: str, chunk_texts: List[str], top_k: int = 5) -> List[int]:
    if not chunk_texts:
        return []
    vect = TfidfVectorizer(stop_words=None, max_features=50000)
    X = vect.fit_transform(chunk_texts)
    q = vect.transform([question])
    scores = (X @ q.T).toarray().reshape(-1)
    idx = np.argsort(-scores)[:top_k]
    return idx.tolist()