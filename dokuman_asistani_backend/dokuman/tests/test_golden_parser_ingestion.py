from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from .assets.mini_varlik_havuzu import VARLIK_HAVUZU
from .yardimcilar import (
    adresler_benzersiz_mi,
    basliklari_getir,
    belge_fixture_yolu,
    belge_yapisini_coz,
    beklenen_basliklari_kontrol_et,
    dokuman_kaydi_olustur,
    parca_sayisi_makul_mu,
    parcalari_getir,
    pdf_destegi_var_mi,
    section_pathlerini_topla,
)


def ingestion_modulu():
    from dokuman.services import ingestion

    return ingestion


class _GeciciAlanKarismi:
    def gecici_klasor_olustur(self) -> Path:
        gecici_klasor = TemporaryDirectory()
        self.addCleanup(gecici_klasor.cleanup)
        return Path(gecici_klasor.name)


class AltinParserRegressionTestleri(_GeciciAlanKarismi, SimpleTestCase):
    @skipUnless(pdf_destegi_var_mi(), "PDF regression icin fitz gerekli.")
    def test_altin_basit_giris_numarali_yapi_pdf_parserde_sabit_kaliniyor(self):
        varlik = VARLIK_HAVUZU["pdf_numarali_belge"]
        dosya = belge_fixture_yolu(self.gecici_klasor_olustur(), "pdf_numarali_belge")

        parsed = belge_yapisini_coz(dosya)

        self.assertTrue(beklenen_basliklari_kontrol_et(parsed, varlik["beklenen_basliklar"]))
        self.assertEqual(section_pathlerini_topla(parsed), varlik["beklenen_pathler"])
        self.assertEqual(parsed["sections"][0]["path"], "0")
        self.assertEqual(parsed["sections"][1]["path"], "1")
        self.assertTrue(adresler_benzersiz_mi(section_pathlerini_topla(parsed)))
        self.assertTrue(parca_sayisi_makul_mu(parsed["section_count"], min_sayi=4, max_sayi=6))

    @skipUnless(pdf_destegi_var_mi(), "PDF regression icin fitz gerekli.")
    def test_altin_uppercase_paragraf_heading_patlamasi_yapmiyor(self):
        varlik = VARLIK_HAVUZU["pdf_buyuk_harf_paragraf"]
        dosya = belge_fixture_yolu(self.gecici_klasor_olustur(), "pdf_buyuk_harf_paragraf")

        parsed = belge_yapisini_coz(dosya)
        basliklar = basliklari_getir(parsed)

        self.assertTrue(beklenen_basliklari_kontrol_et(parsed, varlik["beklenen_basliklar"]))
        self.assertLessEqual(parsed["section_count"], varlik["maks_section_sayisi"])
        self.assertNotIn(
            "BU BOLUMDE SISTEMIN NASIL CALISTIGI DETAYLI OLARAK ANLATILMAKTADIR.",
            basliklar,
        )

    def test_altin_kisa_gercek_docx_basliklari_korunuyor(self):
        varlik = VARLIK_HAVUZU["docx_kisa_gercek_basliklar"]
        dosya = belge_fixture_yolu(self.gecici_klasor_olustur(), "docx_kisa_gercek_basliklar")

        parsed = belge_yapisini_coz(dosya)
        basliklar = basliklari_getir(parsed)

        self.assertTrue(beklenen_basliklari_kontrol_et(parsed, varlik["beklenen_basliklar"]))
        self.assertEqual(section_pathlerini_topla(parsed), varlik["beklenen_pathler"])
        self.assertIn("Özet", basliklar)
        self.assertIn("Sonuç", basliklar)
        self.assertIn("Ek A: Veri Seti", basliklar)
        self.assertTrue(adresler_benzersiz_mi(section_pathlerini_topla(parsed)))

    def test_altin_ozel_basliklar_ve_caps_tuzagi_docx_parserde_sabit(self):
        varlik = VARLIK_HAVUZU["docx_ozel_baslik_caps_tuzagi"]
        dosya = belge_fixture_yolu(self.gecici_klasor_olustur(), "docx_ozel_baslik_caps_tuzagi")

        parsed = belge_yapisini_coz(dosya)
        basliklar = basliklari_getir(parsed)

        self.assertTrue(beklenen_basliklari_kontrol_et(parsed, varlik["beklenen_basliklar"]))
        self.assertEqual(section_pathlerini_topla(parsed), varlik["beklenen_pathler"])
        self.assertNotIn(
            "AMA VE KAPSAM BU BELGENIN TEMEL HEDEFLERINI ACIKLAR",
            basliklar,
        )
        self.assertTrue(adresler_benzersiz_mi(section_pathlerini_topla(parsed)))

    def test_altin_kurumsal_stilize_docx_parserde_section_patlamasi_yapmiyor(self):
        varlik = VARLIK_HAVUZU["docx_kurumsal_stilize_kenar"]
        dosya = belge_fixture_yolu(self.gecici_klasor_olustur(), "docx_kurumsal_stilize_kenar")

        parsed = belge_yapisini_coz(dosya)
        basliklar = basliklari_getir(parsed)

        self.assertTrue(beklenen_basliklari_kontrol_et(parsed, varlik["beklenen_basliklar"]))
        self.assertEqual(section_pathlerini_topla(parsed), varlik["beklenen_pathler"])
        self.assertNotIn(
            "OPERASYONEL RISK VE KONTROL AKISI BU SATIRDA NORMAL ACIKLAMA OLARAK VERILIR",
            basliklar,
        )
        self.assertTrue(adresler_benzersiz_mi(section_pathlerini_topla(parsed)))

    def test_altin_kurumsal_stilize_docx_caps_satiri_heading_olmuyor(self):
        varlik = VARLIK_HAVUZU["docx_kurumsal_stilize_kenar"]
        dosya = belge_fixture_yolu(self.gecici_klasor_olustur(), "docx_kurumsal_stilize_kenar")

        parsed = belge_yapisini_coz(dosya)
        basliklar = basliklari_getir(parsed)

        self.assertTrue(beklenen_basliklari_kontrol_et(parsed, varlik["beklenen_basliklar"]))
        self.assertEqual(section_pathlerini_topla(parsed), varlik["beklenen_pathler"])
        self.assertNotIn(
            "OPERASYONEL RISK VE KONTROL AKISI BU SATIRDA NORMAL ACIKLAMA OLARAK VERILIR",
            basliklar,
        )


class AltinIngestionRegressionTestleri(_GeciciAlanKarismi, TestCase):
    @classmethod
    def setUpTestData(cls):
        kullanici_modeli = get_user_model()
        cls.test_kullanicisi = kullanici_modeli.objects.create_user(
            username=f"parser_test_{uuid4().hex[:8]}",
            password="12345678",
        )

    @skipUnless(pdf_destegi_var_mi(), "PDF regression icin fitz gerekli.")
    def test_altin_pdf_parser_ve_ingestion_birlikte_sabit_kaliniyor(self):
        ingestion = ingestion_modulu()
        varlik = VARLIK_HAVUZU["pdf_numarali_belge"]
        gecici_klasor = self.gecici_klasor_olustur()
        media_root = gecici_klasor / "media"
        media_root.mkdir(parents=True, exist_ok=True)
        dosya = belge_fixture_yolu(gecici_klasor, "pdf_numarali_belge")

        with override_settings(MEDIA_ROOT=media_root):
            dokuman = dokuman_kaydi_olustur(
                kullanici=self.test_kullanicisi,
                dosya_yolu=dosya,
                baslik="Altin PDF",
                mime="application/pdf",
            )
            ingestion.dokumani_parcala_ve_kaydet(dokuman)
            dokuman.refresh_from_db()
            parcalar = parcalari_getir(dokuman)

        self.assertEqual(dokuman.durum, "parcalandi")
        self.assertTrue(parca_sayisi_makul_mu(len(parcalar), min_sayi=4, max_sayi=6))
        self.assertEqual([parca.adres for parca in parcalar], varlik["beklenen_pathler"])
        self.assertTrue(adresler_benzersiz_mi([parca.adres for parca in parcalar]))
        self.assertNotEqual(parcalar[0].adres, parcalar[1].adres)

    def test_altin_docx_duzeni_asiri_bolunmuyor(self):
        ingestion = ingestion_modulu()
        varlik = VARLIK_HAVUZU["docx_karma_duzen"]
        gecici_klasor = self.gecici_klasor_olustur()
        media_root = gecici_klasor / "media"
        media_root.mkdir(parents=True, exist_ok=True)
        dosya = belge_fixture_yolu(gecici_klasor, "docx_karma_duzen")

        parsed = belge_yapisini_coz(dosya)
        self.assertTrue(beklenen_basliklari_kontrol_et(parsed, varlik["beklenen_basliklar"]))
        self.assertEqual(section_pathlerini_topla(parsed), varlik["beklenen_pathler"])

        with override_settings(MEDIA_ROOT=media_root):
            dokuman = dokuman_kaydi_olustur(
                kullanici=self.test_kullanicisi,
                dosya_yolu=dosya,
                baslik="Altin Zor DOCX",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            ingestion.dokumani_parcala_ve_kaydet(dokuman)
            dokuman.refresh_from_db()
            parcalar = parcalari_getir(dokuman)

        self.assertEqual(dokuman.durum, "parcalandi")
        self.assertTrue(
            parca_sayisi_makul_mu(
                len(parcalar),
                min_sayi=varlik["beklenen_parca_sayisi"],
                max_sayi=varlik["beklenen_parca_sayisi"],
            )
        )
        self.assertTrue(all((parca.metin or "").strip() for parca in parcalar))
        self.assertTrue(all((parca.meta or {}).get("icerik_uzunlugu", 0) > 30 for parca in parcalar))

    def test_altin_kisa_ama_anlamli_docx_bolumleri_elenmiyor(self):
        ingestion = ingestion_modulu()
        varlik = VARLIK_HAVUZU["docx_kisa_anlamli_bolumler"]
        gecici_klasor = self.gecici_klasor_olustur()
        media_root = gecici_klasor / "media"
        media_root.mkdir(parents=True, exist_ok=True)
        dosya = belge_fixture_yolu(gecici_klasor, "docx_kisa_anlamli_bolumler")

        parsed = belge_yapisini_coz(dosya)
        self.assertTrue(beklenen_basliklari_kontrol_et(parsed, varlik["beklenen_basliklar"]))
        self.assertEqual(section_pathlerini_topla(parsed), varlik["beklenen_pathler"])

        with override_settings(MEDIA_ROOT=media_root):
            dokuman = dokuman_kaydi_olustur(
                kullanici=self.test_kullanicisi,
                dosya_yolu=dosya,
                baslik="Altin Kisa DOCX",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            ingestion.dokumani_parcala_ve_kaydet(dokuman)
            dokuman.refresh_from_db()
            parcalar = parcalari_getir(dokuman)

        self.assertEqual(dokuman.durum, "parcalandi")
        self.assertEqual(len(parcalar), varlik["beklenen_parca_sayisi"])
        self.assertEqual([parca.adres for parca in parcalar], varlik["beklenen_pathler"])

    def test_ingestion_quality_ve_heading_meta_guvenli_olarak_parca_meta_uzerinde_tasinir(self):
        ingestion = ingestion_modulu()
        gecici_klasor = self.gecici_klasor_olustur()
        media_root = gecici_klasor / "media"
        media_root.mkdir(parents=True, exist_ok=True)
        dosya = belge_fixture_yolu(gecici_klasor, "docx_kisa_anlamli_bolumler")

        with override_settings(
            MEDIA_ROOT=media_root,
            DOCVERSE_DEBUG_SUMMARY_ENABLED=True,
        ):
            parsed = belge_yapisini_coz(dosya)
            dokuman = dokuman_kaydi_olustur(
                kullanici=self.test_kullanicisi,
                dosya_yolu=dosya,
                baslik="Meta Gorunurlugu",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            ingestion.dokumani_parcala_ve_kaydet(dokuman)
            dokuman.refresh_from_db()
            ilk_parca = dokuman.parcalar.order_by("sira").first()

        self.assertIn("debug_ozeti", parsed)
        self.assertIsNotNone(ilk_parca)
        self.assertIn("quality_score", ilk_parca.meta)
        self.assertIn("quality_reason", ilk_parca.meta)
        self.assertIn("weak_content", ilk_parca.meta)
        self.assertIn("heading_score", ilk_parca.meta)
        self.assertIn("heading_decision_reason", ilk_parca.meta)

    def test_altin_kurumsal_stilize_docx_ingestion_parcalari_korur(self):
        ingestion = ingestion_modulu()
        varlik = VARLIK_HAVUZU["docx_kurumsal_stilize_kenar"]
        gecici_klasor = self.gecici_klasor_olustur()
        media_root = gecici_klasor / "media"
        media_root.mkdir(parents=True, exist_ok=True)
        dosya = belge_fixture_yolu(gecici_klasor, "docx_kurumsal_stilize_kenar")

        parsed = belge_yapisini_coz(dosya)
        self.assertTrue(beklenen_basliklari_kontrol_et(parsed, varlik["beklenen_basliklar"]))
        self.assertEqual(section_pathlerini_topla(parsed), varlik["beklenen_pathler"])

        with override_settings(MEDIA_ROOT=media_root):
            dokuman = dokuman_kaydi_olustur(
                kullanici=self.test_kullanicisi,
                dosya_yolu=dosya,
                baslik="Altin Kurumsal DOCX",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            ingestion.dokumani_parcala_ve_kaydet(dokuman)
            dokuman.refresh_from_db()
            parcalar = parcalari_getir(dokuman)

        self.assertEqual(dokuman.durum, "parcalandi")
        self.assertEqual(len(parcalar), varlik["beklenen_parca_sayisi"])
        self.assertEqual([parca.adres for parca in parcalar], varlik["beklenen_pathler"])

    def test_altin_kurumsal_stilize_docx_ingestionda_fazladan_bolunmuyor(self):
        ingestion = ingestion_modulu()
        varlik = VARLIK_HAVUZU["docx_kurumsal_stilize_kenar"]
        gecici_klasor = self.gecici_klasor_olustur()
        media_root = gecici_klasor / "media"
        media_root.mkdir(parents=True, exist_ok=True)
        dosya = belge_fixture_yolu(gecici_klasor, "docx_kurumsal_stilize_kenar")

        parsed = belge_yapisini_coz(dosya)
        self.assertTrue(beklenen_basliklari_kontrol_et(parsed, varlik["beklenen_basliklar"]))
        self.assertEqual(section_pathlerini_topla(parsed), varlik["beklenen_pathler"])

        with override_settings(MEDIA_ROOT=media_root):
            dokuman = dokuman_kaydi_olustur(
                kullanici=self.test_kullanicisi,
                dosya_yolu=dosya,
                baslik="Altin Kurumsal DOCX",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            ingestion.dokumani_parcala_ve_kaydet(dokuman)
            dokuman.refresh_from_db()
            parcalar = parcalari_getir(dokuman)

        self.assertEqual(dokuman.durum, "parcalandi")
        self.assertEqual(len(parcalar), varlik["beklenen_parca_sayisi"])
        self.assertEqual([parca.adres for parca in parcalar], varlik["beklenen_pathler"])

    def test_altin_zayif_belge_sahte_parcalandi_olmuyor(self):
        ingestion = ingestion_modulu()
        varlik = VARLIK_HAVUZU["docx_zayif_icerik"]
        gecici_klasor = self.gecici_klasor_olustur()
        media_root = gecici_klasor / "media"
        media_root.mkdir(parents=True, exist_ok=True)
        dosya = belge_fixture_yolu(gecici_klasor, "docx_zayif_icerik")

        parsed = belge_yapisini_coz(dosya)
        self.assertEqual(parsed["section_count"], 1)
        self.assertTrue(beklenen_basliklari_kontrol_et(parsed, varlik["beklenen_basliklar"]))

        with override_settings(MEDIA_ROOT=media_root):
            dokuman = dokuman_kaydi_olustur(
                kullanici=self.test_kullanicisi,
                dosya_yolu=dosya,
                baslik="Altin Zayif",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            ingestion.dokumani_parcala_ve_kaydet(dokuman)
            dokuman.refresh_from_db()

        self.assertEqual(dokuman.durum, varlik["beklenen_durum"])
        self.assertEqual(dokuman.parcalar.count(), 0)
        self.assertNotIn("parcalandi", (dokuman.hata or "").lower())

    def test_parser_bolum_cikarsa_bile_ingestion_hepsini_elerse_sahte_parcalandi_yazilmaz(self):
        ingestion = ingestion_modulu()
        gecici_klasor = self.gecici_klasor_olustur()
        media_root = gecici_klasor / "media"
        media_root.mkdir(parents=True, exist_ok=True)
        dosya = belge_fixture_yolu(gecici_klasor, "docx_kisa_gercek_basliklar")

        sahte_parser_ciktisi = {
            "section_count": 2,
            "sections": [
                {
                    "title": "1. Imza",
                    "content": "Tarih: 2024-01-01",
                    "level": 1,
                    "page_start": 1,
                    "path": "1",
                },
                {
                    "title": "2. Imzalayan",
                    "content": "Dijital olarak imzalayan",
                    "level": 1,
                    "page_start": 1,
                    "path": "2",
                },
            ],
        }

        with override_settings(MEDIA_ROOT=media_root):
            dokuman = dokuman_kaydi_olustur(
                kullanici=self.test_kullanicisi,
                dosya_yolu=dosya,
                baslik="Altin Kalite Esigi",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            with patch(
                "dokuman.services.ingestion.parse_document_structure",
                return_value=sahte_parser_ciktisi,
            ):
                ingestion.dokumani_parcala_ve_kaydet(dokuman)
            dokuman.refresh_from_db()

        self.assertEqual(dokuman.durum, "hata")
        self.assertEqual(dokuman.parcalar.count(), 0)
        self.assertIn("kalite filtresi", (dokuman.hata or "").lower())
        self.assertNotIn("parcalandi", (dokuman.hata or "").lower())
