
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from dokuman.models import Dokuman
from dokuman.services.product_panels import (
    build_boss_rush_panel_payload,
    build_export_readiness_payload,
    build_personalization_confidence_payload,
    build_weekly_progress_payload,
)


class BossRushPanelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not getattr(settings, "DOCVERSE_BOSS_ENABLED", False):
            return Response({"detail": "Boss rush paneli kapali."}, status=status.HTTP_404_NOT_FOUND)
        
        dokuman = get_object_or_404(Dokuman, pk=pk, owner=request.user)
        payload = build_boss_rush_panel_payload(dokuman)
        return Response(payload)


class WeeklyProgressPanelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not getattr(settings, "DOCVERSE_METRIC_STORE_ENABLED", False):
            return Response({"detail": "Metric store paneli kapali."}, status=status.HTTP_404_NOT_FOUND)
        
        payload = build_weekly_progress_payload(request.user)
        return Response(payload)


class ExportReadinessPanelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not getattr(settings, "DOCVERSE_EXPORT_PLAN_ENABLED", False):
            return Response({"detail": "Export readiness paneli kapali."}, status=status.HTTP_404_NOT_FOUND)
        
        dokuman = get_object_or_404(Dokuman, pk=pk, owner=request.user)
        payload = build_export_readiness_payload(dokuman)
        return Response(payload)


class PersonalizationConfidencePanelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not getattr(settings, "DOCVERSE_PERSONALIZATION_ENABLED", False):
            return Response({"detail": "Personalization paneli kapali."}, status=status.HTTP_404_NOT_FOUND)
        
        payload = build_personalization_confidence_payload(request.user)
        return Response(payload)
