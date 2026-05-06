from django.db import models
from django.conf import settings

class DokumanNotu(models.Model):
    NOT_TURU_SECENEKLERI = [
        ("portal_calisma", "Portal Calisma"),
        ("portal_ozet", "Portal Ozet"),
    ]
    OLUSTURMA_KAYNAGI_SECENEKLERI = [
        ("user", "User"),
        ("ai", "AI"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",   # ✅ User tarafında reverse ilişki yok -> çakışma biter
    )
    dokuman = models.ForeignKey(
        "Dokuman",
        on_delete=models.CASCADE,
        related_name="portal_notlari",   # doc.portal_notlari
    )
    parca = models.ForeignKey(
        "Parca",
        on_delete=models.CASCADE,
        related_name="portal_notlari",   # parca.portal_notlari
        null=True, blank=True
    )

    adres = models.CharField(max_length=160, blank=True, default="")
    baslik = models.CharField(max_length=120, blank=True, default="")
    icerik = models.TextField(default="")
    not_turu = models.CharField(max_length=32, choices=NOT_TURU_SECENEKLERI, default="portal_calisma")
    etiketler = models.JSONField(default=list, blank=True)
    pinned = models.BooleanField(default=False)
    arsivli = models.BooleanField(default=False)
    olusturma_kaynagi = models.CharField(
        max_length=16,
        choices=OLUSTURMA_KAYNAGI_SECENEKLERI,
        default="user",
    )
    meta = models.JSONField(default=dict, blank=True)
    bagli_notlar = models.ManyToManyField(
        "Not",
        blank=True,
        related_name="bagli_portal_notlar",
    )
    kaynak_parcalar = models.ManyToManyField(
        "Parca",
        blank=True,
        related_name="bagli_portal_notlar",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-pinned", "-updated_at"]
        indexes = [
            models.Index(fields=["owner", "dokuman"]),
            models.Index(fields=["dokuman", "parca"]),
            models.Index(fields=["owner", "updated_at"]),
        ]

    def __str__(self):
        return f"DokumanNotu({self.id}) doc={self.dokuman_id} adres={self.adres}"

class Not(models.Model):
    NOT_TURU_SECENEKLERI = [
        ("serbest", "Serbest"),
        ("ozet", "Ozet"),
        ("kaynak", "Kaynak"),
        ("calisma", "Calisma"),
    ]
    OLUSTURMA_KAYNAGI_SECENEKLERI = [
        ("user", "User"),
        ("ai", "AI"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notlar"
    )

    dokuman = models.ForeignKey(
        "Dokuman",
        on_delete=models.CASCADE,
        related_name="notlar",
        null=True,
        blank=True,
    )

    parca = models.ForeignKey(
        "Parca",
        on_delete=models.CASCADE,
        related_name="notlar",
        null=True,
        blank=True,
    )

    adres = models.CharField(max_length=255, blank=True, default="")
    baslik = models.CharField(max_length=200, blank=True, default="")
    metin = models.TextField()

    not_turu = models.CharField(max_length=32, choices=NOT_TURU_SECENEKLERI, default="serbest")
    etiketler = models.JSONField(default=list, blank=True)
    pinned = models.BooleanField(default=False)
    arsivli = models.BooleanField(default=False)
    olusturma_kaynagi = models.CharField(
        max_length=16,
        choices=OLUSTURMA_KAYNAGI_SECENEKLERI,
        default="user",
    )
    kaynak_parca_idleri = models.JSONField(default=list, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-pinned", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["owner", "dokuman"], name="dokuman_not_owner_i_57d8a0_idx"),
            models.Index(fields=["owner", "parca"], name="dokuman_not_owner_i_0fe8bd_idx"),
            models.Index(fields=["owner", "updated_at"], name="dokuman_not_owner_i_64b632_idx"),
            models.Index(fields=["owner", "not_turu"], name="dokuman_not_owner_i_998269_idx"),
        ]

    def __str__(self):
        return f"Not({self.id}) doc={self.dokuman_id} adres={self.adres}"


class MetrikKaydi(models.Model):
    kullanici = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="metrik_kayitlari",
    )
    dokuman = models.ForeignKey(
        "Dokuman",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="metrik_kayitlari",
    )
    parca = models.ForeignKey(
        "Parca",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="metrik_kayitlari",
    )
    ilgili_not_id = models.PositiveIntegerField(null=True, blank=True)
    ilgili_portal_not_id = models.PositiveIntegerField(null=True, blank=True)
    ilgili_feedback_id = models.PositiveIntegerField(null=True, blank=True)
    olay_turu = models.CharField(max_length=64)
    kaynak_modul = models.CharField(max_length=64, default="dokuman.api")
    skor_ozeti = models.JSONField(default=dict, blank=True)
    durum = models.CharField(max_length=32, default="ok")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["kullanici", "created_at"], name="dokuman_met_kullani_0aab03_idx"),
            models.Index(fields=["olay_turu", "created_at"], name="dokuman_met_olay_t_89f31c_idx"),
            models.Index(fields=["dokuman", "olay_turu"], name="dokuman_met_dokuman_2177f2_idx"),
        ]

    def __str__(self):
        return f"MetrikKaydi({self.olay_turu}) kullanici={self.kullanici_id}"


class KullaniciGeriBildirim(models.Model):
    FEEDBACK_TURU_SECENEKLERI = [
        ("iyi", "Iyi"),
        ("kotu", "Kotu"),
        ("eksik", "Eksik"),
        ("alakasiz", "Alakasiz"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="geri_bildirimler",
    )
    dokuman = models.ForeignKey(
        "Dokuman",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="geri_bildirimler",
    )
    parca = models.ForeignKey(
        "Parca",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="geri_bildirimler",
    )
    not_kaydi = models.ForeignKey(
        "Not",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="geri_bildirimler",
    )
    portal_not = models.ForeignKey(
        "DokumanNotu",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="geri_bildirimler",
    )
    feedback_turu = models.CharField(max_length=24, choices=FEEDBACK_TURU_SECENEKLERI)
    kisa_not = models.CharField(max_length=280, blank=True, default="")
    kaynak_modul = models.CharField(max_length=64, default="dokuman.api")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["owner", "created_at"], name="dokuman_kul_owner_i_7ab942_idx"),
            models.Index(fields=["feedback_turu", "created_at"], name="dokuman_kul_feedbac_95f770_idx"),
            models.Index(fields=["kaynak_modul", "created_at"], name="dokuman_kul_kaynak__7af523_idx"),
        ]

    def __str__(self):
        return f"KullaniciGeriBildirim({self.feedback_turu}) owner={self.owner_id}"
class KullaniciTercih(models.Model):
    TEMA_S = [
        ("spor", "Spor"),
        ("yemek", "Yemek"),
        ("oyun", "Oyun"),
        ("teknoloji", "Teknoloji"),
        ("film", "Film/Dizi"),
        ("genel", "Genel"),
    ]
    TARZ_S = [
        ("kisa", "Kısa"),
        ("adim_adim", "Adım adım"),
        ("bol_ornek", "Bol örnek"),
        ("hafif_mizah", "Hafif mizah"),
    ]
    SEVIYE_S = [
        ("baslangic", "Başlangıç"),
        ("orta", "Orta"),
        ("ileri", "İleri"),
    ]
    TEMA_CHOICES = [
        ("genel", "Genel"),
        ("yazilim", "Yazılım"),
        ("saglik", "Sağlık"),
        ("matematik", "Matematik"),
        ("spor", "Spor"),
        ("yemek", "Yemek"),
        ("oyun", "Oyun"),
        ("teknoloji", "Teknoloji"),
        ("film", "Film"),
    ]

    TARZ_CHOICES = [
        ("adim_adim", "Adım adım"),
        ("ornekli", "Örnekli"),
        ("kisa", "Kısa"),
        ("derin", "Derin"),
    ]

    SEVIYE_CHOICES = [
        ("baslangic", "Başlangıç"),
        ("orta", "Orta"),
        ("ileri", "İleri"),
    ]
    TON_CHOICES = [
        ("kanka", "Kanka"),
        ("hoca", "Hoca"),
        ("teknik", "Teknik"),
        ("sunum", "Sunum"),
    ]
    DETAY_CHOICES = [
        ("dusuk", "Düşük"),
        ("orta", "Orta"),
        ("yuksek", "Yüksek"),
    ]
    MIZAH_CHOICES = [
        ("yok", "Yok"),
        ("hafif", "Hafif"),
        ("orta", "Orta"),
    ]
    tema = models.CharField(max_length=32, choices=TEMA_CHOICES, default="genel")
    tarz = models.CharField(max_length=32, choices=TARZ_CHOICES, default="adim_adim")
    seviye = models.CharField(max_length=32, choices=SEVIYE_CHOICES, default="baslangic")
    ton = models.CharField(max_length=32, choices=TON_CHOICES, default="teknik")
    detay_seviyesi = models.CharField(max_length=32, choices=DETAY_CHOICES, default="orta")
    mizah_seviyesi = models.CharField(max_length=32, choices=MIZAH_CHOICES, default="yok")
    kullanici = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="doc_tercih")

    def __str__(self):
        return f"Tercih({self.kullanici_id}) {self.tema}/{self.ton}/{self.detay_seviyesi}"

class Dokuman(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dokumanlar")
    baslik = models.CharField(max_length=255, blank=True)
    dosya = models.FileField(upload_to="dokuman_asistani/")
    mime = models.CharField(max_length=128, blank=True)
    durum = models.CharField(max_length=32, default="yuklendi")  # yuklendi|parcalandi|hata
    hata = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Parca(models.Model):
    dokuman = models.ForeignKey(Dokuman, on_delete=models.CASCADE, related_name="parcalar")
    sira = models.PositiveIntegerField(default=0)
    tur = models.CharField(max_length=32, default="paragraf")
    metin = models.TextField()
    adres = models.CharField(max_length=255)
    meta = models.JSONField(default=dict, blank=True)
    zorluk_skoru = models.FloatField(default=0.0)
    zorluk = models.CharField(max_length=16, default="kolay")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["dokuman", "sira"]),
            models.Index(fields=["dokuman", "zorluk"]),
        ]

class AnlamadimKaydi(models.Model):
    kullanici = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="anlamadim_kayitlari")

    dokuman = models.ForeignKey("Dokuman", null=True, blank=True, on_delete=models.SET_NULL, related_name="anlamadim_kayitlari")
    parca = models.ForeignKey("Parca", null=True, blank=True, on_delete=models.SET_NULL, related_name="anlamadim_kayitlari")

    adres = models.CharField(max_length=255, blank=True, default="")

    tema = models.CharField(max_length=20, blank=True, default="genel")
    tarz = models.CharField(max_length=20, blank=True, default="adim_adim")
    seviye = models.CharField(max_length=20, blank=True, default="baslangic")

    kullanici_mesaj = models.TextField(blank=True, default="")
    cikti_text = models.TextField(blank=True, default="")
    cikti_json = models.JSONField(blank=True, null=True)

    olusturuldu = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"AnlamadimKaydi(u={self.kullanici_id}, parca={self.parca_id})"
    
class Profil(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profil")
    xp = models.IntegerField(default=0)
    seviye = models.IntegerField(default=1)
    unvan = models.CharField(max_length=100, blank=True, default="Yeni Başlayan")

    def __str__(self):
        return f"{self.user.username} | Lv.{self.seviye} | XP:{self.xp}"

class OdulLog(models.Model):
    kullanici = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dokuman_odul_loglari"
    )

    dokuman = models.ForeignKey(
        "Dokuman",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="dokuman_odul_loglari"
    )

    parca = models.ForeignKey(
        "Parca",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="dokuman_odul_loglari"
    )

    kaynak = models.CharField(max_length=50, default="boss")
    puan = models.IntegerField(default=0)
    xp_kazanilan = models.IntegerField(default=0)
    aciklama = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.kullanici} +{self.xp_kazanilan} XP ({self.kaynak})"


class YapayZekaModeli(models.Model):
    ad = models.CharField(max_length=120)
    aciklama = models.TextField(blank=True)
    gguf_dosya_adi = models.CharField(max_length=255)
    gguf_dosya_yolu = models.CharField(max_length=500)
    model_kisa_adi = models.CharField(max_length=120, default="qwen-docverse")
    kuantizasyon_turu = models.CharField(max_length=50, default="Q5_K_M")
    aktif_mi = models.BooleanField(default=True)
    varsayilan_mi = models.BooleanField(default=False)
    olusturulma_tarihi = models.DateTimeField(auto_now_add=True)
    guncellenme_tarihi = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Yapay Zeka Modeli"
        verbose_name_plural = "Yapay Zeka Modelleri"

    def __str__(self):
        return self.ad
