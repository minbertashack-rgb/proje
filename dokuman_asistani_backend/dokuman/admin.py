from django.contrib import admin
from .models import Dokuman, YapayZekaModeli

@admin.register(Dokuman)
class DokumanYonetimi(admin.ModelAdmin):
    list_display = ("id", "baslik", "durum", "mime", "created_at", "owner")
    list_filter = ("durum", "mime")
    search_fields = ("baslik",)
    ordering = ("-created_at",)


@admin.register(YapayZekaModeli)
class YapayZekaModeliYonetimi(admin.ModelAdmin):
    list_display = ("ad", "model_kisa_adi", "kuantizasyon_turu", "aktif_mi", "varsayilan_mi", "guncellenme_tarihi")
    list_filter = ("aktif_mi", "varsayilan_mi", "kuantizasyon_turu")
    search_fields = ("ad", "gguf_dosya_adi", "model_kisa_adi")
    ordering = ("-guncellenme_tarihi",)
