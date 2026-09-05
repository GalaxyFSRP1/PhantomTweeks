"""Security invariants: things Phantom Tweeks must refuse to do, ever."""
import pytest

from phantom_tweeks.engine import winsettings as ws
from phantom_tweeks.engine.catalog import CATALOG, Category, Confidence
from phantom_tweeks.engine.winsettings import ForbiddenSetting


@pytest.mark.parametrize("subkey", [
    r"SOFTWARE\Microsoft\Windows Defender",
    r"SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection",
    r"SYSTEM\CurrentControlSet\Services\WinDefend",
    r"SYSTEM\CurrentControlSet\Services\MpsSvc",
    r"SYSTEM\CurrentControlSet\Services\wuauserv",
    r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU",
    r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\FeatureSettings",
    r"SYSTEM\CurrentControlSet\Services\EasyAntiCheat",
    r"SYSTEM\CurrentControlSet\Services\BEService",
    r"SYSTEM\CurrentControlSet\Services\vgc",
])
def test_security_keys_are_forbidden(subkey):
    with pytest.raises(ForbiddenSetting):
        ws._check_allowed("HKLM", subkey, "Start")


def test_normal_keys_are_allowed():
    ws._check_allowed("HKCU", r"Software\Microsoft\GameBar", "AutoGameModeEnabled")


def test_catalog_entries_are_documented():
    """Every optimization must carry a real technical justification."""
    for opt in CATALOG:
        assert len(opt.purpose) > 40, f"{opt.id} lacks a real purpose"
        assert opt.expected_effect, f"{opt.id} lacks an expected effect"
        assert opt.supported, f"{opt.id} lacks platform support info"
        assert opt.risk is not None
        card = opt.info_card()
        for field in ("Purpose:", "Expected effect:", "Risk:", "Supported:", "Reversible:"):
            assert field in card


def test_catalog_ids_unique():
    ids = [o.id for o in CATALOG]
    assert len(ids) == len(set(ids))


def test_irreversible_items_are_never_auto_applicable():
    from phantom_tweeks.engine.optimizer import Recommendation
    from phantom_tweeks.engine.catalog import Evaluation
    for opt in CATALOG:
        if opt.reversible:
            continue
        rec = Recommendation(opt, Evaluation(True, Confidence.HIGH, "test"))
        assert not rec.auto_applicable, f"{opt.id} is irreversible but auto-applicable"


def test_advanced_items_are_never_auto_applicable():
    from phantom_tweeks.engine.optimizer import Recommendation
    from phantom_tweeks.engine.catalog import Evaluation
    for opt in CATALOG:
        if not opt.advanced:
            continue
        rec = Recommendation(opt, Evaluation(True, Confidence.HIGH, "test"))
        assert not rec.auto_applicable, f"advanced {opt.id} must not auto-apply"


def test_medium_and_low_confidence_never_auto_apply():
    from phantom_tweeks.engine.optimizer import Recommendation
    from phantom_tweeks.engine.catalog import Evaluation
    for opt in CATALOG:
        for conf in (Confidence.MEDIUM, Confidence.LOW, Confidence.NOT_RECOMMENDED):
            rec = Recommendation(opt, Evaluation(True, conf, "test"))
            assert not rec.auto_applicable


def test_no_privacy_defaults_leak():
    from phantom_tweeks.core.config import DEFAULTS
    for key in ("telemetry", "share_hardware_info", "share_game_info"):
        assert DEFAULTS[key] is False, f"{key} must default to off"
    assert DEFAULTS["auto_apply_high_confidence"] is False


def test_premium_is_inert():
    from phantom_tweeks.core import premium
    assert premium.PREMIUM_AVAILABLE is False
    assert premium.is_premium() is False
    assert premium.NullValidator().validate(premium.License(plan="pro")) is False


def test_background_analyzer_never_kills():
    from phantom_tweeks.engine.background import request_close
    ok, msg = request_close("chrome.exe")
    assert ok is False
    ok, msg = request_close("discord.exe")
    assert ok is False
    assert "Phantom Shield" in msg
