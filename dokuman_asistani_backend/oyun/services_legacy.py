from django.db import transaction
from django.utils import timezone
from django.db.models import Sum
from .models import (
    OyunProfil, OdulIslemi, Bildirim,
    KullaniciGorev, Gorev,
    Basarim, KullaniciBasarim,
    AktifBooster, Envanter, Esya,
)


def _week_range(today):
    start = today - timezone.timedelta(days=today.weekday())  # pazartesi
    end = start + timezone.timedelta(days=7)
    return start, end


def profil_getir(user):
    profil, _ = OyunProfil.objects.get_or_create(kullanici=user)
    return profil


def booster_carpanlari(user):
    ab = getattr(user, "aktif_booster", None)
    if not ab:
        return 1.0, 1.0
    if not ab.aktif_mi():
        return 1.0, 1.0
    return float(ab.esya.xp_carpan or 1.0), float(ab.esya.puan_carpan or 1.0)


def streak_carpani(profil: OyunProfil) -> float:
    s = int(profil.streak_gun or 0)
    if s >= 14:
        return 1.15
    if s >= 7:
        return 1.10
    if s >= 3:
        return 1.05
    return 1.0


@transaction.atomic
def odul_ver(user, kaynak, aciklama, xp, puan):
    profil = profil_getir(user)
    profil.enerji_guncelle()

    xp_mul, puan_mul = booster_carpanlari(user)
    s_mul = streak_carpani(profil)

    xp_final = int(round(max(0, xp) * xp_mul * s_mul))
    puan_final = int(round(max(0, puan) * puan_mul * s_mul))

    # ✅ Delta yoksa: log yazma + DB yazma
    if xp_final <= 0 and puan_final <= 0:
        return 0, 0, profil

    profil.xp_ekle(xp_final)
    profil.puan_ekle(puan_final)
    profil.save()

    OdulIslemi.objects.create(
        kullanici=user,
        kaynak=kaynak,
        aciklama=aciklama,
        delta_xp=xp_final,
        delta_puan=puan_final,
    )
    return xp_final, puan_final, profil

def bildirim_gonder(user, baslik, mesaj):
    Bildirim.objects.create(kullanici=user, baslik=baslik, mesaj=mesaj)


def gunluk_giris(user):
    profil = profil_getir(user)
    today = timezone.localdate()

    last = profil.son_giris_tarihi
    if last == today:
        return profil, False

    if last == (today - timezone.timedelta(days=1)):
        profil.streak_gun += 1
    else:
        profil.streak_gun = 1

    profil.son_giris_tarihi = today
    profil.save()

    xp = 20 + min(80, profil.streak_gun * 5)
    puan = 10 + min(40, profil.streak_gun * 2)

    xp_final, puan_final, profil = odul_ver(user, "GIRIS", "Günlük giriş ödülü", xp, puan)
    bildirim_gonder(user, "Günlük giriş!", f"+{xp_final} XP, +{puan_final} puan (streak: {profil.streak_gun})")
    return profil, True


def _gorev_pencere(gorev_tur):
    today = timezone.localdate()
    if gorev_tur == Gorev.TUR_DAILY:
        return today, today
    start, end = _week_range(today)
    return start, end - timezone.timedelta(days=1)


def gorevleri_hazirla(user):
    for g in Gorev.objects.filter(aktif=True):
        bas, bit = _gorev_pencere(g.tur)
        KullaniciGorev.objects.get_or_create(
            kullanici=user, gorev=g, baslangic=bas, bitis=bit,
            defaults={"ilerleme": 0, "tamamlandi": False, "odul_alindi": False}
        )


def gorev_event(user, event_type, amount=1, boss_id=None, gained_xp=0, gained_puan=0, perfect=False, boss_completed=False):
    gorevleri_hazirla(user)
    today = timezone.localdate()

    qs = KullaniciGorev.objects.select_related("gorev").filter(
        kullanici=user,
        baslangic__lte=today,
        bitis__gte=today,
        tamamlandi=False,
    )

    for kg in qs:
        g = kg.gorev

        if boss_id is not None and g.param.get("boss_id"):
            if int(g.param["boss_id"]) != int(boss_id):
                continue

        inc = 0
        if g.hedef_tur == Gorev.HEDEF_DENEME and event_type == "DENEME":
            inc = amount
        elif g.hedef_tur == Gorev.HEDEF_BOSS_TAMAMLA and boss_completed:
            inc = 1
        elif g.hedef_tur == Gorev.HEDEF_PUAN_TOPLA and gained_puan > 0:
            inc = int(gained_puan)
        elif g.hedef_tur == Gorev.HEDEF_XP_TOPLA and gained_xp > 0:
            inc = int(gained_xp)
        elif g.hedef_tur == Gorev.HEDEF_PERFECT and perfect:
            inc = 1

        if inc <= 0:
            continue

        kg.ilerleme = min(g.hedef_deger, kg.ilerleme + inc)
        if kg.ilerleme >= g.hedef_deger:
            kg.tamamlandi = True
            bildirim_gonder(user, "Görev tamamlandı!", f"'{g.ad}' görevi bitti. Ödülü almayı unutma.")
        kg.save()


def gorev_odul_al(user, kullanici_gorev: KullaniciGorev):
    if not kullanici_gorev.tamamlandi:
        raise ValueError("Görev tamamlanmamış.")
    if kullanici_gorev.odul_alindi:
        return 0, 0, profil_getir(user)

    g = kullanici_gorev.gorev
    xp, puan, profil = odul_ver(user, "GOREV", f"Görev ödülü: {g.ad}", g.odul_xp, g.odul_puan)
    kullanici_gorev.odul_alindi = True
    kullanici_gorev.save()
    return xp, puan, profil


def basarim_kontrol(user):
    profil = profil_getir(user)
    tamamlanan_boss_sayisi = user.boss_ilerlemeleri.filter(tamamlandi=True).count()
    perfect_sayisi = user.boss_denemeleri.filter(puan__gte=100).count()  # max_puan=100 varsayımı

    adaylar = Basarim.objects.filter(aktif=True).exclude(kazananlar__kullanici=user)
    kazanilanlar = []

    for b in adaylar:
        ok = False
        if b.kosul_tur == Basarim.KOSUL_TOPLAM_XP and profil.toplam_xp >= b.kosul_deger:
            ok = True
        elif b.kosul_tur == Basarim.KOSUL_TOPLAM_PUAN and profil.toplam_puan >= b.kosul_deger:
            ok = True
        elif b.kosul_tur == Basarim.KOSUL_STREAK and profil.streak_gun >= b.kosul_deger:
            ok = True
        elif b.kosul_tur == Basarim.KOSUL_BOSS_TAMAMLAMA and tamamlanan_boss_sayisi >= b.kosul_deger:
            ok = True
        elif b.kosul_tur == Basarim.KOSUL_PERFECT and perfect_sayisi >= b.kosul_deger:
            ok = True

        if ok:
            KullaniciBasarim.objects.create(kullanici=user, basarim=b)
            xp, puan, _ = odul_ver(user, "BASARIM", f"Başarım: {b.ad}", b.odul_xp, b.odul_puan)
            bildirim_gonder(user, "Başarım açıldı!", f"{b.ad} (+{xp} XP, +{puan} puan)")
            kazanilanlar.append(b.kod)

    return kazanilanlar


@transaction.atomic
def market_satin_al(user, esya: Esya, adet: int):
    if adet <= 0:
        raise ValueError("adet>0 olmalı")

    profil = profil_getir(user)

    toplam_puan = esya.fiyat_puan * adet
    toplam_xp = esya.fiyat_xp * adet

    if profil.toplam_puan < toplam_puan or profil.toplam_xp < toplam_xp:
        raise ValueError("Yetersiz bakiye.")

    profil.toplam_puan -= toplam_puan
    profil.toplam_xp -= toplam_xp
    profil.seviye = (profil.toplam_xp // 100) + 1
    profil.save()

    OdulIslemi.objects.create(
        kullanici=user, kaynak="MARKET",
        aciklama=f"Satın alım: {esya.ad} x{adet}",
        delta_xp=-toplam_xp, delta_puan=-toplam_puan
    )

    env, _ = Envanter.objects.get_or_create(kullanici=user, esya=esya, defaults={"adet": 0})
    env.adet += adet
    env.save()

    return env.adet, profil


@transaction.atomic
def booster_kullan(user, esya: Esya):
    if esya.tip != Esya.TIP_BOOSTER:
        raise ValueError("Bu eşya booster değil.")
    if esya.sure_dk <= 0:
        raise ValueError("Booster süresi hatalı.")

    env = Envanter.objects.select_for_update().filter(kullanici=user, esya=esya).first()
    if not env or env.adet <= 0:
        raise ValueError("Envanterde yok.")

    env.adet -= 1
    env.save()

    bitis = timezone.now() + timezone.timedelta(minutes=esya.sure_dk)

    ab = getattr(user, "aktif_booster", None)
    if ab and ab.aktif_mi():
        ab.bitis = max(ab.bitis, timezone.now()) + timezone.timedelta(minutes=esya.sure_dk)
        ab.esya = esya
        ab.save()
    else:
        AktifBooster.objects.update_or_create(kullanici=user, defaults={"esya": esya, "bitis": bitis})

    bildirim_gonder(user, "Booster aktif!", f"{esya.ad} aktif edildi.")
    return True