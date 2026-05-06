from __future__ import annotations

from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import AnlamadimKaydi, Dokuman, MetrikKaydi, Parca
from dokuman.services.metric_store import compute_mastery_score


def _create_doc(user, *, title: str = "Boss Runtime"):
    doc = Dokuman.objects.create(
        owner=user,
        baslik=title,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save(f"{title.lower().replace(' ', '-')}.pdf", ContentFile(b"ornek"), save=True)
    return doc


def test_boss_adayi_secimi_calisir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = _create_doc(test_kullanicisi, title="Boss Candidates")
    kolay = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="Genel giris notu.",
        meta={"quality_score": 0.82, "difficulty_score": 0.20},
        zorluk="kolay",
        zorluk_skoru=0.20,
    )
    zor = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="1.2",
        metin="OAuth refresh token rotation, nonce=42 ve session replay korunumu teknik akista anlatilir.",
        meta={"quality_score": 0.91, "difficulty_score": 0.84, "heading_score": 0.78},
        zorluk="zor",
        zorluk_skoru=0.84,
    )
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc,
        parca=zor,
        adres=zor.adres,
        kullanici_mesaj="Bu akisa tekrar bakmam gerekiyor.",
        cikti_text="Karisik.",
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/boss-rush/?limit=2")

    assert response.status_code == 200
    arena = response.data["boss_rush"]["arena"]
    assert arena[0]["parca_id"] == zor.id
    assert arena[1]["parca_id"] == kolay.id
    assert "boss_meta" in arena[0]
    assert MetrikKaydi.objects.filter(olay_turu="boss_adayi_secildi").exists()


def test_boss_rush_snippet_ham_parca_metnini_sizdirmaz(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    secret = "HAM_BOSS_RUNTIME_SECRET"
    doc = _create_doc(test_kullanicisi, title="Boss Snippet Safety")
    Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin=f"{secret} refresh token rotation ve replay korumasi.",
        meta={"quality_score": 0.93, "difficulty_score": 0.88},
        zorluk="zor",
        zorluk_skoru=0.88,
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/boss-rush/?limit=1")

    assert response.status_code == 200
    arena = response.data["boss_rush"]["arena"]
    assert len(arena) == 1
    assert secret not in str(response.data)
    assert arena[0]["snippet"]
    assert "kelime" in arena[0]["snippet"]


def test_boss_sonucu_guvenli_metric_storea_yazilir_ve_mastery_baglanir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = _create_doc(test_kullanicisi, title="Boss Result")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="2.1",
        metin="Replay attack ve token rotation detaylari.",
        meta={"quality_score": 0.88, "difficulty_score": 0.74},
        zorluk="zor",
        zorluk_skoru=0.74,
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        f"/api/dokuman-asistani/parcalar/{parca.id}/boss/",
        {"dogru_sayisi": 2, "toplam_soru": 3},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["sonuc_orani"] == 0.6667
    kayit = MetrikKaydi.objects.get(olay_turu="boss_deneme_tamamlandi")
    assert kayit.skor_ozeti["dogru_sayisi"] == 2
    assert kayit.skor_ozeti["toplam_soru"] == 3
    assert kayit.skor_ozeti["boss_parca_idleri"] == [parca.id]
    assert "Replay attack" not in str(kayit.skor_ozeti)

    mastery = compute_mastery_score(user=test_kullanicisi, dokuman=doc)
    assert mastery["mastery_quiz_success_ratio"] >= 0.6


def test_boss_feature_flag_kapaliyken_kontrollu_kapanir(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_BOSS_ENABLED = False
    doc = _create_doc(test_kullanicisi, title="Boss Flag Off")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="3.1",
        metin="Boss modu test parcasi.",
        meta={"quality_score": 0.77, "difficulty_score": 0.61},
        zorluk_skoru=0.61,
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response_list = client.get(f"/api/dokuman-asistani/dokumanlar/{doc.id}/boss-rush/")
    response_post = client.post(
        f"/api/dokuman-asistani/parcalar/{parca.id}/boss/",
        {"dogru_sayisi": 1, "toplam_soru": 1},
        format="json",
    )

    assert response_list.status_code == 404
    assert response_post.status_code == 404
