# oyun/apps.py
from django.apps import AppConfig

class OyunConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "oyun"

    def ready(self):
        import oyun.signals  # signal'ları register eder
        
        