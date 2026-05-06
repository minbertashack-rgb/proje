from __future__ import annotations

from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import Dokuman, DokumanNotu, MetrikKaydi, Not, Parca


def _dokuman_ve_parca_olustur(kullanici, *, baslik: str = "Not Test"):
    doc = Dokuman.objects.create(
        owner=kullanici,
        baslik=baslik,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("not-test.pdf", ContentFile(b"ornek"), save=True)
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres="1.1",
        metin="JWT access token kullanicinin kimligini tasir.",
        meta={"path": "1.1"},
    )
    return doc, parca


def test_not_olusturma_dokuman_bazli_alanlari_kaydeder(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, _ = _dokuman_ve_parca_olustur(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/notlar/",
        {
            "dokuman": doc.id,
            "baslik": "JWT ozeti",
            "metin": "Token akisina dair kisa bir ozet.",
            "not_turu": "ozet",
            "pinned": True,
            "arsivli": False,
            "olusturma_kaynagi": "user",
            "etiketler": ["jwt", "auth"],
            "meta": {"renk": "sari"},
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.data
    assert data["dokuman"] == doc.id
    assert data["parca"] is None
    assert data["not_turu"] == "ozet"
    assert data["olusturma_kaynagi"] == "user"
    assert data["pinned"] is True
    assert data["arsivli"] is False


def test_not_olusturma_parca_bazli_kaynak_parcalari_ile_calisir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca = _dokuman_ve_parca_olustur(test_kullanicisi)
    ikinci_parca = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="1.2",
        metin="Refresh token ile yeni token alinir.",
        meta={"path": "1.2"},
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/notlar/",
        {
            "parca": parca.id,
            "baslik": "Parca notu",
            "metin": "Bu parca kimlik tasima isini anlatiyor.",
            "kaynak_parca_idleri": [parca.id, ikinci_parca.id],
            "not_turu": "kaynak",
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.data
    assert data["dokuman"] == doc.id
    assert data["parca"] == parca.id
    assert data["kaynak_parca_idleri"] == [parca.id, ikinci_parca.id]
    assert data["adres"] == "1.1"


def test_ai_notu_ile_user_notu_ayrisir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, _ = _dokuman_ve_parca_olustur(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/notlar/",
        {
            "dokuman": doc.id,
            "baslik": "AI notu",
            "metin": "Bu not model tarafindan zenginlestirildi.",
            "olusturma_kaynagi": "ai",
            "not_turu": "calisma",
        },
        format="json",
    )

    assert response.status_code == 201
    not_kaydi = Not.objects.get(id=response.data["id"])
    assert not_kaydi.olusturma_kaynagi == "ai"
    assert response.data["olusturma_kaynagi"] == "ai"


def test_portal_notu_bagli_notlari_ve_parcalari_baglar(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca = _dokuman_ve_parca_olustur(test_kullanicisi)
    ikinci_not = Not.objects.create(
        owner=test_kullanicisi,
        dokuman=doc,
        parca=parca,
        adres=parca.adres,
        baslik="Alt not",
        metin="Parcaya bagli alt not.",
        not_turu="serbest",
        kaynak_parca_idleri=[parca.id],
    )
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.post(
        "/api/dokuman-asistani/portal-notlar/",
        {
            "dokuman": doc.id,
            "baslik": "Calisma notu",
            "icerik": "JWT ve refresh token akisini birlestiren calisma notu.",
            "bagli_not_idleri": [ikinci_not.id],
            "kaynak_parca_idleri": [parca.id],
            "not_turu": "portal_calisma",
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.data
    assert data["dokuman"] == doc.id
    assert data["bagli_not_idleri"] == [ikinci_not.id]
    assert data["kaynak_parca_idleri"] == [parca.id]
    portal_not = DokumanNotu.objects.get(id=data["id"])
    assert list(portal_not.bagli_notlar.values_list("id", flat=True)) == [ikinci_not.id]


def test_feature_flag_kapaliyken_notlar_endpointi_kontrollu_kapanir(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_NOTLAR_ENABLED = False
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get("/api/dokuman-asistani/notlar/")

    assert response.status_code == 404
    assert "devre disi" in response.data["detail"].lower()


def test_feature_flag_kapaliyken_portal_notlar_endpointi_kontrollu_kapanir(
    db,
    test_kullanicisi,
    gecici_media_root,
    settings,
):
    settings.DOCVERSE_PORTAL_NOTLAR_ENABLED = False
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)

    response = client.get("/api/dokuman-asistani/portal-notlar/")

    assert response.status_code == 404
    assert "devre disi" in response.data["detail"].lower()


def test_metric_kaydi_not_olusturunca_guvenli_alanlarla_yazilir(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, _ = _dokuman_ve_parca_olustur(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    gizli_metin = "Bu ham not icerigi metrik kaydina girmemeli."

    response = client.post(
        "/api/dokuman-asistani/notlar/",
        {
            "dokuman": doc.id,
            "baslik": "Metric test",
            "metin": gizli_metin,
            "etiketler": ["jwt", "kritik"],
            "not_turu": "serbest",
        },
        format="json",
    )

    assert response.status_code == 201
    kayit = MetrikKaydi.objects.get(olay_turu="not_olusturuldu")
    assert kayit.dokuman_id == doc.id
    assert kayit.kaynak_modul == "notlar.api"
    assert kayit.ilgili_not_id == response.data["id"]
    assert kayit.skor_ozeti["etiket_sayisi"] == 2
    assert "ham" not in kayit.skor_ozeti


def test_metric_store_ham_icerigi_saklamaz(
    db,
    test_kullanicisi,
    gecici_media_root,
):
    doc, parca = _dokuman_ve_parca_olustur(test_kullanicisi)
    client = APIClient()
    client.force_authenticate(user=test_kullanicisi)
    ham_metin = "JWT access token kullanicinin kimligini tasir ve bu cumle metrikte gorunmemeli."

    response = client.post(
        "/api/dokuman-asistani/portal-notlar/",
        {
            "dokuman": doc.id,
            "parca": parca.id,
            "baslik": "Portal metric",
            "icerik": ham_metin,
            "kaynak_parca_idleri": [parca.id],
        },
        format="json",
    )

    assert response.status_code == 201
    kayit = MetrikKaydi.objects.get(olay_turu="portal_not_olusturuldu")
    assert kayit.ilgili_portal_not_id == response.data["id"]
    assert kayit.skor_ozeti["kaynak_parca_sayisi"] == 1
    assert ham_metin not in str(kayit.skor_ozeti)
    assert not hasattr(kayit, "metin")
