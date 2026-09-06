"""Tests for admin elevation, the resizing confirm dialog, and new settings."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom_tweeks.core import elevation  # noqa: E402
from phantom_tweeks.core.config import DEFAULTS  # noqa: E402


# ------------------------------------------------------------- elevation

def test_no_elevation_attempt_off_windows(monkeypatch):
    monkeypatch.setattr(elevation, "IS_WINDOWS", False)
    assert elevation.wanted(["app"]) is False
    assert elevation.relaunch_as_admin(["app"]) is False


def test_asks_when_launched_as_a_standard_user(monkeypatch):
    monkeypatch.setattr(elevation, "IS_WINDOWS", True)
    monkeypatch.setattr(elevation, "is_admin", lambda: False)
    assert elevation.wanted(["PhantomTweeks.exe"]) is True


def test_does_not_ask_when_already_elevated(monkeypatch):
    monkeypatch.setattr(elevation, "IS_WINDOWS", True)
    monkeypatch.setattr(elevation, "is_admin", lambda: True)
    assert elevation.wanted(["PhantomTweeks.exe"]) is False


def test_cannot_loop_forever(monkeypatch):
    """The relaunched copy carries a marker so it never re-elevates."""
    monkeypatch.setattr(elevation, "IS_WINDOWS", True)
    monkeypatch.setattr(elevation, "is_admin", lambda: False)
    assert elevation.wanted(["app.exe", "--elevated"]) is False


def test_no_elevate_flag_is_respected(monkeypatch):
    monkeypatch.setattr(elevation, "IS_WINDOWS", True)
    monkeypatch.setattr(elevation, "is_admin", lambda: False)
    assert elevation.wanted(["app.exe", "--no-elevate"]) is False


def test_cli_commands_never_trigger_a_uac_prompt(monkeypatch):
    """Asking for a report should not pop UAC."""
    monkeypatch.setattr(elevation, "IS_WINDOWS", True)
    monkeypatch.setattr(elevation, "is_admin", lambda: False)
    for argv in (["app.exe", "scan"], ["app.exe", "perf"],
                 ["app.exe", "report", "-o", "x.html"]):
        assert elevation.wanted(argv) is False, f"{argv} would prompt"


def test_relaunch_uses_runas_and_passes_the_marker(monkeypatch):
    monkeypatch.setattr(elevation, "IS_WINDOWS", True)
    calls = {}

    class Shell:
        @staticmethod
        def ShellExecuteW(handle, verb, exe, params, directory, show):
            calls.update(verb=verb, params=params)
            return 42

    fake = types.SimpleNamespace(
        windll=types.SimpleNamespace(shell32=Shell))
    monkeypatch.setitem(sys.modules, "ctypes", fake)
    assert elevation.relaunch_as_admin(["app.py"]) is True
    assert calls["verb"] == "runas"
    assert "--elevated" in calls["params"], "the loop guard is missing"


def test_declining_elevation_is_reported_not_fatal(monkeypatch):
    """ShellExecute returns <= 32 when the user cancels UAC."""
    monkeypatch.setattr(elevation, "IS_WINDOWS", True)

    class Shell:
        @staticmethod
        def ShellExecuteW(*a):
            return 5          # SE_ERR_ACCESSDENIED / cancelled

    monkeypatch.setitem(sys.modules, "ctypes", types.SimpleNamespace(
        windll=types.SimpleNamespace(shell32=Shell)))
    assert elevation.relaunch_as_admin(["app.py"]) is False


def test_limits_are_explained_specifically():
    text = elevation.explain_limits().lower()
    assert "power plan" in text
    assert "restore point" in text
    # It must also say what still works, or it reads as "nothing works".
    assert "everything else works" in text


def test_manifest_does_not_hard_require_admin():
    """A requireAdministrator manifest blocks standard users entirely,
    including read-only and CLI use."""
    spec = (ROOT / "packaging" / "PhantomTweeks.spec").read_text(encoding="utf-8")
    assert "uac_admin=False" in spec, (
        "the frozen build demands elevation before it can even start")


# --------------------------------------------------------------- settings

def test_new_settings_exist_with_safe_defaults():
    expected = {
        "request_admin_on_start": True,
        "warn_when_not_admin": True,
        "restore_point_before_tweaks": False,
        "confirm_every_tweak": True,
        "require_double_confirm_high_risk": True,
        "keep_backups_forever": True,
        "start_minimised": False,
        "compact_mode": False,
    }
    for key, default in expected.items():
        assert key in DEFAULTS, f"{key} is missing"
        assert DEFAULTS[key] == default, f"{key} has an unsafe default"


def test_nothing_automatic_is_enabled_by_default():
    for key in ("auto_apply_high_confidence", "auto_apply_game_profile",
                "telemetry", "share_hardware_info", "share_game_info",
                "restore_point_before_tweaks"):
        assert DEFAULTS[key] is False, f"{key} is on by default"


def test_every_setting_is_exposed_in_the_interface():
    """A setting nobody can find is not a setting."""
    gui = (ROOT / "src" / "phantom_tweeks" / "gui"
           / "app_window.py").read_text(encoding="utf-8")
    internal = {"theme", "protected_apps", "active_profile", "last_page",
                "network_targets", "maintenance_schedule", "ui_scale"}
    for key in DEFAULTS:
        if key in internal:
            continue
        assert f'"{key}"' in gui, f"{key} is not exposed in Settings"


# ----------------------------------------------------------- nvidia page

def test_nvidia_lives_under_tweaks():
    from phantom_tweeks.gui import app_window
    assert app_window.PAGE_SECTION["nvidia"] == "tweaks", (
        "the NVIDIA page is a tweaks page, not a dashboard page")


# --------------------------------------------------------- confirm dialog

def test_dialog_reserves_space_for_its_buttons():
    """A fixed-height dialog pushed Confirm off-screen with a long message."""
    src = (ROOT / "src" / "phantom_tweeks" / "gui"
           / "widgets.py").read_text(encoding="utf-8")
    body = src[src.index("def confirm_dialog"):src.index("class Toast")]
    assert 'win.geometry("540x330")' not in body, "still a fixed size"
    assert 'side="bottom"' in body, "buttons are not bottom-anchored"
    assert "winfo_screenheight" in body, "the dialog ignores the screen size"
    # The message must scroll rather than push everything else down.
    assert "yscrollcommand" in body, "a long message cannot scroll"


def test_dialog_buttons_are_packed_before_the_message():
    """Pack order decides who gets starved when space runs short."""
    src = (ROOT / "src" / "phantom_tweeks" / "gui"
           / "widgets.py").read_text(encoding="utf-8")
    body = src[src.index("def confirm_dialog"):src.index("class Toast")]
    btns = body.index("btns.pack(")
    message = body.index("body.pack(")
    assert btns < message, (
        "the message is packed before the buttons, so a long message will "
        "starve them of height")
