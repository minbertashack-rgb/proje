VARLIK_HAVUZU = {
    "pdf_numarali_belge": {
        "tur": "pdf",
        "dosya_adi": "pdf_numarali_belge.pdf",
        "ogeler": [
            {
                "tur": "paragraf",
                "metin": "Belge giris metni bu dokumanin amacini ve genel cercevesini aciklar.",
            },
            {"tur": "baslik", "metin": "1. Giris", "seviye": 1},
            {
                "tur": "paragraf",
                "metin": "Giris bolumu sistemin neyi cozdugunu ve neden gerekli oldugunu anlatir.",
            },
            {"tur": "baslik", "metin": "1.1 Amac", "seviye": 2},
            {
                "tur": "paragraf",
                "metin": "Amac kisminin iceriginde olculebilir hedefler ve kullanim beklentileri yer alir.",
            },
            {"tur": "baslik", "metin": "1.2 Kapsam", "seviye": 2},
            {
                "tur": "paragraf",
                "metin": "Kapsam bolumu hangi adimlarin bu dokumana dahil oldugunu netlestirir.",
            },
            {"tur": "baslik", "metin": "2. Yontem", "seviye": 1},
            {
                "tur": "paragraf",
                "metin": "Yontem bolumu veri toplama ve analiz akisinin ana hatlarini ozetler.",
            },
        ],
        "beklenen_basliklar": [
            "Belge Başlangıcı",
            "1. Giris",
            "1.1 Amac",
            "1.2 Kapsam",
            "2. Yontem",
        ],
        "beklenen_pathler": ["0", "1", "1.1", "1.2", "2"],
        "beklenen_parca_sayisi": 5,
    },
    "pdf_buyuk_harf_paragraf": {
        "tur": "pdf",
        "dosya_adi": "pdf_buyuk_harf_paragraf.pdf",
        "ogeler": [
            {
                "tur": "paragraf",
                "metin": "BU BOLUMDE SISTEMIN NASIL CALISTIGI DETAYLI OLARAK ANLATILMAKTADIR.",
            },
            {"tur": "baslik", "metin": "1. Yontem", "seviye": 1},
            {
                "tur": "paragraf",
                "metin": "Yontem bolumu ana adimlari ve veri akisindaki temel karar noktalari aciklar.",
            },
        ],
        "beklenen_basliklar": ["Belge Başlangıcı", "1. Yontem"],
        "maks_section_sayisi": 2,
    },
    "docx_kisa_gercek_basliklar": {
        "tur": "docx",
        "dosya_adi": "docx_kisa_gercek_basliklar.docx",
        "ogeler": [
            {"tur": "baslik", "metin": "Özet", "seviye": 1, "yazi_boyutu": 15, "kalin": True},
            {
                "tur": "paragraf",
                "metin": "Özet bölümü dokümanın temel fikrini kısa ama anlamlı şekilde sunar.",
            },
            {"tur": "baslik", "metin": "Sonuç", "seviye": 1, "yazi_boyutu": 15, "kalin": True},
            {
                "tur": "paragraf",
                "metin": "Sonuç bölümü karar ve çıkarımları toplu halde verir.",
            },
            {"tur": "baslik", "metin": "Ek A: Veri Seti", "seviye": 1, "yazi_boyutu": 15, "kalin": True},
            {
                "tur": "paragraf",
                "metin": "Ek bölümü veri setinin kolonlarını ve kaynak bilgisini açıklar.",
            },
        ],
        "beklenen_basliklar": ["Özet", "Sonuç", "Ek A: Veri Seti"],
        "beklenen_pathler": ["1", "2", "3"],
    },
    "docx_karma_duzen": {
        "tur": "docx",
        "dosya_adi": "docx_karma_duzen.docx",
        "ogeler": [
            {"tur": "baslik", "metin": "Özet", "seviye": 1, "yazi_boyutu": 15, "kalin": True},
            {
                "tur": "paragraf",
                "metin": "İlk paragraf konuya hızlı bir giriş yapar ve temel problemi tanımlar.",
            },
            {
                "tur": "paragraf",
                "metin": "İkinci paragraf kullanıcının neden bu akışla çalıştığını daha net biçimde açıklar.",
            },
            {"tur": "baslik", "metin": "Yöntem", "seviye": 1, "stil_baslik": True},
            {
                "tur": "paragraf",
                "metin": "Yöntem bölümü veri toplama, temizleme ve değerlendirme adımlarını birlikte anlatır.",
            },
            {
                "tur": "paragraf",
                "metin": "Ek paragraf, bölüm içindeki ayrıntıları korur ama yeni bir section patlaması yaratmaz.",
            },
            {"tur": "baslik", "metin": "Alt Notlar", "seviye": 2, "yazi_boyutu": 14, "kalin": True},
            {
                "tur": "paragraf",
                "metin": "Notlar kısmı ana yöntemin altında kalan kısa ama anlamlı bir açıklama sağlar.",
            },
        ],
        "beklenen_basliklar": ["Özet", "Yöntem", "Alt Notlar"],
        "beklenen_pathler": ["1", "2", "2.1"],
        "beklenen_parca_sayisi": 3,
    },
    "docx_ozel_baslik_caps_tuzagi": {
        "tur": "docx",
        "dosya_adi": "docx_ozel_baslik_caps_tuzagi.docx",
        "ogeler": [
            {"tur": "baslik", "metin": "Giriş", "seviye": 1, "yazi_boyutu": 15, "kalin": True},
            {
                "tur": "paragraf",
                "metin": "İlk paragraf belge yapısını tanımlar ve ana problemi kısa biçimde açıklar.",
            },
            {
                "tur": "paragraf",
                "metin": "AMA VE KAPSAM BU BELGENIN TEMEL HEDEFLERINI ACIKLAR",
                "yazi_boyutu": 13,
                "kalin": True,
            },
            {
                "tur": "paragraf",
                "metin": "Bu satır aynı bölüm gövdesinin devamı olmalı ve gereksiz yeni section oluşturmamalıdır.",
            },
            {"tur": "baslik", "metin": "Alt Notlar", "seviye": 2, "yazi_boyutu": 14, "kalin": False},
            {
                "tur": "paragraf",
                "metin": "Alt notlar kısmı kısa ama gerçek bir alt başlığı temsil eder ve içerik taşır.",
            },
            {"tur": "baslik", "metin": "EK B", "seviye": 1, "yazi_boyutu": 15, "kalin": True},
            {
                "tur": "paragraf",
                "metin": "Ek bölümü veri dosyalarının ikinci kümesini kısa biçimde özetler.",
            },
        ],
        "beklenen_basliklar": ["Giriş", "Alt Notlar", "EK B"],
        "beklenen_pathler": ["1", "1.1", "2"],
    },
    "docx_kisa_anlamli_bolumler": {
        "tur": "docx",
        "dosya_adi": "docx_kisa_anlamli_bolumler.docx",
        "ogeler": [
            {"tur": "baslik", "metin": "Giris", "seviye": 1, "yazi_boyutu": 15, "kalin": True},
            {"tur": "paragraf", "metin": "Net bir aciklama."},
            {"tur": "baslik", "metin": "Sonuc", "seviye": 1, "yazi_boyutu": 15, "kalin": True},
            {"tur": "paragraf", "metin": "Somut bir sonuc var."},
        ],
        "beklenen_basliklar": ["Giris", "Sonuc"],
        "beklenen_pathler": ["1", "2"],
        "beklenen_parca_sayisi": 2,
    },
    "docx_kurumsal_stilize_kenar": {
        "tur": "docx",
        "dosya_adi": "docx_kurumsal_stilize_kenar.docx",
        "ogeler": [
            {"tur": "baslik", "metin": "Giris", "seviye": 1, "yazi_boyutu": 16, "kalin": True},
            {"tur": "paragraf", "metin": "Kurumsal belge acilisi sistemin genel cercevesini ozetler."},
            {
                "tur": "paragraf",
                "metin": "OPERASYONEL RISK VE KONTROL AKISI BU SATIRDA NORMAL ACIKLAMA OLARAK VERILIR",
                "yazi_boyutu": 13,
                "kalin": True,
            },
            {"tur": "paragraf", "metin": "Bu satir ayni bolum govdesinin devami olmali ve yeni section olmamali."},
            {"tur": "baslik", "metin": "Degerlendirme", "seviye": 1, "yazi_boyutu": 15, "kalin": True},
            {"tur": "paragraf", "metin": "Degerlendirme bolumu risklerin nasil yorumlanacagini anlatir."},
        ],
        "beklenen_basliklar": ["Giris", "Degerlendirme"],
        "beklenen_pathler": ["1", "2"],
        "beklenen_parca_sayisi": 2,
    },
    "docx_zayif_icerik": {
        "tur": "docx",
        "dosya_adi": "docx_zayif_icerik.docx",
        "ogeler": [
            {"tur": "paragraf", "metin": "İmza"},
            {"tur": "paragraf", "metin": "Tarih: 2024-01-01"},
            {"tur": "paragraf", "metin": "Not"},
        ],
        "beklenen_basliklar": ["Belge Başlangıcı"],
        "beklenen_durum": "hata",
    },
}
