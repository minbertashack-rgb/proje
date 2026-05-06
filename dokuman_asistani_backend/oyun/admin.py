from django.contrib import admin
from .models import (
    Boss, BossSoru, BossOnKosul, BossIlerleme, BossDeneme,
    Gorev, KullaniciGorev,
    Basarim, KullaniciBasarim,
    Esya, Envanter, AktifBooster,
    Bildirim, OdulIslemi,
    OyunProfil
)

class BossSoruInline(admin.StackedInline):
    model = BossSoru
    extra = 0
    max_num = 1
    can_delete = True

class BossOnKosulInline(admin.TabularInline):
    model = BossOnKosul
    fk_name = "boss"
    extra = 0

@admin.register(Boss)
class BossAdmin(admin.ModelAdmin):
    list_display = ("id", "ad", "aktif", "siralama", "seviye_gereksinim", "odul_xp", "odul_puan", "tamamlama_esigi")
    list_filter = ("aktif", "seviye_gereksinim")
    search_fields = ("ad", "aciklama")
    ordering = ("siralama", "id")
    inlines = [BossSoruInline, BossOnKosulInline]

@admin.register(Gorev)
class GorevAdmin(admin.ModelAdmin):
    list_display = ("id", "ad", "tur", "hedef_tur", "hedef_deger", "odul_xp", "odul_puan", "aktif")
    list_filter = ("tur", "hedef_tur", "aktif")
    search_fields = ("ad",)

@admin.register(Basarim)
class BasarimAdmin(admin.ModelAdmin):
    list_display = ("id", "kod", "ad", "kosul_tur", "kosul_deger", "odul_xp", "odul_puan", "aktif")
    list_filter = ("kosul_tur", "aktif")
    search_fields = ("kod", "ad")

@admin.register(Esya)
class EsyaAdmin(admin.ModelAdmin):
    list_display = ("id", "kod", "ad", "tip", "fiyat_puan", "fiyat_xp", "aktif")
    list_filter = ("tip", "aktif")
    search_fields = ("kod", "ad")

# Okuma amaçlı (kalabalık olmasın diye istersen kaldırırsın)
admin.site.register(OyunProfil)
admin.site.register(BossIlerleme)
admin.site.register(BossDeneme)
admin.site.register(KullaniciGorev)
admin.site.register(KullaniciBasarim)
admin.site.register(Envanter)
admin.site.register(AktifBooster)
admin.site.register(Bildirim)
admin.site.register(OdulIslemi)