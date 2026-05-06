# oyun/models.py
from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL

# oyun/models.py  (OyunProfil bloğunu buna göre düzenle)

def seviye_hesapla(toplam_xp: int) -> int:
    return (toplam_xp // 100) + 1


class OyunProfil(models.Model):
    kullanici = models.OneToOneField(User, on_delete=models.CASCADE, related_name="oyun_profil")

    toplam_xp = models.PositiveIntegerField(default=0)
    seviye = models.PositiveIntegerField(default=1)
    toplam_puan = models.PositiveIntegerField(default=0)

    enerji = models.PositiveIntegerField(default=10)
    enerji_max = models.PositiveIntegerField(default=10)
    enerji_son_guncelleme = models.DateTimeField(default=timezone.now)
    enerji_yenileme_saniye = models.PositiveIntegerField(default=600)  # 10 dk

    streak_gun = models.PositiveIntegerField(default=0)
    son_giris_tarihi = models.DateField(null=True, blank=True)

    guncellendi = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"OyunProfil({self.kullanici}) lvl={self.seviye} xp={self.toplam_xp}"

    def enerji_guncelle(self):
        now = timezone.now()
        if self.enerji >= self.enerji_max:
            self.enerji_son_guncelleme = now
            return

        diff = (now - self.enerji_son_guncelleme).total_seconds()
        if diff <= 0:
            return

        kazanilan = int(diff // self.enerji_yenileme_saniye)
        if kazanilan <= 0:
            return

        self.enerji = min(self.enerji_max, self.enerji + kazanilan)

        kalan = diff % self.enerji_yenileme_saniye
        self.enerji_son_guncelleme = now - timezone.timedelta(seconds=kalan)

    def enerji_harcala(self, miktar: int) -> bool:
        self.enerji_guncelle()
        if miktar <= 0:
            return True
        if self.enerji < miktar:
            return False
        self.enerji -= miktar
        return True

    def xp_ekle(self, miktar: int):
        if miktar <= 0:
            return
        self.toplam_xp += miktar
        self.seviye = seviye_hesapla(self.toplam_xp)

    def puan_ekle(self, miktar: int):
        if miktar <= 0:
            return
        self.toplam_puan += miktar

class Gorev(models.Model):
    TUR_DAILY = "DAILY"
    TUR_WEEKLY = "WEEKLY"
    TUR_S = [(TUR_DAILY, "Günlük"), (TUR_WEEKLY, "Haftalık")]

    HEDEF_DENEME = "DENEME"
    HEDEF_BOSS_TAMAMLA = "BOSS_TAMAMLA"
    HEDEF_PUAN_TOPLA = "PUAN_TOPLA"
    HEDEF_XP_TOPLA = "XP_TOPLA"
    HEDEF_PERFECT = "PERFECT"
    HEDEFLER = [
        (HEDEF_DENEME, "Deneme yap"),
        (HEDEF_BOSS_TAMAMLA, "Boss tamamla"),
        (HEDEF_PUAN_TOPLA, "Puan topla"),
        (HEDEF_XP_TOPLA, "XP topla"),
        (HEDEF_PERFECT, "Mükemmel skor"),
    ]

    ad = models.CharField(max_length=120)
    tur = models.CharField(max_length=10, choices=TUR_S, default=TUR_DAILY)
    hedef_tur = models.CharField(max_length=20, choices=HEDEFLER)
    hedef_deger = models.PositiveIntegerField(default=1)

    param = models.JSONField(default=dict, blank=True)  # {"boss_id": 3} gibi

    odul_xp = models.PositiveIntegerField(default=50)
    odul_puan = models.PositiveIntegerField(default=20)

    aktif = models.BooleanField(default=True)

    def __str__(self):
        return f"Gorev({self.ad})"


class GorevIlerleme(models.Model):
    kullanici = models.ForeignKey(User, on_delete=models.CASCADE, related_name="gorev_ilerlemeler")
    gorev = models.ForeignKey(Gorev, on_delete=models.CASCADE, related_name="ilerlemeler")

    ilerleme_sayi = models.IntegerField(default=0)
    tamamlandi = models.BooleanField(default=False)
    odul_alindi = models.BooleanField(default=False)

    xp_kazanilan_toplam = models.IntegerField(default=0)
    puan_kazanilan_toplam = models.IntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("kullanici", "gorev")]


class Bildirim(models.Model):
    kullanici = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bildirimler")
    baslik = models.CharField(max_length=120)
    mesaj = models.TextField()
    okundu = models.BooleanField(default=False)
    olusturuldu = models.DateTimeField(auto_now_add=True)


class OdulLog(models.Model):
    kullanici = models.ForeignKey(User, on_delete=models.CASCADE, related_name="odul_loglari")
    tip = models.CharField(max_length=50)  # "BOSS", "GOREV" vs.
    ref_id = models.IntegerField(null=True, blank=True)

    xp_delta = models.IntegerField(default=0)
    puan_delta = models.IntegerField(default=0)

    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
class BossKategori(models.Model):
    ad = models.CharField(max_length=80)
    def __str__(self):
        return self.ad    
    
class Boss(models.Model):
    ad = models.CharField(max_length=120)
    aciklama = models.TextField(blank=True)
    aktif = models.BooleanField(default=True)

    kategori = models.ForeignKey(
        "BossKategori", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="bosslar"
    )

    seviye_gereksinim = models.PositiveIntegerField(default=1)
    siralama = models.PositiveIntegerField(default=1)

    zorluk = models.PositiveIntegerField(default=1)  # 1-10
    enerji_maliyeti = models.PositiveIntegerField(default=1)
    cooldown_saniye = models.PositiveIntegerField(default=10)

    odul_xp = models.PositiveIntegerField(default=100)
    odul_puan = models.PositiveIntegerField(default=100)

    tamamlama_esigi = models.PositiveIntegerField(default=60)

    olusturuldu = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Boss({self.ad})"
    
class BossSoru(models.Model):
    TIP_MCQ = "MCQ"
    TIP_TEXT = "TEXT"
    TIPLER = [(TIP_MCQ, "Çoktan Seçmeli"), (TIP_TEXT, "Metin")]

    boss = models.OneToOneField("Boss", on_delete=models.CASCADE, related_name="soru")
    tip = models.CharField(max_length=10, choices=TIPLER, default=TIP_MCQ)
    soru_metni = models.TextField()

    secenekler = models.JSONField(default=list, blank=True)
    dogru_secenek_index = models.IntegerField(null=True, blank=True)

    dogru_cevap_metni = models.CharField(max_length=500, blank=True, default="")
    kabul_edilen_cevaplar = models.JSONField(default=list, blank=True)

    context_doc_id = models.IntegerField(null=True, blank=True)  # dokuman id (ör: 3)
    ai_degerlendirme = models.BooleanField(default=False)        # AI feedback açık mı
    max_puan = models.PositiveIntegerField(default=100)

    def __str__(self):
        return f"BossSoru({self.boss.ad})"

class BossOnKosul(models.Model):
    boss = models.ForeignKey("Boss", on_delete=models.CASCADE, related_name="on_kosullar")
    gerekir_boss = models.ForeignKey("Boss", on_delete=models.CASCADE, related_name="kapi_acanlar")

    class Meta:
        unique_together = ("boss", "gerekir_boss")


class BossIlerleme(models.Model):
    kullanici = models.ForeignKey(User, on_delete=models.CASCADE, related_name="boss_ilerlemeleri")
    boss = models.ForeignKey("Boss", on_delete=models.CASCADE, related_name="ilerlemeler")

    en_yuksek_puan = models.PositiveIntegerField(default=0)
    xp_kazanilan_toplam = models.PositiveIntegerField(default=0)
    puan_kazanilan_toplam = models.PositiveIntegerField(default=0)
    tamamlandi = models.BooleanField(default=False)

    deneme_sayisi = models.PositiveIntegerField(default=0)
    son_deneme = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("kullanici", "boss")


class BossDeneme(models.Model):
    kullanici = models.ForeignKey(User, on_delete=models.CASCADE, related_name="boss_denemeleri")
    boss = models.ForeignKey("Boss", on_delete=models.CASCADE, related_name="denemeler")
    soru = models.ForeignKey("BossSoru", on_delete=models.CASCADE, related_name="denemeler")

    cevap_metni = models.TextField(blank=True, default="")
    secilen_index = models.IntegerField(null=True, blank=True)
    feedback = models.TextField(blank=True, default="")
    puan = models.PositiveIntegerField(default=0)
    dogru_mu = models.BooleanField(default=False)

    xp_eklendi = models.PositiveIntegerField(default=0)
    puan_eklendi = models.PositiveIntegerField(default=0)
    enerji_harcandi = models.PositiveIntegerField(default=0)

    olusturuldu = models.DateTimeField(default=timezone.now)
class KullaniciGorev(models.Model):
    kullanici = models.ForeignKey(User, on_delete=models.CASCADE, related_name="gorevlerim")
    gorev = models.ForeignKey(Gorev, on_delete=models.CASCADE, related_name="kullanicilar")

    baslangic = models.DateField()
    bitis = models.DateField()

    ilerleme = models.PositiveIntegerField(default=0)
    tamamlandi = models.BooleanField(default=False)
    odul_alindi = models.BooleanField(default=False)

    class Meta:
        unique_together = ("kullanici", "gorev", "baslangic", "bitis")

    def __str__(self):
        return f"KullaniciGorev(u={self.kullanici_id}, g={self.gorev_id}, {self.baslangic}-{self.bitis})"
        
class Basarim(models.Model):
    KOSUL_BOSS_TAMAMLAMA = "BOSS_TAMAMLAMA"
    KOSUL_TOPLAM_XP = "TOPLAM_XP"
    KOSUL_TOPLAM_PUAN = "TOPLAM_PUAN"
    KOSUL_STREAK = "STREAK"
    KOSUL_PERFECT = "PERFECT"
    KOSULLAR = [
        (KOSUL_BOSS_TAMAMLAMA, "Boss tamamla sayısı"),
        (KOSUL_TOPLAM_XP, "Toplam XP"),
        (KOSUL_TOPLAM_PUAN, "Toplam puan"),
        (KOSUL_STREAK, "Streak gün"),
        (KOSUL_PERFECT, "Perfect deneme"),
    ]

    kod = models.CharField(max_length=60, unique=True)
    ad = models.CharField(max_length=120)
    aciklama = models.TextField(blank=True)
    kosul_tur = models.CharField(max_length=30, choices=KOSULLAR)
    kosul_deger = models.PositiveIntegerField(default=1)
    param = models.JSONField(default=dict, blank=True)

    odul_xp = models.PositiveIntegerField(default=100)
    odul_puan = models.PositiveIntegerField(default=50)

    rozet = models.CharField(max_length=60, blank=True, default="")
    aktif = models.BooleanField(default=True)

    def __str__(self):
        return f"Basarim({self.kod})"


class KullaniciBasarim(models.Model):
    kullanici = models.ForeignKey(User, on_delete=models.CASCADE, related_name="basarimlarim")
    basarim = models.ForeignKey(Basarim, on_delete=models.CASCADE, related_name="kazananlar")
    kazanildi = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("kullanici", "basarim")


class Esya(models.Model):
    TIP_BOOSTER = "BOOSTER"
    TIP_TITLE = "TITLE"
    TIP_SKIN = "SKIN"
    TIPLER = [(TIP_BOOSTER, "Booster"), (TIP_TITLE, "Unvan"), (TIP_SKIN, "Skin")]

    kod = models.CharField(max_length=60, unique=True)
    ad = models.CharField(max_length=120)
    tip = models.CharField(max_length=20, choices=TIPLER)

    sure_dk = models.PositiveIntegerField(default=0)
    xp_carpan = models.FloatField(default=1.0)
    puan_carpan = models.FloatField(default=1.0)

    fiyat_puan = models.PositiveIntegerField(default=0)
    fiyat_xp = models.PositiveIntegerField(default=0)

    aktif = models.BooleanField(default=True)

    def __str__(self):
        return f"Esya({self.kod})"


class Envanter(models.Model):
    kullanici = models.ForeignKey(User, on_delete=models.CASCADE, related_name="envanter")
    esya = models.ForeignKey(Esya, on_delete=models.CASCADE, related_name="envanterler")
    adet = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("kullanici", "esya")


class AktifBooster(models.Model):
    kullanici = models.OneToOneField(User, on_delete=models.CASCADE, related_name="aktif_booster")
    esya = models.ForeignKey(Esya, on_delete=models.CASCADE, related_name="aktifler")
    bitis = models.DateTimeField()

    def aktif_mi(self):
        return timezone.now() < self.bitis
    
class OdulIslemi(models.Model):
    KAYNAK_BOSS = "BOSS"
    KAYNAK_GOREV = "GOREV"
    KAYNAK_BASARIM = "BASARIM"
    KAYNAK_MARKET = "MARKET"
    KAYNAK_GIRIS = "GIRIS"
    KAYNAKLAR = [
        (KAYNAK_BOSS, "Boss"),
        (KAYNAK_GOREV, "Görev"),
        (KAYNAK_BASARIM, "Başarım"),
        (KAYNAK_MARKET, "Market"),
        (KAYNAK_GIRIS, "Günlük giriş"),
    ]

    kullanici = models.ForeignKey(User, on_delete=models.CASCADE, related_name="odul_islemleri")
    kaynak = models.CharField(max_length=20, choices=KAYNAKLAR)
    aciklama = models.CharField(max_length=255, blank=True, default="")
    delta_xp = models.IntegerField(default=0)
    delta_puan = models.IntegerField(default=0)
    olusturuldu = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"OdulIslemi({self.kaynak}) xp={self.delta_xp} puan={self.delta_puan}"

