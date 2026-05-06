"""
URL configuration for dokuman_asistani project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.settings import api_settings as drf_api_settings

from dokuman.views_kimlik import DocverseTokenObtainPairView, DocverseTokenRefreshView

# Patch 2: auth/error response standardization without touching existing endpoint paths.
settings.REST_FRAMEWORK = dict(getattr(settings, "REST_FRAMEWORK", {}) or {})
settings.REST_FRAMEWORK["EXCEPTION_HANDLER"] = "dokuman.views_kimlik.docverse_exception_handler"
if hasattr(drf_api_settings, "reload"):
    drf_api_settings.reload()

urlpatterns = [
    path("admin/", admin.site.urls),

    # Kimlik
    path("api/kimlik/kayit/", include("dokuman.kimlik_urls")),
    path("api/kimlik/token/", DocverseTokenObtainPairView.as_view(), name="token_al"),
    path("api/kimlik/token/yenile/", DocverseTokenRefreshView.as_view(), name="token_yenile"),

    # Doküman Asistanı
    path("api/dokuman-asistani/", include("dokuman.urls")),
    path("api/oyun/", include("oyun.urls")),
    path("api/export/", include("exporter.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
