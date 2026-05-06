from django.urls import path
from .views import CheatSheetExportCreateView, CheatSheetExportDownloadView

urlpatterns = [
    path("cheatsheet/", CheatSheetExportCreateView.as_view()),
    path("cheatsheet/<uuid:export_id>/indir/", CheatSheetExportDownloadView.as_view()),
]