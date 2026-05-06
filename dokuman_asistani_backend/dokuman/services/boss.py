import re
from collections import Counter

TR_STOP = {
    "ve","veya","ile","ama","fakat","çünkü","için","gibi","de","da","ki",
    "bir","bu","şu","o","çok","daha","en","mi","mı","mu","mü",
    "olarak","olan","olur","ile","neden","sonuç","şekilde"
}

def _kelimeler(text: str):
    toks = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9_]+", text.lower())
    toks = [t for t in toks if len(t) >= 4 and t not in TR_STOP]
    return toks

def boss_uret(metin: str, difficulty_meta: dict | None = None):
    toks = _kelimeler(metin)
    frek = Counter(toks)
    anahtarlar = [w for w, _ in frek.most_common(6)]
    difficulty_meta = difficulty_meta or {}
    band = str(difficulty_meta.get("boss_difficulty_band") or "medium").strip()
    if band == "easy":
        ilk_soru = "Bu parçanın ana fikrini tek bir net cümleyle söyle."
        ikinci_soru = f"Şu 2 terimi kısa tanımla: {', '.join(anahtarlar[:2])}"
        gorev = "Parçayı 2 adım halinde açıkla."
    elif band == "hard":
        ilk_soru = "Bu parçanın ana fikrini ve olası yanlış anlamayı birlikte açıkla."
        ikinci_soru = f"Şu 2 terimi kıyaslayıp örnek ver: {', '.join(anahtarlar[:2])}"
        gorev = "Parçayı neden-sonuç ilişkisiyle 3 adımda çözümle."
    else:
        ilk_soru = "Bu parçanın ana fikri ne?"
        ikinci_soru = f"Şu 2 terimi açıklayıp örnek ver: {', '.join(anahtarlar[:2])}"
        gorev = "Parçayı 3 adıma böl (1-2-3 şeklinde)."

    return {
        "boss": {
            "kisa_ozet_gorev": "Bu parçayı 2 cümleyle kendi cümlenle özetle.",
            "anahtar_kelimeler": anahtarlar,
            "difficulty_band": band,
        },
        "arena": [
            {"tip": "soru", "soru": ilk_soru, "beklenen": "1-2 cümle"},
            {"tip": "soru", "soru": ikinci_soru, "beklenen": "kısa tanım + örnek"},
            {"tip": "gorev", "soru": gorev, "beklenen": "adım adım"},
            {"tip": "mini_test", "sorular": [
                "S1) En kritik terim hangisi?",
                "S2) En çok karıştırılacak nokta ne?",
                "S3) Konuyu pekiştirecek 1 örnek üret."
            ]}
        ]
    }
