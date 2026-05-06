"""AI2 guardrail, fallback ve metric-store davranislarini no-leak cizgisinde dogrulayan testler."""

from __future__ import annotations

import json

from django.core.files.base import ContentFile
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from dokuman.ai2.prompts import build_anlamadim_prompt
from dokuman.ai2.validators import (
    analyze_anlamadim_completeness,
    evaluate_completeness_score,
    evaluate_hallucination_risk,
    evaluate_usefulness_score_v2,
)
from dokuman.models import AnlamadimKaydi, Dokuman, MetrikKaydi, Parca
from dokuman.services.metric_store import (
    compute_confusion_map_score,
    compute_mastery_score,
)
from dokuman.views import _anlamadim_alan_durumu
from dokuman.views_ai2 import AnlamadimAI2APIView


def _anlamadim_ai2_post(user, parca_id: int, payload: dict):
    """Anlamadim AI2 endpoint'ini testlerde request factory ile cagirmayi sadeletir."""
    factory = APIRequestFactory()
    request = factory.post(
        f"/api/dokuman-asistani/ai2/parcalar/{parca_id}/anlamadim/",
        payload,
        format="json",
    )
    force_authenticate(request, user=user)
    response = AnlamadimAI2APIView.as_view()(request, parca_id=parca_id)
    response.render()
    return response


def _create_ai2_doc(test_kullanicisi, *, title: str = "AI2 Guardrail Doc") -> Dokuman:
    """Guardrail senaryolari icin parcalanmaya hazir yalın dokuman kaydi uretir."""
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik=title,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save(f"{title.lower().replace(' ', '-')}.pdf", ContentFile(b"ornek"), save=True)
    return doc


def test_ai2_kanitli_cevap_low_evidence_short_circuits_before_llm(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    # Hazırlık: Soruyla alakasız, çok kısa ve düşük kaliteli bir test parçası (kanıtı) oluştur.
    doc = _create_ai2_doc(test_kullanicisi, title="Low Evidence")
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Ek > Not",
        metin="Kisa alakasiz not.",
        meta={"path": "Ek > Not"},
    )

    chat_cagrisi = {"adet": 0}

    # Hazırlık: LLM metodunu mock'la. Eğer test düşük kanıt yüzünden kısa devre yapmazsa, bu fonksiyon tetiklenecek ve test patlayacaktır.
    def fake_chat(messages, max_tokens=256):
        chat_cagrisi["adet"] += 1
        raise AssertionError("Low evidence durumunda LLM cagrilmamali.")

    monkeypatch.setattr("dokuman.views_ai2.chat", fake_chat)

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    # Çağrı: "Kuantum" gibi belgeyle alakasız bir soru sor.
    response = client.post(
        "/api/dokuman-asistani/ai2/kanitli-cevap/",
        {"question": "Kuantum dolaniklik nasil olculur?", "doc_id": doc.id, "top_k": 1},
        format="json",
    )

    # Doğrulama: LLM'e hiç gidilmeden "low_evidence_abstain" ile doğrudan güvenlik reddi döndüğü teyit edilir.
    assert response.status_code == 200
    assert chat_cagrisi["adet"] == 0
    data = response.data
    assert data["supported"] is False
    assert data["answer"] == "Dokümanda geçmiyor."
    assert data["citations"] == []
    assert data["unsupported_reason"] == "low_evidence_abstain"
    assert data["kullanilan_kanit_sayisi"] == 0


def test_ai2_kanitli_cevap_rejects_citation_outside_allowlist(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    # Hazırlık: İki farklı doküman parçası oluştur.
    doc = _create_ai2_doc(test_kullanicisi, title="Citation Allowlist Reject")
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="RAG > Giris",
        metin="RAG ilgili parcayi bulur ve cevap kurarken kaynaga bagli kalir.",
        meta={"path": "RAG > Giris"},
    )
    second = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="RAG > Kaynak",
        metin="Kaynakli cevapta parca_id izlenebilirligi cevap guvenini arttirir.",
        meta={"path": "RAG > Kaynak"},
    )

    # Hazırlık: LLM'in kasıtlı olarak allowlist (izin verilenler) dışında bir citation ID dönmesini simüle et (mock).
    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: json.dumps(
            {
                "answer": "Parca kimligini gostermek izlenebilirlik saglar.",
                "supported": True,
                "citations": [second.id, 999999],
                "missing": [],
                "followups": [],
            },
            ensure_ascii=False,
        ),
    )
    monkeypatch.setattr("dokuman.views_ai2._should_abstain_for_low_evidence", lambda kanit_meta: False)

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    # Çağrı: İzin verilmeyen bir kaynağa atıf yapan kanıtlı cevap isteği at.
    response = client.post(
        "/api/dokuman-asistani/ai2/kanitli-cevap/",
        {"question": "Kaynakli cevapta parca_id neden onemli?", "doc_id": doc.id, "top_k": 2},
        format="json",
    )

    # Doğrulama: Güvenlik mekanizmasının (guardrail) geçersiz citation'ı yakalayıp reddettiğini teyit et.
    assert response.status_code == 200
    data = response.data
    assert data["supported"] is False
    assert data["citations"] == []
    assert data["answer"] == "Dokümanda geçmiyor."
    assert data["unsupported_reason"] == "gecersiz_citation"
    assert data["kullanilan_kanit_sayisi"] == 0


def test_ai2_kanitli_cevap_accepts_allowed_citations_and_wires_prompt(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    # Hazirlik: Allowlist icinde kalacak iki parca ve yakalanacak prompt yuzeyi kur.
    doc = _create_ai2_doc(test_kullanicisi, title="Citation Allowlist Accept")
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="RAG > Giris",
        metin="RAG ilgili parcayi bulur ve cevap icin bu parcayi kullanir.",
        meta={"path": "RAG > Giris"},
    )
    second = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="RAG > Kaynak",
        metin="Kaynakli cevapta parca_id ve kanit takibi izlenebilirligi guclendirir.",
        meta={"path": "RAG > Kaynak"},
    )

    yakalanan = {}

    def fake_chat(messages, max_tokens=256):
        yakalanan["messages"] = messages
        return json.dumps(
            {
                "answer": "Parca kimligini gostermek cevabin hangi kanita dayandigini izlenebilir kilar.",
                "supported": True,
                "citations": [second.id],
                "missing": [],
                "followups": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("dokuman.views_ai2.chat", fake_chat)

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    # Cagri: Kanitli cevap endpoint'ini dokuman bazli retrieval ile cagir.
    response = client.post(
        "/api/dokuman-asistani/ai2/kanitli-cevap/",
        {"question": "Kaynakli cevapta parca_id neden onemli?", "doc_id": doc.id, "top_k": 2},
        format="json",
    )

    # Dogrulama: Izinli citation korunmali ve prompt'a strict allowlist bilgisi yazilmali.
    assert response.status_code == 200
    data = response.data
    assert data["supported"] is True
    assert data["citations"] == [second.id]
    assert data["kullanilan_parca_idleri"] == [second.id]
    assert data["kullanilan_kanit_sayisi"] == 1
    assert "ALLOWED_CITATION_IDS" in yakalanan["messages"][0]["content"]
    assert str(second.id) in yakalanan["messages"][0]["content"]
    assert "STRICT_EVIDENCE_MODE=true" in yakalanan["messages"][0]["content"]
    assert "ALLOWED_CITATION_IDS" in yakalanan["messages"][1]["content"]


def test_ai2_eval_metrics_store_ham_icerik_saklamaz_ve_response_shapei_bozmaz(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    # Hazirlik: Kaynakli basarili cevap donduren mock ile metric-store davranisini gozle.
    doc = _create_ai2_doc(test_kullanicisi, title="Eval Metric Store")
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="JWT > Giris",
        metin="JWT access token kullanicinin kimligini tasir ve refresh token akisina giris saglar.",
        meta={"path": "JWT > Giris"},
    )
    ikinci = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="JWT > Yenileme",
        metin="Refresh token ile yeni access token alinabilir ve oturum yenileme akisinda kullanilir.",
        meta={"path": "JWT > Yenileme"},
    )

    ham_cevap = "Refresh token ile yeni access token alinabilir ve bu cumle metric store icine ham olarak yazilmamali."
    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: json.dumps(
            {
                "answer": ham_cevap,
                "supported": True,
                "citations": [ikinci.id],
                "missing": [],
                "followups": [],
            },
            ensure_ascii=False,
        ),
    )
    monkeypatch.setattr("dokuman.views_ai2._should_abstain_for_low_evidence", lambda kanit_meta: False)

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    # Cagri: Endpoint'i calistirip hem response shape'ini hem de arka plan kaydini uret.
    response = client.post(
        "/api/dokuman-asistani/ai2/kanitli-cevap/",
        {"question": "Refresh token ile yeni access token ne zaman alinir?", "doc_id": doc.id, "top_k": 2},
        format="json",
    )

    # Dogrulama: Response'ta eval alanlari sizmiyor, metric store ise yalnizca skorlari tasiyor.
    assert response.status_code == 200
    data = response.data
    assert "hallucination_risk" not in data
    assert "usefulness_score_v2" not in data
    assert data["supported"] is True

    kayit = MetrikKaydi.objects.get(olay_turu="ai2_cevap_degerlendirildi")
    assert kayit.dokuman_id == doc.id
    assert "completeness_score" in kayit.skor_ozeti
    assert "hallucination_risk" in kayit.skor_ozeti
    assert "usefulness_score_v2" in kayit.skor_ozeti
    assert ham_cevap not in str(kayit.skor_ozeti)


def test_ai2_kanitli_cevap_blocks_source_leakage_in_answer_text(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    # Hazirlik: Cevap metninin icine allowlist disi kaynak izi sizdiran sahte model cevabi kur.
    doc = _create_ai2_doc(test_kullanicisi, title="Source Leakage")
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="RAG > Giris",
        metin="Kaynakli cevap ilgili parcayi bulur ve secili parcaya dayanir.",
        meta={"path": "RAG > Giris"},
    )
    second = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="RAG > Kaynak",
        metin="Kaynakli cevapta yalniz secili parcaya dayali bilgi paylasilmali ve dis kaynak sizdirilmamalidir.",
        meta={"path": "RAG > Kaynak"},
    )

    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: json.dumps(
            {
                "answer": "Secili kaynak bunu destekliyor ama [999] nolu dis kaynak da ayni seyi soyluyor.",
                "supported": True,
                "citations": [second.id],
                "missing": [],
                "followups": [],
            },
            ensure_ascii=False,
        ),
    )
    monkeypatch.setattr("dokuman.views_ai2._should_abstain_for_low_evidence", lambda kanit_meta: False)

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    # Cagri: Kaynak sizintisi iceren cevabi kanitli endpoint'ten gecir.
    response = client.post(
        "/api/dokuman-asistani/ai2/kanitli-cevap/",
        {"question": "Kaynakli cevapta secili parca nasil kullanilir?", "doc_id": doc.id, "top_k": 2},
        format="json",
    )

    # Dogrulama: Guardrail cevabi unsupported hale getirip citation'lari temizlemeli.
    assert response.status_code == 200
    data = response.data
    assert data["supported"] is False
    assert data["citations"] == []
    assert data["answer"] == "Dokümanda geçmiyor."
    assert data["unsupported_reason"] == "source_leakage"


def test_eval_helpers_hallucination_risk_low_and_high_cases_are_separated():
    # Hazirlik: Ayni helper'i dusuk risk, yuksek risk ve guvenli abstain senaryolarinda cagir.
    completeness = evaluate_completeness_score(
        "JWT istemci kimligini tasir ve yetki bilgisini iletir.",
        ["JWT istemci kimligini tasir ve yetki bilgisini iletir."],
    )
    low_risk = evaluate_hallucination_risk(
        citation_ids=[11],
        provided_ids=[11],
        completeness_score=completeness,
    )
    high_risk = evaluate_hallucination_risk(
        citation_ids=[11, 99],
        provided_ids=[11],
        completeness_score=0.20,
    )
    safe_abstain = evaluate_hallucination_risk(
        citation_ids=[],
        provided_ids=[],
        completeness_score=0.0,
        supported=False,
        unsupported_reason="low_evidence_abstain",
    )

    # Dogrulama: Yetersiz hizalanmis kanit daha yuksek risk, safe abstain ise dusuk risk üretmeli.
    assert low_risk["hallucination_risk"] < high_risk["hallucination_risk"]
    assert safe_abstain["hallucination_risk"] < 0.2
    assert high_risk["hallucination_risk"] > 0.4


def test_eval_helpers_usefulness_score_v2_is_calculated():
    # Hazirlik + cagri: usefulness helper'ini temsilci completeness/hallucination skorlarinda calistir.
    sonuc = evaluate_usefulness_score_v2(
        completeness_score=0.80,
        hallucination_risk=0.35,
    )

    # Dogrulama: Yardimci skor beklenen banda dusmeli ve reason alani stabil kalmali.
    assert 0.50 <= sonuc["usefulness_score_v2"] <= 0.53
    assert sonuc["usefulness_reason"] in {"useful", "partial_usefulness"}


def test_build_anlamadim_prompt_quiz_readiness_dusukse_mini_quiz_istegini_kapatir():
    # Hazirlik + cagri: Prompt builder'a mini quiz kapali profil ver.
    messages, meta = build_anlamadim_prompt(
        "1. Giris",
        "Bu projede temel amacimiz verimliligi artirmaktir.",
        7,
        {
            "tema": "genel",
            "tarz": "adim_adim",
            "seviye": "baslangic",
            "quality_score": 0.9,
            "mini_quiz_aktif": False,
        },
        return_meta=True,
    )

    # Dogrulama: Prompt mini_quiz alanini istememeli ama kalan shape bozulmamali.
    assert meta["mini_quiz_aktif"] is False
    assert "Alanlar: one_liner, very_simple, glossary, steps, examples, trap, dokumanda_yok." in messages[0]["content"]
    assert '"mini_quiz"' not in messages[0]["content"]


def test_anlamadim_ai2_quiz_uygun_degilsse_quiz_atlar_ama_shape_korur(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    # Hazirlik: Dusuk kalite parca ve mini quiz'siz ama gecerli AI cevabi kur.
    doc = _create_ai2_doc(test_kullanicisi, title="Quiz Gate Skip")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Ek > Kisa",
        metin="JWT",
        meta={"path": "Ek > Kisa", "quality_score": 0.12, "difficulty_score": 0.08, "weak_content": True},
    )

    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: json.dumps(
            {
                "one_liner": "JWT kimlik bilgisini tasir.",
                "very_simple": "Bu terim token ile ilgilidir.",
                "glossary": [{"terim": "JWT", "tanim": "Token yapisidir."}],
                "steps": ["Terimi gor.", "Baglami anla."],
                "examples": ["API isteginde kullanilir."],
                "trap": "JWT ile refresh tokeni ayni sey sanmak.",
            },
            ensure_ascii=False,
        ),
    )

    # Cagri: Quiz gate elese bile endpoint shape'i ayni response ile donmeli.
    response = _anlamadim_ai2_post(test_kullanicisi, parca.id, {"tema": "teknoloji"})

    # Dogrulama: mini_test bos kalmali, skip reason ise metrik kayitlarinda gorunmeli.
    assert response.status_code == 200
    assert "mini_test" in response.data
    assert response.data["mini_test"] == []
    hazirlik = MetrikKaydi.objects.get(olay_turu="quiz_hazirlik_hesaplandi")
    atlandi = MetrikKaydi.objects.get(olay_turu="mini_quiz_atlandi")
    assert hazirlik.skor_ozeti["quiz_eligible"] is False
    assert atlandi.skor_ozeti["quiz_skip_reason"]


def test_anlamadim_completeness_flags_empty_steps():
    # Hazirlik + cagri: Steps alani bos bir payload completeness helper'ina verilir.
    analiz = analyze_anlamadim_completeness(
        {
            "one_liner": "JWT access token kimlik bilgisini tasir.",
            "very_simple": "Sistem access token ile kim oldugunu anlar ve sure bitince yeniler.",
            "glossary": [{"terim": "JWT", "tanim": "Kimlik bilgisini tasiyan token yapisidir."}],
            "steps": [""],
            "examples": ["API isteginde token gonderilir ve sistem kullaniciyi tanir."],
            "trap": "Tuzak access token ile refresh tokeni ayni sey sanmaktir.",
            "mini_quiz": [
                {"q": "JWT ne tasir?", "a": "Kimlik bilgisini tasir."},
                {"q": "Token ne zaman yenilenir?", "a": "Sure bitince yenilenir."},
                {"q": "Tuzak nedir?", "a": "Iki tokeni ayni sanmaktir."},
            ],
        }
    )

    # Dogrulama: Sadece bir alanin eksikligi bile yeterlilik kararini dusurmelidir.
    assert analiz["yeterli_mi"] is False
    assert "steps" in analiz["eksik_alanlar"]
    assert analiz["completeness_score"] < 7


def test_code_field_guardrail_marks_generic_comment_fields_as_weak():
    durum = _anlamadim_alan_durumu(
        {
            "one_liner": "Bu test API cagrisi ve assertion zincirini acikliyor.",
            "very_simple": "Test once istegi gonderiyor, sonra donen sonucu ve final state'i kontrol ediyor.",
            "glossary": [{"terim": "POST", "tanim": "Endpoint'e veri gonderen HTTP cagrisi."}],
            "steps": ["Hazirlik adimini ayir.", "Cagriyi takip et.", "Assertion sonucunu oku."],
            "examples": ["Ornek: istemci POST ile endpoint'e gider."],
            "trap": "Tuzak, butun assertion'lari tek kontrol sanmaktir.",
            "mini_quiz": [
                {"q": "Hazirlik nedir?", "a": "Yetki ve payload kurulumudur."},
                {"q": "Cagri nedir?", "a": "Endpoint'e istek gondermektir."},
                {"q": "Assertion neyi ayirir?", "a": "Status, alan ve final state dogrulamalarini."},
            ],
            "function_purpose": "Bu test bir sey yapar.",
            "flow_summary": "Kod bir sey yapar.",
            "block_comments": ["Bu blok bir sey yapar."],
            "line_comments": ["Bu satir bir sey yapar."],
        },
        "response = client.post('/api/v1/documents/', payload)\nassert response.status_code == 201\nassert document.status == 'draft'",
    )

    assert "function_purpose" in durum["zayif_alanlar"]
    assert "flow_summary" in durum["zayif_alanlar"]
    assert "block_comments" in durum["bicim_hatasi_olan_alanlar"]
    assert "line_comments" in durum["bicim_hatasi_olan_alanlar"]

def test_anlamadim_ai2_fallback_repairs_empty_glossary(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    # Hazirlik: Aciklama metni guclu ama glossary bos bir model cevabi simule edilir.
    doc = _create_ai2_doc(test_kullanicisi, title="Anlamadim Glossary")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="JWT > Giris",
        metin=(
            "JWT access token kullanicinin kimligini tasir. "
            "Refresh token ile suresi dolan access token yenilenir."
        ),
        meta={"path": "JWT > Giris"},
    )

    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: json.dumps(
            {
                "one_liner": "JWT access token kimligi tasir.",
                "very_simple": "Sistem access token ile kim oldugunu anlar ve refresh token ile yeni token alir.",
                "glossary": [],
                "steps": [
                    "Once access token gonderilir.",
                    "Sure bitince refresh token ile yeni token alinir.",
                ],
                "examples": ["API istegi access token ile gonderilir."],
                "trap": "Tuzak access token ile refresh tokeni ayni sanmaktir.",
                "mini_quiz": [
                    {"q": "JWT ne tasir?", "a": "Kimlik bilgisini tasir."},
                    {"q": "Refresh token ne yapar?", "a": "Yeni token alinmasini saglar."},
                    {"q": "Tuzak nedir?", "a": "Iki tokeni ayni sanmaktir."},
                ],
            },
            ensure_ascii=False,
        ),
    )

    # Cagri: Endpoint fallback ile glossary onarsin.
    response = _anlamadim_ai2_post(test_kullanicisi, parca.id, {"tema": "teknoloji"})

    # Dogrulama: fallback_json bayragi kalkmali ve glossary en az bir terimle onarilmis olmali.
    assert response.status_code == 200
    data = response.data
    assert data["fallback_json_kullanildi"] is True
    assert len(data["terimler"]) >= 1
    assert any(item["terim"] == "JWT" for item in data["terimler"])


def test_anlamadim_ai2_runs_fallback_when_completeness_is_low(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    # Hazirlik: Bilerek zayif ve eksik alanli LLM cevabi ile fallback yolu zorlanir.
    doc = _create_ai2_doc(test_kullanicisi, title="Anlamadim Weak")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Auth > Akis",
        metin=(
            "API istemcisi once access token gonderir. "
            "Token gecersizse refresh token ile yeni access token alinir. "
            "Bu sayede kullanici yeniden giris yapmadan oturumu surdurur."
        ),
        meta={"path": "Auth > Akis"},
    )

    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: json.dumps(
            {
                "one_liner": "Bu parca basitce sunu soyluyor.",
                "very_simple": "",
                "glossary": [],
                "steps": [""],
                "examples": [],
                "trap": "",
                "mini_quiz": [{"q": "Nedir?", "a": ""}],
                "dokumanda_yok": False,
            },
            ensure_ascii=False,
        ),
    )

    # Cagri: Completeness dusuk oldugu icin endpoint fallback uretsin.
    response = _anlamadim_ai2_post(test_kullanicisi, parca.id, {"tema": "teknoloji"})

    # Dogrulama: Fallback zengin alanlari doldurup mini quiz shape'ini onarmali.
    assert response.status_code == 200
    data = response.data
    assert data["fallback_json_kullanildi"] is True
    assert len(data["adim_adim"]) >= 3
    assert len(data["ornekler"]) >= 2
    assert len(data["mini_test"]) == 3


def test_anlamadim_ai2_uses_script_guidance_for_html_script_block(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _create_ai2_doc(test_kullanicisi, title="HTML Script Guidance")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="kod",
        adres="code:html:script:1",
        metin="fetch('/api/save')\nreturn result;",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "html",
            "code_language": "html",
            "code_unit_kind": "script_block",
            "code_unit_name": "script",
            "line_start": 12,
            "line_end": 13,
        },
    )

    yakalanan = {}

    def fake_chat(messages, max_tokens=256):
        yakalanan["prompt"] = "\n".join(item["content"] for item in messages)
        return json.dumps(
            {
                "one_liner": "Bu script blogu gorunen API ve donus adimini acikliyor.",
                "very_simple": "Kod once fetch ile gorunen dis cagrisi yapiyor, sonra gorunen sonucu donduruyor.",
                "glossary": [{"terim": "script", "tanim": "Davranis katmanini tasiyan bloktur."}],
                "steps": ["Girdi: script adimini ayir.", "Islem: fetch cagrisi ve donusu oku.", "Beklenen sonuc: gorunen ciktiyi not et."],
                "examples": ["Script ornegi: fetch ile cagrisi yapip sonucu dondurur."],
                "trap": "Tuzak, gorunmeyen framework davranisi uydurmaktir.",
                "mini_quiz": [
                    {"q": "Hangi dis cagrisi var?", "a": "fetch cagrisi var."},
                    {"q": "Son adim ne?", "a": "Gorunen sonucu donduruyor."},
                    {"q": "Ne uydurulmamalidir?", "a": "Gorunmeyen framework davranisi."},
                ],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("dokuman.views_ai2.chat", fake_chat)

    response = _anlamadim_ai2_post(test_kullanicisi, parca.id, {"tema": "teknoloji"})

    assert response.status_code == 200
    assert "script ise event/handler, callback, api/dom akislarini ayir" in yakalanan["prompt"].lower()
    assert "html/markup ise hangi yapisal bloklarin kuruldugunu anlat" not in yakalanan["prompt"].lower()


def test_anlamadim_ai2_fallback_preserves_response_contract(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _create_ai2_doc(test_kullanicisi, title="Anlamadim Contract")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Cache > Tanim",
        metin="Cache ayni sonucu tekrar hesaplamadan daha hizli cevap vermeyi saglar.",
        meta={"path": "Cache > Tanim"},
    )

    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: json.dumps(
            {
                "one_liner": "Cache vardir.",
                "very_simple": "",
                "glossary": [],
                "steps": [],
                "examples": [],
                "trap": "",
                "mini_quiz": [],
            },
            ensure_ascii=False,
        ),
    )

    response = _anlamadim_ai2_post(test_kullanicisi, parca.id, {"tema": "teknoloji"})

    assert response.status_code == 200
    data = response.data
    for alan in (
        "ozet_1c",
        "cok_basit",
        "terimler",
        "adim_adim",
        "ornekler",
        "tuzak",
        "mini_test",
        "kanit_parca_idleri",
    ):
        assert alan in data

    assert isinstance(data["ozet_1c"], str) and data["ozet_1c"]
    assert isinstance(data["cok_basit"], str) and data["cok_basit"]
    assert isinstance(data["terimler"], list) and data["terimler"]
    assert isinstance(data["adim_adim"], list) and data["adim_adim"]
    assert isinstance(data["ornekler"], list) and data["ornekler"]
    assert isinstance(data["mini_test"], list) and len(data["mini_test"]) == 3
    assert data["kanit_parca_idleri"] == [parca.id]


def test_anlamadim_ai2_metric_store_completeness_skoru_yazar_ve_ham_icerik_saklamaz(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _create_ai2_doc(test_kullanicisi, title="Anlamadim Metric")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Cache > Metric",
        metin="Cache ayni sonucu tekrar hesaplamadan daha hizli cevap verir.",
        meta={"path": "Cache > Metric"},
    )

    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: json.dumps(
            {
                "one_liner": "Cache tekrar hesaplamayi azaltir.",
                "very_simple": "",
                "glossary": [],
                "steps": [],
                "examples": [],
                "trap": "",
                "mini_quiz": [],
            },
            ensure_ascii=False,
        ),
    )

    response = _anlamadim_ai2_post(test_kullanicisi, parca.id, {"tema": "teknoloji"})

    assert response.status_code == 200
    kayit = MetrikKaydi.objects.get(olay_turu="ai2_anlamadim_degerlendirildi")
    assert kayit.parca_id == parca.id
    assert "completeness_score" in kayit.skor_ozeti
    assert "usefulness_score_v2" in kayit.skor_ozeti
    assert "Cache tekrar hesaplamayi azaltir." not in str(kayit.skor_ozeti)


def test_confusion_ve_mastery_skorlari_hesaplanir_metricte_yazilir_ve_responsea_sizmaz(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _create_ai2_doc(test_kullanicisi, title="Confusion Mastery")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="OAuth > Akis",
        metin="OAuth akisinda access token ve refresh token birlikte kullanilir.",
        meta={"path": "OAuth > Akis"},
    )
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc,
        parca=parca,
        adres=parca.adres,
        kullanici_mesaj="Access token neden yenileniyor?",
        cikti_text="Yanit eksik kaldi.",
    )
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc,
        parca=parca,
        adres=parca.adres,
        kullanici_mesaj="Refresh token ne zaman devreye girer?",
        cikti_text="Yanit tekrar istendi.",
    )

    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: json.dumps(
            {
                "one_liner": "OAuth token akisinda kimlik token ile tasinir.",
                "very_simple": "",
                "glossary": [],
                "steps": [],
                "examples": [],
                "trap": "",
                "mini_quiz": [],
            },
            ensure_ascii=False,
        ),
    )

    response = _anlamadim_ai2_post(test_kullanicisi, parca.id, {"tema": "teknoloji"})

    assert response.status_code == 200
    assert "confusion_map_score" not in response.data
    assert "mastery_score" not in response.data

    confusion_meta = compute_confusion_map_score(
        user=test_kullanicisi,
        dokuman=doc,
        parca=parca,
    )
    mastery_meta = compute_mastery_score(
        user=test_kullanicisi,
        dokuman=doc,
    )
    assert 0.0 <= confusion_meta["confusion_map_score"] <= 1.0
    assert confusion_meta["confusion_map_score"] > 0.2
    assert 0.0 <= mastery_meta["mastery_score"] <= 1.0

    kayit = MetrikKaydi.objects.get(olay_turu="ai2_anlamadim_degerlendirildi")
    assert "confusion_map_score" in kayit.skor_ozeti
    assert "mastery_score" in kayit.skor_ozeti
    assert "OAuth token akisinda kimlik token ile tasinir." not in str(kayit.skor_ozeti)


def test_ai2_metric_store_flag_kapaliyken_endpoint_shape_korunur(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
    settings,
):
    settings.DOCVERSE_METRIC_STORE_ENABLED = False
    doc = _create_ai2_doc(test_kullanicisi, title="AI2 Metric Flag Off")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="Cache > Flag",
        metin="Cache ayni istegi hizlandirmak icin ara katmanda tutar.",
        meta={"path": "Cache > Flag", "quality_score": 0.78},
    )

    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: json.dumps(
            {
                "one_liner": "Cache tekrarlanan veriyi hizli sunar.",
                "very_simple": "",
                "glossary": [],
                "steps": [],
                "examples": [],
                "trap": "",
                "mini_quiz": [],
            },
            ensure_ascii=False,
        ),
    )

    response = _anlamadim_ai2_post(test_kullanicisi, parca.id, {"tema": "teknoloji"})

    assert response.status_code == 200
    for alan in ("ozet_1c", "cok_basit", "terimler", "adim_adim", "ornekler", "mini_test"):
        assert alan in response.data
    assert "confusion_map_score" not in response.data
    assert MetrikKaydi.objects.filter(olay_turu="ai2_anlamadim_degerlendirildi").count() == 0
