from django.core.files.base import ContentFile
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status as http_status

from dokuman.models import Dokuman
from .models import CheatSheetExport
from .serializers import CheatSheetExportCreateSerializer
from .services import render_cheatsheet, ExportError, mark_processing, mark_failed, mark_done


class CheatSheetExportCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = CheatSheetExportCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        dokuman_id = ser.validated_data["dokuman_id"]
        fmt = ser.validated_data["format"]

        # SAHİPLİK KONTROLÜ (başkasının dokümanını export etmesin)
        dok = get_object_or_404(Dokuman, id=dokuman_id, owner=request.user)

        export_obj = CheatSheetExport.objects.create(
            dokuman=dok,
            olusturan=request.user,
            format=fmt,
            status="pending",
        )

        mark_processing(export_obj)

        try:
            rr = render_cheatsheet(dok, fmt)
            export_obj.dosya.save(rr.filename, ContentFile(rr.content), save=True)
            mark_done(export_obj)
        except ExportError as e:
            mark_failed(export_obj, "export_failed")
            return Response(
                {"durum": "hata", "mesaj": "Export üretilemedi.", "export_id": str(export_obj.id)},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            mark_failed(export_obj, "unexpected_export_error")
            return Response(
                {"durum": "hata", "mesaj": "Beklenmeyen export hatasi.", "export_id": str(export_obj.id)},
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "durum": "ok",
                "export_id": str(export_obj.id),
                "status": export_obj.status,
                "download_url": f"/api/export/cheatsheet/{export_obj.id}/indir/",
            },
            status=http_status.HTTP_201_CREATED,
        )


class CheatSheetExportDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, export_id):
        export_obj = get_object_or_404(CheatSheetExport, id=export_id, olusturan=request.user)

        if export_obj.status != "done" or not export_obj.dosya:
            return Response(
                {"durum": "hata", "mesaj": "Export hazır değil", "status": export_obj.status},
                status=http_status.HTTP_409_CONFLICT,
            )

        f = export_obj.dosya.open("rb")
        return FileResponse(f, as_attachment=True, filename=export_obj.dosya.name.split("/")[-1])
