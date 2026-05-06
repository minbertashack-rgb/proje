from django.db import transaction
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import Dokuman
from dokuman.models import Dokuman, Parca
from dokuman.serializers import ZorYerSerializer
from dokuman.services.zor_yer import (
    parcala_metni,
    dokuman_global_freq,
    zorluk_skoru_hesapla,
    sayfa_no_bul,
)
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from dokuman.services.difficulty import calculate_part_difficulty, difficulty_label_from_score
from dokuman.models import Dokuman, Parca
from dokuman.parcalama import chunk_text

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


def _request_language(request) -> str:
    return request.headers.get("Accept-Language") or request.META.get("HTTP_ACCEPT_LANGUAGE") or "tr"


def _enabled() -> bool:
    return bool(getattr(settings, "DOCVERSE_HARDEST_PARTS_ENABLED", True))


def _part_difficulty_payload(parca: Parca, *, preview_limit: int = 240, language: str = "tr") -> dict:
    profile = calculate_part_difficulty(parca.metin or "", parca.meta, language=language)
    score = float(profile["difficulty_score"])
    label = str(profile["difficulty_label"])
    reasons = list(profile["difficulty_reasons"])
    stored_score = parca.zorluk_skoru
    if stored_score is not None and float(stored_score or 0.0) > 0.0:
        score = float(stored_score or 0.0)
        label = difficulty_label_from_score(score)
    return {
        "part_id": parca.id,
        "id": parca.id,
        "title": (parca.meta or {}).get("baslik")
        or (parca.meta or {}).get("chunk_title")
        or parca.adres
        or f"Parca {parca.sira}",
        "preview": _safe_text_preview(parca.metin, limit=preview_limit),
        "adres": parca.adres,
        "path": parca.adres,
        "difficulty_score": round(max(0.0, min(float(score), 1.0)), 3),
        "difficulty_label": label,
        "difficulty_reasons": reasons[:4],
    }


def _summary_for_parts(parcalar: list[Parca]) -> dict:
    summary = {"easy": 0, "medium": 0, "hard": 0}
    for parca in parcalar:
        profile = calculate_part_difficulty(parca.metin or "", parca.meta)
        label = str(profile["difficulty_label"])
        if parca.zorluk_skoru is not None and float(parca.zorluk_skoru or 0.0) > 0.0:
            label = difficulty_label_from_score(float(parca.zorluk_skoru or 0.0))
        if label == "zor":
            summary["hard"] += 1
        elif label == "orta":
            summary["medium"] += 1
        else:
            summary["easy"] += 1
    return summary


class _DokumanSahiplikMixin:
    def dokuman_getir(self, request, doc_id: int) -> Dokuman:
        # ✅ owner kontrolü doğru alanla
        dok = get_object_or_404(Dokuman, id=doc_id, owner_id=request.user.id)
        return dok


class ZorYerHesaplaAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, doc_id: int, *args, **kwargs):
        doc = get_object_or_404(Dokuman, id=doc_id, owner_id=request.user.id)
        if not _enabled():
            return Response(
                {
                    "document_id": doc.id,
                    "enabled": False,
                    "hardest_parts": [],
                    "summary": {"easy": 0, "medium": 0, "hard": 0},
                },
                status=status.HTTP_200_OK,
            )

        yeniden = bool(request.data.get("yeniden_hesapla", True))
        otomatik_parcala = bool(request.data.get("otomatik_parcala", True))
        chunk_char = int(request.data.get("chunk_char", 1200))
        overlap = int(request.data.get("overlap", 150))

        parcalar_qs = doc.parcalar.all().order_by("id")
        parca_count = parcalar_qs.count()

        # ✅ Kaynak metni bul:
        # - parça yoksa: dosyadan oku (TXT için)
        # - 1 parça varsa: o parçanın metnini baz al (çok uzunsa re-chunk yapabilelim)
        source_text = ""
        if parca_count == 0:
            # Dosyadan oku (TXT gibi)
            try:
                if doc.dosya and hasattr(doc.dosya, "path"):
                    with open(doc.dosya.path, "r", encoding="utf-8") as f:
                        source_text = f.read()
            except Exception:
                source_text = ""
        elif parca_count == 1:
            source_text = (parcalar_qs.first().metin or "")

        # ✅ Otomatik chunk tetik kuralı:
        # - hiç parça yoksa
        # - veya tek parça var ve metin çok uzunsa (chunk_char*1.3 üstü)
        should_chunk = otomatik_parcala and (
            (parca_count == 0 and len(source_text) > 0) or
            (parca_count == 1 and len(source_text) > int(chunk_char * 1.3))
        )

        created = 0
        if should_chunk:
            spans = chunk_text(source_text, chunk_char=chunk_char, overlap=overlap)
            if not spans:
                return Response(
                    {"durum": "bos", "mesaj": "Metin boş, parça üretilemedi."},
                    status=status.HTTP_200_OK
                )

            with transaction.atomic():
                # eski tek paragrafı silip chunk’lara geç (MVP)
                doc.parcalar.all().delete()

                bulk = []
                for i, (b, e) in enumerate(spans, start=1):
                    chunk = source_text[b:e].strip()
                    if not chunk:
                        continue
                    bulk.append(Parca(
                        dokuman=doc,
                        sira=i,
                        tur="chunk",
                        adres=f"txt:chunk:{i}",
                        meta={"chunk": i, "b": b, "e": e},
                        metin=chunk,
                    ))
                Parca.objects.bulk_create(bulk)
                created = len(bulk)

        # ✅ Skor hesapla
        parcalar = list(doc.parcalar.all())
        if not parcalar:
            return Response(
                {"durum": "bos", "mesaj": "Parça yok. Ingestion ya da otomatik_parcala ile üret."},
                status=status.HTTP_200_OK,
            )

        updated = 0
        with transaction.atomic():
            for p in parcalar:
                if (not yeniden) and (p.zorluk_skoru is not None):
                    continue
                profile = calculate_part_difficulty(p.metin or "", p.meta, language=_request_language(request))
                skor = float(profile["difficulty_score"])
                label = str(profile["difficulty_label"])
                if float(p.zorluk_skoru or 0.0) != float(skor) or (p.zorluk or "") != label:
                    p.zorluk_skoru = skor
                    p.zorluk = label
                    p.save(update_fields=["zorluk_skoru", "zorluk"])
                    updated += 1

        top = list(doc.parcalar.order_by("-zorluk_skoru")[:8])
        return Response(
            {
                "durum": "ok",
                "dokuman_id": doc.id,
                "created": created,
                "updated": updated,
                "top": [
                    {
                        "parca_id": p.id,
                        "adres": p.adres,
                        "skor": float(p.zorluk_skoru or 0.0),
                        "difficulty_label": difficulty_label_from_score(float(p.zorluk_skoru or 0.0)),
                    }
                    for p in top
                ],
            },
            status=status.HTTP_200_OK,
        )



class ZorYerListeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id: int, *args, **kwargs):
        limit = int(request.query_params.get("limit", 8))
        limit = max(1, min(limit, 50))

        doc = Dokuman.objects.filter(id=doc_id, owner_id=request.user.id).first()
        if not doc:
            return Response({"detail": "Doküman yok"}, status=404)
        if not _enabled():
            return Response(
                {
                    "document_id": doc.id,
                    "dokuman_id": doc.id,
                    "enabled": False,
                    "hardest_parts": [],
                    "zor_yerler": [],
                    "summary": {"easy": 0, "medium": 0, "hard": 0},
                }
            )

        parcalar = list(doc.parcalar.all())
        language = _request_language(request)
        ranked = sorted(
            parcalar,
            key=lambda p: _part_difficulty_payload(p, language=language)["difficulty_score"],
            reverse=True,
        )[:limit]
        hardest_parts = [_part_difficulty_payload(p, language=language) for p in ranked]
        return Response(
            {
                "document_id": doc.id,
                "dokuman_id": doc.id,
                "enabled": True,
                "limit": limit,
                "hardest_parts": hardest_parts,
                "zor_yerler": [
                    {
                        "id": item["id"],
                        "sira": next((p.sira for p in ranked if p.id == item["id"]), None),
                        "tur": next((p.tur for p in ranked if p.id == item["id"]), ""),
                        "adres": item["adres"],
                        "meta": _safe_meta(next((p.meta for p in ranked if p.id == item["id"]), {})),
                        "zorluk_skoru": item["difficulty_score"],
                        "zorluk": item["difficulty_label"],
                        "metin": item["preview"],
                        "difficulty_score": item["difficulty_score"],
                        "difficulty_label": item["difficulty_label"],
                        "difficulty_reasons": item["difficulty_reasons"],
                    }
                    for item in hardest_parts
                ],
                "summary": _summary_for_parts(parcalar),
            }
        )
