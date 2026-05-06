import math
from collections.abc import Mapping

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import serializers, status
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    PermissionDenied as DRFPermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView, exception_handler as drf_exception_handler
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_api_settings
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from dokuman_asistani.renderers import UTF8JSONRenderer

from .i18n import error_code_from_message, get_request_lang, t
from .throttles import TokenObtainThrottle, TokenRefreshThrottle

User = get_user_model()


def _stringify_error(value) -> str:
    if isinstance(value, Mapping):
        for item in value.values():
            text = _stringify_error(item)
            if text:
                return text
        return ""
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _stringify_error(item)
            if text:
                return text
        return ""
    if value is None:
        return ""
    return str(value).strip()


def _normalize_error_value(value):
    if isinstance(value, Mapping):
        return {str(key): _normalize_error_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_error_value(item) for item in value]
    if value is None:
        return ""
    return str(value).strip()


def _extract_detail(data) -> str:
    if isinstance(data, Mapping):
        detail = _stringify_error(data.get("detail"))
        if detail:
            return detail
        messages = data.get("messages")
        detail = _stringify_error(messages)
        if detail:
            return detail
        for key, value in data.items():
            if key in {"detail", "status_text", "error_code", "field_errors", "code", "messages"}:
                continue
            detail = _stringify_error(value)
            if detail:
                return detail
    else:
        detail = _stringify_error(data)
        if detail:
            return detail
    return "Istek islenemedi."


def _extract_field_errors(data) -> dict:
    if isinstance(data, Mapping):
        errors = {}
        for key, value in data.items():
            if key in {"detail", "status_text", "error_code", "field_errors", "code", "messages"}:
                continue
            errors[str(key)] = _normalize_error_value(value)
        return errors

    normalized = _normalize_error_value(data)
    if normalized in ("", [], {}):
        return {}
    if isinstance(normalized, list):
        return {"non_field_errors": normalized}
    return {"non_field_errors": [normalized]}


def _should_preserve_original_detail(error_code: str, detail: str) -> bool:
    return bool(str(detail or "").strip()) and error_code in {
        "validation_error",
        "permission_denied",
    }


def _build_error_payload(*, detail: str, error_code: str = "", field_errors: dict | None = None, extra: dict | None = None) -> dict:
    translated = "" if _should_preserve_original_detail(error_code, detail) else (t(error_code, "tr") if error_code else "")
    detail = translated or detail
    payload = {
        "detail": str(detail or "").strip(),
        "status_text": str(detail or "").strip(),
    }
    if str(error_code or "").strip():
        payload["error_code"] = str(error_code).strip()
    if field_errors:
        payload["field_errors"] = field_errors
    payload.update(dict(extra or {}))
    return payload


def _token_type() -> str:
    header_types = tuple(getattr(jwt_api_settings, "AUTH_HEADER_TYPES", ()) or ())
    return str(header_types[0] if header_types else "Bearer")


def _access_expires_in() -> int:
    return int(jwt_api_settings.ACCESS_TOKEN_LIFETIME.total_seconds())


def _resolve_error_code(exc, response, data, *, request_path: str = "") -> str:
    source_code = ""
    if isinstance(data, Mapping) and data.get("code") is not None:
        source_code = str(data.get("code") or "").strip()

    if isinstance(exc, Throttled) or response.status_code == 429:
        return "rate_limited"
    raw_code = error_code_from_message(_extract_detail(data))
    if raw_code:
        return raw_code
    if response.status_code == 401 and request_path.rstrip("/") == "/api/kimlik/token":
        return "invalid_credentials"
    if isinstance(exc, (InvalidToken, NotAuthenticated)) or source_code == "token_not_valid":
        return "token_invalid"
    if isinstance(exc, AuthenticationFailed):
        if source_code == "no_active_account" or getattr(exc, "default_code", "") == "no_active_account":
            return "invalid_credentials"
        return "session_required"
    if isinstance(exc, (DRFPermissionDenied, DjangoPermissionDenied)) or response.status_code == 403:
        return "permission_denied"
    if isinstance(exc, (NotFound, Http404)) or response.status_code == 404:
        return "resource_not_found"
    if isinstance(exc, ValidationError) or response.status_code == 400:
        return "validation_error"
    if response.status_code == 401:
        return "session_required"
    return ""


def docverse_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    request = context.get("request")
    request_path = str(getattr(request, "path", "") or "")
    if request_path and not request_path.startswith("/api/"):
        return response

    original_data = response.data
    detail = _extract_detail(original_data)
    field_errors = _extract_field_errors(original_data)
    error_code = _resolve_error_code(exc, response, original_data, request_path=request_path)
    response_lang = get_request_lang(request)
    translated_detail = "" if _should_preserve_original_detail(error_code, detail) else (t(error_code, response_lang) if error_code else "")

    payload = dict(original_data) if isinstance(original_data, Mapping) else {}
    payload["detail"] = translated_detail or detail
    payload["status_text"] = translated_detail or detail
    if error_code:
        payload["error_code"] = error_code
    if field_errors:
        payload["field_errors"] = field_errors
    if error_code == "rate_limited":
        friendly_detail = t("rate_limited", response_lang)
        payload["detail"] = friendly_detail
        payload["status_text"] = friendly_detail
        payload.pop("field_errors", None)
        wait_seconds = getattr(exc, "wait", None)
        if wait_seconds is not None:
            payload["retry_after"] = max(1, int(math.ceil(float(wait_seconds))))

    response.data = payload
    return response


class DocverseTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data["token_type"] = _token_type()
        data["expires_in"] = _access_expires_in()
        data["status_text"] = "Oturum acildi."
        return data


class DocverseTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data["token_type"] = _token_type()
        data["expires_in"] = _access_expires_in()
        data["status_text"] = "Token yenilendi."
        return data


class DocverseTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = DocverseTokenObtainPairSerializer
    throttle_classes = [TokenObtainThrottle]


class DocverseTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    serializer_class = DocverseTokenRefreshSerializer
    throttle_classes = [TokenRefreshThrottle]


class AlwaysJSONContentNegotiation(BaseContentNegotiation):
    def select_parser(self, request, parsers):
        return parsers[0] if parsers else None

    def select_renderer(self, request, renderers, format_suffix=None):
        renderer = renderers[0]
        return renderer, renderer.media_type


class KayitSerializer(serializers.Serializer):
    username = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        error_messages={
            "required": "Bu alan zorunludur.",
            "blank": "Bu alan zorunludur.",
        },
    )
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=False,
        write_only=True,
        error_messages={
            "required": "Bu alan zorunludur.",
            "blank": "Bu alan zorunludur.",
        },
    )
    password2 = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        write_only=True,
        error_messages={
            "required": "Bu alan zorunludur.",
            "blank": "Bu alan zorunludur.",
        },
    )
    password_confirm = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        write_only=True,
        error_messages={
            "required": "Bu alan zorunludur.",
            "blank": "Bu alan zorunludur.",
        },
    )

    default_error_messages = {
        "duplicate_username": "Bu kullanıcı adı zaten kullanımda.",
        "password_mismatch": "Şifre tekrar alanları eşleşmiyor.",
    }

    def validate_username(self, value):
        username = str(value or "").strip()
        if not username:
            raise serializers.ValidationError("Bu alan zorunludur.")
        if User.objects.filter(username=username).exists():
            raise serializers.ValidationError(self.error_messages["duplicate_username"])
        return username

    def validate(self, attrs):
        password = attrs.get("password") or ""
        password2 = attrs.get("password2") or ""
        password_confirm = attrs.get("password_confirm") or ""

        confirmations = [item for item in [password2, password_confirm] if str(item or "").strip()]
        if confirmations and any(item != password for item in confirmations):
            raise serializers.ValidationError(
                {
                    "password_confirm": [self.error_messages["password_mismatch"]],
                }
            )

        return attrs

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", "") or "",
            password=validated_data["password"],
        )


class KayitView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    renderer_classes = [UTF8JSONRenderer, JSONRenderer]
    content_negotiation_class = AlwaysJSONContentNegotiation

    def post(self, request):
        serializer = KayitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "detail": "Kayıt başarılı.",
                "status_text": "Kayıt başarılı.",
                "username": user.username,
                "email": user.email,
            },
            status=status.HTTP_201_CREATED,
        )
