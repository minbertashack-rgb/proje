from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured
from rest_framework.settings import api_settings
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class _DynamicRateMixin:
    def get_rate(self):
        if not getattr(self, "scope", None):
            msg = "You must set either `.scope` or `.rate` for '%s' throttle" % self.__class__.__name__
            raise ImproperlyConfigured(msg)

        try:
            return api_settings.DEFAULT_THROTTLE_RATES[self.scope]
        except KeyError as exc:
            msg = "No default throttle rate set for '%s' scope" % self.scope
            raise ImproperlyConfigured(msg) from exc


class _MethodThrottleMixin:
    throttle_methods: set[str] | None = None

    def allow_request(self, request, view):
        methods = {str(item).upper() for item in (self.throttle_methods or set()) if str(item).strip()}
        if methods and request.method.upper() not in methods:
            return True
        return super().allow_request(request, view)


class TokenObtainThrottle(_DynamicRateMixin, _MethodThrottleMixin, AnonRateThrottle):
    scope = "token_obtain"
    throttle_methods = {"POST"}


class TokenRefreshThrottle(_DynamicRateMixin, _MethodThrottleMixin, AnonRateThrottle):
    scope = "token_refresh"
    throttle_methods = {"POST"}


class UploadThrottle(_DynamicRateMixin, _MethodThrottleMixin, UserRateThrottle):
    scope = "upload"
    throttle_methods = {"POST"}


class ExplainThrottle(_DynamicRateMixin, _MethodThrottleMixin, UserRateThrottle):
    scope = "anlamadim"
    throttle_methods = {"POST"}


class EvidenceThrottle(_DynamicRateMixin, _MethodThrottleMixin, UserRateThrottle):
    scope = "kanitli_cevap"
    throttle_methods = {"POST"}


class NotesWriteThrottle(_DynamicRateMixin, _MethodThrottleMixin, UserRateThrottle):
    scope = "notes_write"
    throttle_methods = {"POST", "PUT", "PATCH"}
