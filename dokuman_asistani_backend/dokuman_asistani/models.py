# dokuman_asistani/models.py
from django.conf import settings
from django.db import models
from django.db.models import Q, F
from django.utils import timezone


class Dokuman(models.Model):
    """
    Modül 6 için minimum doküman modeli:
    - metin: normalize edilmiş tam metin
    - sayfa_kirilimlari: PDF/text parse sırasında page start char index listesi (opsiyonel)
      örn: [0, 1820, 3655, ...] => 1. sayfa 0'dan başlar, 2. sayfa 1820'den...
    """
    kullanici = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dokumanlar")
    baslik = models.CharField(max_length=200)
    metin = models.TextField(default="", blank=True)
    dil = models.CharField(max_length=10, default="tr")
    sayfa_kirilimlari = models.JSONField(null=True, blank=True)  # opsiyonel
    newline_indices = models.JSONField(null=True, blank=True)  # O(log N) satır hesabı için önbellek
    olusturuldu = models.DateTimeField(default=timezone.now)
    guncellendi = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.id} - {self.baslik}"


class Vurgu(models.Model):
    """
    Highlight / Evidence span’i.
    Span referansı: dokuman.metin içindeki char offset aralığı [baslangic_char, bitis_char)
    """
    ETIKET_SECENEKLERI = [
        ("kanit", "Kanit"),
        ("cevap", "Cevap"),
        ("not", "Not"),
        ("secim", "Secim"),
    ]

    dokuman = models.ForeignKey(Dokuman, on_delete=models.CASCADE, related_name="vurgular")
    olusturan = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vurgular")

    etiket = models.CharField(max_length=20, choices=ETIKET_SECENEKLERI, default="kanit")
    baslangic_char = models.PositiveIntegerField()
    bitis_char = models.PositiveIntegerField()

    # UI için opsiyonel, istersen hiç kullanma
    renk = models.CharField(max_length=20, null=True, blank=True)

    # skor, kaynak chunk_id, qa_id, embedding_score vs gibi metadata’yı buraya basarsın
    meta = models.JSONField(null=True, blank=True)

    olusturuldu = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["dokuman", "etiket"]),
            models.Index(fields=["dokuman", "baslangic_char", "bitis_char"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(bitis_char__gt=F("baslangic_char")),
                name="vurgu_bitis_gt_baslangic",
            ),
        ]

    def __str__(self):
        return f"Vurgu({self.id}) doc={self.dokuman_id} [{self.baslangic_char},{self.bitis_char})"
    
# --- MODÜL 8: Zor Yer (Chunk + Zorluk Skoru) ---

class DokumanParca(models.Model):
    """
    Doküman metni içinden alınan parça/chunk.
    Referans: Dokuman.metin içindeki [baslangic_char, bitis_char) aralığı.
    """
    dokuman = models.ForeignKey(Dokuman, on_delete=models.CASCADE, related_name="parcalar")
    sira_no = models.PositiveIntegerField()

    baslangic_char = models.PositiveIntegerField()
    bitis_char = models.PositiveIntegerField()

    # UI / debug için opsiyonel (istersen hiç kullanma)
    sayfa_no = models.IntegerField(null=True, blank=True)
    baslik = models.CharField(max_length=255, blank=True, default="")
    icerik = models.TextField(default="", blank=True)  # ister substring, ister boş bırak

    meta = models.JSONField(null=True, blank=True)  # skor detayları, kaynak vs

    olusturuldu = models.DateTimeField(default=timezone.now)
    guncellendi = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("dokuman", "sira_no")]
        indexes = [
            models.Index(fields=["dokuman", "sira_no"]),
            models.Index(fields=["dokuman", "baslangic_char", "bitis_char"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(bitis_char__gt=F("baslangic_char")),
                name="parca_bitis_gt_baslangic",
            ),
        ]
        ordering = ["dokuman_id", "sira_no"]

    def __str__(self):
        return f"Parca(doc={self.dokuman_id}, sira={self.sira_no})"


class ZorYer(models.Model):
    """
    Her parça için 0-100 arası zorluk skoru + metrikleri tutar.
    """
    parca = models.OneToOneField(DokumanParca, on_delete=models.CASCADE, related_name="zor_yer")
    zorluk_skoru = models.PositiveSmallIntegerField(default=0)  # 0..100
    metrikler = models.JSONField(default=dict, blank=True)      # neden/hesap çıktıları

    olusturuldu = models.DateTimeField(default=timezone.now)
    guncellendi = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-zorluk_skoru", "-guncellendi"]
        indexes = [
            models.Index(fields=["zorluk_skoru"]),
        ]

    def __str__(self):
        return f"ZorYer(parca={self.parca_id}, skor={self.zorluk_skoru})"
    
