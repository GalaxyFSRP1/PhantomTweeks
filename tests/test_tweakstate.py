"""Tests that selected tweaks are actually saved.

Nineteen toggles could not read their own state back from Windows. They
reported False unconditionally, so every switch the user flipped appeared OFF
again on the next launch and there was no way to distinguish "off" from
"cannot tell".
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom_tweeks.engine import (nettweaks, perftweaks,  # noqa: E402
                                   tweakstate)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    from phantom_tweeks.core import paths
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "ensure_dirs", lambda: None)
    return tmp_path


def test_unreadable_tweaks_declare_themselves():
    """is_on=None means "cannot read", which is different from "off".

    Using `lambda: False` for both made the saved selection unusable: the
    resolver could not tell a real reading from a placeholder.
    """
    for module in (nettweaks, perftweaks):
        unreadable = [t for t in module.TWEAKS if t.is_on is None]
        assert unreadable, f"{module.__name__} marks nothing as unreadable"
        for t in module.TWEAKS:
            if t.is_on is not None:
                assert callable(t.is_on)


def test_remembered_selection_is_used_when_windows_cannot_answer(data_dir):
    tweakstate.remember("nv_power_max", True, "NVIDIA")
    is_on, label = tweakstate.resolve("nv_power_max", None, detectable=False)
    assert is_on is True
    assert "remembered" in label


def test_the_machine_wins_when_it_can_answer(data_dir):
    """A saved record must never override a real reading."""
    tweakstate.remember("hags", True, "System")
    is_on, _ = tweakstate.resolve("hags", False, detectable=True)
    assert is_on is False, "the saved record overrode the actual system state"


def test_drift_is_reported(data_dir):
    """Windows Update and driver reinstalls silently revert settings."""
    tweakstate.remember("hags", True, "System")
    _, label = tweakstate.resolve("hags", False, detectable=True)
    assert label == tweakstate.DRIFTED


def test_agreement_is_not_reported_as_drift(data_dir):
    tweakstate.remember("hags", True, "System")
    _, label = tweakstate.resolve("hags", True, detectable=True)
    assert label == tweakstate.CONFIRMED_ON


def test_nothing_saved_is_unknown_not_off(data_dir):
    is_on, label = tweakstate.resolve("never_touched", None, detectable=False)
    assert is_on is False
    assert label == tweakstate.UNKNOWN


def test_reverting_is_remembered_too(data_dir):
    tweakstate.remember("nv_power_max", True)
    tweakstate.remember("nv_power_max", False)
    is_on, label = tweakstate.resolve("nv_power_max", None, detectable=False)
    assert is_on is False
    assert "remembered" in label


def test_corrupt_state_file_is_ignored(data_dir):
    (data_dir / "tweak-state.json").write_text("not json", encoding="utf-8")
    assert tweakstate.load().records == {}


def test_clear_removes_everything(data_dir):
    tweakstate.remember("a", True)
    tweakstate.remember("b", True)
    assert tweakstate.clear() == 2
    assert tweakstate.load().records == {}


def test_reapply_only_touches_enabled_tweaks(data_dir):
    tweakstate.remember("on_one", True)
    tweakstate.remember("off_one", False)
    seen = []

    def fake_apply(tweak_id, enabled):
        seen.append((tweak_id, enabled))
        return True, "done", []

    result = tweakstate.reapply_all(fake_apply)
    assert seen == [("on_one", True)], "re-applied something that was off"
    assert len(result["applied"]) == 1


def test_reapply_survives_a_failing_tweak(data_dir):
    tweakstate.remember("bad", True)
    tweakstate.remember("good", True)

    def flaky(tweak_id, enabled):
        if tweak_id == "bad":
            raise OSError("access denied")
        return True, "ok", []

    result = tweakstate.reapply_all(flaky)
    assert len(result["applied"]) == 1
    assert len(result["failed"]) == 1


def test_selection_survives_a_real_process_restart():
    """The behaviour the user actually asked for, end to end."""
    home = tempfile.mkdtemp()
    env = dict(os.environ, PHANTOM_TWEEKS_HOME=home)

    apply_code = (
        "import sys, types; sys.path.insert(0, 'src');"
        "from phantom_tweeks.engine import perftweaks as P;"
        "P.IS_WINDOWS=True; P.is_admin=lambda: True;"
        "P.runproc.run=lambda *a,**k: types.SimpleNamespace("
        "stdout='',stderr='',returncode=0);"
        "P.runproc.output=lambda *a,**k: '';"
        "P.ws.write_registry=lambda h,k,n,v,**kw: None;"
        "P.set_tweak('nv_power_max', True);"
        "print(P.states()['nv_power_max'])"
    )
    read_code = (
        "import sys, types; sys.path.insert(0, 'src');"
        "from phantom_tweeks.engine import perftweaks as P;"
        "P.IS_WINDOWS=True; P.is_admin=lambda: True;"
        "P.runproc.run=lambda *a,**k: types.SimpleNamespace("
        "stdout='',stderr='',returncode=0);"
        "P.runproc.output=lambda *a,**k: '';"
        "print(P.states()['nv_power_max'])"
    )

    first = subprocess.run([sys.executable, "-c", apply_code], env=env,
                           cwd=str(ROOT), capture_output=True, text=True,
                           timeout=180)
    assert first.stdout.strip().endswith("True"), first.stderr[-400:]

    second = subprocess.run([sys.executable, "-c", read_code], env=env,
                            cwd=str(ROOT), capture_output=True, text=True,
                            timeout=180)
    assert second.stdout.strip().endswith("True"), (
        "the selection was lost when the app restarted")


def test_both_modules_record_what_they_apply():
    for module in (nettweaks, perftweaks):
        src = Path(module.__file__).read_text(encoding="utf-8")
        assert "tweakstate.remember" in src, (
            f"{module.__name__} does not save the user's selection")
