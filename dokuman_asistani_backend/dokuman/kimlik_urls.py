from django.urls import path
from .views_kimlik import KayitView

urlpatterns = [
    path("", KayitView.as_view(), name="kayit"),
]