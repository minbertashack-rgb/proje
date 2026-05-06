# dokuman_asistani/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import Dokuman, Vurgu
from .serializers import VurguSerializer, VurguOlusturSerializer
import bisect
import re


def char_to_line_col(text: str, idx: int, newline_indices: list = None):
    """
    idx char indexini (1-based) satır/kolona çevir.
    Satır: 1..N, Kolon: 1..M
    """
    if idx < 0:
        idx = 0
    if idx > len(text):
        idx = len(text)

    if newline_indices is not None:
        # O(log N) Karmaşıklık ile Binary Search
        line_idx = bisect.bisect_right(newline_indices, idx - 1)
        line = line_idx + 1
        if line_idx == 0:
            col = idx + 1
        else:
            last_nl = newline_indices[line_idx - 1]
            col = idx - last_nl
        return line, col

    # O(N) Fallback (Eğer indeks listesi yoksa)
    before = text[:idx]
    line = before.count("\n") + 1
    last_nl = before.rfind("\n")
    col = idx + 1 if last_nl == -1 else (idx - last_nl)
    return line, col


def char_to_page(page_breaks, idx: int):
    """
    page_breaks: [0, 1820, 3655, ...] şeklinde sayfa başlangıç indexleri.
    idx hangi sayfada? (1-based)
    """
    if not page_breaks:
        return None
    # ensure sorted
    pb = sorted([int(x) for x in page_breaks if x is not None])
    page = 1
    for i, start in enumerate(pb):
        if start <= idx:
            page = i + 1
        else:
            break
    return page


def context_window(text: str, b: int, e: int, win: int = 80):
    left = max(0, b - win)
    right = min(len(text), e + win)
    return {
        "once": text[left:b],
        "parca": text[b:e],
        "sonra": text[e:right],
        "pencere": win,
    }


class VurguListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_dokuman(self, request, dokuman_id: int) -> Dokuman:
        return Dokuman.objects.get(id=dokuman_id, kullanici=request.user)

    def get(self, request, dokuman_id: int):
        dok = self.get_dokuman(request, dokuman_id)
        qs = dok.vurgular.order_by("-olusturuldu")
        return Response(VurguSerializer(qs, many=True).data)

    def post(self, request, dokuman_id: int):
        dok = self.get_dokuman(request, dokuman_id)
        s = VurguOlusturSerializer(data=request.data, context={"request": request, "dokuman": dok})
        s.is_valid(raise_exception=True)
        vurgu = s.save()
        return Response(VurguSerializer(vurgu).data, status=status.HTTP_201_CREATED)


class VurguDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, dokuman_id: int, vurgu_id: int):
        dok = Dokuman.objects.get(id=dokuman_id, kullanici=request.user)
        vurgu = Vurgu.objects.get(id=vurgu_id, dokuman=dok)
        vurgu.delete()
        return Response({"durum": "silindi", "vurgu_id": vurgu_id})


class AdresleAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, dokuman_id: int):
        dok = Dokuman.objects.get(id=dokuman_id, kullanici=request.user)

        vurgu_id = request.data.get("vurgu_id")
        metin_parcasi = request.data.get("metin_parcasi")
        baslangic_char = request.data.get("baslangic_char")
        bitis_char = request.data.get("bitis_char")
        secim_index = int(request.data.get("secim_index", 0))

        if vurgu_id:
            vurgu = Vurgu.objects.get(id=vurgu_id, dokuman=dok)
            b, e = vurgu.baslangic_char, vurgu.bitis_char
        elif baslangic_char is not None and bitis_char is not None:
            b, e = int(baslangic_char), int(bitis_char)
        elif metin_parcasi:
            snippet = str(metin_parcasi)
            hits = []
            start = 0
            while True:
                idx = dok.metin.find(snippet, start)
                if idx == -1:
                    break
                hits.append(idx)
                start = idx + 1
            if not hits:
                return Response({"hata": "metin_parcasi dokümanda bulunamadı."}, status=400)
            if secim_index >= len(hits):
                return Response({"hata": f"secim_index geçersiz. {len(hits)} eşleşme var."}, status=400)
            b = hits[secim_index]
            e = b + len(snippet)
        else:
            return Response({"hata": "vurgu_id veya (baslangic_char+bitis_char) veya metin_parcasi vermelisin."}, status=400)

        if b < 0 or e > len(dok.metin) or e <= b:
            return Response({"hata": "Span geçersiz."}, status=400)

        # Eğer newline indeksleri veritabanında henüz önbelleğe alınmamışsa hesapla
        if dok.newline_indices is None:
            dok.newline_indices = [m.start() for m in re.finditer(r'\n', dok.metin)]
            dok.save(update_fields=["newline_indices"])

        b_line, b_col = char_to_line_col(dok.metin, b, dok.newline_indices)
        e_line, e_col = char_to_line_col(dok.metin, e, dok.newline_indices)

        page = char_to_page(dok.sayfa_kirilimlari, b) if dok.sayfa_kirilimlari else None
        ctx = context_window(dok.metin, b, e, win=int(request.data.get("pencere", 80)))

        return Response({
            "dokuman_id": dok.id,
            "baslangic_char": b,
            "bitis_char": e,
            "baslangic_satir": b_line,
            "baslangic_kolon": b_col,
            "bitis_satir": e_line,
            "bitis_kolon": e_col,
            "sayfa": page,  # yoksa None
            "baglam": ctx,
        })