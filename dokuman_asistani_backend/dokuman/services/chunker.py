from typing import List, Dict, Any
from .parsers import Eleman
from .confusion import zorluk_hesapla

def chunkla(elemanlar: List[Eleman], max_chars: int = 1200, overlap: int = 120) -> List[Dict[str, Any]]:
    parcalar = []
    sira = 0

    for el in elemanlar:
        txt = (el.metin or "").strip()
        if not txt:
            continue

        if len(txt) <= max_chars:
            sira += 1
            skor, zorluk = zorluk_hesapla(txt, el.tur)
            parcalar.append({
                "sira": sira,
                "tur": el.tur,
                "metin": txt,
                "adres": el.adres,
                "meta": el.meta,
                "zorluk_skoru": skor,
                "zorluk": zorluk,
            })
            continue

        start = 0
        part = 0
        while start < len(txt):
            end = min(len(txt), start + max_chars)
            piece = txt[start:end].strip()
            if piece:
                part += 1
                sira += 1
                skor, zorluk = zorluk_hesapla(piece, el.tur)
                parcalar.append({
                    "sira": sira,
                    "tur": el.tur,
                    "metin": piece,
                    "adres": f"{el.adres}@part:{part}",
                    "meta": {**el.meta, "part": part, "start": start, "end": end},
                    "zorluk_skoru": skor,
                    "zorluk": zorluk,
                })
            start = end - overlap if end - overlap > start else end

    return parcalar