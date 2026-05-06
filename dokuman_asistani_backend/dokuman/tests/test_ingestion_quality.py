from types import SimpleNamespace

from dokuman.parcalama import chunk_text


def parca(metin: str, baslik: str = "", icerik_uzunlugu: int = 0, adres: str = "1"):
    return SimpleNamespace(
        metin=metin,
        adres=adres,
        meta={
            "baslik": baslik,
            "icerik_uzunlugu": icerik_uzunlugu,
        },
    )


def ingestion_modulu():
    from dokuman.services import ingestion

    return ingestion


def ingestion_contract_modulu():
    from dokuman.services import ingestion_contract

    return ingestion_contract


def test_kisa_ama_gercek_icerik_parcasi_kabul_edilir():
    ingestion = ingestion_modulu()
    assert ingestion._is_meaningful_chunk("Net bir aciklama.") is True


def test_baslik_only_parca_hala_elenir():
    ingestion = ingestion_modulu()
    assert ingestion._is_meaningful_chunk("Giris") is False
    assert ingestion._has_meaningful_content(parca("Giris", baslik="Giris", icerik_uzunlugu=0)) is False


def test_kisa_ama_gercek_icerikli_bolumler_kaliteyi_gecebilir():
    ingestion = ingestion_modulu()
    bulk = [
        parca("1. Giris Kisa ama gercek bilgi var.", baslik="1. Giris", icerik_uzunlugu=25, adres="1"),
        parca("2. Amac Ozet ama anlamli bir aciklama.", baslik="2. Amac", icerik_uzunlugu=29, adres="2"),
        parca("3. Yontem Son derece kisa ama gercek icerik.", baslik="3. Yontem", icerik_uzunlugu=33, adres="3"),
    ]

    kalite_ok, hata = ingestion._validate_bulk_quality(bulk, {"section_count": 3}, 10)

    assert kalite_ok is True
    assert hata == ""


def test_meta_benzeri_kisa_icerik_hala_elenir():
    ingestion = ingestion_modulu()
    sahte = parca(
        "1. Imza Tarih: 2024-01-01",
        baslik="1. Imza",
        icerik_uzunlugu=17,
    )

    assert ingestion._has_meaningful_content(sahte) is False


def test_cok_kisa_ama_iki_anlamli_parca_kaliteyi_gecebilir():
    ingestion = ingestion_modulu()
    bulk = [
        parca("1. Giris Net bir aciklama.", baslik="1. Giris", icerik_uzunlugu=17, adres="1"),
        parca("2. Sonuc Somut bir sonuc var.", baslik="2. Sonuc", icerik_uzunlugu=19, adres="2"),
    ]

    kalite_ok, hata = ingestion._validate_bulk_quality(bulk, {"section_count": 2}, 10)

    assert kalite_ok is True
    assert hata == ""


def test_tekrar_eden_adresler_kalite_hatasi_uretir():
    ingestion = ingestion_modulu()
    bulk = [
        parca("1. Giris Kisa ama gercek bilgi var.", baslik="1. Giris", icerik_uzunlugu=25, adres="1"),
        parca("2. Amac Ozet ama anlamli bir aciklama.", baslik="2. Amac", icerik_uzunlugu=29, adres="1"),
    ]

    kalite_ok, hata = ingestion._validate_bulk_quality(bulk, {"section_count": 2}, 10)

    assert kalite_ok is False
    assert "adres" in hata.lower()


def test_parser_bolum_cikarip_ingestion_hepsini_elerse_neden_gorunur():
    ingestion = ingestion_modulu()

    kalite_ok, hata = ingestion._validate_bulk_quality([], {"section_count": 2}, 10)

    assert kalite_ok is False
    assert "kalite filtresi" in hata.lower()
    assert "eledi" in hata.lower()


def test_short_valid_icerik_quality_gate_korunur():
    ingestion = ingestion_modulu()

    analiz = ingestion._quality_score_analizi(
        "Skor = dogru / toplam",
        baslik="Tanim",
        icerik_uzunlugu=18,
    )

    assert analiz["gate_ok"] is True
    assert analiz["short_valid"] is True
    assert analiz["quality_score"] >= 0.42


def test_quality_score_uses_word_count_and_alpha_ratio_formula():
    ingestion = ingestion_modulu()

    analiz = ingestion._quality_score_analizi(
        "Alfa beta gamma delta epsilon zeta eta theta iota kappa",
        icerik_uzunlugu=54,
    )

    assert 0.40 <= analiz["quality_score"] <= 0.55
    assert analiz["weak_content"] is False
    assert analiz["gate_ok"] is True


def test_gurultulu_ve_bos_icerik_quality_olarak_zayif_isaretlenir():
    ingestion = ingestion_modulu()

    bos = ingestion._quality_score_analizi("")
    gurultu = ingestion._quality_score_analizi("Tarih: 2024-01-01")

    assert bos["weak_content"] is True
    assert bos["quality_reason"] == "empty_content"
    assert bos["gate_ok"] is False
    assert gurultu["weak_content"] is True
    assert gurultu["quality_reason"] == "signature_or_meta"
    assert gurultu["gate_ok"] is False


def test_quality_meta_advisory_bilgisi_bulkte_tasinabilir():
    ingestion = ingestion_modulu()
    parca_ornegi = parca(
        "1. Amac API tokeni yenilenir.",
        baslik="1. Amac",
        icerik_uzunlugu=24,
        adres="1",
    )
    analiz = ingestion._quality_score_analizi(
        ingestion._extract_content_candidate(parca_ornegi),
        baslik="1. Amac",
        icerik_uzunlugu=24,
    )

    assert "quality_score" in analiz
    assert "quality_reason" in analiz
    assert "quality_advisory" in analiz
    assert analiz["quality_reason"] in {"short_valid_content", "contentful"}


def test_difficulty_score_meta_yazilabilir():
    ingestion = ingestion_modulu()
    analiz = ingestion._difficulty_score_analizi(
        "Bu formulde JWT_REFRESH_TOKEN suresi doldugunda access token yeniden uretilir ve sistem HMAC-SHA256 kullanabilir."
    )

    assert "difficulty_score" in analiz
    assert "difficulty_reason" in analiz
    assert 0.0 <= analiz["difficulty_score"] <= 1.0


def test_cheatsheet_priority_teknik_kisa_parcada_yuksek_olur():
    from dokuman.services.phase2_scores import analyze_cheatsheet_priority

    analiz = analyze_cheatsheet_priority("Excel'de XLOOKUP kullanimi: =XLOOKUP(A1; B:B; C:C)")

    assert analiz["cheatsheet_priority_score"] >= 0.70
    assert analiz["is_cheatsheet"] is True


def test_chunk_text_near_boundary_prefers_forward_sentence_end():
    text = ("A" * 1185) + " anlamli cumle burada biter. Sonraki cumle de devam eder."

    spans = chunk_text(text, chunk_char=1200, overlap=50)

    assert len(spans) >= 2
    first_chunk = text[spans[0][0]:spans[0][1]]
    assert first_chunk.endswith(". ")


def test_chunk_text_keeps_overlap_when_no_semantic_boundary_exists():
    text = "x" * 2600

    spans = chunk_text(text, chunk_char=1200, overlap=150)

    assert len(spans) == 3
    assert spans[0] == (0, 1200)
    assert spans[1][0] == 1050
    assert spans[1][1] == 2250


def test_ingestion_contract_sets_quality_gate_failed_reason():
    ingestion_contract = ingestion_contract_modulu()

    sonuc = ingestion_contract.ingestion_sonucu_uret(
        kaynak_turu="heading_parser",
        mime="application/pdf",
        aday_parca_sayisi=3,
        kaydedilen_parca_sayisi=0,
        kalite_durumu="hata",
    )

    assert sonuc["durum_nedeni"] == "quality_gate_failed"
    assert sonuc["durum_gecisi"] == "hata"


def test_ingestion_contract_sets_no_candidate_chunks_reason():
    ingestion_contract = ingestion_contract_modulu()

    sonuc = ingestion_contract.ingestion_sonucu_uret(
        kaynak_turu="heading_parser",
        mime="application/pdf",
        aday_parca_sayisi=0,
        kaydedilen_parca_sayisi=0,
        kalite_durumu="ok",
    )

    assert sonuc["durum_nedeni"] == "no_candidate_chunks"
    assert sonuc["durum_gecisi"] == "hata"


def test_ingestion_contract_sets_zero_saved_after_bulk_reason():
    ingestion_contract = ingestion_contract_modulu()

    sonuc = ingestion_contract.ingestion_sonucu_uret(
        kaynak_turu="heading_parser",
        mime="application/pdf",
        aday_parca_sayisi=4,
        kaydedilen_parca_sayisi=0,
        kalite_durumu="ok",
    )

    assert sonuc["durum_nedeni"] == "zero_saved_after_bulk"
    assert sonuc["durum_gecisi"] == "hata"


def test_ingestion_contract_sets_partial_persistence_reason():
    ingestion_contract = ingestion_contract_modulu()

    sonuc = ingestion_contract.ingestion_sonucu_uret(
        kaynak_turu="heading_parser",
        mime="application/pdf",
        aday_parca_sayisi=5,
        kaydedilen_parca_sayisi=3,
        kalite_durumu="ok",
    )

    assert sonuc["durum_nedeni"] == "partial_persistence"
    assert sonuc["durum_gecisi"] == "hata"


def test_ingestion_contract_sets_ok_reason_on_full_success():
    ingestion_contract = ingestion_contract_modulu()

    sonuc = ingestion_contract.ingestion_sonucu_uret(
        kaynak_turu="heading_parser",
        mime="application/pdf",
        aday_parca_sayisi=2,
        kaydedilen_parca_sayisi=2,
        kalite_durumu="ok",
    )

    assert sonuc["durum_nedeni"] == "ok"
    assert sonuc["durum_gecisi"] == "parcalandi"
