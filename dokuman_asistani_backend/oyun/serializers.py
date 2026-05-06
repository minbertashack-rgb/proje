from difflib import SequenceMatcher
from rest_framework import serializers
from .models import (
    Boss, BossSoru, BossDeneme, BossIlerleme, OyunProfil,
    BossOnKosul,
    KullaniciGorev, Basarim, KullaniciBasarim,
    Esya, Envanter,
    Bildirim, OdulIslemi
)


def _normalize(s: str) -> str:
    return (s or "").strip().casefold()


def text_puanla(kullanici_cevap: str, dogru: str, kabul_list: list, max_puan: int) -> int:
    uc = _normalize(kullanici_cevap)
    if not uc:
        return 0

    kabul = [_normalize(x) for x in (kabul_list or []) if str(x).strip()]
    dogru_n = _normalize(dogru)

    if dogru_n and uc == dogru_n:
        return max_puan
    if kabul and uc in kabul:
        return max_puan

    hedef = dogru_n or (kabul[0] if kabul else "")
    if not hedef:
        return 0

    ratio = SequenceMatcher(None, uc, hedef).ratio()
    return int(round(max_puan * ratio))




def seviye_hesapla(toplam_xp: int) -> int:
    return (int(toplam_xp or 0) // 100) + 1

class OyunProfilSerializer(serializers.ModelSerializer):
    seviye = serializers.SerializerMethodField()
    enerji_max = serializers.SerializerMethodField()
    streak_gun = serializers.SerializerMethodField()
    son_giris_tarihi = serializers.SerializerMethodField()

    class Meta:
        model = OyunProfil
        fields = [
            "toplam_xp", "seviye", "toplam_puan",
            "enerji", "enerji_max",
            "streak_gun", "son_giris_tarihi",
        ]

    def get_seviye(self, obj):
        # DB'de alan varsa onu kullan, yoksa hesapla
        v = getattr(obj, "seviye", None)
        return int(v) if v is not None else seviye_hesapla(getattr(obj, "toplam_xp", 0))

    def get_enerji_max(self, obj):
        v = getattr(obj, "enerji_max", None)
        return int(v) if v is not None else 10

    def get_streak_gun(self, obj):
        v = getattr(obj, "streak_gun", None)
        return int(v) if v is not None else 0

    def get_son_giris_tarihi(self, obj):
        v = getattr(obj, "son_giris_tarihi", None)
        return v  # yoksa None döner
    
class BossSoruPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = BossSoru
        fields = ["tip", "soru_metni", "secenekler", "max_puan"]


class BossListeSerializer(serializers.ModelSerializer):
    kilitli_mi = serializers.SerializerMethodField()
    tamamlandi_mi = serializers.SerializerMethodField()
    en_yuksek_puan = serializers.SerializerMethodField()
    on_kosullar = serializers.SerializerMethodField()

    class Meta:
        model = Boss
        fields = [
            "id", "ad", "aciklama", "aktif",
            "seviye_gereksinim", "siralama",
            "zorluk", "enerji_maliyeti", "cooldown_saniye",
            "odul_xp", "odul_puan", "tamamlama_esigi",
            "kilitli_mi", "tamamlandi_mi", "en_yuksek_puan",
            "on_kosullar",
        ]

    def _ilerleme(self, obj):
        req = self.context["request"]
        return BossIlerleme.objects.filter(kullanici=req.user, boss=obj).first()

    def get_on_kosullar(self, obj):
        return list(
            BossOnKosul.objects.filter(boss=obj).values_list("gerekir_boss_id", flat=True)
        )

    def get_kilitli_mi(self, obj):
        req = self.context["request"]
        profil, _ = OyunProfil.objects.get_or_create(kullanici=req.user)

        if profil.seviye < obj.seviye_gereksinim:
            return True

        prereq_ids = self.get_on_kosullar(obj)
        if prereq_ids:
            done = set(
                BossIlerleme.objects.filter(
                    kullanici=req.user, boss_id__in=prereq_ids, tamamlandi=True
                ).values_list("boss_id", flat=True)
            )
            return len(done) != len(prereq_ids)

        return False

    def get_tamamlandi_mi(self, obj):
        il = self._ilerleme(obj)
        return bool(il and il.tamamlandi)

    def get_en_yuksek_puan(self, obj):
        il = self._ilerleme(obj)
        return int(il.en_yuksek_puan) if il else 0


class BossDetaySerializer(serializers.ModelSerializer):
    soru = BossSoruPublicSerializer()

    class Meta:
        model = Boss
        fields = [
            "id", "ad", "aciklama",
            "seviye_gereksinim", "siralama",
            "zorluk", "enerji_maliyeti", "cooldown_saniye",
            "odul_xp", "odul_puan", "tamamlama_esigi",
            "soru",
        ]


class BossCevaplaSerializer(serializers.Serializer):
    cevap_metni = serializers.CharField(required=False, allow_blank=True)
    secilen_index = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if (attrs.get("cevap_metni", "").strip() == "") and (attrs.get("secilen_index", None) is None):
            raise serializers.ValidationError("cevap_metni veya secilen_index göndermelisin.")
        return attrs


class BossDenemeSerializer(serializers.ModelSerializer):
    boss_ad = serializers.CharField(source="boss.ad", read_only=True)
    soru_tip = serializers.CharField(source="soru.tip", read_only=True)

    class Meta:
        model = BossDeneme
        fields = [
            "id",
            "boss", "boss_ad",
            "soru_tip",
            "puan", "dogru_mu",
            "xp_eklendi", "puan_eklendi",
            "enerji_harcandi",
            "feedback",
            "olusturuldu",
        ]


class KullaniciGorevSerializer(serializers.ModelSerializer):
    gorev_ad = serializers.CharField(source="gorev.ad", read_only=True)
    tur = serializers.CharField(source="gorev.tur", read_only=True)
    hedef_tur = serializers.CharField(source="gorev.hedef_tur", read_only=True)
    hedef_deger = serializers.IntegerField(source="gorev.hedef_deger", read_only=True)
    odul_xp = serializers.IntegerField(source="gorev.odul_xp", read_only=True)
    odul_puan = serializers.IntegerField(source="gorev.odul_puan", read_only=True)

    class Meta:
        model = KullaniciGorev
        fields = [
            "id",
            "gorev_ad", "tur", "hedef_tur", "hedef_deger",
            "baslangic", "bitis",
            "ilerleme", "tamamlandi", "odul_alindi",
            "odul_xp", "odul_puan",
        ]


class BasarimSerializer(serializers.ModelSerializer):
    kazanildi_mi = serializers.SerializerMethodField()

    class Meta:
        model = Basarim
        fields = [
            "id", "kod", "ad", "aciklama", "rozet",
            "kosul_tur", "kosul_deger",
            "odul_xp", "odul_puan",
            "kazanildi_mi",
        ]

    def get_kazanildi_mi(self, obj):
        req = self.context["request"]
        return KullaniciBasarim.objects.filter(kullanici=req.user, basarim=obj).exists()


class EsyaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Esya
        fields = [
            "id", "kod", "ad", "tip",
            "sure_dk", "xp_carpan", "puan_carpan",
            "fiyat_puan", "fiyat_xp",
            "aktif",
        ]


class EnvanterSerializer(serializers.ModelSerializer):
    esya = EsyaSerializer()

    class Meta:
        model = Envanter
        fields = ["esya", "adet"]


class BildirimSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bildirim
        fields = ["id", "baslik", "mesaj", "okundu", "olusturuldu"]


class OdulIslemiSerializer(serializers.ModelSerializer):
    class Meta:
        model = OdulIslemi
        fields = ["id", "kaynak", "aciklama", "delta_xp", "delta_puan", "olusturuldu"]
        
