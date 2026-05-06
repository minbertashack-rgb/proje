from __future__ import annotations

from collections import Counter
from statistics import mean
import json
import re


_STOPWORDS = {
    "aciklar",
    "adim",
    "adimlar",
    "ait",
    "ama",
    "ana",
    "ancak",
    "artik",
    "az",
    "baglam",
    "basit",
    "belge",
    "bir",
    "biraz",
    "birlikte",
    "bunu",
    "bu",
    "burada",
    "cok",
    "daha",
    "de",
    "degil",
    "dokuman",
    "dokumanda",
    "genel",
    "gibi",
    "gore",
    "icin",
    "icerir",
    "ile",
    "ilgili",
    "ise",
    "kadar",
    "kisa",
    "metin",
    "neden",
    "olan",
    "olarak",
    "olur",
    "ornek",
    "parca",
    "sadece",
    "sekilde",
    "sonra",
    "su",
    "temel",
    "uzerinden",
    "ve",
    "veya",
    "yani",
}
_FALLBACK_IPUCLARI = (
    "en basit haliyle bu parca",
    "gundelik dilde:",
    "once ana fikri yakala:",
    "bu parcanin ana fikri nedir?",
    "bu parcayi cok basit dille nasil anlatirsin?",
)
_ALANLAR = (
    "one_liner",
    "very_simple",
    "glossary",
    "steps",
    "examples",
    "trap",
    "mini_quiz",
)


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _kelimeler(text: str) -> list[str]:
    words = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]+", _norm_text(text))
    return [w.lower() for w in words if len(w) >= 3 and w.lower() not in _STOPWORDS]


def _ortak_kelime_sayisi(sol: str, sag: str) -> int:
    return len(set(_kelimeler(sol)) & set(_kelimeler(sag)))


def _liste_alanini_al(cikti: dict, alan: str) -> list:
    value = (cikti or {}).get(alan)
    return value if isinstance(value, list) else []


def _quiz_oge_listesi(cikti: dict) -> list[dict]:
    quiz = _liste_alanini_al(cikti, "mini_quiz")
    normalized: list[dict] = []
    for item in quiz:
        if isinstance(item, dict):
            q = _norm_text(item.get("q") or item.get("soru") or "")
            a = _norm_text(item.get("a") or item.get("cevap") or "")
            if q or a:
                normalized.append({"q": q, "a": a})
    return normalized


def alan_doluluk_skoru(cikti: dict, alan: str) -> int:
    if alan in {"glossary", "steps", "examples", "mini_quiz"}:
        return 1 if _liste_alanini_al(cikti, alan) else 0
    return 1 if _norm_text((cikti or {}).get(alan)) else 0


def glossary_kalite_skoru(cikti: dict, base_text: str) -> int:
    glossary = _liste_alanini_al(cikti, "glossary")
    if not glossary:
        return 0

    guclu = 0
    zayif = 0
    base_lower = _norm_text(base_text).lower()

    for item in glossary:
        if not isinstance(item, dict):
            continue
        term = _norm_text(item.get("terim") or item.get("term"))
        tanim = _norm_text(item.get("tanim") or item.get("definition"))
        if len(term) < 2 or len(tanim) < 10:
            continue
        zayif += 1
        if term.lower() in base_lower and len(tanim) >= 18:
            guclu += 1

    if guclu >= 2:
        return 3
    if guclu >= 1 or zayif >= 2:
        return 2
    if zayif >= 1:
        return 1
    return 0


def step_kalite_skoru(cikti: dict, base_text: str) -> int:
    steps = [_norm_text(x) for x in _liste_alanini_al(cikti, "steps") if _norm_text(x)]
    if not steps:
        return 0

    guclu = sum(1 for step in steps if len(step) >= 20 and _ortak_kelime_sayisi(step, base_text) >= 1)
    if guclu >= 3:
        return 3
    if guclu >= 2:
        return 2
    if guclu >= 1 or len(steps) >= 2:
        return 1
    return 0


def example_kalite_skoru(cikti: dict, base_text: str) -> int:
    examples = [_norm_text(x) for x in _liste_alanini_al(cikti, "examples") if _norm_text(x)]
    if not examples:
        return 0

    guclu = sum(1 for item in examples if len(item) >= 18 and _ortak_kelime_sayisi(item, base_text) >= 1)
    if guclu >= 2:
        return 3
    if guclu >= 1:
        return 2
    if len(examples) >= 1:
        return 1
    return 0


def trap_kalite_skoru(cikti: dict, base_text: str) -> int:
    trap = _norm_text((cikti or {}).get("trap"))
    if not trap:
        return 0
    if len(trap) >= 24 and _ortak_kelime_sayisi(trap, base_text) >= 1:
        return 2
    return 1


def mini_quiz_kalite_skoru(cikti: dict, base_text: str) -> int:
    quiz = _quiz_oge_listesi(cikti)
    if not quiz:
        return 0

    guclu = 0
    for item in quiz:
        if len(item["q"]) >= 10 and len(item["a"]) >= 10:
            if _ortak_kelime_sayisi(item["a"], base_text) >= 1:
                guclu += 1

    if len(quiz) >= 3 and guclu >= 3:
        return 3
    if len(quiz) >= 2 and guclu >= 2:
        return 2
    return 1


def dokumanda_yok_supheli_mi(cikti: dict, base_text: str) -> bool:
    if not _kelimeler(base_text):
        return False

    if bool((cikti or {}).get("dokumanda_yok")):
        return True

    one_liner = _norm_text((cikti or {}).get("one_liner")).lower()
    very_simple = _norm_text((cikti or {}).get("very_simple")).lower()
    return one_liner in {"dokumanda yok.", "dokumanda yok"} or very_simple in {"dokumanda yok.", "dokumanda yok"}


def parcaya_baglilik_skoru(cikti: dict, base_text: str) -> int:
    base_terms = set(_kelimeler(base_text))
    if not base_terms:
        return 0

    aday_metinler = [
        _norm_text((cikti or {}).get("one_liner")),
        _norm_text((cikti or {}).get("very_simple")),
        _norm_text((cikti or {}).get("trap")),
    ]
    aday_metinler.extend(_norm_text(x) for x in _liste_alanini_al(cikti, "steps"))
    aday_metinler.extend(_norm_text(x) for x in _liste_alanini_al(cikti, "examples"))
    aday_metinler.extend(_norm_text(item.get("tanim")) for item in _liste_alanini_al(cikti, "glossary") if isinstance(item, dict))
    aday_metinler.extend(_norm_text(item.get("a") or item.get("cevap")) for item in _quiz_oge_listesi(cikti))

    toplam_kesisim = len(base_terms & set().union(*[set(_kelimeler(text)) for text in aday_metinler if text]))
    bagli_alan_sayisi = sum(1 for text in aday_metinler if _ortak_kelime_sayisi(text, base_text) >= 1)

    if toplam_kesisim >= 6 or bagli_alan_sayisi >= 6:
        return 4
    if toplam_kesisim >= 4 or bagli_alan_sayisi >= 4:
        return 3
    if toplam_kesisim >= 2 or bagli_alan_sayisi >= 2:
        return 2
    if toplam_kesisim >= 1 or bagli_alan_sayisi >= 1:
        return 1
    return 0


def fallback_izi_var_mi(cikti: dict) -> bool:
    metinler = [
        _norm_text((cikti or {}).get("one_liner")),
        _norm_text((cikti or {}).get("very_simple")),
        _norm_text((cikti or {}).get("trap")),
        " ".join(_norm_text(x) for x in _liste_alanini_al(cikti, "steps")),
        " ".join(_norm_text(x) for x in _liste_alanini_al(cikti, "examples")),
        " ".join(_norm_text(json.dumps(x, ensure_ascii=False)) for x in _quiz_oge_listesi(cikti)),
    ]
    joined = " ".join(text.lower() for text in metinler if text)
    return any(ipucu in joined for ipucu in _FALLBACK_IPUCLARI)


def genel_kalite_ozeti(cikti: dict, base_text: str, ornek_adi: str = "") -> dict:
    cikti = cikti if isinstance(cikti, dict) else {}

    one_liner = _norm_text(cikti.get("one_liner"))
    very_simple = _norm_text(cikti.get("very_simple"))
    skorlar = {
        "one_liner": 0,
        "very_simple": 0,
        "glossary": glossary_kalite_skoru(cikti, base_text),
        "steps": step_kalite_skoru(cikti, base_text),
        "examples": example_kalite_skoru(cikti, base_text),
        "trap": trap_kalite_skoru(cikti, base_text),
        "mini_quiz": mini_quiz_kalite_skoru(cikti, base_text),
        "parcaya_baglilik": parcaya_baglilik_skoru(cikti, base_text),
    }

    if one_liner:
        skorlar["one_liner"] = 2 if len(one_liner) >= 16 and _ortak_kelime_sayisi(one_liner, base_text) >= 1 else 1

    if very_simple:
        if len(very_simple) >= 40 and _ortak_kelime_sayisi(very_simple, base_text) >= 2:
            skorlar["very_simple"] = 3
        elif len(very_simple) >= 24 and _ortak_kelime_sayisi(very_simple, base_text) >= 1:
            skorlar["very_simple"] = 2
        else:
            skorlar["very_simple"] = 1

    supheli_missing = dokumanda_yok_supheli_mi(cikti, base_text)
    supheli_ceza = -3 if supheli_missing else 0

    toplam = sum(skorlar.values()) + supheli_ceza
    max_toplam = 23
    yuzde = round((max(toplam, 0) / max_toplam) * 100, 1)

    uyarilar: list[str] = []
    if skorlar["one_liner"] <= 1:
        uyarilar.append("one_liner_zayif")
    if skorlar["very_simple"] <= 1:
        uyarilar.append("very_simple_zayif")
    if skorlar["glossary"] <= 1:
        uyarilar.append("glossary_zayif")
    if skorlar["steps"] <= 1:
        uyarilar.append("steps_zayif")
    if skorlar["examples"] <= 1:
        uyarilar.append("examples_zayif")
    if skorlar["trap"] <= 1:
        uyarilar.append("trap_zayif")
    if skorlar["mini_quiz"] <= 1:
        uyarilar.append("mini_quiz_zayif")
    if skorlar["parcaya_baglilik"] <= 1:
        uyarilar.append("parcaya_baglilik_zayif")
    if supheli_missing:
        uyarilar.append("supheli_dokumanda_yok")
    if fallback_izi_var_mi(cikti):
        uyarilar.append("fallback_izi")

    return {
        "ornek_adi": ornek_adi,
        "alan_doluluk": {alan: alan_doluluk_skoru(cikti, alan) for alan in _ALANLAR},
        "skorlar": skorlar,
        "supheli_dokumanda_yok_cezasi": supheli_ceza,
        "toplam_skor": toplam,
        "yuzde_skor": yuzde,
        "uyarilar": uyarilar,
        "fallback_izi": "fallback_izi" in uyarilar,
        "supheli_dokumanda_yok": supheli_missing,
    }


def benchmark_toplam_rapor(ornek_sonuclari: list[dict]) -> dict:
    tamamlanan = [item for item in ornek_sonuclari if isinstance(item, dict)]
    if not tamamlanan:
        return {
            "ornek_sonuclari": [],
            "alan_ortalamalari": {},
            "zayif_alanlar": [],
            "hata_sikliklari": {},
            "fallback_nedeni_sikliklari": {},
            "supheli_dokumanda_yok_sayisi": 0,
            "fallback_ile_kurtarilan_sayisi": 0,
            "genel_kalite_ozeti": "Hic benchmark sonucu yok.",
        }

    skor_alanlari = [
        "one_liner",
        "very_simple",
        "glossary",
        "steps",
        "examples",
        "trap",
        "mini_quiz",
        "parcaya_baglilik",
    ]
    alan_ortalamalari = {
        alan: round(mean(item.get("skorlar", {}).get(alan, 0) for item in tamamlanan), 2)
        for alan in skor_alanlari
    }
    zayif_alanlar = [alan for alan, ort in sorted(alan_ortalamalari.items(), key=lambda item: item[1]) if ort <= 1.5]

    hata_sayaci = Counter()
    for item in tamamlanan:
        hata_sayaci.update(item.get("uyarilar", []))

    toplam_ortalama = round(mean(item.get("toplam_skor", 0) for item in tamamlanan), 2)
    yuzde_ortalama = round(mean(item.get("yuzde_skor", 0.0) for item in tamamlanan), 1)

    return {
        "ornek_sonuclari": tamamlanan,
        "alan_ortalamalari": alan_ortalamalari,
        "zayif_alanlar": zayif_alanlar,
        "hata_sikliklari": dict(hata_sayaci),
        "fallback_nedeni_sikliklari": dict(
            Counter(
                str((item.get("debug_ai2") or {}).get("fallback_nedeni") or "").strip()
                for item in tamamlanan
                if str((item.get("debug_ai2") or {}).get("fallback_nedeni") or "").strip()
            )
        ),
        "supheli_dokumanda_yok_sayisi": sum(1 for item in tamamlanan if item.get("supheli_dokumanda_yok")),
        "fallback_ile_kurtarilan_sayisi": sum(1 for item in tamamlanan if item.get("fallback_izi")),
        "genel_kalite_ozeti": f"Ortalama kalite {toplam_ortalama}/23 (%{yuzde_ortalama}).",
    }


def okunur_benchmark_ozeti(rapor: dict) -> str:
    satirlar = []
    satirlar.append("Anlamadim Benchmark Ozeti")
    satirlar.append("=========================")
    satirlar.append(rapor.get("genel_kalite_ozeti", ""))
    satirlar.append("")
    satirlar.append("Alan Ortalamalari:")
    for alan, ort in (rapor.get("alan_ortalamalari") or {}).items():
        satirlar.append(f"- {alan}: {ort}")

    satirlar.append("")
    satirlar.append("En Zayif Alanlar:")
    zayif_alanlar = rapor.get("zayif_alanlar") or []
    if zayif_alanlar:
        for alan in zayif_alanlar:
            satirlar.append(f"- {alan}")
    else:
        satirlar.append("- yok")

    satirlar.append("")
    satirlar.append("Hata Tipleri:")
    hata_sikliklari = rapor.get("hata_sikliklari") or {}
    if hata_sikliklari:
        for hata, adet in sorted(hata_sikliklari.items(), key=lambda item: (-item[1], item[0])):
            satirlar.append(f"- {hata}: {adet}")
    else:
        satirlar.append("- yok")

    satirlar.append("")
    satirlar.append("Fallback Nedenleri:")
    fallback_nedenleri = rapor.get("fallback_nedeni_sikliklari") or {}
    if fallback_nedenleri:
        for hata, adet in sorted(fallback_nedenleri.items(), key=lambda item: (-item[1], item[0])):
            satirlar.append(f"- {hata}: {adet}")
    else:
        satirlar.append("- yok")

    satirlar.append("")
    satirlar.append(f"Supheli dokumanda_yok sayisi: {rapor.get('supheli_dokumanda_yok_sayisi', 0)}")
    satirlar.append(f"Fallback ile kurtarilan ornek sayisi: {rapor.get('fallback_ile_kurtarilan_sayisi', 0)}")
    satirlar.append("")
    satirlar.append("Ornek Bazli Skorlar:")
    for item in rapor.get("ornek_sonuclari") or []:
        satirlar.append(
            f"- {item.get('ornek_adi') or 'ornek'}: {item.get('toplam_skor', 0)}/23 (%{item.get('yuzde_skor', 0)})"
        )
    return "\n".join(satirlar).strip() + "\n"


def benchmark_ornekleri(mod: str = "smoke") -> list[dict]:
    tum_ornekler = [
        {
            "slug": "kisa_tanim",
            "baslik": "JWT",
            "paragraflar": [
                "JWT access token kullanicinin kimligini tasir ve API cagrilarinda dogrulama icin gonderilir.",
                "Refresh token ile suresi dolan access token yenilenir ve oturum akisi korunur.",
            ],
            "mesaj": "Bu parcayi cok basit anlat.",
        },
        {
            "slug": "kavramsal_aciklama",
            "baslik": "RAG Mantigi",
            "paragraflar": [
                "RAG yaklasimi once ilgili parcalari bulur, sonra sadece bu baglama dayanarak cevap uretir.",
                "Boylece modelin genel ezber yerine dokuman kanitlarina yakin kalmasi saglanir.",
            ],
            "mesaj": "Ana fikri ve tuzagi anlat.",
        },
        {
            "slug": "numarali_surec",
            "baslik": "1. Is Akisi",
            "paragraflar": [
                "Surec uc adimdan olusur: veri once toplanir, sonra temizlenir ve son olarak indekslenir.",
                "Her adim bir sonraki adimin dogru calismasi icin gerekli girisleri hazirlar.",
            ],
            "mesaj": "Adim adim anlat.",
        },
        {
            "slug": "terim_yogun_teknik",
            "baslik": "Teknik Terimler",
            "paragraflar": [
                "Embedding, retrieval, rerank ve citation sinyalleri birlikte kullanildiginda RAG kalitesi daha olculebilir hale gelir.",
                "Bu terimler ayni zamanda parcanin hangi kanitla cevaplandigini gosteren izlenebilirlik katmani olusturur.",
            ],
            "mesaj": "Terimleri ve ornekleri guclu ver.",
        },
        {
            "slug": "kisa_ama_anlamli",
            "baslik": "Ozet",
            "paragraflar": [
                "Cache ayni sonucu tekrar hesaplamadan daha hizli cevap vermeyi saglar.",
            ],
            "mesaj": "Kisa parcayi bile dokumanda yok sanmadan anlat.",
        },
        {
            "slug": "dokumanda_yok_sinir",
            "baslik": "Hatirlatma",
            "paragraflar": [
                "JWT token kullanicinin kimligini tasir ve kisa olsa da anlamli bir bilgi parcasi sunar.",
            ],
            "mesaj": "Bu kisa metni dokumanda yok demeden acikla.",
        },
    ]

    if str(mod or "").strip().lower() == "detailed":
        return tum_ornekler
    return tum_ornekler[:2]
