from __future__ import annotations
from datetime import timedelta
from django.utils import timezone
from dokuman.models import Parca, MetrikKaydi, KullaniciTercih
from dokuman.services.metric_store import guvenli_metrik_kaydi_olustur

def clamp(val: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    return max(min_val, min(val, max_val))

def build_boss_rush_panel_payload(doc) -> dict:
    """
    Boss Rush modu icin hazirlik durumunu hesaplar.
    Zorluk skoru 0.6 uzerinde olan parcalari aday olarak secer.
    """
    aday_parcalar = doc.parcalar.filter(zorluk_skoru__gte=0.60)
    aday_sayisi = aday_parcalar.count()
    
    ortalama_zorluk = 0.0
    if aday_sayisi > 0:
        ortalama_zorluk = sum(p.zorluk_skoru for p in aday_parcalar) / aday_sayisi

    # Formül: 3 aday varsa hazırdır, ancak skorlar oransal hesaplanır.
    hazirlik_skoru = clamp(aday_sayisi / 3.0)
    
    zorluk_bandi = "kolay"
    if ortalama_zorluk > 0.75:
        zorluk_bandi = "zor"
    elif ortalama_zorluk > 0.5:
        zorluk_bandi = "orta"

    return {
        "hazir_mi": hazirlik_skoru >= 1.0,
        "hazirlik_skoru": round(hazirlik_skoru, 2),
        "boss_adayi_sayisi": aday_sayisi,
        "tahmini_boss_rush_suresi_dk": max(1, aday_sayisi * 2),
        "zorluk_bandi": zorluk_bandi,
        "onerilen_baslangic": "simdi" if hazirlik_skoru >= 1.0 else "daha_fazla_oku"
    }

def build_weekly_progress_payload(user) -> dict:
    """
    Kullanicinin son 7 gunluk etkilesimlerinden haftalik gorev ilerlemesini cikarir.
    """
    bir_hafta_once = timezone.now() - timedelta(days=7)
    son_metrikler = MetrikKaydi.objects.filter(kullanici=user, created_at__gte=bir_hafta_once)
    
    quiz_sayisi = son_metrikler.filter(olay_turu="mini_quiz_sonuclandi").count()
    boss_sayisi = son_metrikler.filter(olay_turu="boss_deneme_tamamlandi").count()
    ozet_sayisi = son_metrikler.filter(olay_turu="study_summary_uretildi").count()

    hedefler = [
        {"kod": "quiz_hedefi", "hedef": 3, "mevcut": quiz_sayisi, "isim": "3 Mini Quiz Çöz"},
        {"kod": "boss_hedefi", "hedef": 1, "mevcut": boss_sayisi, "isim": "1 Boss Yen"},
        {"kod": "ozet_hedefi", "hedef": 2, "mevcut": ozet_sayisi, "isim": "2 Özet Çıkar"},
    ]

    tamamlananlar = 0
    toplam_oran = 0.0
    eksikler = []

    for h in hedefler:
        oran = clamp(h["mevcut"] / h["hedef"])
        toplam_oran += oran
        if oran >= 1.0:
            tamamlananlar += 1
        else:
            eksikler.append(h["isim"])

    haftalik_skor = clamp(toplam_oran / len(hedefler))

    return {
        "haftalik_gorevler": hedefler,
        "tamamlanan_gorev_sayisi": tamamlananlar,
        "tamamlanma_orani": round(haftalik_skor, 2),
        "sonraki_rozet": "Haftanın Bilgesi" if haftalik_skor >= 1.0 else "Öğrenci",
        "ne_eksik": eksikler,
        "haftalik_ilerleme_skoru": round(haftalik_skor, 2)
    }

def build_export_readiness_payload(doc) -> dict:
    """
    Dokumanin yapisal zenginligine bakarak hangi formatta export edilmeye hazir
    oldugunu hesaplar. Gercek export islemi yapmaz.
    """
    parcalar = doc.parcalar.all()
    chunk_count = len(parcalar)
    
    if chunk_count == 0:
        return {"pdf_hazirlik": 0.0, "docx_hazirlik": 0.0, "pptx_hazirlik": 0.0, "readme_hazirlik": 0.0, "onerilen_format": "yok", "eksik_bilesenler": ["icerik"]}

    quality_sum = sum(p.meta.get("quality_score", 0) for p in parcalar if isinstance(p.meta, dict))
    heading_sum = sum(p.meta.get("heading_score", 0) for p in parcalar if isinstance(p.meta, dict))
    table_count = sum(1 for p in parcalar if p.tur == "tablo")
    code_count = sum(1 for p in parcalar if p.tur == "kod")

    avg_quality = quality_sum / chunk_count
    avg_heading = heading_sum / chunk_count

    # Formuller (Phase 5 Mathematical Grounding)
    docx_score = clamp(0.4 * avg_quality + 0.4 * clamp(chunk_count / 15.0) + 0.2 * avg_heading)
    pptx_score = clamp(0.5 * avg_heading + 0.3 * avg_quality + 0.2 * clamp(table_count / 2.0))
    pdf_score = clamp(docx_score + 0.1) # PDF genelde DOCX'e yakındır ama standartdır
    readme_score = clamp(0.6 * clamp(code_count / 3.0) + 0.4 * avg_heading)

    skorlar = {
        "docx": round(docx_score, 2),
        "pptx": round(pptx_score, 2),
        "pdf": round(pdf_score, 2),
        "readme": round(readme_score, 2)
    }

    onerilen = max(skorlar, key=skorlar.get)
    
    eksikler = []
    if avg_heading < 0.3: eksikler.append("baslik_hiyerarsisi")
    if chunk_count < 5: eksikler.append("yetersiz_uzunluk")
    if table_count == 0 and pptx_score < 0.5: eksikler.append("gorsel_ve_tablo")

    return {
        "pdf_hazirlik": skorlar["pdf"],
        "docx_hazirlik": skorlar["docx"],
        "pptx_hazirlik": skorlar["pptx"],
        "readme_hazirlik": skorlar["readme"],
        "onerilen_format": onerilen if skorlar[onerilen] > 0.4 else "yok",
        "eksik_bilesenler": eksikler
    }

def build_personalization_confidence_payload(user) -> dict:
    """
    Kullanicinin mevcut ayarlari ile onerilen ayarlari arasindaki guveni hesaplar.
    """
    tercih = KullaniciTercih.objects.filter(kullanici=user).first()
    aktif_tema = tercih.tema if tercih else "genel"
    aktif_ton = tercih.ton if tercih else "standart"

    # Şimdilik statik bir kural tabanlı confidence. (İleride override geçmişine bakılabilir).
    # Sistemin kullanımına dair agresif öneri spam'ini engellemek için baz skor 0.45'ten başlar.
    is_default = (aktif_tema == "genel" and aktif_ton == "standart")
    confidence = 0.85 if is_default else 0.45

    return {
        "aktif_tema": aktif_tema,
        "aktif_ton": aktif_ton,
        "onerilen_tema": "oyun" if is_default else aktif_tema,
        "onerilen_ton": "kanka" if is_default else aktif_ton,
        "personalization_confidence": confidence,
        "neden_bu_oneri": "sistemi_daha_etkili_kullanmak_icin" if is_default else "mevcut_secim_yeterli"
    }