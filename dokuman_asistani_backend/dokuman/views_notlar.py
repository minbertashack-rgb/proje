# dokuman/views_notlar.py
from __future__ import annotations
import re

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Not
from dokuman.models import Dokuman, Parca, DokumanNotu
from dokuman.serializers import DokumanNotuSerializer

TAG_RE = re.compile(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü_]+", re.UNICODE)

def auto_tags(text: str, limit: int = 8):
    toks = [t.lower() for t in TAG_RE.findall(text or "")]
    toks = [t for t in toks if len(t) >= 3]
    out = []
    for t in toks:
        if t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out

class NotListCreate(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        doc = Dokuman.objects.filter(id=doc_id, owner_id=request.user.id).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        q = (request.query_params.get("q") or "").strip().lower()
        qs = DokumanNotu.objects.filter(owner=request.user, dokuman=doc)

        if q:
            qs = qs.filter(metin__icontains=q) | qs.filter(baslik__icontains=q) | qs.filter(adres__icontains=q)

        data = DokumanNotuSerializer(qs[:200], many=True).data
        return Response({"dokuman_id": doc.id, "count": len(data), "notlar": data})

    def post(self, request, doc_id: int):
        doc = Dokuman.objects.filter(id=doc_id, owner_id=request.user.id).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        parca_id = request.data.get("parca_id")
        adres = (request.data.get("adres") or "").strip()
        baslik = (request.data.get("baslik") or "").strip()
        metin = (request.data.get("icerik") or request.data.get("metin") or "").strip()
        pinned = bool(request.data.get("pinned", False))
        etiketler = request.data.get("etiketler")

        if not metin:
            return Response({"detail": "icerik zorunlu"}, status=400)

        parca = None
        if parca_id:
            parca = Parca.objects.filter(id=parca_id, dokuman_id=doc.id).first()
            if not parca:
                return Response({"detail": "Parça yok"}, status=404)
            if not adres:
                adres = parca.adres

        if not etiketler:
            etiketler = auto_tags(baslik + " " + metin)

        n = Not.objects.create(
            owner=request.user,
            dokuman=doc,
            parca=parca,
            adres=adres,
            baslik=baslik,
            metin=metin,       # ✅ burada icerik olmayacak
            etiketler=etiketler,
            pinned=pinned,
        )
        return Response(DokumanNotuSerializer(n).data, status=201)

class NotDetail(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, not_id: int):
        n = Not.objects.filter(id=not_id, owner=request.user).first()
        if not n:
            return Response({"detail": "Not yok"}, status=404)

        # başlık/adres
        if "baslik" in request.data:
            n.baslik = (request.data.get("baslik") or "").strip()
        if "adres" in request.data:
            n.adres = (request.data.get("adres") or "").strip()

        # ✅ D kısmı: API 'icerik' gönderirse DB'deki 'metin'e yaz
        if "icerik" in request.data:
            n.metin = (request.data.get("icerik") or "").strip()

        # (istersen 'metin' ile de kabul et)
        if "metin" in request.data:
            n.metin = (request.data.get("metin") or "").strip()

        # etiketler/pinned
        if "etiketler" in request.data:
            n.etiketler = request.data.get("etiketler") or []
        if "pinned" in request.data:
            n.pinned = bool(request.data.get("pinned"))
        if "icerik" in request.data:
            n.metin = (request.data.get("icerik") or "").strip()
            # opsiyonel: etiketleri de yenile
            if not request.data.get("etiketler"):
                n.etiketler = auto_tags((n.baslik or "") + " " + (n.metin or ""))
                n.save()
        return Response(DokumanNotuSerializer(n).data)

    def delete(self, request, not_id: int):
        n = DokumanNotu.objects.filter(id=not_id, owner=request.user).first()
        if not n:
            return Response({"detail": "Not yok"}, status=404)
        n.delete()
        return Response({"durum": "ok"})

class PortalNotlar(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        doc = Dokuman.objects.filter(id=doc_id, owner_id=request.user.id).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)

        tag = (request.query_params.get("tag") or "").strip().lower()
        if not tag:
            return Response({"detail": "tag zorunlu"}, status=400)

        notes = list(DokumanNotu.objects.filter(owner=request.user, dokuman=doc))
        notes = [n for n in notes if tag in [t.lower() for t in (n.etiketler or [])]]

        targets = doc.parcalar.filter(metin__icontains=tag).order_by("-zorluk_skoru")[:12]
        target_items = [{"parca_id": p.id, "adres": p.adres, "skor": float(p.zorluk_skoru or 0.0)} for p in targets]

        return Response({
            "dokuman_id": doc.id,
            "tag": tag,
            "notlar": DokumanNotuSerializer(notes, many=True).data,
            "hedef_parcalar": target_items
        })