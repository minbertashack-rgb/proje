from django.core.management.base import BaseCommand
from django.db import transaction
from oyun.models import Boss, BossSoru, BossOnKosul, Gorev, Basarim, Esya

class Command(BaseCommand):
    help = "Oyun modülü için demo seed basar."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Önce seed verilerini siler")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["reset"]:
            BossOnKosul.objects.all().delete()
            BossSoru.objects.all().delete()
            Boss.objects.all().delete()
            Gorev.objects.all().delete()
            Basarim.objects.all().delete()
            Esya.objects.all().delete()

        b1, _ = Boss.objects.get_or_create(
            ad="HTTP MiniBoss",
            defaults=dict(aciklama="HTTP temelleri", seviye_gereksinim=1, siralama=1,
                          zorluk=1, enerji_maliyeti=1, cooldown_saniye=5,
                          odul_xp=120, odul_puan=80, tamamlama_esigi=60, aktif=True)
        )
        BossSoru.objects.get_or_create(
            boss=b1,
            defaults=dict(tip="MCQ", soru_metni="HTTP'de istemciden sunucuya giden mesaj hangisi?",
                          secenekler=["Response","Request","Cookie","Session"],
                          dogru_secenek_index=1, max_puan=100)
        )

        b2, _ = Boss.objects.get_or_create(
            ad="SQL Canavarı",
            defaults=dict(aciklama="SELECT sorusu", seviye_gereksinim=1, siralama=2,
                          zorluk=2, enerji_maliyeti=2, cooldown_saniye=8,
                          odul_xp=160, odul_puan=120, tamamlama_esigi=60, aktif=True)
        )
        BossSoru.objects.get_or_create(
            boss=b2,
            defaults=dict(tip="MCQ", soru_metni="SQL'de tüm sütunları getiren ifade hangisi?",
                          secenekler=["SELECT * FROM tablo;","GET ALL tablo;","SHOW tablo;","FETCH tablo;"],
                          dogru_secenek_index=0, max_puan=100)
        )
        BossOnKosul.objects.get_or_create(boss=b2, gerekir_boss=b1)

        Gorev.objects.get_or_create(ad="1 deneme yap", tur="DAILY", hedef_tur="DENEME", hedef_deger=1,
                                    defaults={"odul_xp":40, "odul_puan":20, "aktif":True})
        Gorev.objects.get_or_create(ad="1 boss tamamla", tur="DAILY", hedef_tur="BOSS_TAMAMLA", hedef_deger=1,
                                    defaults={"odul_xp":80, "odul_puan":40, "aktif":True})

        Basarim.objects.get_or_create(kod="BOSS_1",
                                      defaults=dict(ad="İlk Boss", aciklama="1 boss tamamla",
                                                    kosul_tur="BOSS_TAMAMLAMA", kosul_deger=1,
                                                    odul_xp=120, odul_puan=50, rozet="first-boss", aktif=True))

        Esya.objects.get_or_create(kod="XP_BOOST_30",
                                   defaults=dict(ad="XP Booster (30dk)", tip="BOOSTER",
                                                 sure_dk=30, xp_carpan=1.25, puan_carpan=1.0,
                                                 fiyat_puan=120, fiyat_xp=0, aktif=True))

        self.stdout.write(self.style.SUCCESS("seed ok"))