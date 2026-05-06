from __future__ import annotations

from django.core.files.base import ContentFile

from dokuman.models import AnlamadimKaydi, Dokuman, MetrikKaydi, Parca
from dokuman.services.metric_store import (
    compute_confusion_map_score,
    compute_mastery_score,
    guvenli_metrik_kaydi_olustur,
)
from oyun.models import Boss, BossDeneme, BossSoru


def _create_doc_with_parca(user, *, title: str = "Metric Behavioral"):
    doc = Dokuman.objects.create(
        owner=user,
        baslik=title,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save(f"{title.lower().replace(' ', '-')}.pdf", ContentFile(b"ornek"), save=True)
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="JWT access token ve refresh token akisini anlatan teknik bolum.",
        meta={"quality_score": 0.86, "heading_score": 0.72},
        zorluk="zor",
        zorluk_skoru=0.78,
    )
    return doc, parca


def _create_boss_attempt(user, doc, *, correct: bool):
    boss = Boss.objects.create(ad=f"Boss {doc.id} {int(correct)}")
    soru = BossSoru.objects.create(
        boss=boss,
        tip="TEXT",
        soru_metni="Bu akis ne zaman kullanilir?",
        dogru_cevap_metni="Token yenileme akisinda kullanilir.",
        context_doc_id=doc.id,
        max_puan=100,
    )
    BossDeneme.objects.create(
        kullanici=user,
        boss=boss,
        soru=soru,
        cevap_metni="deneme",
        puan=100 if correct else 10,
        dogru_mu=correct,
        feedback="ok",
    )


def test_confusion_map_score_quiz_fail_ve_dwell_sinyalini_hesaplar(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca = _create_doc_with_parca(test_kullanicisi, title="Confusion Signals")
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc,
        parca=parca,
        adres=parca.adres,
        kullanici_mesaj="Bu token akisi neden tekrar ediyor?",
        cikti_text="Aciklama yetersiz kaldi.",
    )
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc,
        parca=parca,
        adres=parca.adres,
        kullanici_mesaj="Hala karisiyor.",
        cikti_text="Tekrar bakildi.",
    )

    guvenli_metrik_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="ai2_anlamadim_degerlendirildi",
        kaynak_modul="ai2.anlamadim",
        dokuman=doc,
        parca=parca,
        skor_ozeti={
            "completeness_score": 0.32,
            "fallback_json_kullanildi": True,
        },
    )
    guvenli_metrik_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="feedback_verildi",
        kaynak_modul="feedback.api",
        dokuman=doc,
        parca=parca,
        skor_ozeti={
            "feedback_weight_score": 0.28,
            "read_ratio": 1.4,
            "observed_read_seconds": 28.0,
        },
    )
    _create_boss_attempt(test_kullanicisi, doc, correct=False)
    _create_boss_attempt(test_kullanicisi, doc, correct=False)

    sonuc = compute_confusion_map_score(user=test_kullanicisi, dokuman=doc, parca=parca)

    assert 0.0 <= sonuc["confusion_map_score"] <= 1.0
    assert sonuc["confusion_map_score"] >= 0.35
    assert sonuc["confusion_quiz_fail_ratio"] >= 0.6
    assert sonuc["confusion_high_dwell_ratio"] > 0.0


def test_mastery_score_user_doc_baglaminda_quiz_ve_usefulness_ile_ayrisir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    good_doc, good_parca = _create_doc_with_parca(test_kullanicisi, title="Mastery Good")
    weak_doc, weak_parca = _create_doc_with_parca(test_kullanicisi, title="Mastery Weak")

    guvenli_metrik_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="ai2_cevap_degerlendirildi",
        kaynak_modul="ai2.kanitli_cevap",
        dokuman=good_doc,
        skor_ozeti={"usefulness_score_v2": 0.88, "supported": True},
    )
    guvenli_metrik_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="ai2_anlamadim_degerlendirildi",
        kaynak_modul="ai2.anlamadim",
        dokuman=good_doc,
        parca=good_parca,
        skor_ozeti={"completeness_score": 0.92},
    )
    _create_boss_attempt(test_kullanicisi, good_doc, correct=True)
    _create_boss_attempt(test_kullanicisi, good_doc, correct=True)

    guvenli_metrik_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="ai2_cevap_degerlendirildi",
        kaynak_modul="ai2.kanitli_cevap",
        dokuman=weak_doc,
        skor_ozeti={"usefulness_score_v2": 0.24, "supported": False},
    )
    guvenli_metrik_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="ai2_anlamadim_degerlendirildi",
        kaynak_modul="ai2.anlamadim",
        dokuman=weak_doc,
        parca=weak_parca,
        skor_ozeti={"completeness_score": 0.28, "fallback_json_kullanildi": True},
    )
    _create_boss_attempt(test_kullanicisi, weak_doc, correct=False)
    _create_boss_attempt(test_kullanicisi, weak_doc, correct=False)

    good = compute_mastery_score(user=test_kullanicisi, dokuman=good_doc)
    weak = compute_mastery_score(user=test_kullanicisi, dokuman=weak_doc)

    assert 0.0 <= weak["mastery_score"] <= 1.0
    assert 0.0 <= good["mastery_score"] <= 1.0
    assert good["mastery_score"] > weak["mastery_score"]
    assert good["mastery_quiz_success_ratio"] > weak["mastery_quiz_success_ratio"]


def test_guvenli_metric_store_allowlist_disinda_ham_alan_saklamaz(
    db,
    test_kullanicisi,
):
    kayit = guvenli_metrik_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="guvenlik_testi",
        kaynak_modul="tests.metric_store",
        skor_ozeti={
            "feedback_weight_score": 0.82,
            "format": "json",
            "ham_icerik": "Bu metin asla saklanmamalidir.",
            "nested_payload": {"raw": "hayir"},
        },
    )

    kayit.refresh_from_db()
    assert kayit.skor_ozeti["feedback_weight_score"] == 0.82
    assert kayit.skor_ozeti["format"] == "json"
    assert "ham_icerik" not in kayit.skor_ozeti
    assert "nested_payload" not in kayit.skor_ozeti
    assert "asla saklanmamalidir" not in str(kayit.skor_ozeti)

    assert MetrikKaydi.objects.filter(olay_turu="guvenlik_testi").count() == 1


def test_guvenli_metric_store_path_ve_hassas_label_degerlerini_redact_eder(
    db,
    test_kullanicisi,
):
    kayit = guvenli_metrik_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="guvenlik_path_testi",
        kaynak_modul="tests.metric_store",
        skor_ozeti={
            "format": r"C:\secret\raw\prompt.txt",
            "concept_a": r"C:\secret\ham_not.txt",
            "concept_pair": ["Refresh Token", "HAM_PORTAL_NOTE_SECRET veri alani"],
            "feedback_reason": "low_context_feedback",
        },
    )

    kayit.refresh_from_db()
    assert kayit.skor_ozeti["format"] == "[redacted]"
    assert "concept_a" not in kayit.skor_ozeti
    assert kayit.skor_ozeti.get("concept_pair") == ["Refresh Token"]
    assert kayit.skor_ozeti["feedback_reason"] == "low_context_feedback"
    assert "secret" not in str(kayit.skor_ozeti).lower()
