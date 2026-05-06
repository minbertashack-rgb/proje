from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest


SLOW_TEST_FILES = {
    "test_ai2_guardrails.py",
    "test_golden_parser_ingestion.py",
    "test_ingestion_quality.py",
    "test_panels_api.py",
    "test_product_extensions.py",
    "test_rag_quality.py",
    "test_study_summary_feedback_export.py",
}

MEDIUM_TEST_FILES = {
    "test_boss_readiness.py",
    "test_boss_runtime.py",
    "test_concept_runtime.py",
    "test_escape_room_runtime.py",
    "test_export_readiness.py",
    "test_learning_runtime.py",
    "test_multiformat_ingestion.py",
    "test_notlar_productization.py",
    "test_phase4_5_surfaces.py",
    "test_quiz_runtime.py",
    "test_readme_generation.py",
    "test_real_user_e2e_smoke.py",
    "test_real_exports.py",
    "test_roulette_runtime.py",
    "test_self_check_runtime.py",
    "test_speedrun_runtime.py",
    "test_upload_fields.py",
}

SUITE_FILE_MARKERS = {
    "suite_a": {
        "test_ai2_guardrails.py",
        "test_boss_readiness.py",
        "test_boss_runtime.py",
        "test_escape_room_runtime.py",
        "test_export_readiness.py",
        "test_learning_runtime.py",
        "test_panels_api.py",
        "test_phase4_5_surfaces.py",
        "test_product_panel_helpers.py",
        "test_quiz_runtime.py",
        "test_roulette_runtime.py",
        "test_self_check_runtime.py",
        "test_speedrun_runtime.py",
    },
    "suite_b": {
        "test_cheatsheet_exports.py",
        "test_notlar_productization.py",
        "test_product_extensions.py",
        "test_readme_generation.py",
        "test_real_user_e2e_smoke.py",
        "test_real_exports.py",
        "test_study_summary_feedback_export.py",
        "test_upload_fields.py",
    },
    "suite_c": {
        "test_ai2_runtime_tools.py",
        "test_ai_eval_contracts.py",
        "test_anlamadim_hard_parts.py",
        "test_anlamadim_quality.py",
        "test_concept_fusion.py",
        "test_concept_runtime.py",
        "test_golden_parser_ingestion.py",
        "test_heading_parser.py",
        "test_ingestion_contract.py",
        "test_ingestion_quality.py",
        "test_metric_store_behavioral_scores.py",
        "test_metric_store_utils.py",
        "test_multiformat_ingestion.py",
        "test_ocr_ingestion.py",
        "test_rag_normalization.py",
        "test_rag_quality.py",
        "test_rerank_deterministic.py",
        "test_special_chunk_explanations.py",
        "test_text_utils.py",
    },
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        file_name = Path(str(item.fspath)).name
        if file_name in SLOW_TEST_FILES:
            item.add_marker(pytest.mark.slow)
        elif file_name in MEDIUM_TEST_FILES:
            item.add_marker(pytest.mark.medium)
        else:
            item.add_marker(pytest.mark.fast)

        for marker_name, files in SUITE_FILE_MARKERS.items():
            if file_name in files:
                item.add_marker(getattr(pytest.mark, marker_name))
                break


@pytest.fixture
def gecici_media_root(settings, tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    settings.MEDIA_ROOT = media_root
    return media_root


@pytest.fixture
def test_kullanicisi(db, django_user_model):
    kullanici_adi = f"parser_test_{uuid4().hex[:8]}"
    return django_user_model.objects.create_user(
        username=kullanici_adi,
        password="12345678",
    )
