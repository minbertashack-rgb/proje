from typing import List

def semantic_chunk_text(text: str, size: int = 1200, overlap: int = 180, window: int = 50) -> List[str]:
    """
    Metni parçalarken (Chunking) tam 'size' değerinde kesmek yerine, 
    belirlenen 'window' aralığında en yakın semantik sınırdan ('.' veya '\\n') keser.
    """
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = start + size
        
        if end >= text_len:
            chunks.append(text[start:text_len])
            break
            
        # window boyutunda semantik sınırı (boundary) ara
        search_start = max(start + 1, end - window)
        search_end = min(text_len, end + window)
        
        boundary = -1
        # Pencereyi sondan başa doğru tarıyoruz ki en büyük anlamlı bloğu alalım
        for i in range(search_end - 1, search_start - 1, -1):
            if text[i] in {'.', '\n'}:
                boundary = i
                break
        
        if boundary != -1:
            chunk_end = boundary + 1  # Nokta veya yeni satırı dahil et
        else:
            chunk_end = end  # Sınır bulunamazsa hard-split yap
            
        chunks.append(text[start:chunk_end])
        start = chunk_end - overlap  # Belirlenen overlap (180) miktarı kadar geri git
        
    return chunks