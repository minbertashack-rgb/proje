from django.urls import path
from . import panels_views

urlpatterns = [
    path('dokumanlar/<int:pk>/boss-rush-panel/', panels_views.BossRushPanelView.as_view(), name='boss-rush-panel'),
    path('dokumanlar/<int:pk>/boss-rush-panel/', panels_views.BossRushPanelView.as_view(), name='dokuman-boss-rush-panel'),
    path('analytics/weekly-progress/', panels_views.WeeklyGoalProgressView.as_view(), name='weekly-progress'),
    path('analytics/weekly-progress/', panels_views.WeeklyGoalProgressView.as_view(), name='analytics-weekly-progress'),
    path('analytics/achievement-progress/', panels_views.AchievementProgressView.as_view(), name='achievement-progress'),
    path('analytics/achievement-progress/', panels_views.AchievementProgressView.as_view(), name='analytics-achievement-progress'),
    path('dokumanlar/<int:pk>/export-readiness/', panels_views.ExportReadinessView.as_view(), name='export-readiness'),
    path('dokumanlar/<int:pk>/export-readiness/', panels_views.ExportReadinessView.as_view(), name='dokuman-export-readiness'),
    path('profil/personalization-confidence/', panels_views.PersonalizationConfidenceView.as_view(), name='personalization-confidence'),
    path('profil/personalization-confidence/', panels_views.PersonalizationConfidenceView.as_view(), name='profil-personalization-confidence'),
    path('analytics/panels-kpi/', panels_views.PanelsKPIView.as_view(), name='panels-kpi'),
]
