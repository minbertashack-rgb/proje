from __future__ import annotations

from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import (
    AnlamadimKaydi,
    Dokuman,
    DokumanNotu,
    KullaniciGeriBildirim,
    KullaniciTercih,
    MetrikKaydi,
    Not,
    Parca,
)
from dokuman.services.metric_store import (
    compute_feedback_weight_score,
)
from dokuman.services.study_summary import build_study_summary_payload
from oyun.models import Basarim, Boss, BossDeneme, BossSoru, KullaniciBasarim, OyunProfil


def _dokuman_ve_parcalar_olustur(kullanici, *, baslik: str = "Calisma Ozeti Testi"):
    doc = Dokuman.objects.create(
        owner=kullanici,
        baslik=baslik,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("summary-test.pdf", ContentFile(b"ornek"), save=True)
    parca1 = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="JWT access token kullanicinin kimligini tasir.",
        meta={"path": "1.1"},
        zorluk="orta",
        zorluk_skoru=0.52,
    )
    parca2 = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="1.2",
        metin="Refresh token yeni access token alma amaciyla kullanilir.",
        meta={"path": "1.2"},
        zorluk="zor",
        zorluk_skoru=0.88,
    )
    return doc, parca1, parca2


def _metric_kaydi_olustur(
    *,
    kullanici,
    olay_turu: str,
    dokuman=None,
    parca=None,
    ilgili_portal_not_id=None,
    skor_ozeti: dict | None = None,
    kaynak_modul: str = "analytics.test",
    durum: str = "ok",
):
    return MetrikKaydi.objects.create(
        kullanici=kullanici,
        dokuman=dokuman,
        parca=parca,
        ilgili_portal_not_id=ilgili_portal_not_id,
        olay_turu=olay_turu,
        kaynak_modul=kaynak_modul,
        skor_ozeti=skor_ozeti or {},
        durum=durum,
    )


def _boss_deneme_olustur(*, kullanici, dokuman, puan: int, dogru_mu: bool):
    boss = Boss.objects.create(ad=f"Boss {dokuman.id} {puan}")
    soru = BossSoru.objects.create(
        boss=boss,
        tip="TEXT",
        soru_metni="Bu bolum ne anlatiyor?",
        dogru_cevap_metni="Teknik akis anlatiliyor.",
        context_doc_id=dokuman.id,
        max_puan=100,
    )
    return BossDeneme.objects.create(
        kullanici=kullanici,
        boss=boss,
        soru=soru,
        cevap_metni="deneme",
        puan=puan,
        dogru_mu=dogru_mu,
        feedback="gizli kalmali",
    )


def _oyun_profil_olustur(*, kullanici, toplam_xp: int = 0, seviye: int = 1, streak_gun: int = 0):
    profil, _ = OyunProfil.objects.get_or_create(kullanici=kullanici)
    profil.toplam_xp = toplam_xp
    profil.seviye = seviye
    profil.streak_gun = streak_gun
    profil.save(update_fields=["toplam_xp", "seviye", "streak_gun"])
    return profil


def test_study_summary_uretimi_dokuman_baglaminda_calisir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    Not.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="JWT amaci",
        metin="JWT istemci ile sunucu arasinda kimlik bilgisini tasir.",
        pinned=True,
        kaynak_parca_idleri=[parca1.id],
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/calisma-ozeti/")

    assert response.status_code == 200
    data = response.data["calisma_ozeti"]
    assert data["dokuman_id"] == doc.id
    assert data["ana_maddeler"]
    kayit = MetrikKaydi.objects.get(olay_turu="study_summary_uretildi")
    assert kayit.dokuman_id == doc.id
    assert kayit.skor_ozeti["ana_madde_sayisi"] >= 1


def test_portal_nottan_study_summary_glossary_ve_bagli_parca_uretir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, parca2 = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    alt_not = Not.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="JWT notu",
        metin="JWT ve refresh token farkini ozetle.",
        pinned=True,
        kaynak_parca_idleri=[parca1.id, parca2.id],
    )
    portal_not = DokumanNotu.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Kimlik akisi calisma notu",
        icerik="JWT ve refresh token akisina odaklanan calisma notu.",
        pinned=True,
    )
    portal_not.bagli_notlar.set([alt_not])
    portal_not.kaynak_parcalar.set([parca1, parca2])
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        kullanici_mesaj="JWT ne ise yarar?",
        cikti_text="JWT kullaniciyi temsil eder.",
        cikti_json={
            "glossary": [
                {"term": "JWT", "definition": "Kimlik bilgisini tasiyan imzali token."},
            ]
        },
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(
        f"/api/dokuman-asistani/dokumanlar/{doc.id}/calisma-ozeti/?portal_not_id={portal_not.id}"
    )

    assert response.status_code == 200
    data = response.data["calisma_ozeti"]
    assert data["portal_not_id"] == portal_not.id
    assert data["baslik"] == "Kimlik akisi calisma notu"
    assert set(data["bagli_parca_idleri"]) == {parca1.id, parca2.id}
    assert data["glossary"][0]["terim"] == "JWT"


def test_cheatsheet_export_json_olusturur(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    Not.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Cheatsheet notu",
        metin="En kritik kavramlari bu notta topladim.",
        kaynak_parca_idleri=[parca1.id],
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/cheatsheet-export/?out=json")

    assert response.status_code == 200
    assert response.data["dokuman_id"] == doc.id
    assert "ana_maddeler" in response.data
    kayit = MetrikKaydi.objects.get(olay_turu="cheatsheet_export_uretildi")
    assert kayit.skor_ozeti["format"] == "json"


def test_cheatsheet_export_markdown_olusturur(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    portal_not = DokumanNotu.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Markdown portal",
        icerik="Markdown export icin sade bir portal not.",
    )
    portal_not.kaynak_parcalar.set([parca1])
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(
        f"/api/dokuman-asistani/dokumanlar/{doc.id}/cheatsheet-export/?out=md&portal_not_id={portal_not.id}"
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert content.startswith("# Markdown portal")
    assert "## Ana Maddeler" in content


def test_feedback_create_kaydi_ve_metric_olayini_uretir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    not_kaydi = Not.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Feedback notu",
        metin="Bu not uzerinden geri bildirim birakilacak.",
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    gizli_not = "Bu aciklama iyiydi ama bu cumle metrikte gorunmemeli."

    response = client.post(
        "/api/dokuman-asistani/feedback/",
        {
            "dokuman": doc.id,
            "parca": parca1.id,
            "not_kaydi": not_kaydi.id,
            "feedback_turu": "iyi",
            "kisa_not": gizli_not,
            "kaynak_modul": "study_summary.api",
            "okuma_suresi_saniye": 0,
        },
        format="json",
    )

    assert response.status_code == 201
    feedback = KullaniciGeriBildirim.objects.get(id=response.data["id"])
    assert feedback.feedback_turu == "iyi"
    kayit = MetrikKaydi.objects.get(olay_turu="feedback_verildi")
    assert kayit.ilgili_feedback_id == feedback.id
    assert kayit.skor_ozeti["feedback_turu"] == "iyi"
    assert "feedback_weight_score" in kayit.skor_ozeti
    assert kayit.skor_ozeti["feedback_ignored"] is True
    assert gizli_not not in str(kayit.skor_ozeti)


def test_feedback_list_kullanici_kapsaminda_calistir(
    db,
    test_kullanicisi,
    django_user_model,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    KullaniciGeriBildirim.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        feedback_turu="eksik",
        kaynak_modul="cheatsheet_export.api",
    )
    ikinci_kullanici = django_user_model.objects.create_user(
        username="feedback_diger_kullanici",
        password="12345678",
    )
    diger_doc, diger_parca, _ = _dokuman_ve_parcalar_olustur(ikinci_kullanici, baslik="Diger")
    KullaniciGeriBildirim.objects.create(
        owner=ikinci_kullanici,
        dokuman=diger_doc,
        parca=diger_parca,
        feedback_turu="kotu",
        kaynak_modul="study_summary.api",
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/feedback/")

    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["feedback_turu"] == "eksik"


def test_feature_flag_kapaliyken_summary_export_feedback_kontrollu_kapanir(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    doc, _, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    settings.DOCVERSE_STUDY_SUMMARY_ENABLED = False
    response_summary = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/calisma-ozeti/")
    assert response_summary.status_code == 404

    settings.DOCVERSE_CHEATSHEET_EXPORT_ENABLED = False
    response_export = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/cheatsheet-export/?out=json")
    assert response_export.status_code == 404

    settings.DOCVERSE_FEEDBACK_ENABLED = False
    response_feedback = client.get("/api/dokuman-asistani/feedback/")
    assert response_feedback.status_code == 404
    response_feedback_analytics = client.get("/api/dokuman-asistani/feedback/analytics/")
    assert response_feedback_analytics.status_code == 404

    settings.DOCVERSE_METRIC_STORE_ENABLED = False
    response_dashboard = client.get("/api/dokuman-asistani/dashboard/summary/")
    assert response_dashboard.status_code == 404
    response_dashboard_v2 = client.get("/api/dokuman-asistani/dashboard/summary/v2/")
    assert response_dashboard_v2.status_code == 404
    response_confusion = client.get("/api/dokuman-asistani/analytics/confusion-hotspots/")
    assert response_confusion.status_code == 404
    response_confusion_map = client.get("/api/dokuman-asistani/analytics/confusion-map/")
    assert response_confusion_map.status_code == 404
    response_kpi = client.get("/api/dokuman-asistani/analytics/kpi/")
    assert response_kpi.status_code == 404
    response_mastery = client.get("/api/dokuman-asistani/analytics/mastery-feedback-trust/")
    assert response_mastery.status_code == 404
    response_learning = client.get("/api/dokuman-asistani/analytics/learning-panel/")
    assert response_learning.status_code == 404
    response_quiz_boss = client.get("/api/dokuman-asistani/analytics/quiz-boss/")
    assert response_quiz_boss.status_code == 404

    settings.DOCVERSE_STYLE_CONSOLE_ENABLED = False
    response_style = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/style-console/")
    assert response_style.status_code == 404

    settings.DOCVERSE_DIRECTORS_CUT_ENABLED = False
    response_directors = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/directors-cut/")
    assert response_directors.status_code == 404

    settings.DOCVERSE_EXPORT_PLAN_ENABLED = False
    response_export_plan = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/export-plan/")
    assert response_export_plan.status_code == 404

    settings.DOCVERSE_EXCEL_MODES_ENABLED = False
    response_excel_modes = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/excel-modes/")
    assert response_excel_modes.status_code == 404

    settings.DOCVERSE_PREMIUM_UI_PAYLOADS_ENABLED = False
    response_premium = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/premium-payloads/")
    assert response_premium.status_code == 404

    settings.DOCVERSE_PERSONALIZATION_ENABLED = False
    response_preferences = client.get("/api/dokuman-asistani/tercih/")
    assert response_preferences.status_code == 404


def test_metric_store_summary_ve_export_icin_ham_icerik_saklamaz(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    ham_not = "Bu portal not icerigi metric store icine asla yazilmamali."
    portal_not = DokumanNotu.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Guvenli metric",
        icerik=ham_not,
    )
    portal_not.kaynak_parcalar.set([parca1])
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response_summary = client.get(
        f"/api/dokuman-asistani/dokumanlar/{doc.id}/calisma-ozeti/?portal_not_id={portal_not.id}"
    )
    response_export = client.get(
        f"/api/dokuman-asistani/dokumanlar/{doc.id}/cheatsheet-export/?out=json&portal_not_id={portal_not.id}"
    )

    assert response_summary.status_code == 200
    assert response_export.status_code == 200
    kayitlar = MetrikKaydi.objects.filter(olay_turu__in=["study_summary_uretildi", "cheatsheet_export_uretildi"])
    assert kayitlar.count() == 2
    for kayit in kayitlar:
        assert ham_not not in str(kayit.skor_ozeti)


def test_portal_not_detail_ve_update_basarili(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    portal_not = DokumanNotu.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Eski Baslik",
        icerik="Eski icerik",
    )
    
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.patch(
        f"/api/dokuman-asistani/portal-notlar/{portal_not.id}/",
        {"baslik": "Yeni Baslik", "icerik": "Guncel icerik, ayni baglam."},
        format="json",
    )

    assert response.status_code == 200
    portal_not.refresh_from_db()
    assert portal_not.baslik == "Yeni Baslik"
    assert portal_not.icerik == "Guncel icerik, ayni baglam."


def test_portal_not_update_farkli_dokumana_tasinamaz(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc1, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Doc 1")
    doc2, _, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Doc 2")
    portal_not = DokumanNotu.objects.create(
        owner=test_kullanicisi,
        dokuman=doc1,
        baslik="Tasima Testi",
        icerik="Icerik",
    )
    
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.patch(
        f"/api/dokuman-asistani/portal-notlar/{portal_not.id}/",
        {"dokuman": doc2.id},
        format="json",
    )

    assert response.status_code == 400
    assert "baglami degistirilemez" in str(response.data).lower()


def test_cheatsheet_export_manifest_icerir_ve_ham_veri_tasimaz(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/cheatsheet-export/?out=json")

    assert response.status_code == 200
    assert "manifest" in response.data
    manifest = response.data["manifest"]
    assert "kullanilan_parca_sayisi" in manifest
    assert manifest["format"] == "json"


def test_feedback_list_filtreleme_calisir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    KullaniciGeriBildirim.objects.create(owner=test_kullanicisi, dokuman=doc, feedback_turu="iyi", kaynak_modul="modul_A")
    KullaniciGeriBildirim.objects.create(owner=test_kullanicisi, dokuman=doc, feedback_turu="eksik", kaynak_modul="modul_B")
    KullaniciGeriBildirim.objects.create(owner=test_kullanicisi, dokuman=doc, feedback_turu="eksik", kaynak_modul="modul_A")

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get("/api/dokuman-asistani/feedback/?feedback_turu=eksik&kaynak_modul=modul_A")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["feedback_turu"] == "eksik"


def test_feedback_analytics_guvenli_calisir_ham_veri_yok(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    KullaniciGeriBildirim.objects.create(owner=test_kullanicisi, dokuman=doc, feedback_turu="iyi", kisa_not="Ham icerik 1", kaynak_modul="modul_A")
    KullaniciGeriBildirim.objects.create(owner=test_kullanicisi, dokuman=doc, feedback_turu="eksik", kisa_not="Ham icerik 2", kaynak_modul="modul_B")

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get("/api/dokuman-asistani/feedback/analytics/")
    assert response.status_code == 200
    data = response.data
    assert data["toplam_feedback"] == 2
    assert "Ham icerik" not in str(data)
    
    turu_dagilimi = {d["feedback_turu"]: d["adet"] for d in data["feedback_turu_dagilimi"]}
    assert turu_dagilimi["iyi"] == 1
    assert turu_dagilimi["eksik"] == 1
    assert "dokuman_dagilimi" in data
    assert "son_gun_trendi" in data
    assert any(item["adet"] >= 0 for item in data["son_gun_trendi"])


def test_feedback_analytics_v2_filtreli_oranli_ve_guvenli_calisir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, _, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    KullaniciGeriBildirim.objects.create(owner=test_kullanicisi, dokuman=doc, feedback_turu="iyi", kisa_not="ham 1", kaynak_modul="study_summary.api")
    KullaniciGeriBildirim.objects.create(owner=test_kullanicisi, dokuman=doc, feedback_turu="iyi", kisa_not="ham 2", kaynak_modul="study_summary.api")
    KullaniciGeriBildirim.objects.create(owner=test_kullanicisi, dokuman=doc, feedback_turu="eksik", kisa_not="ham 3", kaynak_modul="cheatsheet_export.api")

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(f"/api/dokuman-asistani/feedback/analytics/?dokuman={doc.id}")

    assert response.status_code == 200
    data = response.data
    assert data["toplam_feedback"] == 3
    iyi = next(item for item in data["feedback_turu_dagilimi"] if item["feedback_turu"] == "iyi")
    assert iyi["adet"] == 2
    assert iyi["oran"] > 0.6
    assert "ham 1" not in str(data)


def test_feedback_analytics_feedback_trust_ratio_metric_store_uzerinden_hesaplar(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    not_kaydi = Not.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Uzun feedback baglami",
        metin=" ".join(["JWT", "refresh", "token", "guvenlik", "akis"] * 25),
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    client.post(
        "/api/dokuman-asistani/feedback/",
        {
            "dokuman": doc.id,
            "not_kaydi": not_kaydi.id,
            "feedback_turu": "iyi",
            "kaynak_modul": "study_summary.api",
            "okuma_suresi_saniye": 1,
        },
        format="json",
    )
    client.post(
        "/api/dokuman-asistani/feedback/",
        {
            "dokuman": doc.id,
            "not_kaydi": not_kaydi.id,
            "feedback_turu": "iyi",
            "kaynak_modul": "study_summary.api",
            "okuma_suresi_saniye": 40,
        },
        format="json",
    )

    response = client.get("/api/dokuman-asistani/feedback/analytics/")

    assert response.status_code == 200
    data = response.data
    assert data["trusted_feedback"] == 1
    assert 0.49 <= data["feedback_trust_ratio"] <= 0.51


def test_dashboard_summary_endpoint_agregat_ve_guvenli_doner(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    Not.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Dashboard notu",
        metin="Bu not dashboard endpointine ham olarak sizmamali.",
    )
    portal_not = DokumanNotu.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Dashboard portal",
        icerik="Bu portal not da dashboard cevabina ham olarak girmemeli.",
    )
    KullaniciGeriBildirim.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        feedback_turu="iyi",
        kisa_not="Gizli feedback metni",
        kaynak_modul="study_summary.api",
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/calisma-ozeti/?portal_not_id={portal_not.id}")
    client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/cheatsheet-export/?out=json&portal_not_id={portal_not.id}")

    response = client.get("/api/dokuman-asistani/dashboard/summary/")

    assert response.status_code == 200
    data = response.data
    assert data["toplam_not_sayisi"] == 1
    assert data["toplam_portal_not_sayisi"] == 1
    assert data["toplam_feedback"] == 1
    assert "feedback_trust_ratio" in data
    assert "net_usefulness_score" in data
    assert "cheatsheet_yield" in data
    assert data["study_summary_kullanimi"]["toplam_uretim"] == 1
    assert data["study_summary_kullanimi"]["portal_not_bazli_kullanim"] == 1
    assert data["cheatsheet_export_kullanimi"]["toplam_export"] == 1
    assert data["cheatsheet_export_kullanimi"]["portal_not_bazli_kullanim"] == 1
    assert data["cheatsheet_export_kullanimi"]["format_dagilimi"][0]["format"] == "json"
    assert "gecerli_feedback_orani" in data
    assert "dusuk_fayda_orani" in data
    assert "yuksek_confusion_parca_sayisi" in data
    assert "Gizli feedback metni" not in str(data)
    assert "ham olarak" not in str(data)


def test_dashboard_summary_metric_store_uzerinden_usage_sayar(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    portal_not = DokumanNotu.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Usage portal",
        icerik="Usage testi",
    )
    portal_not.kaynak_parcalar.set([parca1])

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/calisma-ozeti/?portal_not_id={portal_not.id}")
    client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/calisma-ozeti/?portal_not_id={portal_not.id}")
    client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/cheatsheet-export/?out=json")
    client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/cheatsheet-export/?out=md&portal_not_id={portal_not.id}")

    response = client.get("/api/dokuman-asistani/dashboard/summary/")

    assert response.status_code == 200
    data = response.data
    assert data["study_summary_kullanimi"]["toplam_uretim"] == 2
    assert data["cheatsheet_export_kullanimi"]["toplam_export"] == 2
    format_dagilimi = {item["format"]: item["adet"] for item in data["cheatsheet_export_kullanimi"]["format_dagilimi"]}
    assert format_dagilimi["json"] == 1
    assert format_dagilimi["md"] == 1


def test_dashboard_summary_v2_sade_stabil_ve_agregat_doner(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Summary V2")
    Not.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Ham not basligi",
        metin="Bu not metni asla dashboard v2 response icinde gorunmemeli.",
    )
    KullaniciGeriBildirim.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        feedback_turu="eksik",
        kisa_not="Ham feedback v2",
        kaynak_modul="study_summary.api",
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="feedback_verildi",
        dokuman=doc,
        parca=parca1,
        skor_ozeti={
            "feedback_weight_score": 0.82,
            "feedback_ignored": False,
            "feedback_reason": "trusted_feedback",
            "confusion_map_score": 0.78,
        },
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="ai2_cevap_degerlendirildi",
        dokuman=doc,
        parca=parca1,
        skor_ozeti={
            "usefulness_score_v2": 0.31,
            "confusion_map_score": 0.76,
        },
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/dashboard/summary/v2/")

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "toplam_not_sayisi",
        "toplam_portal_not_sayisi",
        "toplam_feedback",
        "son_7_gun_feedback",
        "study_summary_kullanimi",
        "cheatsheet_export_kullanimi",
        "feedback_turu_dagilimi",
        "kaynak_modul_dagilimi",
        "gecerli_feedback_orani",
        "dusuk_fayda_orani",
        "yuksek_confusion_parca_sayisi",
        "feedback_trust_ratio",
        "net_usefulness_score",
        "cheatsheet_yield",
    }
    assert data["toplam_not_sayisi"] == 1
    assert data["toplam_feedback"] == 1
    assert data["gecerli_feedback_orani"] == 1.0
    assert data["dusuk_fayda_orani"] == 1.0
    assert data["yuksek_confusion_parca_sayisi"] == 1
    assert "Ham feedback v2" not in str(data)
    assert "dashboard v2 response" not in str(data)


def test_confusion_hotspot_analytics_guvenli_ve_agregat_calisir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc1, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Sorunlu Dokuman")
    doc2, parca2, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Daha Sakin Dokuman")

    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="study_summary_uretildi",
        dokuman=doc1,
        parca=parca1,
        skor_ozeti={"confusion_map_score": 0.83},
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="feedback_verildi",
        dokuman=doc1,
        parca=parca1,
        skor_ozeti={"confusion_map_score": 0.74, "feedback_weight_score": 0.84},
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="study_summary_uretildi",
        dokuman=doc2,
        parca=parca2,
        skor_ozeti={"confusion_map_score": 0.22},
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/analytics/confusion-hotspots/")

    assert response.status_code == 200
    data = response.data
    assert data["yuksek_confusion_parca_sayisi"] == 1
    assert data["top_problemli_dokumanlar"][0]["dokuman_id"] == doc1.id
    assert data["top_problemli_dokumanlar"][0]["baslik"] == "Sorunlu Dokuman"
    assert "JWT access token kullanicinin kimligini tasir." not in str(data)
    assert "Refresh token yeni access token alma amaciyla kullanilir." not in str(data)


def test_mastery_feedback_trust_analytics_guvenli_ve_metric_store_uzerinden_uretilir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc1, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Yuksek Mastery")
    doc2, parca2, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Dusuk Mastery")

    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="ai2_cevap_degerlendirildi",
        dokuman=doc1,
        parca=parca1,
        skor_ozeti={"usefulness_score_v2": 0.88, "confusion_map_score": 0.12},
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="ai2_anlamadim_degerlendirildi",
        dokuman=doc1,
        parca=parca1,
        skor_ozeti={"completeness_score": 0.8, "confusion_map_score": 0.16},
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="ai2_cevap_degerlendirildi",
        dokuman=doc2,
        parca=parca2,
        skor_ozeti={
            "usefulness_score_v2": 0.0,
            "confusion_map_score": 0.82,
            "supported": False,
            "hallucination_risk": 0.91,
        },
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="ai2_anlamadim_degerlendirildi",
        dokuman=doc2,
        parca=parca2,
        skor_ozeti={
            "completeness_score": 0.0,
            "confusion_map_score": 0.86,
            "fallback_json_kullanildi": True,
        },
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="study_summary_uretildi",
        dokuman=doc2,
        parca=parca2,
        skor_ozeti={"confusion_map_score": 0.78},
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="study_summary_uretildi",
        dokuman=doc2,
        parca=parca2,
        skor_ozeti={"confusion_map_score": 0.8},
    )
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc2,
        parca=parca2,
        adres=parca2.adres,
        kullanici_mesaj="Bu kisim zor geldi",
        cikti_text="Yetersiz cevap",
    )
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc2,
        parca=parca2,
        adres=parca2.adres,
        kullanici_mesaj="Hala net degil",
        cikti_text="Tekrar baktim",
    )
    KullaniciGeriBildirim.objects.create(
        owner=test_kullanicisi,
        dokuman=doc2,
        parca=parca2,
        feedback_turu="alakasiz",
        kisa_not="Ham geri bildirim gizli kalmali",
        kaynak_modul="study_summary.api",
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="feedback_verildi",
        dokuman=doc1,
        parca=parca1,
        skor_ozeti={
            "feedback_weight_score": 0.82,
            "feedback_ignored": False,
            "feedback_reason": "trusted_feedback",
        },
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="feedback_verildi",
        dokuman=doc2,
        parca=parca2,
        skor_ozeti={
            "feedback_weight_score": 0.18,
            "feedback_ignored": True,
            "feedback_reason": "burst_feedback",
        },
        durum="ignored",
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/analytics/mastery-feedback-trust/")

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {"mastery_summary", "feedback_trust"}
    assert len(data["mastery_summary"]["dokuman_bazli_ortalama_mastery"]) == 2
    assert data["mastery_summary"]["yuksek_mastery_orani"] == 0.5
    assert data["mastery_summary"]["dusuk_mastery_orani"] == 0.5
    assert data["feedback_trust"]["gecerli_feedback_sayisi"] == 1
    assert data["feedback_trust"]["ignore_edilen_feedback_orani"] == 0.5
    assert data["feedback_trust"]["hizli_oy_orani"] == 0.5
    assert "JWT access token kullanicinin kimligini tasir." not in str(data)


def test_kpi_paneli_yalniz_agregat_ve_stabil_alanlar_doner(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="KPI Dokuman")
    parca1.meta = {"is_cheatsheet": True}
    parca1.save(update_fields=["meta"])

    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="ai2_cevap_degerlendirildi",
        dokuman=doc,
        parca=parca1,
        skor_ozeti={"usefulness_score_v2": 0.72, "confusion_map_score": 0.44},
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="feedback_verildi",
        dokuman=doc,
        parca=parca1,
        skor_ozeti={
            "feedback_weight_score": 0.64,
            "feedback_ignored": False,
            "feedback_reason": "standard_feedback",
        },
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/analytics/kpi/")

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "net_usefulness_score",
        "global_confusion_index",
        "feedback_trust_ratio",
        "cheatsheet_yield",
    }
    assert data["net_usefulness_score"] == 0.72
    assert data["global_confusion_index"] == 0.44
    assert data["feedback_trust_ratio"] == 1.0
    assert data["cheatsheet_yield"] == 0.5
    assert "KPI Dokuman" not in str(data)


def test_feedback_flag_kapaliyken_mastery_endpoint_kontrollu_sifirlar_doner(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Flag Dokuman")
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="ai2_cevap_degerlendirildi",
        dokuman=doc,
        parca=parca1,
        skor_ozeti={"usefulness_score_v2": 0.68, "confusion_map_score": 0.22},
    )

    settings.DOCVERSE_FEEDBACK_ENABLED = False

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/analytics/mastery-feedback-trust/")

    assert response.status_code == 200
    data = response.data
    assert data["feedback_trust"]["gecerli_feedback_sayisi"] == 0
    assert data["feedback_trust"]["ignore_edilen_feedback_orani"] == 0.0
    assert data["feedback_trust"]["hizli_oy_orani"] == 0.0


def test_feedback_weight_score_hizli_spam_oylari_dusurur(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    okunmus = compute_feedback_weight_score(
        user=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        feedback_turu="iyi",
        kisa_not_uzunlugu=32,
        okuma_suresi_saniye=38,
        beklenen_okuma_suresi_saniye=24,
    )
    hizli = compute_feedback_weight_score(
        user=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        feedback_turu="iyi",
        kisa_not_uzunlugu=6,
        okuma_suresi_saniye=1,
        beklenen_okuma_suresi_saniye=24,
    )
    for idx in range(4):
        KullaniciGeriBildirim.objects.create(
            owner=test_kullanicisi,
            dokuman=doc,
            parca=parca1,
            feedback_turu="iyi",
            kisa_not=f"spam-{idx}",
            kaynak_modul="study_summary.api",
        )

    dusuk = compute_feedback_weight_score(
        user=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        feedback_turu="iyi",
        kisa_not_uzunlugu=2,
        okuma_suresi_saniye=1,
        beklenen_okuma_suresi_saniye=24,
    )

    assert okunmus["feedback_weight_score"] > hizli["feedback_weight_score"]
    assert hizli["feedback_weight_reason"] == "too_fast_feedback"
    assert hizli["feedback_weight_score"] > dusuk["feedback_weight_score"]
    assert dusuk["feedback_weight_reason"] == "burst_feedback"


def test_study_summary_importance_secimi_daha_onemli_notu_one_cikarir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, parca2 = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Importance")
    parca2.meta = {
        "quality_score": 0.92,
        "difficulty_score": 0.81,
        "heading_score": 0.76,
    }
    parca2.save(update_fields=["meta"])

    Not.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca2,
        adres=parca2.adres,
        baslik="Refresh token karar noktasi",
        metin="Refresh token hangi kosulda yenileme akisina girdigini aciklar.",
        kaynak_parca_idleri=[parca2.id],
    )
    Not.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Daha yeni ama daha zayif not",
        metin="Genel bir tekrar notu.",
        kaynak_parca_idleri=[parca1.id],
    )
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc,
        parca=parca2,
        adres=parca2.adres,
        kullanici_mesaj="Refresh token neden gerekli?",
        cikti_text="Tekrar bakildi.",
    )
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc,
        parca=parca2,
        adres=parca2.adres,
        kullanici_mesaj="Bu kisim halen karisik.",
        cikti_text="Bir kez daha aciklama istendi.",
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/calisma-ozeti/")

    assert response.status_code == 200
    assert response.data["calisma_ozeti"]["ana_maddeler"][0] == "Refresh token karar noktasi"
    kayit = MetrikKaydi.objects.get(olay_turu="study_summary_uretildi")
    assert "study_summary_importance_score" in kayit.skor_ozeti
    assert "Refresh token hangi kosulda yenileme akisina girdigini aciklar." not in str(kayit.skor_ozeti)


def test_study_summary_importance_gecmis_kullanim_sinyaliyle_parcayi_one_cikarir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, parca2 = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Usage Driven Summary")
    parca1.meta = {
        "quality_score": 0.93,
        "difficulty_score": 0.68,
        "heading_score": 0.78,
    }
    parca1.save(update_fields=["meta"])
    parca2.meta = {
        "quality_score": 0.72,
        "difficulty_score": 0.61,
        "heading_score": 0.58,
        "final_rerank_avg": 0.84,
    }
    parca2.save(update_fields=["meta"])

    for _ in range(3):
        AnlamadimKaydi.objects.create(
            kullanici=test_kullanicisi,
            dokuman=doc,
            parca=parca2,
            adres=parca2.adres,
            kullanici_mesaj="Bu parcaya tekrar donuyorum.",
            cikti_text="Karisiklik devam ediyor.",
        )

    payload = build_study_summary_payload(doc=doc, user=test_kullanicisi)

    assert payload["bagli_parca_idleri"][0] == parca2.id


def test_cheatsheet_priority_kisa_teknik_parcayi_one_cikarir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Cheatsheet Priority",
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("cheatsheet-priority.pdf", ContentFile(b"ornek"), save=True)
    uzun = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="2.1",
        metin="Bu parca uzun ve genel bir aciklama sunar. Cok sayida cumle ile konuyu tekrar eder ancak teknik yogunlugu dusuktur.",
        meta={"quality_score": 0.91},
        zorluk_skoru=0.95,
        zorluk="zor",
    )
    teknik = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="2.2",
        metin="JWT exp=3600, aud=api, sub=user_42.",
        meta={"quality_score": 0.74},
        zorluk_skoru=0.32,
        zorluk="orta",
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/cheatsheet-export/?out=json")

    assert response.status_code == 200
    assert response.data["bagli_parca_idleri"][0] == teknik.id
    assert response.data["bagli_parca_idleri"][1] == uzun.id
    kayit = MetrikKaydi.objects.get(olay_turu="cheatsheet_export_uretildi")
    assert "cheatsheet_priority_score" in kayit.skor_ozeti
    assert "JWT exp=3600" not in str(kayit.skor_ozeti)


def test_study_summary_importance_heading_ve_rerank_sinyaliyle_parca_secebilir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, parca2 = _dokuman_ve_parcalar_olustur(test_kullanicisi)
    parca1.meta = {
        "heading_score": 0.15,
        "difficulty_score": 0.20,
        "final_rerank_avg": 0.10,
    }
    parca1.save(update_fields=["meta"])
    parca2.meta = {
        "heading_score": 0.92,
        "difficulty_score": 0.65,
        "final_rerank_avg": 0.88,
        "is_cheatsheet": True,
    }
    parca2.save(update_fields=["meta"])

    payload = build_study_summary_payload(doc=doc, user=test_kullanicisi)

    assert parca2.id in payload["bagli_parca_idleri"]
    assert payload["bagli_parca_idleri"][0] == parca2.id


def test_confusion_map_endpoint_guvenli_ve_sade_calisir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc1, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Confusion Map A")
    doc2, parca2, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Confusion Map B")
    parca1.meta = {"heading": "JWT Akisi"}
    parca2.meta = {"heading": "Refresh Kontrolu"}
    parca1.save(update_fields=["meta"])
    parca2.save(update_fields=["meta"])

    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="feedback_verildi",
        dokuman=doc1,
        parca=parca1,
        skor_ozeti={"confusion_map_score": 0.84, "feedback_weight_score": 0.82},
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="study_summary_uretildi",
        dokuman=doc1,
        parca=parca1,
        skor_ozeti={"confusion_map_score": 0.74},
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="feedback_verildi",
        dokuman=doc2,
        parca=parca2,
        skor_ozeti={"confusion_map_score": 0.21, "feedback_weight_score": 0.72},
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/analytics/confusion-map/")

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "problemli_parca_sayisi",
        "top_problemli_parcalar",
        "dokuman_bazli_confusion_yogunlugu",
    }
    assert data["problemli_parca_sayisi"] == 1
    assert data["top_problemli_parcalar"][0]["id"] == parca1.id
    assert data["top_problemli_parcalar"][0]["adres"] == parca1.adres
    assert data["top_problemli_parcalar"][0]["baslik"] == "JWT Akisi"
    assert "JWT access token kullanicinin kimligini tasir." not in str(data)
    assert "Refresh token yeni access token alma amaciyla kullanilir." not in str(data)


def test_quiz_boss_urun_yuzeyi_agregat_veri_doner(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_QUIZ_ENABLED = True
    settings.DOCVERSE_BOSS_ENABLED = True

    doc, parca1, parca2 = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Quiz Boss")
    parca1.meta = {"quiz_ready": True, "quiz_readiness_score": 0.84, "heading": "Hazir Parca"}
    parca2.meta = {"quiz_ready": False, "heading": "Zor Parca"}
    parca1.save(update_fields=["meta"])
    parca2.zorluk_skoru = 0.92
    parca2.save(update_fields=["meta", "zorluk_skoru"])

    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="feedback_verildi",
        dokuman=doc,
        parca=parca2,
        skor_ozeti={"confusion_map_score": 0.81, "feedback_weight_score": 0.74},
    )
    _boss_deneme_olustur(kullanici=test_kullanicisi, dokuman=doc, puan=90, dogru_mu=True)
    _boss_deneme_olustur(kullanici=test_kullanicisi, dokuman=doc, puan=10, dogru_mu=False)

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/analytics/quiz-boss/")

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "quiz_hazir_parca_sayisi",
        "boss_adayi_parca_sayisi",
        "son_denemeler_ozeti",
        "basari_orani",
    }
    assert data["quiz_hazir_parca_sayisi"] == 1
    assert data["boss_adayi_parca_sayisi"] >= 1
    assert len(data["son_denemeler_ozeti"]) == 2
    assert data["basari_orani"] == 0.5
    assert "feedback" not in str(data).lower()
    assert "JWT access token kullanicinin kimligini tasir." not in str(data)


def test_portal_note_calisma_paneli_guvenli_ve_modul_iliskili_doner(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Portal Panel")
    alt_not = Not.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Alt Not",
        metin="Bu alt not panel response icine ham olarak girmemeli.",
    )
    portal_not = DokumanNotu.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Merkez Not",
        icerik="Bu portal not icerigi response icine ham olarak girmemeli.",
    )
    portal_not.bagli_notlar.set([alt_not])
    portal_not.kaynak_parcalar.set([parca1])
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="study_summary_uretildi",
        dokuman=doc,
        ilgili_portal_not_id=portal_not.id,
        skor_ozeti={"portal_not_var_mi": True},
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="cheatsheet_export_uretildi",
        dokuman=doc,
        ilgili_portal_not_id=portal_not.id,
        skor_ozeti={"portal_not_var_mi": True, "format": "json"},
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="feedback_verildi",
        dokuman=doc,
        ilgili_portal_not_id=portal_not.id,
        skor_ozeti={"feedback_weight_score": 0.82, "feedback_ignored": False},
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get(f"/api/dokuman-asistani/portal-notlar/{portal_not.id}/calisma-paneli/")

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "portal_not_id",
        "bagli_not_sayisi",
        "kaynak_parca_sayisi",
        "summary_var_mi",
        "cheatsheet_var_mi",
        "son_feedback_sinyali",
        "son_kullanim_sinyali",
    }
    assert data["portal_not_id"] == portal_not.id
    assert data["bagli_not_sayisi"] == 1
    assert data["kaynak_parca_sayisi"] == 1
    assert data["summary_var_mi"] is True
    assert data["cheatsheet_var_mi"] is True
    assert data["son_feedback_sinyali"]["toplam_feedback"] == 1
    assert data["son_kullanim_sinyali"]["study_summary_sayisi"] == 1
    assert "ham olarak" not in str(data)


def test_ogrenme_paneli_metric_store_uzerinden_kpi_uretir(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_QUIZ_ENABLED = True

    doc, parca1, parca2 = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Learning Panel")
    parca1.meta = {"quiz_ready": True, "quiz_readiness_score": 0.91}
    parca2.meta = {"quiz_ready": False, "quiz_readiness_score": 0.12}
    parca1.save(update_fields=["meta"])
    parca2.save(update_fields=["meta"])

    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="ai2_cevap_degerlendirildi",
        dokuman=doc,
        parca=parca1,
        skor_ozeti={"usefulness_score_v2": 0.74, "confusion_map_score": 0.28},
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="feedback_verildi",
        dokuman=doc,
        parca=parca1,
        skor_ozeti={"feedback_weight_score": 0.68, "feedback_ignored": False},
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/analytics/learning-panel/")

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "ortalama_confusion",
        "ortalama_mastery",
        "quiz_ready_orani",
        "gecerli_feedback_orani",
        "net_usefulness",
    }
    assert data["ortalama_confusion"] == 0.28
    assert data["quiz_ready_orani"] == 0.5
    assert data["gecerli_feedback_orani"] == 1.0
    assert data["net_usefulness"] == 0.74


def test_quiz_boss_flag_kapaliyken_urun_yuzeyi_kontrollu_sifir_doner(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_QUIZ_ENABLED = False
    settings.DOCVERSE_BOSS_ENABLED = False

    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Disabled Quiz Boss")
    parca1.meta = {"quiz_ready": True, "quiz_readiness_score": 0.95}
    parca1.save(update_fields=["meta"])
    _boss_deneme_olustur(kullanici=test_kullanicisi, dokuman=doc, puan=100, dogru_mu=True)

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/analytics/quiz-boss/")

    assert response.status_code == 200
    data = response.data
    assert data["quiz_hazir_parca_sayisi"] == 0
    assert data["boss_adayi_parca_sayisi"] == 0
    assert data["son_denemeler_ozeti"] == []
    assert data["basari_orani"] == 0.0


def test_style_console_endpoint_calisir_ve_ham_icerik_sizdirmaz(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Style Console")
    Not.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="JWT Kimlik Akisi",
        metin="HAM_STYLE_GIZLI ifadesi response icinde gorunmemeli.",
        pinned=False,
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/dokumanlar/%s/style-console/?stil=akis&ton=sunum" % doc.id)

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "dokuman_id",
        "portal_not_id",
        "stil",
        "ton",
        "baslik",
        "acilis",
        "maddeler",
        "vurgular",
        "kaynak_parca_idleri",
    }
    assert data["stil"] == "akis"
    assert data["ton"] == "sunum"
    assert data["dokuman_id"] == doc.id
    assert "HAM_STYLE_GIZLI" not in str(data)


def test_directors_cut_payloadlari_guvenli_uretilir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Directors")
    Not.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Refresh Geçişi",
        metin="HAM_DIRECTORS_GIZLI response icinde olmamali.",
        pinned=False,
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/dokumanlar/%s/directors-cut/?mod=exam_cut" % doc.id)

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "dokuman_id",
        "portal_not_id",
        "mod",
        "baslik",
        "ana_maddeler",
        "kritik_noktalar",
        "tuzaklar",
        "sorulabilecekler",
        "kaynak_parca_idleri",
    }
    assert data["mod"] == "exam_cut"
    assert "HAM_DIRECTORS_GIZLI" not in str(data)


def test_xp_paneli_agregat_ve_guvenli_veri_doner(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    _oyun_profil_olustur(kullanici=test_kullanicisi, toplam_xp=320, seviye=4, streak_gun=6)
    basari = Basarim.objects.create(
        kod="BOSS_2",
        ad="Ikinci Boss",
        kosul_tur=Basarim.KOSUL_BOSS_TAMAMLAMA,
        kosul_deger=2,
    )
    KullaniciBasarim.objects.create(kullanici=test_kullanicisi, basarim=basari)

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/analytics/xp-panel/")

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "toplam_xp",
        "seviye",
        "unvan",
        "basari_sayisi",
        "son_kazanilan_basari",
        "streak_bilgisi",
    }
    assert data["toplam_xp"] == 320
    assert data["seviye"] == 4
    assert data["basari_sayisi"] == 1
    assert data["son_kazanilan_basari"]["kod"] == "BOSS_2"
    assert data["streak_bilgisi"]["streak_gun"] == 6


def test_export_plan_payloadi_uretilir_ve_ham_icerik_tasimaZ(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Export Plan")
    Not.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca1,
        adres=parca1.adres,
        baslik="Token Özeti",
        metin="HAM_EXPORT_PLAN_GIZLI response icinde olmamali.",
        pinned=False,
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get("/api/dokuman-asistani/dokumanlar/%s/export-plan/?plan_turu=slayt" % doc.id)

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "dokuman_id",
        "portal_not_id",
        "baslik",
        "plan_turu",
        "slayt_plani",
        "bolum_plani",
    }
    assert data["plan_turu"] == "slayt"
    assert len(data["slayt_plani"]) >= 1
    assert data["bolum_plani"] == []
    assert "HAM_EXPORT_PLAN_GIZLI" not in str(data)


def test_excel_ozel_mod_payloadi_uretilir_ve_ham_icerik_sizdirmaz(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, parca2 = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Excel Surface")
    parca1.tur = "tablo"
    parca1.meta = {
        "path": "1.1",
        "row_count": 18,
        "column_count": 5,
        "formula_count": 6,
    }
    parca1.metin = "HAM_EXCEL_GIZLI satir bazli veri response icine girmemeli."
    parca1.save(update_fields=["tur", "meta", "metin"])
    parca2.tur = "tablo"
    parca2.meta = {
        "path": "1.2",
        "row_count": 10,
        "column_count": 4,
        "chart_count": 1,
    }
    parca2.save(update_fields=["tur", "meta"])

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/excel-modes/?mod=formul_aciklayici")

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "dokuman_id",
        "portal_not_id",
        "mod",
        "baslik",
        "kartlar",
        "oneriler",
        "kaynak_parca_idleri",
    }
    assert data["dokuman_id"] == doc.id
    assert data["mod"] == "formul_aciklayici"
    assert any(item["etiket"] == "formul_hucresi_tahmini" for item in data["kartlar"])
    assert "HAM_EXCEL_GIZLI" not in str(data)


def test_export_manifest_v2_guvenli_ve_stabil_payload_uretir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Manifest V2")
    parca1.metin = "HAM_MANIFEST_GIZLI export manifest icinde gorunmemeli."
    parca1.save(update_fields=["metin"])

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/export-manifest-v2/?format=pptx")

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "dokuman_id",
        "portal_not_id",
        "baslik",
        "hedef_format",
        "bolumler",
        "kaynak_parca_idleri",
        "ozet_kaynaklari",
        "konusma_notu_var_mi",
        "tahmini_slayt_sayisi",
        "tahmini_bolum_sayisi",
    }
    assert data["hedef_format"] == "pptx"
    assert data["konusma_notu_var_mi"] is True
    assert data["tahmini_slayt_sayisi"] >= 1
    assert "HAM_MANIFEST_GIZLI" not in str(data)


def test_premium_payload_yuzeyi_guvenli_sade_ve_metric_destekli_doner(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca1, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Premium Surface")
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="quiz_readiness_degerlendirildi",
        dokuman=doc,
        parca=parca1,
        skor_ozeti={"quiz_readiness_score": 0.81, "confusion_map_score": 0.24},
    )
    _metric_kaydi_olustur(
        kullanici=test_kullanicisi,
        olay_turu="study_summary_uretildi",
        dokuman=doc,
        parca=parca1,
        skor_ozeti={"confusion_map_score": 0.18},
    )

    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/premium-payloads/")

    assert response.status_code == 200
    data = response.data
    assert set(data.keys()) == {
        "dokuman_id",
        "portal_not_id",
        "spotlight_payload",
        "teleport_links",
        "cevap_bilekligi_gostergeleri",
    }
    assert set(data["spotlight_payload"].keys()) == {
        "baslik",
        "netlik_gostergesi",
        "ornek_gostergesi",
        "test_gostergesi",
        "highlight_parca_idleri",
    }
    assert len(data["teleport_links"]) == 3
    assert {item["kod"] for item in data["cevap_bilekligi_gostergeleri"]} == {"netlik", "ornek", "test"}
    assert "JWT access token kullanicinin kimligini tasir." not in str(data)


def test_kisisellestirme_tercihi_kaydedilir_okunur_ve_guvenli_metric_yazar(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response_post = client.post(
        "/api/dokuman-asistani/tercih/",
        {
            "tema": "oyun",
            "ton": "kanka",
            "detay_seviyesi": "yuksek",
            "mizah_seviyesi": "hafif",
        },
        format="json",
    )
    response_get = client.get("/api/dokuman-asistani/tercih/")

    assert response_post.status_code == 200
    assert response_get.status_code == 200
    assert set(response_get.data.keys()) == {
        "tema",
        "tarz",
        "seviye",
        "ton",
        "detay_seviyesi",
        "mizah_seviyesi",
    }
    assert response_get.data["tema"] == "oyun"
    assert response_get.data["ton"] == "kanka"
    assert response_get.data["detay_seviyesi"] == "yuksek"
    assert response_get.data["mizah_seviyesi"] == "hafif"

    tercih = KullaniciTercih.objects.get(kullanici=test_kullanicisi)
    assert tercih.tema == "oyun"
    assert tercih.ton == "kanka"
    assert tercih.detay_seviyesi == "yuksek"
    assert tercih.mizah_seviyesi == "hafif"

    metric = MetrikKaydi.objects.filter(olay_turu="personalization_guncellendi").latest("id")
    assert metric.skor_ozeti["tema"] == "oyun"
    assert metric.skor_ozeti["ton"] == "kanka"
    assert "hafif" in str(metric.skor_ozeti)


def test_yeni_flagler_kapaliyken_endpointler_kontrollu_davranir(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    doc, _, _ = _dokuman_ve_parcalar_olustur(test_kullanicisi, baslik="Yeni Flag")
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    settings.DOCVERSE_EXCEL_MODES_ENABLED = False
    response_excel = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/excel-modes/")
    assert response_excel.status_code == 404

    settings.DOCVERSE_EXPORT_PLAN_ENABLED = False
    response_manifest = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/export-manifest-v2/")
    assert response_manifest.status_code == 404

    settings.DOCVERSE_PREMIUM_UI_PAYLOADS_ENABLED = False
    response_premium = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/premium-payloads/")
    assert response_premium.status_code == 404

    settings.DOCVERSE_PERSONALIZATION_ENABLED = False
    response_preferences = client.get("/api/dokuman-asistani/tercih/")
    assert response_preferences.status_code == 404
