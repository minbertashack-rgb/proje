from typing import List, Dict, Any

def prompt_kanitli_sor(soru: str, kanitlar: List[Dict[str, str]]) -> str:
    ctx = "\n---\n".join([f"KAYNAK {i+1} [{k['adres']}]\n{k['metin']}" for i, k in enumerate(kanitlar)])

    return f"""
Sen “kanıtlı cevap” üreten bir asistansın.

ÇOK ÖNEMLİ KURALLAR:
- SADECE aşağıdaki KAYNAK metinlerini kullan.
- Eğer KAYNAK metinlerinde sorunun cevabı/tanımı yoksa: TAM OLARAK "Dokümanda yok." yaz.
- Cevap vereceksen madde madde yaz.
- Her maddenin sonunda mutlaka kaynak adresi yaz: [txt:para:1] gibi.
- Boş [adres] yazma. Gerçek adres yaz.
- <think> veya benzeri gizli düşünce yazma.

Soru: {soru}

KAYNAKLAR:
{ctx}

Çıktı formatı (örnek):
- .... [txt:para:1]
- .... [txt:para:2]

Cevabı yaz:
""".strip()

# --- BACKWARD COMPAT: views.py bu ismi bekliyor ---
def prompt_bunu_anlamadim(*args, **kwargs) -> str:
    """
    Parça için 'bunu anlamadım' açıklama promptu.
    Eski isimle çağrılan fonksiyon silindiyse server import'ta düşmesin diye eklendi.
    """
    # Parça metnini yakalamaya çalış (esnek)
    parca_metin = ""
    if args:
        parca_metin = str(args[0])
    else:
        parca_metin = str(
            kwargs.get("parca_metin")
            or kwargs.get("metin")
            or kwargs.get("text")
            or ""
        )

    soru = str(kwargs.get("soru") or "Bu parçayı çok basit şekilde açıkla.")

    return f"""Sen bir öğretmensin.
Kullanıcı bu parçayı anlamadı. Çok basit ve kısa anlat.

PARÇA:
{parca_metin}

İSTEK:
{soru}

ÇIKTI:
- 1 cümle özet
- 2-3 cümle basit anlatım
- 3 maddeyle püf noktalar
"""

prompt_bunu_anlamadim = prompt_bunu_anlamadim