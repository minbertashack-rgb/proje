from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    BossViewSet, DenemeViewSet,
    OyunProfilView, GunlukGirisView,
    GorevView, GorevOdulAlView,
    BasarimView, LiderlikView,
    MarketView, EnvanterView, BoosterKullanView,
    BildirimlerView, OdulLogView
)

router = DefaultRouter()
router.register(r"bosslar", BossViewSet, basename="boss")
router.register(r"denemeler", DenemeViewSet, basename="deneme")

urlpatterns = [
    path("profil/", OyunProfilView.as_view()),
    path("profil/gunluk-giris/", GunlukGirisView.as_view()),

    path("", include(router.urls)),

    path("gorevler/", GorevView.as_view()),
    path("gorevler/<int:gorev_id>/odul-al/", GorevOdulAlView.as_view()),

    path("basarimlar/", BasarimView.as_view()),
    path("liderlik/", LiderlikView.as_view()),

    path("market/", MarketView.as_view()),
    path("envanter/", EnvanterView.as_view()),
    path("envanter/booster-kullan/", BoosterKullanView.as_view()),

    path("bildirimler/", BildirimlerView.as_view()),
    path("oduller/", OdulLogView.as_view()),
]