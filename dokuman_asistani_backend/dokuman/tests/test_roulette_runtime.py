from __future__ import annotations

from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import AnlamadimKaydi, Dokuman, MetrikKaydi, Parca


def _create_doc(user, *, title: str = "Roulette Runtime"):
    doc = Dokuman.objects.create(
        owner=user,
        baslik=title,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("roulette-runtime.pdf", ContentFile(b"ornek"), save=True)
    return doc


def test_roulette_runtime_calisir_ve_guvenli_metric_yazar(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = _create_doc(test_kullanicisi)
    secret = "HAM_ROULETTE_SECRET"
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin=f"JWT access token once uretilir sonra refresh token ile yenilenir. nonce=42 ve aud=api bilgisi akisi belirler. {secret}",
        meta={"quality_score": 0.9, "difficulty_score": 0.66},
        zorluk_skoru=0.66,
    )
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc,
        parca=parca,
        adres=parca.adres,
        cikti_json={"glossary": [{"terim": "JWT", "tanim": "Kimlik tokeni."}]},
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get(f"/api/dokuman-asistani/parcalar/{parca.id}/quiz-roulette/?mod=eslestirme")

    assert response.status_code == 200
    assert set(response.data.keys()) == {"parca_id", "mod", "uygun_modlar", "gerekce"}
    assert response.data["parca_id"] == parca.id
    assert response.data["mod"] == "eslestirme"
    assert "eslestirme" in response.data["uygun_modlar"]

    mod_kaydi = MetrikKaydi.objects.filter(olay_turu="roulette_mod_secildi").latest("id")
    uretim_kaydi = MetrikKaydi.objects.filter(olay_turu="roulette_uretildi").latest("id")
    assert secret not in str(mod_kaydi.skor_ozeti)
    assert secret not in str(uretim_kaydi.skor_ozeti)
    assert uretim_kaydi.skor_ozeti["roulette_mode"] == "eslestirme"


def test_uygun_olmayan_parcada_mod_secimi_filtrelenir_ve_puzzle_payloadi_uretilir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc = _create_doc(test_kullanicisi, title="Puzzle Runtime")
    zayif = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="paragraf",
        adres="2.1",
        metin="Not.",
        meta={"quality_score": 0.12, "difficulty_score": 0.08, "weak_content": True},
        zorluk_skoru=0.08,
    )
    guclu = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="paragraf",
        adres="2.2",
        metin="JWT access token kullanicinin kimligini tasir. Refresh Token yeni access token alinmasini saglar.",
        meta={"quality_score": 0.85, "difficulty_score": 0.52},
        zorluk_skoru=0.52,
    )
    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc,
        parca=guclu,
        adres=guclu.adres,
        cikti_json={
            "glossary": [
                {"terim": "JWT", "tanim": "Kimlik tasiyan token."},
                {"terim": "Refresh Token", "tanim": "Yeni access token verir."},
            ]
        },
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    roulette_response = client.get(f"/api/dokuman-asistani/parcalar/{zayif.id}/quiz-roulette/?mod=siralama")
    puzzle_response = client.get(f"/api/dokuman-asistani/parcalar/{guclu.id}/puzzle/")

    assert roulette_response.status_code == 200
    assert roulette_response.data["mod"] == "mini_test"
    assert "siralama" not in roulette_response.data["uygun_modlar"]

    assert puzzle_response.status_code == 200
    assert set(puzzle_response.data.keys()) == {"orijinal_parca_id", "bosluklar", "beklenen_kelimeler", "ipucu_var_mi"}
    assert puzzle_response.data["orijinal_parca_id"] == guclu.id
    assert len(puzzle_response.data["beklenen_kelimeler"]) >= 1
    assert puzzle_response.data["ipucu_var_mi"] is True

    puzzle_kaydi = MetrikKaydi.objects.filter(olay_turu="puzzle_uretildi").latest("id")
    assert "Refresh Token yeni access token" not in str(puzzle_kaydi.skor_ozeti)


def test_roulette_flag_kapaliyken_roulette_ve_puzzle_kontrollu_kapanir(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_ROULETTE_ENABLED = False
    doc = _create_doc(test_kullanicisi, title="Roulette Flag")
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="paragraf",
        adres="3.1",
        metin="JWT ve refresh token akisi.",
        meta={"quality_score": 0.82, "difficulty_score": 0.48},
        zorluk_skoru=0.48,
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response_roulette = client.get(f"/api/dokuman-asistani/parcalar/{parca.id}/quiz-roulette/")
    response_puzzle = client.get(f"/api/dokuman-asistani/parcalar/{parca.id}/puzzle/")

    assert response_roulette.status_code == 404
    assert response_puzzle.status_code == 404
