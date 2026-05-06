from rest_framework import serializers
from dokuman.services.difficulty import calculate_part_difficulty, difficulty_label_from_score

from .models import (
    AnlamadimKaydi,
    Dokuman,
    DokumanNotu,
    KullaniciTercih,
    KullaniciGeriBildirim,
    MetrikKaydi,
    Not,
    Parca,
    Profil,
)

class DokumanNotuSerializer(serializers.ModelSerializer):
    bagli_not_idleri = serializers.SerializerMethodField()
    kaynak_parca_idleri = serializers.SerializerMethodField()

    class Meta:
        model = DokumanNotu
        fields = [
            "id",
            "dokuman",
            "parca",
            "adres",
            "baslik",
            "icerik",
            "not_turu",
            "etiketler",
            "pinned",
            "arsivli",
            "olusturma_kaynagi",
            "meta",
            "bagli_not_idleri",
            "kaynak_parca_idleri",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_bagli_not_idleri(self, obj):
        return list(obj.bagli_notlar.order_by("id").values_list("id", flat=True))

    def get_kaynak_parca_idleri(self, obj):
        return list(obj.kaynak_parcalar.order_by("id").values_list("id", flat=True))
class KullaniciTercihSerializer(serializers.ModelSerializer):
    class Meta:
        model = KullaniciTercih
        fields = ["tema", "tarz", "seviye", "ton", "detay_seviyesi", "mizah_seviyesi"]
class AnlamadimKaydiSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnlamadimKaydi
        fields = [
            "id",
            "dokuman", "parca", "adres",
            "tema", "tarz", "seviye",
            "kullanici_mesaj",
            "cikti_text", "cikti_json",
            "olusturuldu",
        ]

class ZorYerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parca
        fields = ["id", "dokuman", "sira", "adres", "zorluk_skoru", "zorluk", "metin"]
        read_only_fields = fields
        
def fix_mojibake(s: str) -> str:
    if not isinstance(s, str):
        return s
    if any(x in s for x in ("Ã", "Ä", "Å", "Â")):
        try:
            return s.encode("latin1").decode("utf-8")
        except Exception:
            return s
    return s

class DokumanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dokuman
        fields = ["id", "baslik", "dosya", "mime", "durum", "hata", "created_at"]


class ParcaSerializer(serializers.ModelSerializer):
    metin = serializers.SerializerMethodField()
    difficulty_score = serializers.SerializerMethodField()
    difficulty_label = serializers.SerializerMethodField()
    difficulty_reasons = serializers.SerializerMethodField()

    def get_metin(self, obj):
        return fix_mojibake(obj.metin)

    def _difficulty(self, obj):
        profile = calculate_part_difficulty(obj.metin or "", getattr(obj, "meta", None))
        score = float(profile["difficulty_score"])
        reasons = list(profile["difficulty_reasons"])
        stored = getattr(obj, "zorluk_skoru", None)
        if stored is not None and float(stored or 0.0) > 0.0:
            score = float(stored or 0.0)
        label = difficulty_label_from_score(score)
        return round(max(0.0, min(float(score), 1.0)), 3), label, reasons

    def get_difficulty_score(self, obj):
        return self._difficulty(obj)[0]

    def get_difficulty_label(self, obj):
        return self._difficulty(obj)[1]

    def get_difficulty_reasons(self, obj):
        return self._difficulty(obj)[2]

    class Meta:
        model = Parca
        fields = [
            "id",
            "sira",
            "tur",
            "adres",
            "meta",
            "zorluk_skoru",
            "zorluk",
            "difficulty_score",
            "difficulty_label",
            "difficulty_reasons",
            "metin",
        ]

class ProfilSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profil
        fields = ["id", "user", "xp", "seviye", "unvan"]
        read_only_fields = ["id", "user"]

class NotSerializer(serializers.ModelSerializer):
    icerik = serializers.SerializerMethodField()
    dokuman_id = serializers.IntegerField(source="dokuman.id", read_only=True)
    parca_id = serializers.IntegerField(source="parca.id", read_only=True)

    class Meta:
        model = Not
        fields = [
            "id",
            "dokuman",
            "dokuman_id",
            "parca",
            "parca_id",
            "adres",
            "baslik",
            "not_turu",
            "metin",
            "icerik",
            "etiketler",
            "pinned",
            "arsivli",
            "olusturma_kaynagi",
            "kaynak_parca_idleri",
            "meta",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_icerik(self, obj):
        return obj.metin

    def validate(self, attrs):
        if "metin" not in attrs:
            incoming_icerik = self.initial_data.get("icerik")
            if incoming_icerik is not None:
                attrs["metin"] = incoming_icerik

        metin = attrs.get("metin")
        if self.instance:
            metin = attrs.get("metin", self.instance.metin)

        if not metin or not str(metin).strip():
            raise serializers.ValidationError({"metin": "Bu alan boş olamaz."})

        return attrs


class MetrikKaydiSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetrikKaydi
        fields = [
            "id",
            "olay_turu",
            "dokuman",
            "parca",
            "ilgili_not_id",
            "ilgili_portal_not_id",
            "ilgili_feedback_id",
            "kaynak_modul",
            "skor_ozeti",
            "durum",
            "created_at",
        ]
        read_only_fields = fields


class KullaniciGeriBildirimSerializer(serializers.ModelSerializer):
    class Meta:
        model = KullaniciGeriBildirim
        fields = [
            "id",
            "dokuman",
            "parca",
            "not_kaydi",
            "portal_not",
            "feedback_turu",
            "kisa_not",
            "kaynak_modul",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class DashboardSummarySerializer(serializers.Serializer):
    toplam_not_sayisi = serializers.IntegerField()
    toplam_portal_not_sayisi = serializers.IntegerField()
    toplam_feedback = serializers.IntegerField()
    son_7_gun_feedback = serializers.IntegerField()
    study_summary_kullanimi = serializers.DictField()
    cheatsheet_export_kullanimi = serializers.DictField()
    feedback_turu_dagilimi = serializers.ListField(child=serializers.DictField())
    kaynak_modul_dagilimi = serializers.ListField(child=serializers.DictField())
    gecerli_feedback_orani = serializers.FloatField()
    dusuk_fayda_orani = serializers.FloatField()
    yuksek_confusion_parca_sayisi = serializers.IntegerField()
    feedback_trust_ratio = serializers.FloatField()
    net_usefulness_score = serializers.FloatField()
    cheatsheet_yield = serializers.FloatField()


class FeedbackAnalyticsV2Serializer(serializers.Serializer):
    toplam_feedback = serializers.IntegerField()
    trusted_feedback = serializers.IntegerField()
    feedback_trust_ratio = serializers.FloatField()
    feedback_turu_dagilimi = serializers.ListField(child=serializers.DictField())
    kaynak_modul_dagilimi = serializers.ListField(child=serializers.DictField())
    dokuman_dagilimi = serializers.ListField(child=serializers.DictField())
    son_gun_trendi = serializers.ListField(child=serializers.DictField())


class ConfusionHotspotAnalyticsSerializer(serializers.Serializer):
    yuksek_confusion_parca_sayisi = serializers.IntegerField()
    dokuman_problem_yogunlugu = serializers.ListField(child=serializers.DictField())
    top_problemli_dokumanlar = serializers.ListField(child=serializers.DictField())


class MasteryFeedbackTrustAnalyticsSerializer(serializers.Serializer):
    mastery_summary = serializers.DictField()
    feedback_trust = serializers.DictField()


class KPIPanelSerializer(serializers.Serializer):
    net_usefulness_score = serializers.FloatField()
    global_confusion_index = serializers.FloatField()
    feedback_trust_ratio = serializers.FloatField()
    cheatsheet_yield = serializers.FloatField()


class ProductPanelsKPISerializer(serializers.Serializer):
    boss_rush_ready_ratio = serializers.FloatField()
    weekly_goal_completion_avg = serializers.FloatField()
    achievement_progress_avg = serializers.FloatField()
    export_readiness_avg = serializers.FloatField()
    personalization_confidence_avg = serializers.FloatField()


class QuizResultSerializer(serializers.Serializer):
    dogru_sayisi = serializers.IntegerField(min_value=0)
    toplam_soru = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        if attrs["dogru_sayisi"] > attrs["toplam_soru"]:
            raise serializers.ValidationError({"dogru_sayisi": "dogru_sayisi toplam_soru degerini asamaz."})
        return attrs


class QuizReadinessRequestSerializer(serializers.Serializer):
    parca_id = serializers.IntegerField(min_value=1)
    observed_read_seconds = serializers.FloatField(min_value=0.0, required=False)
    expected_read_seconds = serializers.FloatField(min_value=0.0, required=False)
    read_ratio = serializers.FloatField(min_value=0.0, required=False)
    note_count = serializers.IntegerField(min_value=0, required=False)
    quiz_action = serializers.ChoiceField(
        choices=["accepted", "dismissed", "completed"],
        required=False,
    )


class BossResultSerializer(serializers.Serializer):
    dogru_sayisi = serializers.IntegerField(min_value=0)
    toplam_soru = serializers.IntegerField(min_value=1)
    ipucu_sayisi = serializers.IntegerField(min_value=0, required=False, default=0)
    parca_idleri = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )

    def validate(self, attrs):
        if attrs["dogru_sayisi"] > attrs["toplam_soru"]:
            raise serializers.ValidationError({"dogru_sayisi": "dogru_sayisi toplam_soru degerini asamaz."})
        attrs["parca_idleri"] = list(dict.fromkeys(attrs.get("parca_idleri") or []))[:12]
        return attrs


class BossReadinessSerializer(serializers.Serializer):
    boss_difficulty_score = serializers.FloatField()
    boss_difficulty_band = serializers.CharField()
    boss_retry_count = serializers.IntegerField()
    boss_instruction = serializers.CharField()
    mastery_score = serializers.FloatField(required=False)
    learning_momentum_score = serializers.FloatField(required=False)


class BossRushPanelSerializer(serializers.Serializer):
    hazir_mi = serializers.BooleanField()
    hazirlik_skoru = serializers.FloatField()
    boss_rush_readiness_score = serializers.FloatField()
    boss_adayi_sayisi = serializers.IntegerField()
    tahmini_boss_rush_suresi_dk = serializers.IntegerField()
    zorluk_bandi = serializers.CharField()
    onerilen_baslangic = serializers.CharField()


class ConfusionMapSurfaceSerializer(serializers.Serializer):
    problemli_parca_sayisi = serializers.IntegerField()
    top_problemli_parcalar = serializers.ListField(child=serializers.DictField())
    dokuman_bazli_confusion_yogunlugu = serializers.ListField(child=serializers.DictField())


class QuizBossProductAnalyticsSerializer(serializers.Serializer):
    quiz_hazir_parca_sayisi = serializers.IntegerField()
    boss_adayi_parca_sayisi = serializers.IntegerField()
    son_denemeler_ozeti = serializers.ListField(child=serializers.DictField())
    basari_orani = serializers.FloatField()


class PortalNoteStudyPanelSerializer(serializers.Serializer):
    portal_not_id = serializers.IntegerField()
    bagli_not_sayisi = serializers.IntegerField()
    kaynak_parca_sayisi = serializers.IntegerField()
    summary_var_mi = serializers.BooleanField()
    cheatsheet_var_mi = serializers.BooleanField()
    son_feedback_sinyali = serializers.DictField()
    son_kullanim_sinyali = serializers.DictField()


class LearningPanelSerializer(serializers.Serializer):
    ortalama_confusion = serializers.FloatField()
    ortalama_mastery = serializers.FloatField()
    quiz_ready_orani = serializers.FloatField()
    gecerli_feedback_orani = serializers.FloatField()
    net_usefulness = serializers.FloatField()


class LearningKPISerializer(serializers.Serializer):
    boss_win_rate = serializers.FloatField()
    confusion_recovery_rate = serializers.FloatField()
    quiz_engagement_ratio = serializers.FloatField()
    platform_momentum_index = serializers.FloatField()
    boss_started = serializers.IntegerField()
    boss_completed = serializers.IntegerField()
    quiz_prompted = serializers.IntegerField()
    quiz_accepted = serializers.IntegerField()


class StyleConsoleSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    portal_not_id = serializers.IntegerField(allow_null=True)
    stil = serializers.CharField()
    ton = serializers.CharField()
    baslik = serializers.CharField()
    acilis = serializers.CharField()
    maddeler = serializers.ListField(child=serializers.CharField())
    vurgular = serializers.ListField(child=serializers.CharField())
    kaynak_parca_idleri = serializers.ListField(child=serializers.IntegerField())


class DirectorsCutSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    portal_not_id = serializers.IntegerField(allow_null=True)
    mod = serializers.CharField()
    baslik = serializers.CharField()
    ana_maddeler = serializers.ListField(child=serializers.CharField())
    kritik_noktalar = serializers.ListField(child=serializers.CharField())
    tuzaklar = serializers.ListField(child=serializers.CharField())
    sorulabilecekler = serializers.ListField(child=serializers.CharField())
    kaynak_parca_idleri = serializers.ListField(child=serializers.IntegerField())


class XPVisibilityPanelSerializer(serializers.Serializer):
    toplam_xp = serializers.IntegerField()
    seviye = serializers.IntegerField()
    unvan = serializers.CharField()
    basari_sayisi = serializers.IntegerField()
    son_kazanilan_basari = serializers.DictField(allow_null=True)
    streak_bilgisi = serializers.DictField()


class ExportPlanSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    portal_not_id = serializers.IntegerField(allow_null=True)
    baslik = serializers.CharField()
    plan_turu = serializers.CharField()
    slayt_plani = serializers.ListField(child=serializers.DictField())
    bolum_plani = serializers.ListField(child=serializers.DictField())


class ExcelModesSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    portal_not_id = serializers.IntegerField(allow_null=True)
    mod = serializers.CharField()
    baslik = serializers.CharField()
    kartlar = serializers.ListField(child=serializers.DictField())
    oneriler = serializers.ListField(child=serializers.CharField())
    kaynak_parca_idleri = serializers.ListField(child=serializers.IntegerField())


class ExportManifestV2Serializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    portal_not_id = serializers.IntegerField(allow_null=True)
    baslik = serializers.CharField()
    hedef_format = serializers.CharField()
    bolumler = serializers.ListField(child=serializers.DictField())
    kaynak_parca_idleri = serializers.ListField(child=serializers.IntegerField())
    ozet_kaynaklari = serializers.DictField()
    konusma_notu_var_mi = serializers.BooleanField()
    tahmini_slayt_sayisi = serializers.IntegerField()
    tahmini_bolum_sayisi = serializers.IntegerField()


class ReadmeExportSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    baslik = serializers.CharField()
    proje_ozeti = serializers.CharField()
    kurulum = serializers.ListField(child=serializers.CharField())
    kullanim = serializers.ListField(child=serializers.CharField())
    kritik_bilesenler = serializers.ListField(child=serializers.CharField())
    kaynak_parca_idleri = serializers.ListField(child=serializers.IntegerField())
    manifest = serializers.DictField()
    output_meta = serializers.DictField()


class RealExportSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    baslik = serializers.CharField()
    hedef_format = serializers.CharField()
    durum = serializers.CharField()
    readiness = serializers.CharField()
    export_readiness_score = serializers.FloatField(required=False)
    download_ready = serializers.BooleanField()
    manifest = serializers.DictField()
    output_meta = serializers.DictField()


class ExportReadinessPanelSerializer(serializers.Serializer):
    pdf_hazirlik = serializers.FloatField()
    docx_hazirlik = serializers.FloatField()
    pptx_hazirlik = serializers.FloatField()
    readme_hazirlik = serializers.FloatField()
    export_readiness_score = serializers.FloatField()
    onerilen_format = serializers.CharField()
    eksik_bilesenler = serializers.ListField(child=serializers.CharField())


class PersonalizationConfidenceSerializer(serializers.Serializer):
    aktif_tema = serializers.CharField()
    aktif_ton = serializers.CharField()
    onerilen_tema = serializers.CharField()
    onerilen_ton = serializers.CharField()
    personalization_confidence = serializers.FloatField()
    personalization_confidence_score = serializers.FloatField()
    neden_bu_oneri = serializers.CharField()


class WeeklyProgressPanelSerializer(serializers.Serializer):
    haftalik_gorevler = serializers.ListField(child=serializers.DictField())
    tamamlanan_gorev_sayisi = serializers.IntegerField()
    tamamlanma_orani = serializers.FloatField()
    sonraki_rozet = serializers.CharField()
    ne_eksik = serializers.ListField(child=serializers.CharField())
    haftalik_ilerleme_skoru = serializers.FloatField()
    weekly_goal_progress_score = serializers.FloatField()


class AchievementProgressSerializer(serializers.Serializer):
    derived_xp = serializers.IntegerField()
    derived_level = serializers.IntegerField()
    active_title = serializers.CharField()
    achievements = serializers.ListField(child=serializers.DictField())
    streak = serializers.DictField()
    reward_hint = serializers.CharField()
    quiz_count = serializers.IntegerField()
    boss_count = serializers.IntegerField()
    boss_wins = serializers.IntegerField()
    self_check_count = serializers.IntegerField(required=False)
    quiz_avg = serializers.FloatField()
    boss_avg = serializers.FloatField()
    self_check_avg = serializers.FloatField()
    achievement_progress_score = serializers.FloatField()


class PremiumPayloadsSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    portal_not_id = serializers.IntegerField(allow_null=True)
    spotlight_payload = serializers.DictField()
    teleport_links = serializers.ListField(child=serializers.DictField())
    cevap_bilekligi_gostergeleri = serializers.ListField(child=serializers.DictField())


class ConceptGraphSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    dugumler = serializers.ListField(child=serializers.DictField())
    baglar = serializers.ListField(child=serializers.DictField())
    kavram_onceligi = serializers.CharField()
    bag_gucu = serializers.CharField()


class ConceptSurfaceSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    toplam_kavram = serializers.IntegerField()
    kavramlar = serializers.ListField(child=serializers.DictField())


class ConceptDetailSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    kavram = serializers.CharField()
    kisa_tanim = serializers.CharField()
    bagli_parca_idleri = serializers.ListField(child=serializers.IntegerField())
    ornek_gecis_sayisi = serializers.IntegerField()


class SelfCheckRuntimeRequestSerializer(serializers.Serializer):
    kullanici_aciklamasi = serializers.CharField(required=False, allow_blank=True, max_length=1200)
    yanit = serializers.CharField(required=False, allow_blank=True, max_length=1200)

    def validate(self, attrs):
        aciklama = (attrs.get("kullanici_aciklamasi") or self.initial_data.get("kullanici_aciklamasi") or "").strip()
        if not aciklama:
            aciklama = (attrs.get("yanit") or self.initial_data.get("yanit") or "").strip()
        if not aciklama:
            raise serializers.ValidationError({"kullanici_aciklamasi": "Bu alan zorunludur."})
        attrs["kullanici_aciklamasi"] = aciklama
        return attrs


class SelfCheckRuntimeSerializer(serializers.Serializer):
    dogru_noktalar = serializers.ListField(child=serializers.CharField())
    duzeltilecek_noktalar = serializers.ListField(child=serializers.CharField())
    eksik_noktalar = serializers.ListField(child=serializers.CharField())
    self_check_score = serializers.FloatField()


class ConceptFusionRequestSerializer(serializers.Serializer):
    kavram_a = serializers.CharField(max_length=120)
    kavram_b = serializers.CharField(max_length=120)


class ConceptFusionSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    kavram_a = serializers.CharField()
    kavram_b = serializers.CharField()
    ortak_yonler = serializers.ListField(child=serializers.CharField())
    farklar = serializers.ListField(child=serializers.CharField())
    birlikte_kullanim_ornegi = serializers.CharField()
    mini_soru = serializers.CharField()


class QuizRouletteSerializer(serializers.Serializer):
    parca_id = serializers.IntegerField()
    mod = serializers.CharField()
    uygun_modlar = serializers.ListField(child=serializers.CharField())
    gerekce = serializers.CharField()


class EscapeRoomSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    hedef_kavramlar = serializers.ListField(child=serializers.CharField())
    gereken_adimlar = serializers.ListField(child=serializers.DictField())
    ilerleme_durumu = serializers.DictField()
    tamamlandi_mi = serializers.BooleanField()


class EscapeRoomUpdateSerializer(serializers.Serializer):
    tamamlandi_mi = serializers.BooleanField(required=False)
    tamamlanan_adim_sayisi = serializers.IntegerField(required=False, min_value=0, max_value=3)


class PuzzleRuntimeSerializer(serializers.Serializer):
    orijinal_parca_id = serializers.IntegerField()
    bosluklar = serializers.ListField(child=serializers.DictField())
    beklenen_kelimeler = serializers.ListField(child=serializers.CharField())
    ipucu_var_mi = serializers.BooleanField()


class SpeedrunRuntimeSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    en_onemli_cumleler = serializers.ListField(child=serializers.CharField())
    mini_quiz = serializers.ListField(child=serializers.DictField())
    yanlis_tamir_adimi = serializers.CharField()
    hedef_sure_saniye = serializers.IntegerField()


class SpeedrunCompletionSerializer(serializers.Serializer):
    dogru_sayisi = serializers.IntegerField(min_value=0)
    toplam_soru = serializers.IntegerField(min_value=1)
    hedef_sure_saniye = serializers.IntegerField(required=False, min_value=1)


class ReelsSurfaceSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField()
    portal_not_id = serializers.IntegerField(allow_null=True)
    kartlar = serializers.ListField(child=serializers.DictField())


class LearningModesPanelSerializer(serializers.Serializer):
    roulette_hazir_mi = serializers.BooleanField()
    roulette_reason = serializers.CharField()
    escape_room_hazir_mi = serializers.BooleanField()
    escape_room_reason = serializers.CharField()
    speedrun_hazir_mi = serializers.BooleanField()
    speedrun_reason = serializers.CharField()
    boss_hazir_mi = serializers.BooleanField()
    boss_reason = serializers.CharField()
    self_check_hazir_mi = serializers.BooleanField()
    self_check_reason = serializers.CharField()


class WeeklyProgressReportSerializer(serializers.Serializer):
    bu_hafta_quiz_sayisi = serializers.IntegerField()
    bu_hafta_boss_sayisi = serializers.IntegerField()
    mastery_delta = serializers.FloatField()
    confusion_azalisi = serializers.FloatField()
    en_cok_calistigi_konu = serializers.CharField()
    onerilen_sonraki_adim = serializers.CharField()


class RewardPanelSerializer(serializers.Serializer):
    toplam_xp = serializers.IntegerField()
    seviye = serializers.IntegerField()
    aktif_unvan = serializers.CharField()
    basarilar = serializers.ListField(child=serializers.DictField())
    streak = serializers.DictField()
    reward_priority = serializers.FloatField()
    reward_hint = serializers.CharField()


class PersonalizationHintsSerializer(serializers.Serializer):
    onerilen_tema = serializers.CharField()
    onerilen_ton = serializers.CharField()
    onerilen_detay_seviyesi = serializers.CharField()
    onerilen_mod = serializers.CharField()
    onerinin_gerekcesi_kisa = serializers.CharField()
