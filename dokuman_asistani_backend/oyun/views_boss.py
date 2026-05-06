from django.utils import timezone
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    Boss, BossSoru, BossDeneme, BossIlerleme, BossOnKosul,
    OyunProfil, OdulIslemi, Bildirim
)
from .serializers import (
    BossListeSerializer, BossDetaySerializer,
    BossCevaplaSerializer, BossDenemeSerializer,
    OyunProfilSerializer, text_puanla
)


def boss_kilitli_mi(user, boss: Boss):
    profil, _ = OyunProfil.objects.get_or_create(kullanici=user)

    if profil.seviye < boss.seviye_gereksinim:
        return True, "Seviye yetersiz."

    prereq_ids = list(
        BossOnKosul.objects.filter(boss=boss).values_list("gerekir_boss_id", flat=True)
    )
    if prereq_ids:
        done = set(
            BossIlerleme.objects.filter(
                kullanici=user, boss_id__in=prereq_ids, tamamlandi=True
            ).values_list("boss_id", flat=True)
        )
        if len(done) != len(prereq_ids):
            return True, "Ön koşul boss(lar) tamamlanmamış."

    return False, ""


class BossListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Boss.objects.filter(aktif=True).order_by("siralama", "id")
        ser = BossListeSerializer(qs, many=True, context={"request": request})
        return Response(ser.data)


class BossDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, boss_id: int):
        boss = Boss.objects.select_related("soru").filter(id=boss_id, aktif=True).first()
        if not boss:
            return Response({"detail": "Boss yok"}, status=404)
        if not hasattr(boss, "soru"):
            return Response({"detail": "Bu boss için soru tanımlı değil"}, status=400)

        ser = BossDetaySerializer(boss, context={"request": request})
        return Response(ser.data)


class BossCevaplaAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, boss_id: int):
        boss = Boss.objects.select_related("soru").filter(id=boss_id, aktif=True).first()
        if not boss:
            return Response({"detail": "Boss yok"}, status=404)
        if not hasattr(boss, "soru"):
            return Response({"detail": "Bu boss için soru tanımlı değil"}, status=400)

        kilitli, msg = boss_kilitli_mi(request.user, boss)
        if kilitli:
            return Response({"detail": msg}, status=403)

        profil, _ = OyunProfil.objects.get_or_create(kullanici=request.user)
        profil.enerji_guncelle()

        ilerleme, _ = BossIlerleme.objects.get_or_create(kullanici=request.user, boss=boss)

        # cooldown kontrol
        now = timezone.now()
        if ilerleme.son_deneme:
            diff = (now - ilerleme.son_deneme).total_seconds()
            if diff < boss.cooldown_saniye:
                kalan = int(boss.cooldown_saniye - diff)
                return Response({"detail": f"Cooldown aktif. {kalan}s bekle."}, status=429)

        # enerji kontrol/harca
        if not profil.enerji_harcala(boss.enerji_maliyeti):
            return Response(
                {"detail": "Enerji yetersiz.", "enerji": profil.enerji, "enerji_maliyeti": boss.enerji_maliyeti},
                status=400
            )

        inp = BossCevaplaSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        v = inp.validated_data

        soru: BossSoru = boss.soru

        cevap_metni = (v.get("cevap_metni") or "").strip()
        secilen_index = v.get("secilen_index", None)

        # puanlama
        puan = 0
        feedback = ""
        dogru_mu = False

        if soru.tip == BossSoru.TIP_MCQ:
            if secilen_index is None:
                return Response({"detail": "MCQ için secilen_index göndermelisin."}, status=400)

            dogru_idx = soru.dogru_secenek_index
            dogru_mu = (dogru_idx is not None and int(secilen_index) == int(dogru_idx))
            puan = soru.max_puan if dogru_mu else 0
            feedback = "Doğru ✅" if dogru_mu else "Yanlış ❌"

        else:  # TEXT
            puan = text_puanla(
                kullanici_cevap=cevap_metni,
                dogru=soru.dogru_cevap_metni,
                kabul_list=soru.kabul_edilen_cevaplar,
                max_puan=soru.max_puan
            )
            dogru_mu = puan >= int(boss.tamamlama_esigi or 60)
            feedback = f"Puan: {puan}/{soru.max_puan}"

        # kazanım: puana göre kademeli ödül + daha önce kazanılanı aşmayacak şekilde delta
        ratio = (puan / soru.max_puan) if soru.max_puan else 0.0
        hedef_xp_toplam = int(round(boss.odul_xp * ratio))
        hedef_puan_toplam = int(round(boss.odul_puan * ratio))

        xp_delta = max(0, hedef_xp_toplam - int(ilerleme.xp_kazanilan_toplam or 0))
        puan_delta = max(0, hedef_puan_toplam - int(ilerleme.puan_kazanilan_toplam or 0))

        once_tamamlandi = bool(ilerleme.tamamlandi)

        with transaction.atomic():
            # profil güncelle
            profil = OyunProfil.objects.select_for_update().get(kullanici=request.user)
            profil.enerji_guncelle()  # safe
            # enerji harcandığı için enerji zaten düşmüş durumda instance üzerinde; DB’ye yazalım
            profil.xp_ekle(xp_delta)
            profil.puan_ekle(puan_delta)
            profil.save()

            # ilerleme güncelle
            ilerleme = BossIlerleme.objects.select_for_update().get(kullanici=request.user, boss=boss)
            ilerleme.deneme_sayisi = int(ilerleme.deneme_sayisi or 0) + 1
            ilerleme.son_deneme = now
            ilerleme.en_yuksek_puan = max(int(ilerleme.en_yuksek_puan or 0), int(puan))
            ilerleme.xp_kazanilan_toplam = int(ilerleme.xp_kazanilan_toplam or 0) + int(xp_delta)
            ilerleme.puan_kazanilan_toplam = int(ilerleme.puan_kazanilan_toplam or 0) + int(puan_delta)
            ilerleme.tamamlandi = ilerleme.en_yuksek_puan >= int(boss.tamamlama_esigi or 60)
            ilerleme.save()

            # deneme kaydı
            deneme = BossDeneme.objects.create(
                kullanici=request.user,
                boss=boss,
                soru=soru,
                cevap_metni=cevap_metni,
                secilen_index=secilen_index,
                feedback=feedback,
                puan=puan,
                dogru_mu=dogru_mu,
                xp_eklendi=xp_delta,
                puan_eklendi=puan_delta,
                enerji_harcandi=boss.enerji_maliyeti,
            )

            # ödül log
            if xp_delta or puan_delta:
                OdulIslemi.objects.create(
                    kullanici=request.user,
                    kaynak=OdulIslemi.KAYNAK_BOSS,
                    aciklama=f"Boss: {boss.ad}",
                    delta_xp=xp_delta,
                    delta_puan=puan_delta,
                )

            # bildirim (ilk kez tamamlandıysa)
            if (not once_tamamlandi) and ilerleme.tamamlandi:
                Bildirim.objects.create(
                    kullanici=request.user,
                    baslik="Boss Tamamlandı!",
                    mesaj=f"'{boss.ad}' bossunu tamamladın. +{xp_delta} XP, +{puan_delta} puan.",
                )

        return Response({
            "boss_id": boss.id,
            "puan": puan,
            "dogru_mu": dogru_mu,
            "tamamlandi": ilerleme.tamamlandi,
            "en_yuksek_puan": ilerleme.en_yuksek_puan,
            "xp_delta": xp_delta,
            "puan_delta": puan_delta,
            "feedback": feedback,
            "enerji_kaldi": profil.enerji,
            "deneme": BossDenemeSerializer(deneme).data,
            "profil": OyunProfilSerializer(profil).data,
        })