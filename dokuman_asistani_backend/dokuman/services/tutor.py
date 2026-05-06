def anlamadim_cevap(selected_text: str) -> str:
    # v0.2'de buraya LLM bağlayacağız
    return (
        "1) 1 cümlede özet\n"
        f"{selected_text[:120]}...\n\n"
        "2) Çok basit anlatım\n"
        "Bu bölüm yoğun olabilir. Ana fikri 2-3 cümleye indirip adım adım açacağız.\n\n"
        "3) Terimler sözlüğü\n"
        "- (v0.2: otomatik terim çıkarma)\n\n"
        "4) Adım adım mantık\n"
        "1- Ana cümleyi bul.\n"
        "2- Neden/sonuç ayır.\n"
        "3- Örnekle pekiştir.\n\n"
        "5) Tema bazlı örnek\n"
        "- (v0.2: tema ile örnek)\n\n"
        "6) Alternatif örnek\n"
        "- (v0.2)\n\n"
        "7) Tuzak uyarısı\n"
        "- Tanımı örnek sanma.\n\n"
        "8) Mini test\n"
        "S1) Ana fikir?\nS2) 2 terim?\nS3) 1 örnek?\n\n"
        "CEVAPLAR:\nS1) ...\nS2) ...\nS3) ...\n"
    )