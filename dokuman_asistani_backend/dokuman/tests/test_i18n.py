from rest_framework.test import APIRequestFactory

from dokuman.ai2.prompts import build_kanitli_prompt
from dokuman.i18n import get_request_lang, language_instruction, normalize_lang, t


def test_get_request_lang_accept_language_normalizes_region_codes():
    factory = APIRequestFactory()

    tr_request = factory.get("/api/test/", HTTP_ACCEPT_LANGUAGE="tr-TR,tr;q=0.9")
    en_request = factory.get("/api/test/", HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9")
    fr_request = factory.get("/api/test/", HTTP_ACCEPT_LANGUAGE="fr")

    assert get_request_lang(tr_request) == "tr"
    assert get_request_lang(en_request) == "en"
    assert get_request_lang(fr_request) == "fr"
    assert normalize_lang("pt-BR") == "pt"
    assert normalize_lang("zh-CN") == "zh"


def test_error_catalog_translates_invalid_credentials_tr_en():
    assert t("invalid_credentials", "tr") == "Kullanıcı adı veya şifre hatalı."
    assert t("invalid_credentials", "en") == "Username or password is incorrect."
    assert t("invalid_credentials", "fr") == "Username or password is incorrect."


def test_ai_prompt_includes_language_instruction_without_shape_change():
    messages = build_kanitli_prompt(
        "ATP ne işe yarar?",
        [{"parca_id": 1, "addr": "Giris", "text": "ATP enerji tasir."}],
        allowed_citation_ids=[1],
        language_instruction=language_instruction("de"),
    )

    assert len(messages) == 2
    assert "Antworte auf Deutsch." in messages[0]["content"]
    assert "JSON sema" in messages[0]["content"]
