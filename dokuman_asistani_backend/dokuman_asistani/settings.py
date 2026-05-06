import os
import shutil
from datetime import timedelta
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(*adlar: str, varsayilan: bool = False) -> bool:
    for ad in adlar:
        deger = os.getenv(ad)
        if deger is None:
            continue
        return str(deger).strip().lower() in {"1", "true", "evet", "on", "yes"}
    return varsayilan

DJANGO_API_PORTU = int(os.getenv("DJANGO_API_PORTU", "8001"))
AI2_SERVIS_PORTU = int(os.getenv("AI2_SERVIS_PORTU", "8002"))

# --- AI2 (OpenAI-compatible server) ---
AI2_TABAN_ADRESI = (
    os.getenv("AI2_TABAN_ADRESI")
    or os.getenv("AI2_BASE_URL")
    or f"http://127.0.0.1:{AI2_SERVIS_PORTU}/v1"
)
AI2_MODEL_ADI = (
    os.getenv("AI2_MODEL_ADI")
    or os.getenv("AI2_MODEL_ALIAS")
    or os.getenv("AI2_MODEL", "qwen-docverse")
)
AI2_SICAKLIK = float(os.getenv("AI2_SICAKLIK") or os.getenv("AI2_TEMPERATURE", "0.0"))
AI2_ZAMAN_ASIMI = int(os.getenv("AI2_ZAMAN_ASIMI") or os.getenv("AI2_TIMEOUT", "600"))
AI2_AZAMI_TOKEN = int(os.getenv("AI2_AZAMI_TOKEN", "1200"))
AI2_TEST_MODU = _env_bool("AI2_TEST_MODU", "TEST_MODE", varsayilan=False)
AI2_NORMAL_DEFAULT_MAX_TOKENS = int(os.getenv("AI2_NORMAL_DEFAULT_MAX_TOKENS", "256"))
AI2_TEST_DEFAULT_MAX_TOKENS = int(os.getenv("AI2_TEST_DEFAULT_MAX_TOKENS", "128"))
AI2_NORMAL_ANLAMADIM_MAX_TOKENS = int(os.getenv("AI2_NORMAL_ANLAMADIM_MAX_TOKENS", "256"))
AI2_TEST_ANLAMADIM_MAX_TOKENS = int(os.getenv("AI2_TEST_ANLAMADIM_MAX_TOKENS", "128"))
AI2_NORMAL_QA_MAX_TOKENS = int(os.getenv("AI2_NORMAL_QA_MAX_TOKENS", "450"))
AI2_TEST_QA_MAX_TOKENS = int(os.getenv("AI2_TEST_QA_MAX_TOKENS", "256"))
AI2_NORMAL_EXPLAIN_MAX_TOKENS = int(os.getenv("AI2_NORMAL_EXPLAIN_MAX_TOKENS", "320"))
AI2_TEST_EXPLAIN_MAX_TOKENS = int(os.getenv("AI2_TEST_EXPLAIN_MAX_TOKENS", "220"))
AI2_NORMAL_GRADING_MAX_TOKENS = int(os.getenv("AI2_NORMAL_GRADING_MAX_TOKENS", "500"))
AI2_TEST_GRADING_MAX_TOKENS = int(os.getenv("AI2_TEST_GRADING_MAX_TOKENS", "320"))

# --- Yerel model ayarlari ---
QWEN_Q5_GGUF_DOSYASI = BASE_DIR / "models" / "Qwen2.5-7B-Instruct-Q5_K_M.gguf"
QWEN_Q4_LEGACY_GGUF_DOSYASI = BASE_DIR / "models" / "Qwen2.5-7B-Instruct-Q4_K_S.gguf"
DEEPSEEK_Q6_GGUF_DOSYASI = BASE_DIR / "models" / "DeepSeek-R1-Distill-Qwen-7B-Q6_K_L.gguf"
_GGUF_ADAYLARI = [
    os.getenv("ANA_GGUF_YOLU"),
    os.getenv("YEREL_MODEL_YOLU"),
    os.getenv("LLM_MODEL_PATH"),
    str(QWEN_Q5_GGUF_DOSYASI),
    str(QWEN_Q4_LEGACY_GGUF_DOSYASI),
    str(DEEPSEEK_Q6_GGUF_DOSYASI),
]
_secilen_gguf_yolu = next((yol for yol in _GGUF_ADAYLARI if yol and Path(yol).exists()), None)
if not _secilen_gguf_yolu:
    _secilen_gguf_yolu = next((yol for yol in _GGUF_ADAYLARI if yol), str(BASE_DIR / "models"))

ANA_GGUF_YOLU = Path(_secilen_gguf_yolu)
YEREL_MODEL_ETKIN = (os.getenv("YEREL_MODEL_ETKIN") or os.getenv("LLM_ENABLED", "1")) == "1"
YEREL_BAGLAM_BOYU = int(os.getenv("YEREL_BAGLAM_BOYU") or os.getenv("LLM_N_CTX", "4096"))
YEREL_IS_PARCACIGI = int(os.getenv("YEREL_IS_PARCACIGI") or os.getenv("LLM_THREADS", "8"))
YEREL_GPU_KATMAN_SAYISI = int(
    os.getenv("YEREL_GPU_KATMAN_SAYISI") or os.getenv("LLM_N_GPU_LAYERS", "0")
)
YEREL_SICAKLIK = float(os.getenv("YEREL_SICAKLIK") or os.getenv("LLM_TEMPERATURE", "0.2"))

# Geriye donuk uyumluluk aliaslari
AI2_BASE_URL = AI2_TABAN_ADRESI
AI2_MODEL_ALIAS = AI2_MODEL_ADI
AI2_MODEL = AI2_MODEL_ADI
AI2_TEMPERATURE = AI2_SICAKLIK
AI2_TIMEOUT = AI2_ZAMAN_ASIMI
YEREL_MODEL_YOLU = ANA_GGUF_YOLU
DEFAULT_GGUF = ANA_GGUF_YOLU
LLM_ENABLED = YEREL_MODEL_ETKIN
LLM_MODEL_PATH = YEREL_MODEL_YOLU
LLM_N_CTX = YEREL_BAGLAM_BOYU
LLM_THREADS = YEREL_IS_PARCACIGI
LLM_N_GPU_LAYERS = YEREL_GPU_KATMAN_SAYISI
LLM_TEMPERATURE = YEREL_SICAKLIK
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# The real `SECRET_KEY` is loaded later from env; avoid hardcoding values here.
RAG_ENABLED = True
RAG_AUTO_INDEX_ON_INGEST = _env_bool("RAG_AUTO_INDEX_ON_INGEST", varsayilan=False)
DOCVERSE_RERANK_ENABLED = _env_bool("DOCVERSE_RERANK_ENABLED", varsayilan=True)
DOCVERSE_DEBUG_SUMMARY_ENABLED = _env_bool("DOCVERSE_DEBUG_SUMMARY_ENABLED", varsayilan=False)
DOCVERSE_HEADING_SCORE_ENABLED = _env_bool("DOCVERSE_HEADING_SCORE_ENABLED", varsayilan=True)
DOCVERSE_QUALITY_SCORE_ENABLED = _env_bool("DOCVERSE_QUALITY_SCORE_ENABLED", varsayilan=True)
CHROMA_DIR = BASE_DIR / "chroma_db"
EMBED_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CHROMA_COLLECTION = "docverse_parcalar"
# SECURITY WARNING: don't run with debug turned on in production!
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "gecici-gelistirme-anahtari-degistir")
DEBUG = _env_bool("DJANGO_DEBUG", varsayilan=False)

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "10.0.2.2",
    "citadel-revisable-drool.ngrok-free.dev",
    ".ngrok-free.dev",
    ".ngrok.app",
]

CSRF_TRUSTED_ORIGINS = [
    "https://citadel-revisable-drool.ngrok-free.dev",
    "https://*.ngrok-free.dev",
    "https://*.ngrok.app",
]

# Tesseract binary resolution: prefer explicit env, then PATH. Do not embed OS-specific defaults here.
# If Tesseract is not present, leave empty and let release_checks/reporting handle it.
_tess_env = os.getenv("TESSERACT_CMD")
_tess_from_path = shutil.which("tesseract")
if _tess_env and Path(_tess_env).exists():
    TESSERACT_CMD = _tess_env
elif _tess_from_path:
    TESSERACT_CMD = _tess_from_path
else:
    TESSERACT_CMD = ""

OCR_LANG = os.getenv("OCR_LANG", "tur+eng")
OCR_PSM = 6
OCR_OEM = 3
OCR_CHUNK_SIZE = 1200
DOCVERSE_OCR_STRICT_QUALITY_MODE = _env_bool("DOCVERSE_OCR_STRICT_QUALITY_MODE", varsayilan=False)
# Upload uzantilari kategori bazli katalogdan gelir; parser destegi ayrica kontrol edilir.
from dokuman.config.file_types import (
    DOCVERSE_ARCHIVE_EXTENSIONS,
    DOCVERSE_BLOCKED_EXTENSIONS,
    DOCVERSE_CODE_EXTENSIONS,
    DOCVERSE_DATA_EXTENSIONS,
    DOCVERSE_MEDIA_EXTENSIONS,
    DOCVERSE_OCR_EXTENSIONS,
    DOCVERSE_OFFICE_EXTENSIONS,
    DOCVERSE_PARSE_SUPPORTED_EXTENSIONS,
    DOCVERSE_UPLOAD_EXTENSIONS,
)
DOCVERSE_UPLOAD_MIN_BYTES = int(os.getenv("DOCVERSE_UPLOAD_MIN_BYTES", "8"))
DOCVERSE_UPLOAD_MAX_BYTES = int(os.getenv("DOCVERSE_UPLOAD_MAX_BYTES", str(25 * 1024 * 1024)))
DOCVERSE_IMAGE_UPLOAD_ENABLED = _env_bool("DOCVERSE_IMAGE_UPLOAD_ENABLED", varsayilan=True)
DOCVERSE_ARCHIVE_MAX_FILES = int(os.getenv("DOCVERSE_ARCHIVE_MAX_FILES", "80"))
DOCVERSE_ARCHIVE_MAX_UNCOMPRESSED_BYTES = int(os.getenv("DOCVERSE_ARCHIVE_MAX_UNCOMPRESSED_BYTES", str(50 * 1024 * 1024)))
DOCVERSE_NOTLAR_ENABLED = _env_bool("DOCVERSE_NOTLAR_ENABLED", varsayilan=True)
DOCVERSE_PORTAL_NOTLAR_ENABLED = _env_bool("DOCVERSE_PORTAL_NOTLAR_ENABLED", varsayilan=True)
DOCVERSE_METRIC_STORE_ENABLED = _env_bool("DOCVERSE_METRIC_STORE_ENABLED", varsayilan=True)
DOCVERSE_HARDEST_PARTS_ENABLED = _env_bool("DOCVERSE_HARDEST_PARTS_ENABLED", varsayilan=True)
DOCVERSE_THEMED_EXAMPLES_ENABLED = _env_bool("DOCVERSE_THEMED_EXAMPLES_ENABLED", varsayilan=True)
DOCVERSE_SPECIAL_CHUNK_FALLBACKS_ENABLED = _env_bool("DOCVERSE_SPECIAL_CHUNK_FALLBACKS_ENABLED", varsayilan=True)
DOCVERSE_CHEATSHEET_EXPORT_ENABLED = _env_bool("DOCVERSE_CHEATSHEET_EXPORT_ENABLED", varsayilan=True)
DOCVERSE_REAL_EXPORTS_ENABLED = _env_bool("DOCVERSE_REAL_EXPORTS_ENABLED", varsayilan=True)
DOCVERSE_README_EXPORT_ENABLED = _env_bool("DOCVERSE_README_EXPORT_ENABLED", varsayilan=True)
DOCVERSE_STUDY_SUMMARY_ENABLED = _env_bool("DOCVERSE_STUDY_SUMMARY_ENABLED", varsayilan=True)
DOCVERSE_FEEDBACK_ENABLED = _env_bool("DOCVERSE_FEEDBACK_ENABLED", varsayilan=True)
DOCVERSE_QUIZ_ENABLED = _env_bool("DOCVERSE_QUIZ_ENABLED", varsayilan=True)
DOCVERSE_BOSS_ENABLED = _env_bool("DOCVERSE_BOSS_ENABLED", varsayilan=True)
DOCVERSE_STYLE_CONSOLE_ENABLED = _env_bool("DOCVERSE_STYLE_CONSOLE_ENABLED", varsayilan=True)
DOCVERSE_DIRECTORS_CUT_ENABLED = _env_bool("DOCVERSE_DIRECTORS_CUT_ENABLED", varsayilan=True)
DOCVERSE_EXPORT_PLAN_ENABLED = _env_bool("DOCVERSE_EXPORT_PLAN_ENABLED", varsayilan=True)
DOCVERSE_BOSS_RUSH_PANEL_ENABLED = _env_bool("DOCVERSE_BOSS_RUSH_PANEL_ENABLED", varsayilan=DOCVERSE_BOSS_ENABLED)
DOCVERSE_EXPORT_READINESS_ENABLED = _env_bool("DOCVERSE_EXPORT_READINESS_ENABLED", varsayilan=DOCVERSE_EXPORT_PLAN_ENABLED)
DOCVERSE_WEEKLY_PROGRESS_ENABLED = _env_bool("DOCVERSE_WEEKLY_PROGRESS_ENABLED", varsayilan=DOCVERSE_METRIC_STORE_ENABLED)
DOCVERSE_ACHIEVEMENT_PROGRESS_ENABLED = _env_bool("DOCVERSE_ACHIEVEMENT_PROGRESS_ENABLED", varsayilan=DOCVERSE_METRIC_STORE_ENABLED)
DOCVERSE_PANEL_SCORE_HOOKS = {}
DOCVERSE_EXCEL_MODES_ENABLED = _env_bool("DOCVERSE_EXCEL_MODES_ENABLED", varsayilan=True)
DOCVERSE_PREMIUM_UI_PAYLOADS_ENABLED = _env_bool("DOCVERSE_PREMIUM_UI_PAYLOADS_ENABLED", varsayilan=True)
DOCVERSE_PERSONALIZATION_ENABLED = _env_bool("DOCVERSE_PERSONALIZATION_ENABLED", varsayilan=True)
DOCVERSE_CONCEPTS_ENABLED = _env_bool("DOCVERSE_CONCEPTS_ENABLED", varsayilan=True)
DOCVERSE_SELF_CHECK_ENABLED = _env_bool("DOCVERSE_SELF_CHECK_ENABLED", varsayilan=True)
DOCVERSE_FUSION_ENABLED = _env_bool("DOCVERSE_FUSION_ENABLED", varsayilan=True)
DOCVERSE_ROULETTE_ENABLED = _env_bool("DOCVERSE_ROULETTE_ENABLED", varsayilan=True)
DOCVERSE_ESCAPE_ROOM_ENABLED = _env_bool("DOCVERSE_ESCAPE_ROOM_ENABLED", varsayilan=True)
DOCVERSE_SPEEDRUN_ENABLED = _env_bool("DOCVERSE_SPEEDRUN_ENABLED", varsayilan=True)
DOCVERSE_REELS_ENABLED = _env_bool("DOCVERSE_REELS_ENABLED", varsayilan=True)
DOCVERSE_REWARD_PANEL_ENABLED = _env_bool("DOCVERSE_REWARD_PANEL_ENABLED", varsayilan=True)
DOCVERSE_PANEL_SCORE_OVERRIDES = {}
# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "dokuman",
    "oyun.apps.OyunConfig",
    "exporter",
]


MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = 'dokuman_asistani.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'dokuman_asistani.wsgi.application'
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "URL_FORMAT_OVERRIDE": None,
}
REST_FRAMEWORK = REST_FRAMEWORK if "REST_FRAMEWORK" in globals() else {}

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (
    "dokuman_asistani.renderers.UTF8JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "token_obtain": os.getenv("DOCVERSE_THROTTLE_TOKEN_OBTAIN_RATE", "10/min"),
    "token_refresh": os.getenv("DOCVERSE_THROTTLE_TOKEN_REFRESH_RATE", "20/min"),
    "upload": os.getenv("DOCVERSE_THROTTLE_UPLOAD_RATE", "12/hour"),
    "anlamadim": os.getenv("DOCVERSE_THROTTLE_ANLAMADIM_RATE", "30/min"),
    "kanitli_cevap": os.getenv("DOCVERSE_THROTTLE_KANITLI_CEVAP_RATE", "20/min"),
    "notes_write": os.getenv("DOCVERSE_THROTTLE_NOTES_WRITE_RATE", "40/min"),
}
TEST_RUNNER = "dokuman_asistani.test_runner.PytestTestRunner"
DEFAULT_CHARSET = "utf-8"
# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        # Resolve DB path from env if provided; otherwise use project-local db.sqlite3.
        "NAME": os.getenv("DJANGO_DB_PATH", os.getenv("DB_PATH", str(BASE_DIR / "db.sqlite3"))),
        "OPTIONS": {
            "timeout": 30,
        },
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
CORS_ALLOW_ALL_ORIGINS = _env_bool(
    "DJANGO_CORS_ALLOW_ALL_ORIGINS",
    "CORS_ALLOW_ALL_ORIGINS",
    varsayilan=True,
)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),

    # opsiyonel ama iyi:
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
}
