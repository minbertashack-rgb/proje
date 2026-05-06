from __future__ import annotations

import json

from django.core.files.base import ContentFile
from django.test import override_settings
from rest_framework.test import APIClient

from dokuman.ai2.validators import extract_json
from dokuman.models import Dokuman, Parca
from dokuman.views import (
    _anlamadim_merge_quiz,
    _anlamadim_should_mark_missing,
    _fallback_sections_v2,
    _merge_with_fallback_v2,
)
from .anlamadim_yardimcilari import (
    benchmark_toplam_rapor,
    dokumanda_yok_supheli_mi,
    genel_kalite_ozeti,
    mini_quiz_kalite_skoru,
    okunur_benchmark_ozeti,
)


def test_fallback_sections_v2_produces_grounded_fields():
    text = (
        "JWT access token kullanicinin kimligini tasir. "
        "Refresh token ile suresi dolan access token yenilenir. "
        "Bu akis kimlik dogrulama tarafinda kritik bir guvenlik adimidir."
    )

    out = _fallback_sections_v2(text, "genel", "adim_adim", "baslangic")

    assert len(out["one_liner"]) >= 20
    assert "JWT" in out["very_simple"]
    assert len(out["glossary"]) >= 1
    assert len(out["steps"]) >= 3
    assert len(out["examples"]) >= 2
    assert len(out["mini_quiz"]) == 3


def test_merge_with_fallback_v2_strengthens_weak_llm_output():
    text = (
        "API istemcisi once access token gonderir. "
        "Token gecersizse refresh token ile yeni access token alinir. "
        "Bu sayede kullanici yeniden giris yapmadan oturumu surdurur."
    )
    weak = {
        "one_liner": "Bu parca basitce sunu soyluyor.",
        "very_simple": "",
        "glossary": [{"terim": "API", "tanim": "Metindeki teknik terim/kisaltma."}],
        "steps": [""],
        "examples": [],
        "trap": "",
        "mini_quiz": [{"q": "Nedir?", "a": ""}],
    }

    merged = _merge_with_fallback_v2(weak, text, "genel", "adim_adim", "baslangic")

    assert "Bu parca basitce sunu soyluyor" not in merged["one_liner"]
    assert len(merged["very_simple"]) >= 20
    assert len(merged["glossary"]) >= 1
    assert all(len(item["tanim"]) >= 12 for item in merged["glossary"])
    assert len(merged["steps"]) >= 3
    assert len(merged["examples"]) >= 2
    assert len(merged["mini_quiz"]) == 3


def test_should_mark_missing_only_for_meaningless_text():
    parsed = _fallback_sections_v2(
        "JWT token kullanicinin kimligini tasir ve refresh token ile yenilenir.",
        "genel",
        "adim_adim",
        "baslangic",
    )

    assert _anlamadim_should_mark_missing(
        {"dokumanda_yok": True},
        parsed,
        "JWT token kullanicinin kimligini tasir ve refresh token ile yenilenir.",
        '{"dokumanda_yok": true}',
    ) is False

    assert _anlamadim_should_mark_missing(
        {"dokumanda_yok": True},
        {},
        "Dijital olarak imzalayan Kisi Tarih: 2024-01-01",
        '{"dokumanda_yok": true}',
    ) is True


def test_should_not_mark_missing_for_short_but_meaningful_piece():
    parsed = _fallback_sections_v2("JWT dogrulama zorunludur.", "genel", "adim_adim", "baslangic")

    assert _anlamadim_should_mark_missing(
        {"dokumanda_yok": True},
        parsed,
        "JWT dogrulama zorunludur.",
        '{"dokumanda_yok": true}',
    ) is False


def test_should_not_mark_missing_for_short_acronym_note():
    parsed = _fallback_sections_v2("JWT zorunlu.", "genel", "adim_adim", "baslangic")

    assert _anlamadim_should_mark_missing(
        {"dokumanda_yok": True},
        parsed,
        "JWT zorunlu.",
        '{"dokumanda_yok": true}',
    ) is False


def test_should_not_mark_missing_for_clipped_but_technical_note():
    parsed = _fallback_sections_v2("API anahtari gizli tutulur...", "genel", "adim_adim", "baslangic")

    assert _anlamadim_should_mark_missing(
        {"dokumanda_yok": True},
        parsed,
        "API anahtari gizli tutulur...",
        '{"dokumanda_yok": true}',
    ) is False


def test_should_not_mark_missing_for_short_technical_definition():
    parsed = _fallback_sections_v2("TTL onbellek suresidir.", "genel", "adim_adim", "baslangic")

    assert _anlamadim_should_mark_missing(
        {"dokumanda_yok": True},
        parsed,
        "TTL onbellek suresidir.",
        '{"dokumanda_yok": true}',
    ) is False


def test_short_technical_label_gets_concrete_glossary_and_summary():
    out = _fallback_sections_v2("Excel | IF | XLOOKUP", "genel", "adim_adim", "baslangic")

    assert len(out["one_liner"]) >= 20
    assert len(out["glossary"]) >= 2
    assert any(item["terim"] == "IF" for item in out["glossary"])
    assert any(item["terim"] == "XLOOKUP" for item in out["glossary"])
    assert "Excel" in out["very_simple"]
    assert "XLOOKUP" in out["very_simple"]


def test_numeric_table_row_gets_table_specific_fallback():
    out = _fallback_sections_v2("100 | 200 | 300", "genel", "adim_adim", "baslangic")

    assert "kesin degil" in out["one_liner"].lower()
    assert "100, 200, 300" in out["very_simple"]
    assert "sutun basliklari" in out["very_simple"].lower()
    assert any(item["terim"] == "sayisal deger" for item in out["glossary"])
    assert any("tahmin edilmemeli" in item.lower() for item in out["examples"])


def test_column_header_row_gets_label_specific_fallback():
    out = _fallback_sections_v2("SUTUN_A | SUTUN_B | SUTUN_C", "genel", "adim_adim", "baslangic")

    assert "sutun etiketlerini" in out["one_liner"].lower()
    assert "SUTUN_A" in out["very_simple"]
    assert "SUTUN_B" in out["very_simple"]
    assert len(out["glossary"]) >= 2
    assert any("sutun etiketi" in item["tanim"].lower() for item in out["glossary"])


def test_short_technical_note_gets_grounded_very_simple():
    out = _fallback_sections_v2(
        "RLS, JWT, API Gateway gibi terimler gecsin. SQL: SELECT * FROM users WHERE id=1;",
        "genel",
        "adim_adim",
        "baslangic",
    )

    assert "SQL sorgusu" in out["very_simple"]
    assert "RLS" in out["very_simple"]


def test_clipped_meaningful_note_gets_less_round_very_simple():
    out = _fallback_sections_v2("API anahtari gizli tutulur...", "genel", "adim_adim", "baslangic")

    assert "API" in out["very_simple"]
    assert "kirpilmis" in out["very_simple"].lower() or "teknik bir not" in out["very_simple"].lower()


def test_merge_with_string_fields_repairs_partial_json_payload():
    text = "Excel | IF | XLOOKUP"
    weak = {
        "one_liner": "Excel IF XLOOKUP",
        "very_simple": "",
        "glossary": "IF: Kosula gore sonuc ureten Excel fonksiyonu.\nXLOOKUP: Aranan degeri tabloda bulur.",
        "steps": "1) Terimleri ayir\n2) Ne yaptiklarini dusun",
        "examples": "Bu satir, Excel notundaki temel araclari listeler.",
        "trap": "",
        "mini_quiz": "Q: IF ne yapar?\nA: Kosula gore sonuc uretir.",
    }

    merged = _merge_with_fallback_v2(weak, text, "genel", "adim_adim", "baslangic")

    assert len(merged["glossary"]) >= 2
    assert len(merged["steps"]) >= 2
    assert len(merged["examples"]) >= 1
    assert len(merged["mini_quiz"]) == 3
    assert any(item["terim"] == "IF" for item in merged["glossary"])


def test_merge_yeterli_model_alanlarini_gereksiz_buyutmez():
    text = (
        "JWT access token kullanicinin kimligini tasir. "
        "Refresh token ile suresi dolan access token yenilenir."
    )
    strong = {
        "one_liner": "JWT access token kimligi tasir, refresh token ise yenileme yapar.",
        "very_simple": "Sistem once access token ile kim oldugunu anlar, sure bitince refresh token ile yeni token alir.",
        "glossary": [
            {"terim": "JWT", "tanim": "Kimlik bilgisini tasiyan token yapisidir."},
            {"terim": "Refresh token", "tanim": "Access token suresi dolunca yeni token almaya yarar."},
        ],
        "steps": [
            "Once access token gonderilir.",
            "Sonra sure biterse refresh token kullanilir.",
        ],
        "examples": [
            "API isteginde access token gonderilir, sonra yenileme gerekir.",
        ],
        "trap": "Tuzak: access token ile refresh tokeni ayni is icin sanmak.",
        "mini_quiz": [
            {"q": "JWT ne tasir?", "a": "JWT kimlik bilgisini tasir."},
            {"q": "Refresh token ne zaman kullanilir?", "a": "Access token suresi doldugunda kullanilir."},
            {"q": "Bu akisin tuzagi nedir?", "a": "Iki tokeni ayni rol sanmaktir."},
        ],
    }

    merged = _merge_with_fallback_v2(strong, text, "genel", "adim_adim", "baslangic")

    assert len(merged["glossary"]) == 2
    assert len(merged["steps"]) == 2
    assert len(merged["examples"]) == 1
    assert len(merged["mini_quiz"]) == 3


def test_merge_replaces_vague_very_simple_with_grounded_fallback():
    text = "RLS, JWT, API Gateway gibi terimler gecsin. SQL: SELECT * FROM users WHERE id=1;"
    weak = {
        "one_liner": "Bu parca teknik terimler ve bir SQL sorgusu iceriyor.",
        "very_simple": "Bu metinde bazi teknik kelimeler var.",
        "glossary": [{"terim": "RLS", "tanim": "RLS, satir bazinda erisim kontrolu saglar."}],
        "steps": ["Teknik terimleri ayir.", "Sorguyu fark et."],
        "examples": ["Bu satirda teknik etiketler var."],
        "trap": "Tuzak: terimleri karistirmak.",
        "mini_quiz": [{"q": "Ne var?", "a": "Terimler var."}],
    }

    merged = _merge_with_fallback_v2(weak, text, "genel", "adim_adim", "baslangic")

    assert "SQL sorgusu" in merged["very_simple"]
    assert "RLS" in merged["very_simple"]


def test_merge_quiz_single_term_and_single_question_still_completes():
    out = _anlamadim_merge_quiz(
        [{"q": "Ne var?", "a": "Terimler var."}],
        [],
        "RLS ve JWT birlikte geciyor.",
        "Bu parca RLS ve JWT kavramlarini birlikte acikliyor.",
        [{"terim": "RLS", "tanim": "RLS satir bazinda erisim kontrolu saglar."}],
        ["RLS terimini fark et.", "JWT ile farkini ayir."],
    )

    assert len(out) == 3
    assert len({item["q"] for item in out}) == 3


def test_extract_json_repairs_prefix_suffix_and_missing_brace():
    raw = 'Model cevabi basliyor {"one_liner":"JWT kimligi tasir","steps":["Tokeni gonder","Sureyi kontrol et"]'

    out = extract_json(raw)

    assert isinstance(out, dict)
    assert out["one_liner"] == "JWT kimligi tasir"
    assert out["steps"] == ["Tokeni gonder", "Sureyi kontrol et"]


def test_extract_json_repairs_fenced_json_and_trailing_comma():
    raw = """```json
    {
      "one_liner": "Cache tekrar hesaplamayi azaltir",
      "glossary": [
        {"terim": "Cache", "tanim": "Ayni sonucun tekrar kullanilmasi."},
      ],
    }
    ```"""

    out = extract_json(raw)

    assert isinstance(out, dict)
    assert out["one_liner"].startswith("Cache")
    assert isinstance(out["glossary"], list)
    assert out["glossary"][0]["terim"] == "Cache"


def test_extract_json_salvages_markdown_mixed_fields():
    raw = """
    one_liner: JWT kimligi tasir.
    very_simple: JWT kullanicinin kim oldugunu gosteren kisa bilettir.
    glossary:
    - JWT: Kimlik bilgisini tasiyan token yapisidir.
    - API: Servislerin nasil konusacagini anlatan arayuzdur.
    steps:
    1) JWT terimini fark et
    2) Bunun kimlik amacli oldugunu anla
    examples:
    - API isteginde JWT gonderilir.
    trap: JWT ile sifreyi ayni sey sanmak.
    mini_quiz:
    Q: JWT ne tasir?
    A: Kimlik bilgisini tasir.
    dokumanda_yok: false
    """

    out = extract_json(raw)

    assert isinstance(out, dict)
    assert out["one_liner"] == "JWT kimligi tasir."
    assert "JWT" in out["very_simple"]
    assert len(out["glossary"]) >= 2
    assert len(out["steps"]) >= 2
    assert len(out["examples"]) >= 1
    assert len(out["mini_quiz"]) >= 1
    assert out["dokumanda_yok"] is False


def test_extract_json_salvages_half_json_half_plain_text():
    raw = """
    {
      "one_liner": "RLS satir bazinda erisimi sinirlar",
      "very_simple": "RLS her kullanicinin sadece izinli satirlari gormesini saglar",
      "glossary": "- RLS: Satir bazinda erisim kontrolu.",
      "steps": "1) Kural uygula\n2) Satiri filtrele",
      "examples": "- Kullanicinin sadece kendi kaydini gormesi",
      "trap": "Tum satirlari herkese acmak",
      mini_quiz:
      Q: RLS neyi sinirlar?
      A: Satir erisimini.
    """

    out = extract_json(raw)

    assert isinstance(out, dict)
    assert out["one_liner"].startswith("RLS")
    assert "RLS" in out["very_simple"]
    assert len(out["glossary"]) >= 1
    assert len(out["steps"]) >= 2
    assert len(out["examples"]) >= 1
    assert len(out["mini_quiz"]) >= 1


def test_genel_kalite_ozeti_guclu_ciktiyi_yuksek_skorlar():
    text = (
        "JWT access token kullanicinin kimligini tasir. "
        "Refresh token ile suresi dolan access token yenilenir. "
        "Bu akis oturumun kesilmeden devam etmesini saglar."
    )
    payload = {
        "one_liner": "JWT access token kimligi tasir, refresh token ise oturumu yeniler.",
        "very_simple": "Kisaca sistem kim oldugunu access token ile anlar, sure bitince refresh token ile yeni token alir.",
        "glossary": [
            {"terim": "JWT", "tanim": "Kimlik bilgisini tasiyan token yapisidir."},
            {"terim": "Refresh token", "tanim": "Suresi dolan access token icin yeni token uretmeye yarar."},
        ],
        "steps": [
            "Once access token kullaniciyi tanitir.",
            "Sonra sure biterse refresh token devreye girer.",
            "En sonda oturum yeni token ile devam eder.",
        ],
        "examples": [
            "Ornek olarak API istegi once access token ile gider.",
            "Token suresi bitince sistem kullaniciyi tekrar cikis yaptirmadan yenileme yapar.",
        ],
        "trap": "Tuzak, refresh token ile access tokeni ayni rol saniip ikisini de ayni is icin kullanmaktir.",
        "mini_quiz": [
            {"q": "JWT ne tasir?", "a": "JWT kullanicinin kimligini tasir."},
            {"q": "Refresh token ne zaman kullanilir?", "a": "Access token suresi doldugunda kullanilir."},
            {"q": "Bu akis neyi korur?", "a": "Oturumun kesilmeden devam etmesini korur."},
        ],
        "dokumanda_yok": False,
    }

    ozet = genel_kalite_ozeti(payload, text, ornek_adi="jwt")

    assert ozet["toplam_skor"] >= 17
    assert ozet["skorlar"]["mini_quiz"] == 3
    assert ozet["skorlar"]["parcaya_baglilik"] >= 3
    assert ozet["supheli_dokumanda_yok"] is False


def test_dokumanda_yok_supheli_mi_anlamli_metinde_ceza_uretir():
    text = "Cache ayni sonucu tekrar hesaplamadan daha hizli cevap vermeyi saglar."
    payload = {
        "one_liner": "Dokumanda yok.",
        "very_simple": "",
        "glossary": [],
        "steps": [],
        "examples": [],
        "trap": "",
        "mini_quiz": [],
        "dokumanda_yok": True,
    }

    assert dokumanda_yok_supheli_mi(payload, text) is True

    ozet = genel_kalite_ozeti(payload, text, ornek_adi="supheli")

    assert ozet["supheli_dokumanda_yok_cezasi"] == -3
    assert "supheli_dokumanda_yok" in ozet["uyarilar"]
    assert "glossary_zayif" in ozet["uyarilar"]
    assert "steps_zayif" in ozet["uyarilar"]
    assert "examples_zayif" in ozet["uyarilar"]


def test_benchmark_toplam_rapor_zayif_alanlari_ve_hatalari_sayar():
    text = "RAG once ilgili parcayi bulur sonra bu parcaya dayanarak cevap uretir."
    guclu = genel_kalite_ozeti(
        {
            "one_liner": "RAG ilgili parcayi bulup ona dayali cevap uretir.",
            "very_simple": "Sistem once dogru parcayi secer sonra cevabi o parcadan kurar.",
            "glossary": [{"terim": "RAG", "tanim": "Ilgili parcayi bulup cevap ureten yontemdir."}],
            "steps": ["Once ilgili parcayi bul.", "Sonra cevabi bu parcadan kur."],
            "examples": ["Bir soru geldiginde once en ilgili parca cekilir."],
            "trap": "Tuzak, parcayi bulmadan cevap uretmeye calismaktir.",
            "mini_quiz": [
                {"q": "RAG ne yapar?", "a": "Ilgili parcayi bulur."},
                {"q": "Cevap neye dayanir?", "a": "Bulunan parcaya dayanir."},
                {"q": "Tuzak nedir?", "a": "Parca bulmadan cevap uretmektir."},
            ],
        },
        text,
        ornek_adi="guclu",
    )
    zayif = genel_kalite_ozeti(
        {
            "one_liner": "Dokumanda yok.",
            "very_simple": "",
            "glossary": [],
            "steps": [],
            "examples": [],
            "trap": "",
            "mini_quiz": [],
            "dokumanda_yok": True,
        },
        text,
        ornek_adi="zayif",
    )

    rapor = benchmark_toplam_rapor([guclu, zayif])
    ozet_metin = okunur_benchmark_ozeti(rapor)

    assert rapor["supheli_dokumanda_yok_sayisi"] == 1
    assert "glossary" in rapor["alan_ortalamalari"]
    assert rapor["hata_sikliklari"]["supheli_dokumanda_yok"] == 1
    assert "glossary" in rapor["zayif_alanlar"]
    assert "Supheli dokumanda_yok sayisi: 1" in ozet_metin


def test_mini_quiz_kalite_skoru_uc_tam_soruda_yuksek_doner():
    text = "Embedding vektor temsili uretir, retrieval ilgili parcayi bulur, rerank ise siralamayi iyilestirir."
    payload = {
        "mini_quiz": [
            {"q": "Embedding ne uretir?", "a": "Embedding vektor temsili uretir."},
            {"q": "Retrieval ne yapar?", "a": "Retrieval ilgili parcayi bulur."},
            {"q": "Rerank neyi iyilestirir?", "a": "Rerank siralamayi iyilestirir."},
        ]
    }

    assert mini_quiz_kalite_skoru(payload, text) == 3


@override_settings(DEBUG=True)
def test_parca_anlamadim_v2_endpoint_temel_alanlari_ve_benchmark_verisini_dondurur(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="JWT Benchmark",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        durum="parcalandi",
    )
    doc.dosya.save("jwt-benchmark.docx", ContentFile(b"ornek"), save=True)

    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1",
        metin=(
            "JWT access token kullanicinin kimligini tasir. "
            "Refresh token ile suresi dolan access token yenilenir."
        ),
        meta={"path": "1", "baslik": "JWT"},
    )

    weak_json = {
        "one_liner": "Bu parca basitce sunu soyluyor.",
        "very_simple": "",
        "glossary": [],
        "steps": [""],
        "examples": [],
        "trap": "",
        "mini_quiz": [],
        "dokumanda_yok": False,
    }

    chat_cagrilari = []

    def fake_chat(messages, max_tokens=256):
        chat_cagrilari.append({"messages": messages, "max_tokens": max_tokens})
        return json.dumps(weak_json, ensure_ascii=False)

    monkeypatch.setattr("dokuman.views.chat", fake_chat)

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        f"/api/dokuman-asistani/parcalar/{parca.id}/anlamadim-v2/",
        {"mesaj": "Bu parcayi sade anlat.", "max_tokens": 96, "debug_ai2": True},
        format="json",
    )

    assert response.status_code == 200
    data = response.data

    for alan in ("one_liner", "very_simple", "glossary", "steps", "examples", "trap", "mini_quiz", "dokumanda_yok"):
        assert alan in data

    assert data["dokumanda_yok"] is False
    assert isinstance(data["glossary"], list) and len(data["glossary"]) >= 1
    assert isinstance(data["steps"], list) and len(data["steps"]) >= 3
    assert isinstance(data["examples"], list) and len(data["examples"]) >= 2
    assert isinstance(data["mini_quiz"], list) and len(data["mini_quiz"]) == 3
    assert chat_cagrilari
    assert chat_cagrilari[0]["max_tokens"] == 96
    assert data["debug_ai2"]["parca_sinifi"] == "kisa"
    assert data["debug_ai2"]["istenen_alan_sayisi"] == 7
    assert data["debug_ai2"]["prompt_parca_metin_uzunlugu"] <= data["debug_ai2"]["parca_metin_uzunlugu"]
    assert "steps" in data["debug_ai2"]["merge_ile_tamamlanan_alanlar"]
    assert data["debug_ai2"]["merge_gerekli_miydi"] is True
    assert data["debug_ai2"]["json_bulundu_mu"] is True
    assert data["debug_ai2"]["parse_basarili_mi"] is True
    assert data["debug_ai2"]["fallback_nedeni"] == "ai2_short_output"

    ozet = genel_kalite_ozeti(data, parca.metin, ornek_adi="endpoint")
    assert ozet["skorlar"]["mini_quiz"] >= 2
    assert ozet["skorlar"]["parcaya_baglilik"] >= 2


@override_settings(DEBUG=True)
def test_parca_anlamadim_v2_endpoint_bozuk_jsonu_onarip_alanlari_doldurur(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Broken JSON Benchmark",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("broken-json.pdf", ContentFile(b"ornek"), save=True)

    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="txt:1",
        metin="Excel | IF | XLOOKUP",
        meta={"path": "txt:1", "baslik": "Etiketler"},
    )

    broken_json = (
        'Aciklama: {"one_liner":"Excel araclari birlikte listelenmis",'
        '"very_simple":"Bu satir Excel notundaki temel etiketleri yan yana veriyor.",'
        '"glossary":"IF: Kosula gore sonuc ureten Excel fonksiyonu.\\nXLOOKUP: Aranan degeri tabloda bulur.",'
        '"steps":"1) Etiketleri ayir\\n2) Her birinin gorevini dusun",'
        '"examples":"Bu satir temel Excel araclarini ayni notta toplar.",'
        '"mini_quiz":"Q: IF ne yapar?\\nA: Kosula gore sonuc uretir."'
    )

    def fake_chat(messages, max_tokens=256):
        return broken_json

    monkeypatch.setattr("dokuman.views.chat", fake_chat)

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        f"/api/dokuman-asistani/parcalar/{parca.id}/anlamadim-v2/",
        {"mesaj": "Bu satiri acikla.", "max_tokens": 96, "debug_ai2": True},
        format="json",
    )

    assert response.status_code == 200
    data = response.data

    assert data["dokumanda_yok"] is False
    assert data["debug_ai2"]["json_bulundu_mu"] is True
    assert data["debug_ai2"]["parse_basarili_mi"] is True
    assert len(data["glossary"]) >= 2
    assert len(data["steps"]) >= 2
    assert len(data["examples"]) >= 1
    assert len(data["mini_quiz"]) == 3
