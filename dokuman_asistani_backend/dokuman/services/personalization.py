from __future__ import annotations

from collections.abc import Mapping

from django.conf import settings

from dokuman.models import KullaniciTercih

THEMES = ["default", "spor", "yemek", "oyun", "teknoloji", "film_dizi", "muzik", "tarih", "bilim", "saglik", "is_dunyasi"]
STYLES = ["kisa", "adim_adim", "bol_ornek", "hafif_mizah", "ciddi", "sinav_odakli", "sohbet"]
LEVELS = ["baslangic", "orta", "ileri"]
EXAMPLE_DENSITIES = ["az", "normal", "cok"]

THEME_TO_DB = {}
DB_TO_THEME = {"genel": "default", "film": "film_dizi", "yazilim": "teknoloji", "matematik": "bilim"}
STYLE_TO_DB = {}
DB_TO_STYLE = {"ornekli": "bol_ornek", "derin": "ciddi"}
DENSITY_TO_DB = {}
DB_TO_DENSITY = {"dusuk": "az", "orta": "normal", "yuksek": "cok"}


def personalization_enabled() -> bool:
    return bool(getattr(settings, "DOCVERSE_PERSONALIZATION_ENABLED", True))


def themed_examples_enabled() -> bool:
    return bool(getattr(settings, "DOCVERSE_THEMED_EXAMPLES_ENABLED", True))


def default_preferences() -> dict:
    return {
        "theme": "default",
        "explanation_style": "adim_adim",
        "level": "baslangic",
        "example_density": "normal",
    }


def preference_options() -> dict:
    return {
        "themes": list(THEMES),
        "styles": list(STYLES),
        "levels": list(LEVELS),
        "example_density": list(EXAMPLE_DENSITIES),
    }


def normalize_preferences(data, *, partial: bool = False) -> tuple[dict, dict]:
    src = dict(data or {}) if isinstance(data, Mapping) else {}
    current = {} if partial else default_preferences()
    errors: dict[str, list[str]] = {}
    validators = {
        "theme": (THEMES, "Geçersiz tema."),
        "explanation_style": (STYLES, "Geçersiz anlatım tarzı."),
        "level": (LEVELS, "Geçersiz seviye."),
        "example_density": (EXAMPLE_DENSITIES, "Geçersiz örnek yoğunluğu."),
    }
    for field, (allowed, message) in validators.items():
        if field not in src:
            continue
        value = str(src.get(field) or "").strip()
        if value not in allowed:
            errors[field] = [message]
        else:
            current[field] = value
    return current, errors


def get_user_preferences(user) -> dict:
    prefs = default_preferences()
    if not personalization_enabled() or not getattr(user, "is_authenticated", False):
        return prefs
    obj = KullaniciTercih.objects.filter(kullanici=user).first()
    if obj is None:
        return prefs
    prefs.update(
        {
            "theme": DB_TO_THEME.get(str(obj.tema or ""), str(obj.tema or "") or "default"),
            "explanation_style": DB_TO_STYLE.get(str(obj.tarz or ""), str(obj.tarz or "") or "adim_adim"),
            "level": str(obj.seviye or "baslangic"),
            "example_density": DB_TO_DENSITY.get(
                str(obj.detay_seviyesi or ""),
                str(obj.detay_seviyesi or "") or "normal",
            ),
        }
    )
    return normalize_preferences(prefs)[0]


def resolve_preferences(user, request_data=None) -> dict:
    prefs = get_user_preferences(user)
    overrides = (request_data or {}).get("preferences") if isinstance(request_data, Mapping) else None
    normalized, errors = normalize_preferences(overrides or {}, partial=True)
    if not errors:
        prefs.update(normalized)
    return prefs


def save_user_preferences(user, data) -> tuple[dict, dict]:
    prefs, errors = normalize_preferences(data)
    if errors:
        return prefs, errors
    obj, _ = KullaniciTercih.objects.get_or_create(kullanici=user)
    obj.tema = THEME_TO_DB.get(prefs["theme"], prefs["theme"])
    obj.tarz = STYLE_TO_DB.get(prefs["explanation_style"], prefs["explanation_style"])
    obj.seviye = prefs["level"]
    obj.detay_seviyesi = DENSITY_TO_DB.get(prefs["example_density"], prefs["example_density"])
    obj.mizah_seviyesi = "hafif" if prefs["explanation_style"] == "hafif_mizah" else "yok"
    obj.save()
    return prefs, {}


def build_preferences_response(preferences: dict, *, enabled: bool = True) -> dict:
    return {"enabled": enabled, **preferences, "options": preference_options()}


def themed_example_for_text(text: str, theme: str, lang: str = "tr") -> str:
    if not themed_examples_enabled():
        return ""
    tr = str(lang or "tr").lower().startswith("tr")
    mapping_tr = {
        "oyun": "Bunu oyundaki enerji barı gibi düşünebilirsin.",
        "spor": "Bunu maç sırasında kullanılan hızlı enerji gibi düşünebilirsin.",
        "teknoloji": "Bunu sistemin güç kaynağı gibi düşünebilirsin.",
        "yemek": "Bunu tarifteki temel malzeme gibi düşünebilirsin.",
        "film_dizi": "Bunu hikâyedeki ana olay gibi düşünebilirsin.",
        "muzik": "Bunu şarkının ritmi gibi ana akışı taşıyan öğe gibi düşünebilirsin.",
        "tarih": "Bunu olayları başlatan temel neden gibi düşünebilirsin.",
        "bilim": "Bunu deneyde sonucu etkileyen temel değişken gibi düşünebilirsin.",
        "saglik": "Bunu vücudun hızlı destek kaynağı gibi düşünebilirsin.",
        "is_dunyasi": "Bunu bir ekibin işi ilerletmek için kullandığı ana kaynak gibi düşünebilirsin.",
    }
    mapping_en = {
        "oyun": "Think of it like an energy bar in a game.",
        "spor": "Think of it like quick energy used during a match.",
        "teknoloji": "Think of it like the system's power supply.",
        "yemek": "Think of it like the key ingredient in a recipe.",
        "film_dizi": "Think of it like the main event in a story.",
    }
    return (mapping_tr if tr else mapping_en).get(theme, "")


def build_preference_prompt(preferences: dict, lang: str = "tr") -> str:
    if not personalization_enabled():
        return ""
    tr = str(lang or "tr").lower().startswith("tr")
    if tr:
        return (
            "Kullanıcının öğrenme tercihi:\n"
            f"- Tema: {preferences.get('theme')}\n"
            f"- Seviye: {preferences.get('level')}\n"
            f"- Anlatım tarzı: {preferences.get('explanation_style')}\n"
            f"- Örnek yoğunluğu: {preferences.get('example_density')}\n"
            "Örnekleri mümkünse bu temaya göre ver; dokümanda olmayan bilgiyi uydurma."
        )
    return (
        "User learning preferences:\n"
        f"- Theme: {preferences.get('theme')}\n"
        f"- Level: {preferences.get('level')}\n"
        f"- Explanation style: {preferences.get('explanation_style')}\n"
        f"- Example density: {preferences.get('example_density')}\n"
        "Use theme-like analogies when helpful, but do not invent facts not supported by the document."
    )
