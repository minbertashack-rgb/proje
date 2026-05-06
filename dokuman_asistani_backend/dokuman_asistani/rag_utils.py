import numpy as np

def semantic_chunker(text: str, chunk_size: int = 1200, overlap: int = 180, window: int = 50) -> list[str]:
    """
    Metni belirlenen S (chunk_size) ve O (overlap) parametrelerine göre anlamsal olarak böler.
    Matematiksel formül: Kesim noktasını tam chunk_size'da değil, ± window karakterlik 
    bir tolerans alanında en yakın nokta veya yeni satır sınırında ('Semantic Boundary') yapar.
    """
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = start + chunk_size
        
        # Metin sonuna ulaştıysak kalanı doğrudan al ve döngüyü bitir
        if end >= text_len:
            chunks.append(text[start:text_len])
            break
            
        # Semantic Boundary Arama (Geriye ve İleriye doğru ± window)
        boundary_found = False
        search_start = max(start, end - window)
        search_end = min(text_len, end + window)
        
        # Öncelikle anlamı kırmamak için geriye doğru "." veya "\n" arıyoruz
        for idx in range(min(end, text_len - 1), search_start - 1, -1):
            if text[idx] in [".", "\n"]:
                end = idx + 1
                boundary_found = True
                break
                
        # Eğer geriye doğru sınır bulamadıysak ileriye doğru bakalım
        if not boundary_found:
            for idx in range(end, search_end):
                if text[idx] in [".", "\n"]:
                    end = idx + 1
                    boundary_found = True
                    break
                    
        # Eğer hiçbir ayraç bulunamadıysa fallback olarak boşluk (" ") arayalım
        if not boundary_found:
            for idx in range(end, search_start - 1, -1):
                if text[idx] == " ":
                    end = idx + 1
                    break
                    
        chunks.append(text[start:end])
        
        # Bir sonraki parçaya overlap formülü uyarınca geri çekilerek başla
        start = end - overlap
        
    return chunks

def normalize_vector(v: list[float] | np.ndarray) -> list[float]:
    """
    Vektörleri v_norm = v / ||v||_2 formülü ile L2 normalizasyonuna tabi tutar.
    Bu işlem, Inner/Dot Product aramalarının matematiksel olarak Cosine Similarity'e eşitlenmesini sağlar.
    """
    vec = np.array(v, dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec.tolist()
    return (vec / norm).tolist()