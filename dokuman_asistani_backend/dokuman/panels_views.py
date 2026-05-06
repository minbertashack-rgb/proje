from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from dokuman.services.feature_flags import modul_acik_mi
from dokuman.services.product_analytics import build_product_panels_kpi

from .panels_serializers import PanelsKPISerializer
from .views import (
    AchievementProgressAPIView as AchievementProgressView,
    BossRushPanelAPIView as BossRushPanelView,
    ExportReadinessPanelAPIView as ExportReadinessView,
    PersonalizationConfidencePanelAPIView as PersonalizationConfidenceView,
    WeeklyProgressPanelAPIView as WeeklyGoalProgressView,
)


class PanelsKPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not modul_acik_mi("DOCVERSE_METRIC_STORE_ENABLED", True):
            return Response({"detail": "Metric store flag kapali."}, status=404)

        payload = build_product_panels_kpi(request.user)
        return Response(PanelsKPISerializer(payload).data)


__all__ = [
    "BossRushPanelView",
    "WeeklyGoalProgressView",
    "AchievementProgressView",
    "ExportReadinessView",
    "PersonalizationConfidenceView",
    "PanelsKPIView",
]
