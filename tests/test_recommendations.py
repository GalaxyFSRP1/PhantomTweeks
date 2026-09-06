"""Evaluators must say 'no change recommended' when a tweak would not help."""
import pytest

from phantom_tweeks.engine import catalog
from phantom_tweeks.engine.catalog import BY_ID, Confidence


def test_gpu_preference_declines_on_single_gpu():
    ev = BY_ID["gfx.gpu_preference"].evaluate(
        {"game": {"executable_path": "C:/g.exe"}, "gpu_count": 1})
    assert not ev.applicable
    assert ev.confidence == Confidence.NOT_RECOMMENDED
    assert "No change recommended" in ev.reason


def test_gpu_preference_declines_without_game():
    ev = BY_ID["gfx.gpu_preference"].evaluate({"game": None, "gpu_count": 2})
    assert not ev.applicable


def test_visual_effects_declines_on_healthy_system():
    ev = BY_ID["win.visual_effects"].evaluate({"ram_gb": 32, "gpu_utilization": 40})
    assert not ev.applicable
    assert "No change recommended" in ev.reason


def test_visual_effects_offers_only_low_confidence_on_weak_system():
    ev = BY_ID["win.visual_effects"].evaluate({"ram_gb": 8, "gpu_utilization": 95})
    assert ev.applicable
    assert ev.confidence == Confidence.LOW


def test_power_plan_warns_on_laptop():
    ev = BY_ID["power.high_performance"].evaluate(
        {"power_plan": "Balanced", "is_laptop": True})
    assert ev.confidence == Confidence.LOW
    assert "laptop" in ev.reason.lower()
    assert "throttling" in ev.reason.lower()


def test_power_plan_declines_when_already_high():
    ev = BY_ID["power.high_performance"].evaluate(
        {"power_plan": "High performance", "is_laptop": False})
    assert not ev.applicable
    assert ev.already_optimal


def test_hags_declines_when_unsupported():
    ev = BY_ID["gfx.hags"].evaluate({"hags_supported": False})
    assert not ev.applicable
    assert "not supported" in ev.reason


def test_gamedvr_declines_while_recording():
    """Never fight the user's active recording."""
    ev = BY_ID["win.game_dvr"].evaluate({"recording_active": True})
    assert not ev.applicable
    assert "recording" in ev.reason.lower()


def test_storage_declines_with_plenty_of_space():
    ev = BY_ID["storage.cleanup"].evaluate({"system_disk_free_pct": 55})
    assert not ev.applicable
    assert "No change recommended" in ev.reason


def test_storage_flags_full_disk():
    ev = BY_ID["storage.cleanup"].evaluate({"system_disk_free_pct": 4})
    assert ev.applicable
    assert ev.confidence == Confidence.HIGH


def test_every_evaluator_survives_empty_context():
    """A scan must never crash, whatever the machine looks like."""
    for opt in catalog.CATALOG:
        ev = opt.evaluate({})
        assert ev.reason
