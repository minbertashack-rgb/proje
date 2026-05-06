from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import OyunProfil

User = settings.AUTH_USER_MODEL
# oyun/signals.py
User = get_user_model()

@receiver(post_save, sender=User)
def create_profile_for_new_user(sender, instance, created, **kwargs):
    if created:
        OyunProfil.objects.get_or_create(kullanici=instance)
        
@receiver(post_save, sender=settings.AUTH_USER_MODEL if isinstance(User, type) else None)
def _noop(sender, instance, created, **kwargs):
    # Bazı projelerde AUTH_USER_MODEL string gelir; aşağıdaki receiver onu garantiye alır.
    pass


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def oyun_profil_olustur(sender, instance, created, **kwargs):
    if created:
        OyunProfil.objects.get_or_create(kullanici=instance)
        

UserModel = get_user_model()

@receiver(post_save, sender=UserModel)
def oyun_profil_olustur(sender, instance, created, **kwargs):
    if created:
        OyunProfil.objects.get_or_create(kullanici=instance)