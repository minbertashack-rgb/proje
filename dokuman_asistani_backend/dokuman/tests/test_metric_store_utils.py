import importlib
import sys
import types
import math


def _import_metric_store_with_dummy_models():
    # Provide minimal fake dokuman.models and oyun.models to avoid Django model imports
    if "dokuman.models" not in sys.modules or not hasattr(sys.modules["dokuman.models"], "MetrikKaydi"):
        mm = types.ModuleType("dokuman.models")
        mm.AnlamadimKaydi = type("AnlamadimKaydi", (), {})
        mm.KullaniciGeriBildirim = type("KullaniciGeriBildirim", (), {})
        mm.MetrikKaydi = type("MetrikKaydi", (), {})
        sys.modules["dokuman.models"] = mm

    if "oyun.models" not in sys.modules:
        om = types.ModuleType("oyun.models")
        sys.modules["oyun.models"] = om

    import dokuman.services.metric_store as metric_store
    importlib.reload(metric_store)
    return metric_store


def test_clamp01_and_safe_avg_and_bounded_ratio():
    ms = _import_metric_store_with_dummy_models()
    assert ms._clamp01(-1) == 0.0
    assert ms._clamp01(0.5) == 0.5
    assert ms._clamp01(2) == 1.0
    assert ms._clamp01(None) == 0.0

    assert ms._safe_avg([1, "2", 3.0]) == 2.0
    assert ms._safe_avg([]) == 0.0

    assert ms._bounded_ratio(2, 4) == 0.5
    assert ms._bounded_ratio(1, 0, fallback=0.42) == 0.42


def test_technical_and_fact_density():
    ms = _import_metric_store_with_dummy_models()
    # '123 abc' -> tokens ['123','abc'] -> technical_hits = 1 -> 1/2 = 0.5
    assert math.isclose(ms._technical_density("123 abc"), 0.5, rel_tol=1e-6)
    # fact density similar for plain numeric + short word
    assert math.isclose(ms._fact_density("123 abc"), 0.5, rel_tol=1e-6)


def test_length_bonus_variants():
    ms = _import_metric_store_with_dummy_models()
    # In sweet spot
    assert ms._length_bonus("x" * 15, sweet_min=10, sweet_max=20, hard_limit=50) == 1.0
    # Shorter than sweet_min
    assert math.isclose(ms._length_bonus("x" * 5, sweet_min=10, sweet_max=20, hard_limit=50), 0.5, rel_tol=1e-6)
    # Longer than hard_limit
    assert ms._length_bonus("x" * 60, sweet_min=10, sweet_max=20, hard_limit=50) == 0.18
    # Slightly above sweet_max
    val = ms._length_bonus("x" * 25, sweet_min=10, sweet_max=20, hard_limit=50)
    assert 0.6 < val < 1.0


def test_compute_boss_progress_score_and_mastery_delta():
    ms = _import_metric_store_with_dummy_models()
    out = ms.compute_boss_progress_score(dogru_sayisi=8, toplam_soru=10, ipucu_sayisi=1)
    assert math.isclose(out["boss_progress_score"], 0.7, rel_tol=1e-6)
    assert out["boss_outcome"] == "in_progress"
    assert out["boss_progress_reason"] == "partial_progress"
    assert math.isclose(out["sonuc_orani"], 0.8, rel_tol=1e-6)

    out2 = ms.compute_boss_progress_score(dogru_sayisi=10, toplam_soru=10, ipucu_sayisi=0)
    assert out2["boss_outcome"] == "boss_defeated"

    delta = ms.compute_mastery_progress_delta(old_score=0.1, new_score=0.3)
    assert math.isclose(delta["mastery_progress_delta"], 0.2, rel_tol=1e-6)
    assert delta["mastery_delta_reason"] == "strong_gain"
    assert delta["micro_feedback"] != ""
