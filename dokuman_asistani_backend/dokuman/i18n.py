"""DocVerse icin hafif cok dilli mesaj ve dil normalizasyon katmani."""

from __future__ import annotations

from collections.abc import Mapping


SUPPORTED_LANGUAGE_NAMES = {
    "tr": "Turkce",
    "en": "English",
    "de": "Deutsch",
    "fr": "Francais",
    "es": "Espanol",
    "ar": "Arabic",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "it": "Italiano",
    "pt": "Portugues",
    "nl": "Nederlands",
    "sv": "Svenska",
    "no": "Norsk",
    "da": "Dansk",
    "fi": "Suomi",
    "el": "Greek",
    "he": "Hebrew",
    "hi": "Hindi",
    "ur": "Urdu",
    "fa": "Persian",
    "az": "Azərbaycanca",
    "kk": "Kazakh",
    "ky": "Kyrgyz",
    "uz": "O'zbekcha",
    "tk": "Turkmence",
    "ku": "Kurdi",
    "uk": "Ukrainian",
    "bg": "Bulgarian",
    "ro": "Romana",
    "pl": "Polski",
    "cs": "Cestina",
    "sk": "Slovencina",
    "sl": "Slovenscina",
    "hr": "Hrvatski",
    "sr": "Srpski",
    "bs": "Bosanski",
    "sq": "Shqip",
    "mk": "Macedonian",
    "hu": "Magyar",
    "id": "Indonesia",
    "ms": "Melayu",
    "th": "Thai",
    "vi": "Tieng Viet",
    "fil": "Filipino",
    "sw": "Kiswahili",
    "af": "Afrikaans",
    "am": "Amharic",
    "bn": "Bangla",
    "ca": "Catala",
    "et": "Eesti",
    "eu": "Euskara",
    "gl": "Galego",
    "ka": "Georgian",
    "lt": "Lietuviu",
    "lv": "Latviesu",
    "mt": "Malti",
    "mr": "Marathi",
    "ne": "Nepali",
    "pa": "Punjabi",
    "si": "Sinhala",
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "kn": "Kannada",
    "gu": "Gujarati",
    "ha": "Hausa",
    "yo": "Yoruba",
    "zu": "Zulu",
}

SUPPORTED_LANGS = frozenset(SUPPORTED_LANGUAGE_NAMES)

MESSAGES = {
    "invalid_credentials": {
        "tr": "Kullanıcı adı veya şifre hatalı.",
        "en": "Username or password is incorrect.",
    },
    "auth_credentials_missing": {
        "tr": "Oturum bilgisi bulunamadı. Lütfen giriş yapın.",
        "en": "Authentication credentials were not provided.",
    },
    "token_invalid": {
        "tr": "Oturum anahtarı geçersiz. Lütfen tekrar giriş yapın.",
        "en": "The session token is invalid. Please sign in again.",
    },
    "token_expired": {
        "tr": "Oturum süresi doldu. Lütfen tekrar giriş yapın.",
        "en": "Your session has expired. Please sign in again.",
    },
    "account_disabled": {
        "tr": "Hesap devre dışı bırakılmış.",
        "en": "User account is disabled.",
    },
    "null_characters": {
        "tr": "Geçersiz/görünmeyen karakter var. Lütfen silip tekrar yazın.",
        "en": "Invalid hidden character detected. Please delete and type again.",
    },
    "document_required": {
        "tr": "Doküman gereklidir.",
        "en": "A document is required.",
    },
    "question_required": {
        "tr": "Soru gereklidir.",
        "en": "A question is required.",
    },
    "upload_failed": {
        "tr": "Dosya yüklenemedi.",
        "en": "The file could not be uploaded.",
    },
    "parts_fetch_failed": {
        "tr": "Parçalar alınamadı.",
        "en": "Document parts could not be fetched.",
    },
    "ai_timeout": {
        "tr": "AI servisi zamanında cevap üretemedi.",
        "en": "The AI service did not respond in time.",
    },
    "evidence_empty": {
        "tr": "Bu soru için kanıt bulunamadı.",
        "en": "No evidence was found for this question.",
    },
    "evidence_failed": {
        "tr": "Kanıtlı cevap hazırlanamadı, lütfen tekrar deneyin.",
        "en": "The evidence-based answer could not be prepared. Please try again.",
    },
    "session_required": {
        "tr": "Bu işlem için oturum gerekli. Lütfen tekrar giriş yapın.",
        "en": "This action requires a session. Please sign in again.",
    },
    "validation_error": {
        "tr": "Gönderilen bilgiler kontrol edilmeli.",
        "en": "Please check the submitted information.",
    },
    "unexpected_error": {
        "tr": "Beklenmeyen bir hata oluştu.",
        "en": "An unexpected error occurred.",
    },
    "unsupported_extension": {
        "tr": "Bu dosya türü desteklenmiyor.",
        "en": "This file type is not supported.",
    },
    "blocked_extension": {
        "tr": "Bu dosya türü güvenlik nedeniyle yüklenemez.",
        "en": "This file type cannot be uploaded for security reasons.",
    },
    "parser_not_available": {
        "tr": "Bu dosya türü yüklenebilir ancak şu anda içerik çıkarma desteği yok.",
        "en": "This file type can be uploaded, but content extraction is not available yet.",
    },
    "archive_not_supported": {
        "tr": "Arşiv dosyaları için içerik çıkarma desteği henüz hazır değil.",
        "en": "Content extraction for archive files is not ready yet.",
    },
    "archive_unsafe_path": {
        "tr": "Arşiv içinde güvenli olmayan dosya yolu tespit edildi.",
        "en": "An unsafe file path was detected inside the archive.",
    },
    "archive_too_large": {
        "tr": "Arşiv dosyası çok büyük.",
        "en": "The archive file is too large.",
    },
    "archive_too_many_files": {
        "tr": "Arşiv içinde çok fazla dosya var.",
        "en": "The archive contains too many files.",
    },
    "resource_not_found": {
        "tr": "İstenen kayıt bulunamadı.",
        "en": "The requested resource was not found.",
    },
    "permission_denied": {
        "tr": "Bu işlem için yetkiniz yok.",
        "en": "You do not have permission for this action.",
    },
    "rate_limited": {
        "tr": "Cok fazla istek gonderildi. Lutfen tekrar deneyin.",
        "en": "Too many requests were sent. Please try again.",
    },
    "fallback_warning": {
        "tr": "AI servisi geçici olarak cevap üretemedi, kanıta dayalı hızlı cevap gösterildi.",
        "en": "The AI service could not generate an answer, so a quick evidence-based answer is shown.",
    },
    "fallback_answer_prefix": {
        "tr": "Bu soruya göre belgede en ilgili bölüm şunu anlatıyor: ",
        "en": "According to the question, the most relevant section in the document says: ",
    },
    "invalid_remix_style": {
        "tr": "Geçersiz remix stili.",
        "en": "Invalid remix style.",
    },
    "remix_failed": {
        "tr": "Remix sonucu alınamadı. Güvenli kısa anlatım gösterildi.",
        "en": "The remix result could not be prepared. A safe quick version is shown.",
    },
    "invalid_directors_cut_type": {
        "tr": "Geçersiz Director’s Cut türü.",
        "en": "Invalid Director’s Cut type.",
    },
    "directors_cut_failed": {
        "tr": "Director’s Cut sonucu alınamadı. Güvenli kısa kurgu gösterildi.",
        "en": "The Director’s Cut result could not be prepared. A safe quick cut is shown.",
    },
    "feature_disabled": {
        "tr": "Stil konsolu şu anda kapalı.",
        "en": "The style console is currently disabled.",
    },
    "personalization_disabled": {
        "tr": "Kişiselleştirme şu anda kapalı.",
        "en": "Personalization is currently disabled.",
    },
    "concepts_disabled": {
        "tr": "Kavram sistemi şu anda kapalı.",
        "en": "The concept system is currently disabled.",
    },
    "concept_not_found": {
        "tr": "Bu kavram için detay bulunamadı.",
        "en": "No details were found for this concept.",
    },
    "invalid_concept_query": {
        "tr": "Geçerli bir kavram sorgusu yazın.",
        "en": "Enter a valid concept query.",
    },
    "invalid_preference": {
        "tr": "Geçersiz tercih.",
        "en": "Invalid preference.",
    },
}

RAW_ERROR_CODE_MAP = {
    "no active account found with the given credentials": "invalid_credentials",
    "authentication credentials were not provided.": "auth_credentials_missing",
    "given token not valid for any token type": "token_invalid",
    "token is invalid or expired": "token_expired",
    "user account is disabled": "account_disabled",
    "null characters are not allowed.": "null_characters",
}

LANG_INSTRUCTIONS = {
    "tr": "Yanıtı Türkçe ver.",
    "en": "Answer in English.",
    "de": "Antworte auf Deutsch.",
    "fr": "Réponds en français.",
    "es": "Responde en español.",
    "ar": "أجب باللغة العربية.",
    "ru": "Отвечай на русском языке.",
    "ja": "日本語で答えてください。",
    "ko": "한국어로 답하세요.",
    "zh": "请用中文回答。",
}


def normalize_lang(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "tr"
    first = raw.split(",", 1)[0].split(";", 1)[0].strip()
    if not first:
        return "tr"
    code = first.replace("_", "-").split("-", 1)[0].strip()
    return code if code in SUPPORTED_LANGS else "tr"


def get_request_lang(request) -> str:
    headers = getattr(request, "headers", {}) or {}
    header_lang = headers.get("Accept-Language") if hasattr(headers, "get") else ""
    if header_lang:
        return normalize_lang(header_lang)

    query_params = getattr(request, "query_params", None) or getattr(request, "GET", {}) or {}
    query_lang = query_params.get("lang") if hasattr(query_params, "get") else ""
    if query_lang:
        return normalize_lang(query_lang)

    data = getattr(request, "data", {}) or {}
    if isinstance(data, Mapping):
        body_lang = data.get("lang") or data.get("language")
        if body_lang:
            return normalize_lang(body_lang)
    return "tr"


def t(key: str, lang: str, **kwargs) -> str:
    catalog = MESSAGES.get(str(key or "").strip()) or {}
    normalized = normalize_lang(lang)
    template = catalog.get(normalized) or catalog.get("en") or catalog.get("tr") or str(key or "")
    try:
        return template.format(**kwargs)
    except Exception:
        return template


def error_code_from_message(message: str) -> str:
    normalized = " ".join(str(message or "").lower().split())
    for raw, code in RAW_ERROR_CODE_MAP.items():
        if raw in normalized:
            return code
    return ""


def language_instruction(lang: str) -> str:
    normalized = normalize_lang(lang)
    if normalized in LANG_INSTRUCTIONS:
        return LANG_INSTRUCTIONS[normalized]
    name = SUPPORTED_LANGUAGE_NAMES.get(normalized, normalized)
    return f"Answer in the user's selected language: {normalized} / {name}."
