from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import Dokuman, Parca
from .services.ingestion import dokumani_parcala_ve_kaydet, supported_upload_extensions

DESTEKLENEN_UZANTILAR = set(supported_upload_extensions())

_PARCA_META_ALLOWLIST = {
    "format",
    "chunk_kind",
    "office_document_type",
    "office_unit_kind",
    "code_language",
    "code_unit_kind",
    "code_unit_name",
    "parent_unit",
    "line_start",
    "line_end",
    "quality_score",
    "difficulty_score",
    "weak_content",
}


def _safe_meta(meta):
    raw = meta if isinstance(meta, dict) else {}
    return {key: raw.get(key) for key in _PARCA_META_ALLOWLIST if raw.get(key) is not None}


def _safe_text_preview(value: str, limit: int = 240) -> str:
    clean = " ".join(str(value or "").split()).strip()
    if len(clean) <= limit:
        return clean
    short = clean[:limit].rsplit(" ", 1)[0].strip()
    return (short or clean[:limit].strip()) + "..."

class Ping(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return Response({"durum": "ok", "mesaj": "ingestion ayakta knk"})

class DokumanListeVeYukle(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Dokuman.objects.filter(owner=request.user).order_by("-created_at")
        return Response([{
            "id": d.id,
            "baslik": d.baslik,
            "mime": d.mime,
            "durum": d.durum,
            "hata": d.hata,
            "created_at": d.created_at,
            "parca_sayisi": d.parcalar.count(),
        } for d in qs])

    def post(self, request):
        f = request.FILES.get("dosya")
        if not f:
            return Response({"detay": "dosya alanı zorunlu"}, status=400)

        isim = (f.name or "").lower()
        ext = "." + isim.split(".")[-1] if "." in isim else ""
        if ext not in DESTEKLENEN_UZANTILAR:
            return Response({"detay": f"Desteklenen uzantılar: {sorted(DESTEKLENEN_UZANTILAR)}"}, status=400)

        baslik = request.data.get("baslik", "") or ""
        doc = Dokuman.objects.create(
            owner=request.user,
            baslik=baslik,
            dosya=f,
            mime=getattr(f, "content_type", "") or "",
            durum="yuklendi",
            hata="",
        )

        # Şimdilik sync parçalama
        try:
            dokumani_parcala_ve_kaydet(doc)
        except Exception:
            pass

        return Response({
            "id": doc.id,
            "baslik": doc.baslik,
            "mime": doc.mime,
            "durum": doc.durum,
            "hata": doc.hata,
            "parca_sayisi": doc.parcalar.count(),
        }, status=201)

class DokumanParcalari(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int):
        doc = get_object_or_404(Dokuman, pk=doc_id, owner=request.user)
        limit = int(request.query_params.get("limit", 200))
        qs = Parca.objects.filter(dokuman=doc).order_by("sira")[:limit]
        return Response([{
            "sira": p.sira,
            "tur": p.tur,
            "adres": p.adres,
            "metin": _safe_text_preview(p.metin),
            "meta": _safe_meta(p.meta),
            "zorluk": p.zorluk,
            "zorluk_skoru": p.zorluk_skoru,
        } for p in qs])

class DokumaniYenidenParcala(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, doc_id: int):
        doc = get_object_or_404(Dokuman, pk=doc_id, owner=request.user)
        dokumani_parcala_ve_kaydet(doc)
        return Response({
            "id": doc.id,
            "durum": doc.durum,
            "hata": doc.hata,
            "parca_sayisi": doc.parcalar.count(),
        })
