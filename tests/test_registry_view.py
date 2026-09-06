"""Tests for the registry inspector and the expanded tweak sets."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom_tweeks.engine import (nettweaks, perftweaks,  # noqa: E402
                                   registry as regview)


# -------------------------------------------------------- registry view

def test_managed_values_are_documented():
    assert len(regview.MANAGED) >= 15
    for m in regview.MANAGED:
        assert m.meaning, f"{m.name} has no explanation"
        assert m.default is not None, f"{m.name} has no documented default"
        assert m.hive in ("HKCU", "HKLM")


def test_no_managed_value_touches_security():
    """The inspector must not become a way around the forbidden list."""
    for m in regview.MANAGED:
        low = f"{m.key}\\{m.name}".lower()
        for banned in ("defender", "firewall", "windows update",
                       "featuresettingsoverride", "enablelua",
                       "disableantispyware", "tamperprotection"):
            assert banned not in low, f"{m.name} touches {banned}"


def test_writes_require_explicit_confirmation():
    """A stray click must not be able to change the registry."""
    ok, message, change = regview.set_value(
        "HKCU", r"Control Panel\Mouse", "MouseSpeed", "0")
    assert not ok
    assert "confirmation" in message.lower()
    assert change is None


def test_unmanaged_paths_are_refused():
    ok, message, _ = regview.set_value(
        "HKLM", r"SOFTWARE\Policies\Microsoft\Windows Defender",
        "DisableAntiSpyware", 1, confirm=True)
    assert not ok
    assert "not one phantom tweeks manages" in message.lower()


def test_state_classification(monkeypatch):
    m = regview.MANAGED[0]
    monkeypatch.setattr(regview.ws, "read_registry",
                        lambda h, k, n: m.good)
    assert m.state() == "tweaked"
    monkeypatch.setattr(regview.ws, "read_registry",
                        lambda h, k, n: m.default)
    assert m.state() == "default"
    monkeypatch.setattr(regview.ws, "read_registry",
                        lambda h, k, n: "999")
    assert m.state() == "custom"


def test_snapshot_never_raises(monkeypatch):
    def boom(h, k, n):
        raise OSError("registry unavailable")
    monkeypatch.setattr(regview.ws, "read_registry", boom)
    assert len(regview.snapshot()) == len(regview.MANAGED)


def test_search_finds_by_meaning_and_path():
    assert regview.find("mouse"), "cannot search by name"
    assert regview.find("acceleration"), "cannot search by meaning"
    assert regview.find("") == []


def test_every_managed_value_maps_to_a_real_tweak():
    """A dangling tweak_id would mislead the user about what set a value."""
    known = set(perftweaks.BY_ID) | set(nettweaks.BY_ID)
    for m in regview.MANAGED:
        if m.tweak_id:
            assert m.tweak_id in known, (
                f"{m.name} references tweak '{m.tweak_id}', which no longer "
                "exists")


def test_report_explains_it_is_not_a_general_editor():
    # The disclaimer wraps across lines in the report, so compare on
    # collapsed whitespace rather than the raw string.
    text = " ".join(regview.report().lower().split())
    assert "not a general registry editor" in text


# ---------------------------------------------------- expanded tweak sets

def test_network_tweak_count_grew():
    assert len(nettweaks.TWEAKS) >= 25


def test_perf_tweak_count_grew():
    assert len(perftweaks.TWEAKS) >= 30


@pytest.mark.parametrize("module", [nettweaks, perftweaks])
def test_every_toggle_actually_reverses(module, monkeypatch):
    """Off must write a different value from on, or the toggle is a no-op.

    This caught a real bug: 'pointer_precision_off' wrote the same value in
    both directions, so switching it off did nothing at all.
    """
    monkeypatch.setattr(module, "IS_WINDOWS", True)
    monkeypatch.setattr(module, "is_admin", lambda: True)
    monkeypatch.setattr(module.runproc, "run",
                        lambda *a, **k: types.SimpleNamespace(
                            stdout="", stderr="", returncode=0))
    monkeypatch.setattr(module.runproc, "output", lambda *a, **k: "")
    if hasattr(module, "_adapter_guids"):
        monkeypatch.setattr(module, "_adapter_guids", lambda: ["{A}"])

    writes = []
    monkeypatch.setattr(module.ws, "write_registry",
                        lambda h, k, n, v, **kw: writes.append((n, v)))

    broken = []
    for t in module.TWEAKS:
        writes.clear()
        module.set_tweak(t.id, True)
        on = dict(writes)
        writes.clear()
        module.set_tweak(t.id, False)
        off = dict(writes)
        if on and off and on == off:
            broken.append(t.id)
    assert not broken, f"these toggles do not reverse: {broken}"


@pytest.mark.parametrize("module", [nettweaks, perftweaks])
def test_no_tweak_promises_a_guaranteed_gain(module):
    src = Path(module.__file__).read_text(encoding="utf-8").lower()
    for claim in ("guaranteed", "will increase your fps", "boost your fps",
                  "lowers your ping", "reduce your ping"):
        assert claim not in src, f"{module.__name__} promises: {claim!r}"


def test_honest_about_tweaks_that_do_nothing():
    """Some tweaks are included because people expect them. Say so."""
    src = Path(nettweaks.__file__).read_text(encoding="utf-8").lower()
    assert "do not expect a difference" in src or "expect no measurable" in src


@pytest.mark.parametrize("module", [nettweaks, perftweaks])
def test_risky_tweaks_are_flagged(module):
    risky = [t for t in module.TWEAKS if t.warning]
    assert risky, f"{module.__name__} flags nothing as risky"
    for t in risky:
        assert len(t.warning) > 25, f"{t.id} has a token warning"
