from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from dokuman.models import (
    AnlamadimKaydi,
    Dokuman,
    DokumanNotu,
    KullaniciTercih,
    MetrikKaydi,
    Not,
    Parca,
)


class ProductExtensionsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="test_user", password="pwd")
        self.client.force_authenticate(user=self.user)
        self.dokuman = Dokuman.objects.create(
            owner=self.user,
            baslik="test.pdf",
            mime="application/pdf",
            durum="parcalandi",
        )
        self.dokuman.dosya.save("test.pdf", ContentFile(b"ornek"), save=True)
        self.parca1 = Parca.objects.create(
            dokuman=self.dokuman,
            sira=1,
            tur="tablo",
            adres="1.1",
            metin="JWT refresh token ve replay attack korunumu anlatilir.",
            meta={"quality_score": 0.88, "difficulty_score": 0.62, "quiz_readiness_score": 0.81, "row_count": 10, "column_count": 4},
            zorluk_skoru=0.62,
            zorluk="zor",
        )
        self.parca2 = Parca.objects.create(
            dokuman=self.dokuman,
            sira=2,
            tur="bolum",
            adres="1.2",
            metin="Nonce degeri replay attack riskini azaltir ve oturum guvenligini artirir.",
            meta={"quality_score": 0.84, "difficulty_score": 0.66, "quiz_readiness_score": 0.74},
            zorluk_skoru=0.66,
            zorluk="zor",
        )
        self.parca3 = Parca.objects.create(
            dokuman=self.dokuman,
            sira=3,
            tur="bolum",
            adres="1.3",
            metin="Access token istemci tarafinda kimlik aktarir ve sure sonu yenilenir.",
            meta={"quality_score": 0.79, "difficulty_score": 0.41, "quiz_readiness_score": 0.63},
            zorluk_skoru=0.41,
            zorluk="orta",
        )
        self.note = Not.objects.create(
            owner=self.user,
            dokuman=self.dokuman,
            parca=self.parca1,
            adres=self.parca1.adres,
            baslik="Guvenlik Akisi",
            metin="JWT ve refresh token akisina dair guvenli not.",
            not_turu="calisma",
            etiketler=["JWT", "Refresh Token"],
            kaynak_parca_idleri=[self.parca1.id, self.parca2.id],
        )
        self.portal_note = DokumanNotu.objects.create(
            owner=self.user,
            dokuman=self.dokuman,
            parca=self.parca1,
            adres="portal:1",
            baslik="Portal Guvenlik Akisi",
            icerik="Portal akisi yalnizca yapisal olarak izlenir.",
            not_turu="portal_calisma",
        )
        self.portal_note.kaynak_parcalar.add(self.parca1, self.parca2)
        self.portal_note.bagli_notlar.add(self.note)
        AnlamadimKaydi.objects.create(
            kullanici=self.user,
            dokuman=self.dokuman,
            parca=self.parca1,
            adres=self.parca1.adres,
            cikti_json={
                "glossary": [
                    {"terim": "JWT", "tanim": "Kimlik dogrulama akisinda tasiyici token."},
                    {"terim": "Refresh Token", "tanim": "Yeni access token uretmek icin kullanilan token."},
                ]
            },
        )

    def _create_metric(self, *, olay_turu, score_map=None, doc=None, parca=None, days_ago=0):
        kayit = MetrikKaydi.objects.create(
            kullanici=self.user,
            dokuman=doc or self.dokuman,
            parca=parca,
            olay_turu=olay_turu,
            kaynak_modul="test.runtime",
            skor_ozeti=score_map or {},
            durum="ok",
        )
        created_at = timezone.now() - timedelta(days=days_ago)
        MetrikKaydi.objects.filter(id=kayit.id).update(created_at=created_at)
        kayit.refresh_from_db()
        return kayit

    @override_settings(DOCVERSE_STYLE_CONSOLE_ENABLED=True, DOCVERSE_STUDY_SUMMARY_ENABLED=True)
    def test_style_console_enabled(self):
        url = reverse("dokuman-style-console", args=[self.dokuman.id])
        response = self.client.get(url, {"stil": "tablo", "ton": "kanka"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["stil"], "tablo")
        self.assertEqual(response.data["ton"], "kanka")
        self.assertIn("maddeler", response.data)

    @override_settings(DOCVERSE_DIRECTORS_CUT_ENABLED=True, DOCVERSE_STUDY_SUMMARY_ENABLED=True)
    def test_directors_cut_enabled(self):
        url = reverse("dokuman-directors-cut", args=[self.dokuman.id])
        response = self.client.get(url, {"mod": "exam_cut"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["mod"], "exam_cut")
        self.assertIn("ana_maddeler", response.data)
        self.assertIn("sorulabilecekler", response.data)

    @override_settings(DOCVERSE_EXPORT_PLAN_ENABLED=True, DOCVERSE_STUDY_SUMMARY_ENABLED=True)
    def test_export_plan_enabled(self):
        url = reverse("dokuman-export-plan", args=[self.dokuman.id])
        response = self.client.get(url, {"plan_turu": "slayt"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("slayt_plani", response.data)
        self.assertTrue(isinstance(response.data["slayt_plani"], list))

    @override_settings(DOCVERSE_METRIC_STORE_ENABLED=True)
    def test_xp_panel_enabled(self):
        url = reverse("analytics-xp-panel")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("toplam_xp", response.data)
        self.assertIn("seviye", response.data)
        self.assertIn("basari_sayisi", response.data)
        self.assertIn("streak_bilgisi", response.data)

    @override_settings(
        DOCVERSE_STYLE_CONSOLE_ENABLED=False,
        DOCVERSE_DIRECTORS_CUT_ENABLED=False,
        DOCVERSE_EXPORT_PLAN_ENABLED=False,
        DOCVERSE_METRIC_STORE_ENABLED=False,
    )
    def test_endpoints_disabled_behavior(self):
        url_style = reverse("dokuman-style-console", args=[self.dokuman.id])
        url_directors = reverse("dokuman-directors-cut", args=[self.dokuman.id])
        url_export = reverse("dokuman-export-plan", args=[self.dokuman.id])
        url_xp = reverse("analytics-xp-panel")

        self.assertEqual(self.client.get(url_style).status_code, 404)
        self.assertEqual(self.client.get(url_directors).status_code, 404)
        self.assertEqual(self.client.get(url_export).status_code, 404)
        self.assertEqual(self.client.get(url_xp).status_code, 404)

    @override_settings(DOCVERSE_EXCEL_MODES_ENABLED=True)
    def test_excel_modes_enabled(self):
        url = reverse("dokuman-excel-modes", args=[self.dokuman.id])
        response = self.client.get(url, {"mod": "formul_aciklayici"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["mod"], "formul_aciklayici")
        self.assertIn("kartlar", response.data)
        self.assertTrue(any(item["etiket"] == "formul_hucresi_tahmini" for item in response.data["kartlar"]))

    @override_settings(DOCVERSE_EXCEL_MODES_ENABLED=True)
    def test_excel_modes_tablo_anlatici_more_semantic_guidance(self):
        url = reverse("dokuman-excel-modes", args=[self.dokuman.id])
        response = self.client.get(url, {"mod": "tablo_anlatici"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["mod"], "tablo_anlatici")
        joined = " ".join(response.data["oneriler"]).lower()
        self.assertIn("tablo ne gosteriyor", joined)
        self.assertIn("onemli sutun", joined)

    @override_settings(DOCVERSE_EXCEL_MODES_ENABLED=True)
    def test_excel_modes_no_table_guvenli_reason_doner(self):
        dokuman = Dokuman.objects.create(
            owner=self.user,
            baslik="metin.pdf",
            mime="application/pdf",
            durum="parcalandi",
        )
        dokuman.dosya.save("metin.pdf", ContentFile(b"ornek"), save=True)
        Parca.objects.create(
            dokuman=dokuman,
            sira=1,
            tur="bolum",
            adres="2.1",
            metin="HAM_TABLE_SECRET yalnizca metin parcasi.",
            meta={"quality_score": 0.71},
            zorluk_skoru=0.2,
            zorluk="kolay",
        )

        url = reverse("dokuman-excel-modes", args=[dokuman.id])
        response = self.client.get(url, {"mod": "tablo_anlatici"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["kaynak_parca_idleri"], [])
        self.assertTrue(any(item["etiket"] == "reason" and item["deger"] == "table_data_missing" for item in response.data["kartlar"]))
        self.assertNotIn("HAM_TABLE_SECRET", str(response.data))

    @override_settings(DOCVERSE_EXPORT_PLAN_ENABLED=True)
    def test_export_manifest_v2_enabled(self):
        url = reverse("dokuman-export-manifest-v2", args=[self.dokuman.id])
        response = self.client.get(url, {"format": "pptx"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["hedef_format"], "pptx")
        self.assertIn("bolumler", response.data)

    @override_settings(DOCVERSE_EXPORT_PLAN_ENABLED=True, DOCVERSE_CONCEPTS_ENABLED=True)
    def test_export_manifest_v2_real_source_ids_tasir(self):
        url = reverse("dokuman-export-manifest-v2", args=[self.dokuman.id])
        response = self.client.get(url, {"format": "docx", "portal_not_id": self.portal_note.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["hedef_format"], "docx")
        self.assertIn(self.parca1.id, response.data["kaynak_parca_idleri"])
        self.assertIn(self.parca2.id, response.data["kaynak_parca_idleri"])
        self.assertTrue(all(item["kaynak_parca_idleri"] for item in response.data["bolumler"]))
        self.assertTrue(response.data["ozet_kaynaklari"]["portal_not"])
        self.assertTrue(response.data["ozet_kaynaklari"]["concept_surface"])
        self.assertNotIn("HAM_", str(response.data))

    @override_settings(DOCVERSE_PREMIUM_UI_PAYLOADS_ENABLED=True)
    def test_premium_payload_enabled(self):
        url = reverse("dokuman-premium-payload", args=[self.dokuman.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("spotlight_payload", response.data)
        self.assertIn("teleport_links", response.data)

    @override_settings(DOCVERSE_PERSONALIZATION_ENABLED=True)
    def test_personalization_profile_enabled(self):
        url = reverse("profil-personalization")
        response = self.client.patch(url, {"tema": "spor", "ton": "kanka"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tema"], "spor")
        self.assertEqual(response.data["ton"], "kanka")

    @override_settings(
        DOCVERSE_EXCEL_MODES_ENABLED=False,
        DOCVERSE_PREMIUM_UI_PAYLOADS_ENABLED=False,
        DOCVERSE_PERSONALIZATION_ENABLED=False,
    )
    def test_premium_endpoints_disabled_behavior(self):
        url_excel = reverse("dokuman-excel-modes", args=[self.dokuman.id])
        url_premium = reverse("dokuman-premium-payload", args=[self.dokuman.id])
        url_personalization = reverse("profil-personalization")
        self.assertEqual(self.client.get(url_excel).status_code, 404)
        self.assertEqual(self.client.get(url_premium).status_code, 404)
        self.assertEqual(self.client.get(url_personalization).status_code, 404)

    @override_settings(
        DOCVERSE_EXPORT_PLAN_ENABLED=False,
        DOCVERSE_EXCEL_MODES_ENABLED=False,
        DOCVERSE_PERSONALIZATION_ENABLED=False,
    )
    def test_v2_flags_kapaliyken_kontrollu_davranis_korunur(self):
        url_export_manifest = reverse("dokuman-export-manifest-v2", args=[self.dokuman.id])
        url_excel = reverse("dokuman-excel-modes", args=[self.dokuman.id])
        url_hints = reverse("profil-personalization-hints")
        self.assertEqual(self.client.get(url_export_manifest).status_code, 404)
        self.assertEqual(self.client.get(url_excel).status_code, 404)
        self.assertEqual(self.client.get(url_hints).status_code, 404)

    @override_settings(DOCVERSE_CONCEPTS_ENABLED=True)
    def test_concept_graph_enabled(self):
        self._create_metric(
            olay_turu="concept_fusion_uretildi",
            parca=self.parca1,
            score_map={"concept_a": "JWT", "concept_b": "Refresh Token", "concept_pair": ["JWT", "Refresh Token"]},
        )
        url = reverse("dokuman-concept-graph", args=[self.dokuman.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data.keys()), {"dokuman_id", "dugumler", "baglar", "kavram_onceligi", "bag_gucu"})
        labels = {item["label"] for item in response.data["dugumler"]}
        self.assertIn("JWT", labels)
        self.assertIn("Refresh Token", labels)
        self.assertTrue(any(item["strength"] > 0 for item in response.data["baglar"]))
        self.assertNotIn("HAM_", str(response.data))

    @override_settings(DOCVERSE_FUSION_ENABLED=True)
    def test_fusion_cards_enabled(self):
        url = reverse("dokuman-fusion-cards", args=[self.dokuman.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("fusion_kart_sayisi", response.data)

    @override_settings(DOCVERSE_SELF_CHECK_ENABLED=True)
    def test_self_check_panel_enabled(self):
        url = reverse("analytics-self-check-panel")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("son_self_check_skoru", response.data)

    @override_settings(DOCVERSE_PERSONALIZATION_ENABLED=True)
    def test_personalization_hints_enabled(self):
        KullaniciTercih.objects.update_or_create(
            kullanici=self.user,
            defaults={
                "tema": "oyun",
                "ton": "hoca",
                "detay_seviyesi": "orta",
                "seviye": "orta",
            },
        )
        self._create_metric(
            olay_turu="style_console_uretildi",
            score_map={"stil": "derin", "ton": "teknik"},
        )
        self._create_metric(
            olay_turu="directors_cut_uretildi",
            score_map={"mod": "exam_cut"},
        )
        self._create_metric(
            olay_turu="self_check_calistirildi",
            score_map={"self_check_score": 0.82},
        )
        url = reverse("profil-personalization-hints")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data.keys()),
            {
                "onerilen_tema",
                "onerilen_ton",
                "onerilen_detay_seviyesi",
                "onerilen_mod",
                "onerinin_gerekcesi_kisa",
            },
        )
        self.assertEqual(response.data["onerilen_tema"], "oyun")
        self.assertEqual(response.data["onerilen_mod"], "derin")
        self.assertIn("kullanilan modlar", response.data["onerinin_gerekcesi_kisa"])
        self.assertNotIn("HAM_", str(response.data))

    @override_settings(DOCVERSE_CONCEPTS_ENABLED=False)
    def test_concept_graph_disabled(self):
        url = reverse("dokuman-concept-graph", args=[self.dokuman.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    @override_settings(
        DOCVERSE_REELS_ENABLED=True,
        DOCVERSE_STUDY_SUMMARY_ENABLED=True,
        DOCVERSE_CHEATSHEET_EXPORT_ENABLED=True,
        DOCVERSE_METRIC_STORE_ENABLED=True,
    )
    def test_reels_surface_enabled(self):
        secret = "HAM_REELS_SECRET"
        self.parca2.metin = f"Nonce replay riskini azaltir. {secret}"
        self.parca2.save(update_fields=["metin"])
        weak_parca = Parca.objects.create(
            dokuman=self.dokuman,
            sira=4,
            tur="bolum",
            adres="1.4",
            metin="Kisa zayif parca",
            meta={"quality_score": 0.99, "difficulty_score": 0.92, "weak_content": True},
            zorluk_skoru=0.92,
            zorluk="zor",
        )
        Not.objects.create(
            owner=self.user,
            dokuman=self.dokuman,
            parca=self.parca2,
            baslik="Replay kilidi",
            metin="Nonce ile tekrar akisina odaklan.",
        )
        AnlamadimKaydi.objects.create(
            kullanici=self.user,
            dokuman=self.dokuman,
            parca=self.parca2,
            adres=self.parca2.adres,
            cikti_json={"glossary": [{"terim": "Nonce", "tanim": "Tek seferlik deger ile replay riski duser."}]},
        )
        AnlamadimKaydi.objects.create(
            kullanici=self.user,
            dokuman=self.dokuman,
            parca=self.parca3,
            adres=self.parca3.adres,
            cikti_json={"glossary": [{"terim": "Access Token", "tanim": "Kimlik aktarim tokenidir."}]},
        )
        self._create_metric(
            olay_turu="ai2_anlamadim_degerlendirildi",
            parca=self.parca2,
            score_map={"completeness_score": 0.2, "fallback_json_kullanildi": True},
            days_ago=1,
        )
        self._create_metric(
            olay_turu="ai2_cevap_degerlendirildi",
            parca=self.parca2,
            score_map={"supported": False, "hallucination_risk": 0.82, "usefulness_score_v2": 0.32},
            days_ago=1,
        )
        self._create_metric(
            olay_turu="mini_quiz_sonuclandi",
            parca=self.parca2,
            score_map={"dogru_sayisi": 1, "toplam_soru": 4, "sonuc_orani": 0.25, "mastery_score": 0.44},
            days_ago=1,
        )
        self._create_metric(
            olay_turu="study_summary_uretildi",
            parca=self.parca2,
            score_map={"study_summary_importance_score": 0.88},
            days_ago=2,
        )
        url = reverse("dokuman-reels", args=[self.dokuman.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data.keys()), {"dokuman_id", "portal_not_id", "kartlar"})
        self.assertTrue(isinstance(response.data["kartlar"], list))
        self.assertGreaterEqual(len(response.data["kartlar"]), 1)
        self.assertEqual(set(response.data["kartlar"][0].keys()), {"ozet", "ornek", "mini_soru", "bagli_parca_id"})
        self.assertEqual(response.data["kartlar"][0]["bagli_parca_id"], self.parca2.id)
        self.assertNotIn(secret, str(response.data))
        self.assertNotIn(weak_parca.id, [item["bagli_parca_id"] for item in response.data["kartlar"]])

        kayit = MetrikKaydi.objects.filter(olay_turu="reels_surface_uretildi").latest("id")
        self.assertIn("reels_selected_count", kayit.skor_ozeti)
        self.assertNotIn(secret, str(kayit.skor_ozeti))

    @override_settings(
        DOCVERSE_ROULETTE_ENABLED=True,
        DOCVERSE_ESCAPE_ROOM_ENABLED=True,
        DOCVERSE_SPEEDRUN_ENABLED=True,
        DOCVERSE_SELF_CHECK_ENABLED=True,
        DOCVERSE_METRIC_STORE_ENABLED=True,
    )
    def test_learning_modes_panel_enabled(self):
        url = reverse("dokuman-learning-modes", args=[self.dokuman.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["roulette_hazir_mi"])
        self.assertTrue(response.data["self_check_hazir_mi"])
        self.assertTrue(response.data["speedrun_hazir_mi"])
        self.assertFalse(response.data["escape_room_hazir_mi"])
        self.assertEqual(response.data["escape_room_reason"], "needs_self_check_or_quiz_signal")

        kayit = MetrikKaydi.objects.filter(olay_turu="learning_modes_panel_gosterildi").latest("id")
        self.assertIn("unlock_reason_code", kayit.skor_ozeti)

    @override_settings(
        DOCVERSE_ROULETTE_ENABLED=True,
        DOCVERSE_ESCAPE_ROOM_ENABLED=True,
        DOCVERSE_SPEEDRUN_ENABLED=True,
        DOCVERSE_SELF_CHECK_ENABLED=True,
    )
    def test_learning_modes_panel_low_readiness_returns_false_with_reasons(self):
        dusuk_doc = Dokuman.objects.create(
            owner=self.user,
            baslik="low.pdf",
            mime="application/pdf",
            durum="parcalandi",
        )
        dusuk_doc.dosya.save("low.pdf", ContentFile(b"ornek"), save=True)
        Parca.objects.create(
            dokuman=dusuk_doc,
            sira=1,
            tur="bolum",
            adres="2.1",
            metin="Not.",
            meta={"quality_score": 0.12, "difficulty_score": 0.08, "weak_content": True},
            zorluk_skoru=0.08,
            zorluk="kolay",
        )

        url = reverse("dokuman-learning-modes", args=[dusuk_doc.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["speedrun_hazir_mi"])
        self.assertEqual(response.data["speedrun_reason"], "needs_more_chunks")
        self.assertFalse(response.data["escape_room_hazir_mi"])
        self.assertEqual(response.data["escape_room_reason"], "no_concept_route")

    @override_settings(
        DOCVERSE_ROULETTE_ENABLED=False,
        DOCVERSE_ESCAPE_ROOM_ENABLED=False,
        DOCVERSE_SPEEDRUN_ENABLED=False,
        DOCVERSE_SELF_CHECK_ENABLED=False,
    )
    def test_learning_modes_panel_flag_disabled_reasons_are_controlled(self):
        url = reverse("dokuman-learning-modes", args=[self.dokuman.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["roulette_hazir_mi"])
        self.assertEqual(response.data["roulette_reason"], "module_disabled")
        self.assertFalse(response.data["speedrun_hazir_mi"])
        self.assertEqual(response.data["speedrun_reason"], "module_disabled")
        self.assertFalse(response.data["escape_room_hazir_mi"])
        self.assertEqual(response.data["escape_room_reason"], "module_disabled")

    @override_settings(DOCVERSE_METRIC_STORE_ENABLED=True)
    def test_weekly_report_enabled(self):
        self._create_metric(
            olay_turu="mini_quiz_sonuclandi",
            parca=self.parca2,
            score_map={"sonuc_orani": 0.82, "mastery_score": 0.74, "confusion_map_score": 0.21},
            days_ago=2,
        )
        self._create_metric(
            olay_turu="boss_deneme_tamamlandi",
            parca=self.parca2,
            score_map={"sonuc_orani": 0.9, "boss_progress_score": 0.9, "mastery_score": 0.78, "confusion_map_score": 0.18},
            days_ago=1,
        )
        self._create_metric(
            olay_turu="self_check_calistirildi",
            parca=self.parca2,
            score_map={"self_check_score": 0.72, "sonuc_orani": 0.72},
            days_ago=1,
        )
        self._create_metric(
            olay_turu="mini_quiz_sonuclandi",
            parca=self.parca1,
            score_map={"sonuc_orani": 0.35, "mastery_score": 0.42, "confusion_map_score": 0.58},
            days_ago=9,
        )
        url = reverse("analytics-weekly-report")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data.keys()), {"bu_hafta_quiz_sayisi", "bu_hafta_boss_sayisi", "mastery_delta", "confusion_azalisi", "en_cok_calistigi_konu", "onerilen_sonraki_adim"})
        self.assertEqual(response.data["bu_hafta_quiz_sayisi"], 1)
        self.assertEqual(response.data["bu_hafta_boss_sayisi"], 1)
        self.assertGreater(response.data["mastery_delta"], 0.0)
        self.assertGreater(response.data["confusion_azalisi"], 0.0)
        self.assertIn(self.parca2.adres, response.data["en_cok_calistigi_konu"])

        kayit = MetrikKaydi.objects.filter(olay_turu="weekly_progress_hesaplandi").latest("id")
        self.assertIn("weekly_progress_score", kayit.skor_ozeti)

    @override_settings(DOCVERSE_REWARD_PANEL_ENABLED=True, DOCVERSE_METRIC_STORE_ENABLED=True)
    def test_reward_panel_enabled(self):
        self._create_metric(
            olay_turu="mini_quiz_sonuclandi",
            parca=self.parca1,
            score_map={"sonuc_orani": 0.86, "mastery_score": 0.74},
            days_ago=2,
        )
        self._create_metric(
            olay_turu="self_check_calistirildi",
            parca=self.parca2,
            score_map={"self_check_score": 0.78, "sonuc_orani": 0.78},
            days_ago=1,
        )
        self._create_metric(
            olay_turu="concept_fusion_uretildi",
            parca=self.parca2,
            score_map={"concept_overlap_ratio": 0.66, "matched_concept_count": 3},
            days_ago=0,
        )
        self._create_metric(
            olay_turu="boss_deneme_tamamlandi",
            parca=self.parca2,
            score_map={"sonuc_orani": 0.9, "boss_progress_score": 0.9, "mastery_score": 0.82},
            days_ago=0,
        )
        url = reverse("profil-rewards")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("toplam_xp", response.data)
        self.assertIn("aktif_unvan", response.data)
        self.assertIn("basarilar", response.data)
        self.assertGreater(response.data["toplam_xp"], 0)
        self.assertTrue(response.data["reward_hint"])
        self.assertTrue(any(item["kod"] in {"ilk_quiz", "boss_esik", "kavram_baglayici"} for item in response.data["basarilar"]))

        kayit = MetrikKaydi.objects.filter(olay_turu="reward_panel_gosterildi").latest("id")
        self.assertIn("reward_priority_score", kayit.skor_ozeti)
