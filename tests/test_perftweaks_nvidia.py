"""Tests for latency/performance toggles and NVIDIA reporting."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom_tweeks.engine import perftweaks  # noqa: E402
from phantom_tweeks.hardware import nvidia  # noqa: E402


# ------------------------------------------------------- perf tweaks

def test_catalogue_is_substantial_and_complete():
    assert len(perftweaks.TWEAKS) >= 15
    ids = [t.id for t in perftweaks.TWEAKS]
    assert len(ids) == len(set(ids)), "duplicate ids"
    for t in perftweaks.TWEAKS:
        assert t.name and t.effect and t.apply
        assert len(t.detail) > 60, f"{t.id} does not explain itself"
        assert t.category in perftweaks.CATEGORIES


def test_toggling_off_restores_the_default(monkeypatch):
    """Off must undo, not merely stop applying."""
    monkeypatch.setattr(perftweaks, "IS_WINDOWS", True)
    monkeypatch.setattr(perftweaks, "is_admin", lambda: True)
    writes = []
    monkeypatch.setattr(perftweaks.ws, "write_registry",
                        lambda h, k, n, v, **kw: writes.append((n, v)))

    for tid in ("mouse_accel", "hags", "game_dvr", "power_throttling"):
        writes.clear()
        perftweaks.set_tweak(tid, True)
        on = dict(writes)
        writes.clear()
        perftweaks.set_tweak(tid, False)
        off = dict(writes)
        assert on and off, f"{tid} wrote nothing"
        assert on != off, f"{tid} writes the same value on and off"


def test_risky_tweaks_carry_warnings():
    """Simple toggles must still flag what can backfire."""
    for tid in ("hags", "power_throttling", "paging_executive",
                "search_indexing"):
        assert perftweaks.BY_ID[tid].warning, f"{tid} has no caution note"


def test_no_overclocking_anywhere():
    """A standing rule: never auto-overclock or undervolt."""
    src = Path(perftweaks.__file__).read_text(encoding="utf-8").lower()
    for banned in ("overclock", "voltage", "core offset", "memory offset",
                   "undervolt"):
        for line in src.splitlines():
            if banned in line:
                assert line.strip().startswith("#") or "no " in line, (
                    f"perftweaks may overclock: {line.strip()[:70]}")


def test_security_is_never_touched():
    src = Path(perftweaks.__file__).read_text(encoding="utf-8")
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("#", "*", '"""', "'")):
            continue
        low = stripped.lower()
        for banned in ("defender", "featuresettingsoverride", "enablelua",
                       "disableantispyware", "wuauserv"):
            assert banned not in low, f"line {i} touches {banned}"


def test_admin_required_is_reported(monkeypatch):
    monkeypatch.setattr(perftweaks, "IS_WINDOWS", True)
    monkeypatch.setattr(perftweaks, "is_admin", lambda: False)
    ok, message, changes = perftweaks.set_tweak("hags", True)
    assert not ok and "administrator" in message.lower() and changes == []


def test_user_scope_tweaks_do_not_need_admin():
    """Most input and display settings are per-user; requiring admin for
    them would push people to run elevated unnecessarily."""
    for tid in ("mouse_accel", "menu_delay", "game_dvr"):
        assert not perftweaks.BY_ID[tid].requires_admin


def test_states_never_raises(monkeypatch):
    monkeypatch.setattr(perftweaks.BY_ID["hags"], "is_on",
                        lambda: (_ for _ in ()).throw(OSError("no registry")))
    assert perftweaks.states()["hags"] is False


def test_unknown_tweak_rejected():
    ok, msg, _ = perftweaks.set_tweak("nope", True)
    assert not ok and "Unknown" in msg


# ------------------------------------------------------------- nvidia

_MAIN = ("0, NVIDIA GeForce RTX 4070, 566.36, 95.03.18, "
         "2610, 2790, 10501, 10501, 2610, 2790, "
         "196.42, 200.00, 215.00, 78, 83, 62, 3, 4, 8, 16, 99, 47")
_THROTTLE = ("Not Active, Not Active, Active, Not Active, Not Active, "
             "Active, Not Active, Not Active, Not Active")


@pytest.fixture
def fake_smi(monkeypatch):
    monkeypatch.setattr(nvidia.shutil, "which", lambda n: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(nvidia.runproc, "output",
                        lambda cmd, **kw: (_MAIN
                                           if "clocks.current.graphics"
                                           in " ".join(cmd) else _THROTTLE))


def test_absent_driver_is_reported_honestly(monkeypatch):
    monkeypatch.setattr(nvidia.shutil, "which", lambda n: None)
    assert not nvidia.available()
    text = nvidia.report()
    assert "not found" in text
    assert "never changes clocks" in text
    assert nvidia.diagnose() == []


def test_clocks_are_parsed(fake_smi):
    gpus = nvidia.probe()
    assert len(gpus) == 1
    g = gpus[0]
    assert g.name == "NVIDIA GeForce RTX 4070"
    assert g.clocks[0].current == 2610
    assert g.clocks[0].maximum == 2790
    assert round(g.clocks[0].headroom_pct) == 94


def test_active_throttle_reasons_are_identified(fake_smi):
    labels = {t.label for t in nvidia.probe()[0].active_throttles}
    assert "Power limit" in labels
    assert "Thermal limit" in labels


def test_idle_is_not_reported_as_a_problem(fake_smi):
    for t in nvidia.probe()[0].active_throttles:
        assert t.key != "gpu_idle", "idle clocks reported as throttling"


def test_pcie_downgrade_is_detected(fake_smi):
    """A card in the wrong slot is a real fault most tools miss."""
    g = nvidia.probe()[0]
    assert g.pcie_downgraded
    findings = " ".join(nvidia.diagnose())
    assert "Gen 3 x8" in findings and "Gen 4 x16" in findings
    assert "Reseat" in findings


def test_diagnose_gives_actionable_advice(fake_smi):
    findings = nvidia.diagnose()
    assert len(findings) >= 3
    joined = " ".join(findings).lower()
    assert "airflow" in joined or "cooling" in joined
    assert "power limit" in joined


def test_nvidia_module_never_sets_anything():
    """Read-only by design: clock changes are silicon-specific."""
    src = Path(nvidia.__file__).read_text(encoding="utf-8")
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("#", "*", '"""', "'")):
            continue
        for banned in ("-lgc", "-lmc", "--lock-gpu-clocks", "-pl ",
                       "--power-limit", "-ac "):
            assert banned not in stripped, (
                f"line {i} may change GPU state: {stripped[:70]}")


def test_report_states_why_it_will_not_overclock(fake_smi):
    text = nvidia.report().lower()
    assert "never change" in text or "never changes" in text
    assert "silicon-specific" in text
