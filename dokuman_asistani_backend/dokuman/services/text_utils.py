import bisect
from typing import Tuple, List

def build_newline_indices(text: str) -> List[int]:
    """
    Doküman ilk yüklendiğinde bir kez çalıştırılır O(N).
    Sonucu veritabanında JSONField olarak saklayabilirsiniz.
    """
    return [i for i, char in enumerate(text) if char == '\n']

def char_to_line_col(char_index: int, newline_indices: List[int]) -> Tuple[int, int]:
    """
    Karakter indeksinden (0-tabanlı) satır ve sütun numarasını (1-tabanlı) 
    O(log N) karmaşıklığıyla hesaplar. N = satır sayısı.
    """
    if char_index < 0:
        return 1, 1
        
    if not newline_indices or char_index <= newline_indices[0]:
        return 1, char_index + 1

    # Binary search ile karakterin düştüğü satırı buluyoruz.
    # bisect_right, char_index'ten küçük veya eşit olan yeni satırların sayısını verir.
    line_idx = bisect.bisect_right(newline_indices, char_index - 1)
    
    line_num = line_idx + 1
    
    if line_idx == 0:
        prev_newline_idx = -1
    else:
        prev_newline_idx = newline_indices[line_idx - 1]
        
    col_num = char_index - prev_newline_idx
    return line_num, col_num