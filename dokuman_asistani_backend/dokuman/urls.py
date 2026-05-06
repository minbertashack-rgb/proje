# dokuman/urls.py
from django.urls import path, include
from . import views

from .views_export import CheatSheetExport, ReadmeExportView, RealExportView

# Modül 6 (Highlight / Adresleme)
from .views import VurguListCreateAPIView, VurguDeleteAPIView, AdresleAPIView

# Zor yer
from .views_zor_yer import ZorYerHesaplaAPIView, ZorYerListeAPIView

# Anlamadım / tercih
from .views import DokumanAnlamadimOneri, TercihView

# AI2
from .views_ai2 import KanitliCevapAI2APIView, AnlamadimAI2APIView, MiniQuizResultAPIView

# Kanıtlı QA
from .views_kanitli_qa import KanitliSorAPIView

# Notlar
from .views import (
    ConfusionMapAPIView,
    ConfusionHotspotAnalyticsAPIView,
    DashboardSummaryAPIView,
    DokumanDirectorsCutAPIView,
    DokumanExcelModesAPIView,
    DokumanExportPlanAPIView,
    DokumanStyleConsoleAPIView,
    FeedbackAnalyticsAPIView,
    FeedbackListCreateAPIView,
    LearningKPIAPIView,
    LearningPanelAPIView,
    MasteryFeedbackTrustAnalyticsAPIView,
    NotListCreateAPIView,
    NotDetailAPIView,
    PortalNotStudyPanelAPIView,
    ProductKPIPanelAPIView,
    PortalNotDetailAPIView,
    PortalNotListCreateAPIView,
    QuizReadinessAPIView,
    QuizBossProductAnalyticsAPIView,
    XPVisibilityPanelAPIView,
)
from .views import DokumanYukle, PdfYukleAPIView, WordYukleAPIView, DokumanListe, DokumanParcalari

urlpatterns = [
    path("ping/", views.ping),

    # Tercih
    path("tercih/", TercihView.as_view()),
    path("tercihlerim/", views.TercihlerimView.as_view()),

    # Doküman işlemleri
    path("dokumanlar/yukle/", DokumanYukle.as_view(), name="dokuman-yukle"),
    path("dokumanlar/yukle/pdf/", PdfYukleAPIView.as_view(), name="pdf-yukle"),
    path("dokumanlar/yukle/word/", WordYukleAPIView.as_view(), name="word-yukle"),
    path("dokumanlar/", views.DokumanListe.as_view()),
    path("dokumanlar/<int:doc_id>/parcalar/", views.DokumanParcalari.as_view()),
    path("dokumanlar/<int:doc_id>/kavramlar/", views.DokumanKavramlarAPIView.as_view()),
    path("dokumanlar/<int:doc_id>/kavramlar/ara/", views.DokumanKavramAraAPIView.as_view()),
    path("parcalar/<int:parca_id>/kavramlar/", views.ParcaKavramlarAPIView.as_view()),

    # Zor yerler
    path("dokumanlar/<int:doc_id>/zor-yerler/hesapla/", ZorYerHesaplaAPIView.as_view()),
    path("dokumanlar/<int:doc_id>/zor-yerler/", ZorYerListeAPIView.as_view()),

    # Eski "Bunu anlamadım"
    path("parcalar/<int:parca_id>/anlamadim/", views.Anlamadim.as_view()),

    # Anlamadım kayıt listesi + çözme
    path("anlamadim/", views.AnlamadimListCreateAPIView.as_view()),
    path("anlamadim/<int:kayit_id>/coz/", views.AnlamadimCozAPIView.as_view()),

    # Anlamadım v2 / AI2
    path("parcalar/<int:parca_id>/anlamadim-v2/", views.ParcaAnlamadimV2.as_view()),
    path("parcalar/<int:parca_id>/remix/", views.ParcaRemixAPIView.as_view()),
    path("parcalar/<int:parca_id>/directors-cut/", views.ParcaDirectorsCutAPIView.as_view()),
    path("dokumanlar/<int:doc_id>/anlamadim/", DokumanAnlamadimOneri.as_view()),
    path("ai2/parcalar/<int:parca_id>/anlamadim/", AnlamadimAI2APIView.as_view()),
    path("ai2/parcalar/<int:parca_id>/mini-quiz-sonuc/", MiniQuizResultAPIView.as_view()),
    path("quiz/readiness/", QuizReadinessAPIView.as_view()),

    # Kanıtlı soru
    path("sor/", views.KanitliSor.as_view()),
    path("dokumanlar/<int:doc_id>/sor/", KanitliSorAPIView.as_view()),
    path("ai2/kanitli-cevap/", KanitliCevapAI2APIView.as_view()),

    # Profil / öneri / boss / LLM
    path("profil/", views.ProfilView.as_view()),
    path("dokumanlar/<int:doc_id>/oneriler/", views.Oneriler.as_view()),
    path("parcalar/<int:parca_id>/boss/", views.BossFight.as_view()),
    path("llm-durum/", views.LLMDurum.as_view()),

    # Notlar
    path("notlar/", NotListCreateAPIView.as_view()),
    path("notlar/<int:not_id>/", NotDetailAPIView.as_view()),
    path("portal-notlar/", PortalNotListCreateAPIView.as_view()),
    path("portal-notlar/<int:portal_not_id>/", PortalNotDetailAPIView.as_view()),
    path("portal-notlar/<int:portal_not_id>/calisma-paneli/", PortalNotStudyPanelAPIView.as_view()),
    path("feedback/", FeedbackListCreateAPIView.as_view()),
    path("feedback/analytics/", FeedbackAnalyticsAPIView.as_view()),
    path("dashboard/summary/", DashboardSummaryAPIView.as_view()),
    path("dashboard/summary/v2/", DashboardSummaryAPIView.as_view()),
    path("analytics/confusion-hotspots/", ConfusionHotspotAnalyticsAPIView.as_view()),
    path("analytics/confusion-map/", ConfusionMapAPIView.as_view()),
    path("analytics/quiz-boss/", QuizBossProductAnalyticsAPIView.as_view()),
    path("analytics/boss-readiness/", views.BossReadinessAPIView.as_view()),
    path("analytics/export-readiness/", views.ExportReadinessAPIView.as_view()),
    path("analytics/mastery-feedback-trust/", MasteryFeedbackTrustAnalyticsAPIView.as_view()),
    path("analytics/kpi/", ProductKPIPanelAPIView.as_view(), name="analytics-kpi"),
    path("analytics/learning-panel/", LearningPanelAPIView.as_view()),
    path("analytics/learning-kpi/", LearningKPIAPIView.as_view()),
    path("analytics/xp-panel/", XPVisibilityPanelAPIView.as_view(), name="analytics-xp-panel"),

    # Export
    path("dokumanlar/<int:doc_id>/cheatsheet-export/", CheatSheetExport.as_view(), name="dokuman-cheatsheet-export"),
    path("dokumanlar/<int:doc_id>/readme-export/", ReadmeExportView.as_view(), name="dokuman-readme-export"),
    path("dokumanlar/<int:doc_id>/real-export/", RealExportView.as_view(), name="dokuman-real-export"),
    path("dokumanlar/<int:doc_id>/style-console/", DokumanStyleConsoleAPIView.as_view(), name="dokuman-style-console"),
    path("dokumanlar/<int:doc_id>/directors-cut/", DokumanDirectorsCutAPIView.as_view(), name="dokuman-directors-cut"),
    path("dokumanlar/<int:doc_id>/export-plan/", views.DokumanExportPlanAPIView.as_view(), name="dokuman-export-plan"),
    
    # Faz 3/4: Premium UI, Excel Modlari, Manifest v2 ve Personalization
    path("dokumanlar/<int:doc_id>/excel-modes/", DokumanExcelModesAPIView.as_view(), name="dokuman-excel-modes"),
    path("dokumanlar/<int:doc_id>/export-manifest-v2/", views.DokumanExportManifestV2APIView.as_view(), name="dokuman-export-manifest-v2"),
    path("dokumanlar/<int:doc_id>/premium-payload/", views.DokumanPremiumPayloadAPIView.as_view(), name="dokuman-premium-payload"),
    path("dokumanlar/<int:doc_id>/premium-payloads/", views.DokumanPremiumPayloadAPIView.as_view(), name="dokuman-premium-payloads"),
    path("profil/personalization/", views.PersonalizationProfileAPIView.as_view(), name="profil-personalization"),

    # Faz 4 Ekstraları: Concept, Fusion, Self-Check, Personalization Hints
    path("dokumanlar/<int:doc_id>/concepts/", views.ConceptSurfaceAPIView.as_view(), name="dokuman-concepts"),
    path("dokumanlar/<int:doc_id>/concepts/detail/", views.ConceptDetailAPIView.as_view(), name="dokuman-concept-detail"),
    path("dokumanlar/<int:doc_id>/concept-graph/", views.ConceptGraphAPIView.as_view(), name="dokuman-concept-graph"),
    path("dokumanlar/<int:doc_id>/fusion-cards/", views.FusionCardsAPIView.as_view(), name="dokuman-fusion-cards"),
    path("dokumanlar/<int:doc_id>/concepts/fusion/", views.ConceptFusionAPIView.as_view(), name="dokuman-concept-fusion"),
    path("analytics/self-check-panel/", views.SelfCheckPanelAPIView.as_view(), name="analytics-self-check-panel"),
    path("profil/personalization-hints/", views.PersonalizationHintsAPIView.as_view(), name="profil-personalization-hints"),

    # Faz 5 Ekstraları: Reels, Learning Modes, Weekly Report, Reward Panel
    path("dokumanlar/<int:doc_id>/reels/", views.DokumanReelsSurfaceAPIView.as_view(), name="dokuman-reels"),
    path("dokumanlar/<int:doc_id>/learning-modes/", views.LearningModesPanelAPIView.as_view(), name="dokuman-learning-modes"),
    path("analytics/weekly-report/", views.WeeklyProgressReportAPIView.as_view(), name="analytics-weekly-report"),
    path("profil/rewards/", views.RewardPanelAPIView.as_view(), name="profil-rewards"),

    # Modül 6
    path("dokumanlar/<int:doc_id>/vurgu/", VurguListCreateAPIView.as_view()),
    path("dokumanlar/<int:doc_id>/vurgu/<int:vurgu_id>/", VurguDeleteAPIView.as_view()),
    path("dokumanlar/<int:doc_id>/adresle/", AdresleAPIView.as_view()),
    path("dokumanlar/<int:doc_id>/calisma-ozeti/", views.DokumanCalismaOzetiAPIView.as_view()),
    path("dokumanlar/<int:doc_id>/boss-rush/", views.DokumanBossRushAPIView.as_view()),
    path("parcalar/<int:parca_id>/anlat-kontrol/", views.KendiCumlenleAnlatKontrolAPIView.as_view()),
    path("parcalar/<int:parca_id>/self-check/", views.SelfCheckRuntimeAPIView.as_view(), name="parca-self-check"),
    path("parcalar/<int:parca_id>/quiz-roulette/", views.QuizRouletteAPIView.as_view(), name="parca-quiz-roulette"),
    path("parcalar/<int:parca_id>/puzzle/", views.PuzzleRuntimeAPIView.as_view(), name="parca-puzzle"),
    path("parcalar/<int:parca_id>/boss-cevap-kontrol/", views.BossCevapKontrolAPIView.as_view()),
    path("odul-loglari/", views.OdulLogListAPIView.as_view()),
    path("dokumanlar/<int:doc_id>/rag-ara/", views.RAGAraAPIView.as_view()),
    path("dokumanlar/<int:doc_id>/escape-room/", views.EscapeRoomAPIView.as_view(), name="dokuman-escape-room"),
    path("dokumanlar/<int:doc_id>/speedrun/", views.SpeedrunAPIView.as_view(), name="dokuman-speedrun"),
    
    path("", include("dokuman.panels_urls")),
]
