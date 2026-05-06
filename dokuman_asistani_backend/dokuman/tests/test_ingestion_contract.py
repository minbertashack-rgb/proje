from __future__ import annotations

from django.core.files.base import ContentFile

from dokuman.models import Dokuman
from dokuman.services import ingestion
from dokuman.services.ingestion_contract import ingestion_sonucu_uret


def _dokuman_olustur(test_kullanicisi, gecici_media_root):
    doc = Dokuman.objects.create(
        owner=test_kullanicisi,
        baslik="Ingestion Contract",
        mime="application/pdf",
        durum="yuklendi",
    )
    doc.dosya.save("ingestion-contract.pdf", ContentFile(b"ornek"), save=True)
    return doc


def test_ingestion_sonucu_empty_bulkte_basarili_sayilmaz():
    sonuc = ingestion_sonucu_uret(
        kaynak_turu="heading_parser",
        mime="application/pdf",
        aday_parca_sayisi=0,
        kaydedilen_parca_sayisi=0,
        kalite_durumu="ok",
        hata_mesaji="bos bulk",
    )

    assert sonuc["durum_gecisi"] == "hata"
    assert sonuc["hata_mesaji"] == "bos bulk"


def test_ingestion_noop_bulk_create_sahte_parcalandi_yazmaz(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _dokuman_olustur(test_kullanicisi, gecici_media_root)

    monkeypatch.setattr(
        "dokuman.services.ingestion.parse_document_structure",
        lambda path: {
            "section_count": 1,
            "sections": [
                    {
                        "title": "Giris",
                        "content": "Bu bolum kalite filtresini gececek kadar uzun ve anlamli icerik tasir. Uygulama adimlarini, amaci ve beklenen sonucu ayni baglam icinde net olarak aciklar.",
                        "level": 1,
                        "page_start": 1,
                        "path": "1",
                }
            ],
        },
    )
    monkeypatch.setattr(ingestion.Parca.objects, "bulk_create", lambda bulk, batch_size=500: None)

    ingestion.dokumani_parcala_ve_kaydet(doc)
    doc.refresh_from_db()

    assert doc.durum == "hata"
    assert doc.parcalar.count() == 0
    assert "kaydedilemedi" in doc.hata.lower()


def test_ingestion_gercek_kayitta_parcalandi_olur(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _dokuman_olustur(test_kullanicisi, gecici_media_root)

    monkeypatch.setattr(
        "dokuman.services.ingestion.parse_document_structure",
        lambda path: {
            "section_count": 1,
            "sections": [
                    {
                        "title": "Giris",
                        "content": "Bu bolum kalite filtresini gececek kadar uzun ve anlamli icerik tasir. Uygulama adimlarini, amaci ve beklenen sonucu ayni baglam icinde net olarak aciklar.",
                        "level": 1,
                        "page_start": 1,
                        "path": "1",
                }
            ],
        },
    )
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"denendi": True})

    ingestion.dokumani_parcala_ve_kaydet(doc)
    doc.refresh_from_db()

    assert doc.durum == "parcalandi"
    assert doc.parcalar.count() == 1


def test_ingestion_teknik_kisa_parcayi_cheatsheet_adayi_olarak_isaretler(
    db,
    test_kullanicisi,
    gecici_media_root,
    monkeypatch,
):
    doc = _dokuman_olustur(test_kullanicisi, gecici_media_root)

    monkeypatch.setattr(
        "dokuman.services.ingestion.parse_document_structure",
        lambda path: {
            "section_count": 1,
            "sections": [
                    {
                        "title": "Formul",
                        "content": "Excel XLOOKUP ve IF formul ozeti: =XLOOKUP(A1;B:B;C:C), =IF(A1>0;'EVET';'HAYIR'). Bu bolum XLOOKUP ve IF fonksiyonlarinin temel kullanimini verir.",
                        "level": 1,
                        "page_start": 1,
                        "path": "1.1",
                }
            ],
        },
    )
    monkeypatch.setattr("dokuman.services.rag.sync_dokuman_indexi_if_enabled", lambda d: {"denendi": True})

    ingestion.dokumani_parcala_ve_kaydet(doc)

    parca = doc.parcalar.get()
    assert parca.meta["is_cheatsheet"] is True
    assert parca.meta["cheatsheet_priority_score"] >= 0.70
