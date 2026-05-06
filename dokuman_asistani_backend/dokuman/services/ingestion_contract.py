from __future__ import annotations

"""Ingestion sonucunu dokuman durumuna ve response shape'ine baglayan sozlesme katmani.

Bu modül; aday parça sayısı, kalite sonucu ve kayıt durumu gibi sinyalleri tek
bir sözlükte toplar, ardından bunu `Dokuman` nesnesine güvenli biçimde uygular.
"""

from django.db import transaction

from dokuman.models import Parca


def _ingestion_hata_mesaji_belirle(
    *,
    kalite_durumu: str,
    aday_parca_sayisi: int,
    kaydedilen_parca_sayisi: int,
    hata_mesaji: str,
) -> str:
    """Ham hata yoksa kalite ve kayıt sinyalinden kullanıcıya dönecek mesajı üretir."""
    if str(hata_mesaji or "").strip():
        return str(hata_mesaji).strip()

    if kalite_durumu != "ok":
        return "Ingestion basarisiz."

    if aday_parca_sayisi <= 0:
        return "Ingestion parca adayi uretemedi."

    if kaydedilen_parca_sayisi <= 0:
        return "Hazirlanan parcalar veritabanina kaydedilemedi."

    if kaydedilen_parca_sayisi != aday_parca_sayisi:
        return (
            f"Hazirlanan {aday_parca_sayisi} parcanin "
            f"yalnizca {kaydedilen_parca_sayisi} adedi kaydedildi."
        )

    return "Ingestion basarisiz."


def _ingestion_durum_nedeni_belirle(
    *,
    kalite_durumu: str,
    aday_parca_sayisi: int,
    kaydedilen_parca_sayisi: int,
) -> str:
    """Basarisiz ingestion akisini acceptance/debug icin siniflandirir."""
    if str(kalite_durumu or "").strip().lower() != "ok":
        return "quality_gate_failed"

    if int(aday_parca_sayisi or 0) <= 0:
        return "no_candidate_chunks"

    if int(kaydedilen_parca_sayisi or 0) <= 0:
        return "zero_saved_after_bulk"

    if int(kaydedilen_parca_sayisi or 0) != int(aday_parca_sayisi or 0):
        return "partial_persistence"

    return "ok"


def ingestion_sonucu_uret(
    *,
    kaynak_turu: str,
    mime: str,
    aday_parca_sayisi: int,
    kaydedilen_parca_sayisi: int,
    kalite_durumu: str,
    hata_mesaji: str = "",
    debug_ozeti: dict | None = None,
) -> dict:
    """Ingestion akışını response ve persistence için tek sonuç sözlüğüne normalize eder."""
    aday_parca_sayisi = int(aday_parca_sayisi or 0)
    kaydedilen_parca_sayisi = int(kaydedilen_parca_sayisi or 0)
    kalite_durumu = str(kalite_durumu or "hata").strip().lower()

    # Başarı yalnızca kalite, aday üretimi ve fiili kayıt birlikte tamamsa kabul edilir.
    basarili = (
        kalite_durumu == "ok"
        and aday_parca_sayisi > 0
        and kaydedilen_parca_sayisi > 0
        and kaydedilen_parca_sayisi == aday_parca_sayisi
    )
    durum_nedeni = _ingestion_durum_nedeni_belirle(
        kalite_durumu=kalite_durumu,
        aday_parca_sayisi=aday_parca_sayisi,
        kaydedilen_parca_sayisi=kaydedilen_parca_sayisi,
    )
    hata_mesaji = _ingestion_hata_mesaji_belirle(
        kalite_durumu=kalite_durumu,
        aday_parca_sayisi=aday_parca_sayisi,
        kaydedilen_parca_sayisi=kaydedilen_parca_sayisi,
        hata_mesaji=hata_mesaji,
    )

    return {
        "kaynak_turu": str(kaynak_turu or "").strip(),
        "mime": str(mime or "").strip(),
        "aday_parca_sayisi": aday_parca_sayisi,
        "kaydedilen_parca_sayisi": kaydedilen_parca_sayisi,
        "kalite_durumu": kalite_durumu,
        "durum_nedeni": durum_nedeni,
        "durum_gecisi": "parcalandi" if basarili else "hata",
        "hata_mesaji": "" if basarili else str(hata_mesaji or "Ingestion basarisiz."),
        "debug_ozeti": dict(debug_ozeti or {}),
    }


def ingestion_sonucunu_dokumana_uygula(doc, sonuc: dict) -> list[str]:
    """Sonuç sözlüğündeki durum/mime/hata alanlarını modelin gerçek alanlarına yazar."""
    doc.mime = str(sonuc.get("mime") or getattr(doc, "mime", "") or "").strip()
    doc.durum = str(sonuc.get("durum_gecisi") or "hata").strip()
    hata_mesaji = str(sonuc.get("hata_mesaji") or "")

    # Model sürümleri arasında `hata_mesaji` ve `hata` alan adları değişebildiği için
    # burada kontrollü fallback uygulanır.
    if hasattr(doc, "hata_mesaji"):
        doc.hata_mesaji = hata_mesaji
        return ["mime", "durum", "hata_mesaji"]

    if hasattr(doc, "hata"):
        doc.hata = hata_mesaji
        return ["mime", "durum", "hata"]

    return ["mime", "durum"]


def ingestion_sonucunu_kaydet(
    doc,
    *,
    kaynak_turu: str,
    mime: str,
    aday_parca_sayisi: int,
    kaydedilen_parca_sayisi: int,
    kalite_durumu: str,
    hata_mesaji: str = "",
    debug_ozeti: dict | None = None,
) -> dict:
    """Ingestion sonucunu üretir, dokümana uygular ve minimal alanlarla kaydeder."""
    sonuc = ingestion_sonucu_uret(
        kaynak_turu=kaynak_turu,
        mime=mime,
        aday_parca_sayisi=aday_parca_sayisi,
        kaydedilen_parca_sayisi=kaydedilen_parca_sayisi,
        kalite_durumu=kalite_durumu,
        hata_mesaji=hata_mesaji,
        debug_ozeti=debug_ozeti,
    )
    update_fields = ingestion_sonucunu_dokumana_uygula(doc, sonuc)
    # Save sırasında gereksiz alan yazımı olmasın diye update_fields listesi dar tutulur.
    if "durum" not in update_fields:
        update_fields.append("durum")
    if "mime" not in update_fields:
        update_fields.append("mime")
    doc.save(update_fields=update_fields)
    return sonuc


def ingestion_bulkunu_kaydet(
    doc,
    *,
    bulk,
    kaynak_turu: str,
    mime: str,
    kalite_durumu: str,
    hata_mesaji: str = "",
    debug_ozeti: dict | None = None,
    batch_size: int = 500,
    kayit_basarisiz_mesaji: str = "",
    eksik_kayit_mesaji: str = "",
) -> dict:
    """Parca bulk kaydini ve doc durum gecisini tek merkezden uygular.

    Bu helper'in ana amaci, farkli ingestion kollari arasinda sahte `parcalandi`
    riskini ayni kurallarla kapatmaktir.
    """
    bulk = list(bulk or [])
    with transaction.atomic():
        Parca.objects.filter(dokuman=doc).delete()
        if str(kalite_durumu or "").strip().lower() == "ok" and bulk:
            try:
                Parca.objects.bulk_create(bulk, batch_size=batch_size)
            except TypeError:
                Parca.objects.bulk_create(bulk)
        real_count = Parca.objects.filter(dokuman=doc).count()

        clean_hata = str(hata_mesaji or "").strip()
        if not clean_hata and bulk and real_count == 0:
            clean_hata = kayit_basarisiz_mesaji or "Hazirlanan parcalar veritabanina kaydedilemedi."
        if not clean_hata and bulk and real_count != len(bulk):
            clean_hata = eksik_kayit_mesaji or (
                f"Hazirlanan {len(bulk)} parcanin yalnizca {real_count} adedi kaydedildi."
            )

        sonuc = ingestion_sonucunu_kaydet(
            doc,
            kaynak_turu=kaynak_turu,
            mime=mime,
            aday_parca_sayisi=len(bulk),
            kaydedilen_parca_sayisi=real_count,
            kalite_durumu=kalite_durumu,
            hata_mesaji=clean_hata,
            debug_ozeti=debug_ozeti,
        )

    return {
        "sonuc": sonuc,
        "real_count": real_count,
        "aday_parca_sayisi": len(bulk),
    }
