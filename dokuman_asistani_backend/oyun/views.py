from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import Sum

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView 
from .models import (
    Boss, BossIlerleme, BossDeneme, OyunProfil,
    BossOnKosul,
    KullaniciGorev, Basarim,
    Esya, Envanter,
    Bildirim, OdulIslemi
)
from .serializers import (
    BossListeSerializer, BossDetaySerializer,
    BossCevaplaSerializer, OyunProfilSerializer,
    BossDenemeSerializer, text_puanla,
    KullaniciGorevSerializer, BasarimSerializer,
    EsyaSerializer, EnvanterSerializer,
    BildirimSerializer, OdulIslemiSerializer
)
from .services import (
    profil_getir, odul_ver, gunluk_giris,
    gorev_event, gorev_odul_al, basarim_kontrol,
    market_satin_al, booster_kullan, gorevleri_hazirla
)

import re

# ⚠️ Buradaki import ismini SENDEKİ view adına göre düzelt:
# dokuman/urls.py içinde "sor/" hangi view'a gidiyorsa onu yaz.
UserModel = get_user_model()

class OyunProfilView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profil = profil_getir(request.user)
        profil.enerji_guncelle()
        profil.save()
        return Response(OyunProfilSerializer(profil).data)


class GunlukGirisView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profil, verildi = gunluk_giris(request.user)
        return Response({"verildi": verildi, "profil": OyunProfilSerializer(profil).data})


def dokuman_ile_ai_feedback(user, doc_id: int, soru_metni: str, beklenen: str, kullanici_cevap: str):
    from rest_framework.test import APIRequestFactory, force_authenticate
    """
    dokuman-asistani KanitliSor endpoint'ini içeriden çağırır.
    Dönen metinden PUAN/FEEDBACK parse etmeye çalışır.
    PUAN bulunamazsa, basit bir fallback puan üretir.
    """
    from dokuman.views import KanitliSor

    # Daha güçlü prompt: format ve kanıt zorunlu
    prompt = f"""
Sen bir öğretmensin. Aşağıdaki dokümana göre öğrencinin cevabını değerlendir.

Soru: {soru_metni}
Beklenen: {beklenen}

Öğrenci cevabı:
{kullanici_cevap}

KURALLAR:
- Dokümandan en az 1 kanıt/adres kullan (örn: [txt:para:1]).
- ÇIKTIYI MUTLAKA ŞU FORMATTA VER:

PUAN: <0-100>
FEEDBACK: <2-4 kısa cümle>
EKSİKLER:
- <madde>
- <madde>
KANIT:
- <adres>: <çok kısa alıntı>
""".strip()

    factory = APIRequestFactory()
    req = factory.post(
        "/api/dokuman-asistani/sor/",
        {"doc_id": doc_id, "soru": prompt, "mode": "grade"},
        format="json",
    )
    force_authenticate(req, user=user)

    resp = KanitliSor.as_view()(req)
    resp.render()
    data = resp.data or {}

    # Dokümanda yoksa AI'ı devre dışı say
    if bool(data.get("dokumanda_yok")):
        fb = "Dokümanla eşleşmedi (dokümanda yok). Bu boss için doğru doc_id bağla veya doküman bağımsız değerlendirme modunu aç."
        return None, fb, data.get("kanit_snippet", [])

    txt = (data.get("cevap") or "").strip()

    # 1) PUAN parse (PUAN: 85)
    puan_ai = None
    m = re.search(r"PUAN\s*:\s*(\d{1,3})", txt, flags=re.IGNORECASE)
    if m:
        puan_ai = max(0, min(100, int(m.group(1))))

    # 2) FEEDBACK parse
    fb_ai = txt
    mfb = re.search(r"FEEDBACK\s*:\s*(.*)", txt, flags=re.IGNORECASE | re.DOTALL)
    if mfb:
        fb_ai = mfb.group(1).strip()

        # Eğer FEEDBACK'ten sonra EKSİKLER/KANIT geldiyse, feedback'i sadece o kısmın üstüne kırp
        fb_ai = re.split(r"\n\s*(EKSİKLER|KANIT)\s*:\s*", fb_ai, flags=re.IGNORECASE)[0].strip()

    # 3) PUAN yoksa fallback puan üret
    # (KanitliSor bazen formatı bozarsa sistem çökmeyecek)
    if puan_ai is None:
        # Basit fallback: anahtar kelime yakalama
        beklenen_k = set(re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+", (beklenen or "").lower()))
        cevap_k = set(re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+", (kullanici_cevap or "").lower()))

        if not beklenen_k:
            puan_ai = 60  # beklenen boşsa orta
        else:
            ortak = len(beklenen_k & cevap_k)
            oran = ortak / max(1, len(beklenen_k))
            puan_ai = int(round(100 * oran))

        # Feedback'e not düş
        fb_ai = (fb_ai + "\n\n(Not: PUAN formatı gelmediği için yaklaşık puan hesaplandı.)").strip()

    return puan_ai, fb_ai, data.get("kanit_snippet", [])
class BossViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Boss.objects.filter(aktif=True).order_by("siralama", "id")

    def get_serializer_class(self):
        return BossDetaySerializer if self.action == "retrieve" else BossListeSerializer

    @action(detail=True, methods=["post"], url_path="cevapla")
    def cevapla(self, request, pk=None):
        boss: Boss = self.get_object()

        if not hasattr(boss, "soru"):
            return Response({"detay": "Bu boss için soru tanımlı değil."}, status=400)

        ser = BossCevaplaSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        soru = boss.soru
        max_puan = int(soru.max_puan or 100)

        cevap_metni = ser.validated_data.get("cevap_metni", "")
        secilen_index = ser.validated_data.get("secilen_index", None)

        with transaction.atomic():
            profil, _ = OyunProfil.objects.select_for_update().get_or_create(kullanici=request.user)
            profil.enerji_guncelle()

            # Kilit: seviye
            if profil.seviye < boss.seviye_gereksinim:
                return Response(
                    {"detay": "Boss kilitli (seviye).", "gereken": boss.seviye_gereksinim},
                    status=403
                )

            # Kilit: önkoşul boss
            prereq_ids = list(
                BossOnKosul.objects.filter(boss=boss).values_list("gerekir_boss_id", flat=True)
            )
            if prereq_ids:
                done = set(
                    BossIlerleme.objects.filter(
                        kullanici=request.user,
                        boss_id__in=prereq_ids,
                        tamamlandi=True
                    ).values_list("boss_id", flat=True)
                )
                if len(done) != len(prereq_ids):
                    return Response(
                        {"detay": "Boss kilitli (ön koşul).", "gerekir_bosslar": prereq_ids},
                        status=403
                    )

            # ilerleme her zaman burada oluşur (if DIŞI)
            ilerleme, _ = BossIlerleme.objects.select_for_update().get_or_create(
                kullanici=request.user, boss=boss
            )

            # Cooldown
            if ilerleme.son_deneme:
                delta = (timezone.now() - ilerleme.son_deneme).total_seconds()
                if delta < boss.cooldown_saniye:
                    return Response(
                        {
                            "detay": "Çok hızlı! Cooldown bekle.",
                            "kalan_saniye": int(boss.cooldown_saniye - delta)
                        },
                        status=429
                    )

            # Enerji
            if not profil.enerji_harcala(boss.enerji_maliyeti):
                return Response(
                    {
                        "detay": "Enerji yetersiz.",
                        "enerji": profil.enerji,
                        "enerji_maliyeti": boss.enerji_maliyeti
                    },
                    status=402
                )

            # Puanlama
            puan = 0
            dogru_mu = False
            feedback = ""

            if soru.tip == "MCQ":
                if secilen_index is None:
                    return Response({"detay": "MCQ için secilen_index lazım."}, status=400)
                if soru.dogru_secenek_index is None:
                    return Response({"detay": "MCQ dogru_secenek_index ayarlı değil."}, status=500)

                dogru_mu = int(secilen_index) == int(soru.dogru_secenek_index)
                puan = max_puan if dogru_mu else 0
                feedback = "Doğru! Devam." if dogru_mu else "Yanlış. Tekrar dene."

            else:
                # TEXT puanlama (fallback)
                puan = text_puanla(
                    cevap_metni,
                    soru.dogru_cevap_metni,
                    soru.kabul_edilen_cevaplar,
                    max_puan
                )
                puan = max(0, min(max_puan, int(puan)))
                dogru_mu = puan >= int(boss.tamamlama_esigi)

                # Basit feedback (AI yoksa)
                if puan >= 90:
                    feedback = "Mükemmel. Cevap çok net."
                elif puan >= int(boss.tamamlama_esigi):
                    feedback = "Doğruya yakın. Biraz daha detay verirsen tam olacak."
                else:
                    feedback = "Eksik/yanlış. İpucu: temel tanımı net yaz, sonra 1 örnek ver."

                # AI override (sadece TEXT)
                if getattr(soru, "ai_degerlendirme", False) and getattr(soru, "context_doc_id", None):
                    puan_ai, fb_ai, _snips = dokuman_ile_ai_feedback(
                        user=request.user,
                        doc_id=soru.context_doc_id,
                        soru_metni=soru.soru_metni,
                        beklenen=soru.dogru_cevap_metni,
                        kullanici_cevap=cevap_metni,
                    )
                    if puan_ai is not None:
                        puan = puan_ai
                        dogru_mu = puan >= int(boss.tamamlama_esigi)
                    if fb_ai:
                        feedback = fb_ai

            # Farm engeli: sadece best artışına göre ödül
            yeni_best = max(int(ilerleme.en_yuksek_puan or 0), int(puan))
            hedef_xp_toplam = round(int(boss.odul_xp) * (yeni_best / max_puan))
            hedef_puan_toplam = round(int(boss.odul_puan) * (yeni_best / max_puan))

            xp_delta_raw = max(0, int(hedef_xp_toplam) - int(ilerleme.xp_kazanilan_toplam or 0))
            puan_delta_raw = max(0, int(hedef_puan_toplam) - int(ilerleme.puan_kazanilan_toplam or 0))

            deneme = BossDeneme.objects.create(
                kullanici=request.user,
                boss=boss,
                soru=soru,
                cevap_metni=cevap_metni or "",
                secilen_index=secilen_index,
                puan=puan,
                dogru_mu=dogru_mu,
                enerji_harcandi=boss.enerji_maliyeti,
                feedback=feedback,
            )

            xp_eklendi, puan_eklendi, profil = odul_ver(
                request.user, "BOSS", f"Boss ödülü: {boss.ad}", xp_delta_raw, puan_delta_raw
            )

            deneme.xp_eklendi = xp_eklendi
            deneme.puan_eklendi = puan_eklendi
            deneme.save()

            ilerleme.en_yuksek_puan = yeni_best
            ilerleme.xp_kazanilan_toplam = min(int(boss.odul_xp), int(hedef_xp_toplam))
            ilerleme.puan_kazanilan_toplam = min(int(boss.odul_puan), int(hedef_puan_toplam))
            ilerleme.tamamlandi = ilerleme.en_yuksek_puan >= int(boss.tamamlama_esigi)
            ilerleme.deneme_sayisi += 1
            ilerleme.son_deneme = timezone.now()
            ilerleme.save()

        # ✅ transaction DIŞI
            kazanilan_kodlar = []
            gorev_hata = None

            try:
                gorev_event(
                    request.user, "DENEME",
                    amount=1,
                    boss_id=boss.id,
                    gained_xp=xp_eklendi,
                    gained_puan=puan_eklendi,
                    perfect=(puan == max_puan),
                    boss_completed=ilerleme.tamamlandi
                )
                kazanilan_kodlar = basarim_kontrol(request.user)
            except Exception as e:
                # Şimdilik boss cevabı düşmesin diye görev/başarım tarafını yumuşatıyoruz
                gorev_hata = str(e)
            kazanilan_kodlar = basarim_kontrol(request.user) or []
            if isinstance(kazanilan_kodlar, dict):
                kazanilan_kodlar = list(kazanilan_kodlar.keys())
            return Response({
                "boss_id": boss.id,
                "deneme_id": deneme.id,
                "puan": puan,
                "dogru_mu": dogru_mu,
                "feedback": feedback,
                "xp_eklendi": xp_eklendi,
                "puan_eklendi": puan_eklendi,
                "kazanilan_basarimlar": kazanilan_kodlar,
                "gorev_uyari": gorev_hata,   # istersen bunu sonra kaldırırız
                "profil": OyunProfilSerializer(profil).data,
                "ilerleme": {
                    "en_yuksek_puan": ilerleme.en_yuksek_puan,
                    "tamamlandi": ilerleme.tamamlandi,
                    "deneme_sayisi": ilerleme.deneme_sayisi,
                },
                "kazanilan_basarimlar": kazanilan_kodlar,
            })
  


from rest_framework.pagination import PageNumberPagination

class DenemePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class DenemeViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = BossDenemeSerializer
    pagination_class = DenemePagination

    def get_queryset(self):
        qs = (BossDeneme.objects
               .select_related("boss", "soru")
               .filter(kullanici=self.request.user)
               .order_by("-olusturuldu"))

        # ?boss_id=5
        boss_id = self.request.query_params.get("boss_id")
        if boss_id:
            qs = qs.filter(boss_id=boss_id)

        # ?dogru=1  veya ?dogru=0
        dogru = self.request.query_params.get("dogru")
        if dogru in ("0", "1"):
            qs = qs.filter(dogru_mu=(dogru == "1"))
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(boss__ad__icontains=search.strip())
        # ?from=2026-03-01&to=2026-03-03  (date)
        d_from = self.request.query_params.get("from")
        d_to = self.request.query_params.get("to")
        if d_from:
            qs = qs.filter(olusturuldu__date__gte=d_from)
        if d_to:
            qs = qs.filter(olusturuldu__date__lte=d_to)

        return qs

class GorevView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            gorevleri_hazirla(request.user)
            today = timezone.localdate()
            qs = KullaniciGorev.objects.select_related("gorev").filter(
                kullanici=request.user, baslangic__lte=today, bitis__gte=today
            ).order_by("gorev__tur", "id")
            return Response(KullaniciGorevSerializer(qs, many=True).data)
        except Exception as e:
            return Response({"detail": str(e)}, status=500)

class GorevOdulAlView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, gorev_id):
        kg = KullaniciGorev.objects.select_related("gorev").filter(kullanici=request.user, id=gorev_id).first()
        if not kg:
            return Response({"detay": "Görev bulunamadı."}, status=404)

        try:
            xp, puan, profil = gorev_odul_al(request.user, kg)
        except ValueError as e:
            return Response({"detay": str(e)}, status=400)

        return Response({"xp": xp, "puan": puan, "profil": OyunProfilSerializer(profil).data})


class BasarimView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Basarim.objects.filter(aktif=True).order_by("id")
        return Response(BasarimSerializer(qs, many=True, context={"request": request}).data)


class LiderlikView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        scope = request.query_params.get("scope", "all")  # all | week
        User = UserModel

        if scope == "week":
            today = timezone.localdate()
            start = today - timezone.timedelta(days=today.weekday())
            end = start + timezone.timedelta(days=7)

            qs = (OdulIslemi.objects
                  .filter(olusturuldu__date__gte=start, olusturuldu__date__lt=end)
                  .values("kullanici_id")
                  .annotate(xp=Sum("delta_xp"), puan=Sum("delta_puan"))
                  .order_by("-xp", "-puan")[:50])

            ids = [r["kullanici_id"] for r in qs]
            users = {u.id: u for u in User.objects.filter(id__in=ids)}
            profs = {p.kullanici_id: p for p in OyunProfil.objects.filter(kullanici_id__in=ids)}

            out = []
            for r in qs:
                u = users.get(r["kullanici_id"])
                p = profs.get(r["kullanici_id"])
                out.append({
                    "kullanici_id": r["kullanici_id"],
                    "kullanici_adi": getattr(u, "username", str(r["kullanici_id"])),
                    "seviye": getattr(p, "seviye", 1),
                    "toplam_xp": int(r["xp"] or 0),
                    "toplam_puan": int(r["puan"] or 0),
                })
            return Response(out)

        qs = OyunProfil.objects.select_related("kullanici").order_by("-toplam_xp", "-toplam_puan")[:50]
        return Response([{
            "kullanici_id": p.kullanici_id,
            "kullanici_adi": getattr(p.kullanici, "username", str(p.kullanici_id)),
            "seviye": p.seviye,
            "toplam_xp": p.toplam_xp,
            "toplam_puan": p.toplam_puan,
        } for p in qs])


class MarketView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Esya.objects.filter(aktif=True).order_by("tip", "id")
        return Response(EsyaSerializer(qs, many=True).data)

    def post(self, request):
        kod = request.data.get("esya_kod")
        adet = int(request.data.get("adet", 1))
        esya = Esya.objects.filter(kod=kod, aktif=True).first()
        if not esya:
            return Response({"detay": "Eşya bulunamadı."}, status=404)

        try:
            yeni_adet, profil = market_satin_al(request.user, esya, adet)
        except ValueError as e:
            return Response({"detay": str(e)}, status=400)

        return Response({"envanter_adet": yeni_adet, "profil": OyunProfilSerializer(profil).data})


class EnvanterView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Envanter.objects.select_related("esya").filter(kullanici=request.user).order_by("esya__tip", "esya__id")
        return Response(EnvanterSerializer(qs, many=True).data)


class BoosterKullanView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        kod = request.data.get("esya_kod")
        esya = Esya.objects.filter(kod=kod, aktif=True).first()
        if not esya:
            return Response({"detay": "Eşya bulunamadı."}, status=404)

        try:
            booster_kullan(request.user, esya)
        except ValueError as e:
            return Response({"detay": str(e)}, status=400)

        return Response({"ok": True})


class BildirimlerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Bildirim.objects.filter(kullanici=request.user).order_by("-olusturuldu")[:100]
        return Response(BildirimSerializer(qs, many=True).data)

    def post(self, request):
        bid = request.data.get("id")
        b = Bildirim.objects.filter(kullanici=request.user, id=bid).first()
        if not b:
            return Response({"detay": "Bildirim bulunamadı."}, status=404)
        b.okundu = True
        b.save()
        return Response({"ok": True})


class OdulLogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = OdulIslemi.objects.filter(kullanici=request.user).order_by("-olusturuldu")[:200]
        return Response(OdulIslemiSerializer(qs, many=True).data)