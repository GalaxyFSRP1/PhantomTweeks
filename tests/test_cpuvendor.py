"""Tests for CPU vendor detection and the power-plan OEM fallback."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom_tweeks.hardware import cpuvendor as cv  # noqa: E402
from phantom_tweeks.engine import powerplan as pp  # noqa: E402


def _cpu(monkeypatch, name, maker, cores, threads):
    monkeypatch.setattr(cv, "_wmi_cpu", lambda: {
        "Name": name, "Manufacturer": maker, "NumberOfCores": cores,
        "NumberOfLogicalProcessors": threads, "MaxClockSpeed": 5000})
    return cv.detect()


def test_detects_amd(monkeypatch):
    p = _cpu(monkeypatch, "AMD Ryzen 7 5800X 8-Core Processor",
             "AuthenticAMD", 8, 16)
    assert p.is_amd and not p.is_intel
    assert p.smt is True


def test_detects_intel(monkeypatch):
    p = _cpu(monkeypatch, "Intel(R) Core(TM) i7-9700K CPU @ 3.60GHz",
             "GenuineIntel", 8, 8)
    assert p.is_intel and not p.is_amd
    assert p.smt is False, "a chip with equal cores and threads has no SMT"


def test_detects_intel_hybrid_layout(monkeypatch):
    """12th gen and later split into P-cores and E-cores."""
    p = _cpu(monkeypatch, "12th Gen Intel(R) Core(TM) i7-12700K",
             "GenuineIntel", 12, 20)
    assert p.hybrid is True
    assert p.p_cores == 8 and p.e_cores == 4


def test_older_intel_is_not_hybrid(monkeypatch):
    p = _cpu(monkeypatch, "Intel(R) Core(TM) i7-9700K CPU @ 3.60GHz",
             "GenuineIntel", 8, 8)
    assert p.hybrid is False


def test_detects_amd_chiplets(monkeypatch):
    p = _cpu(monkeypatch, "AMD Ryzen 9 7950X 16-Core Processor",
             "AuthenticAMD", 16, 32)
    assert p.ccds == 2, "a 16-core Ryzen spans two CCDs"


def test_unknown_vendor_is_admitted(monkeypatch):
    monkeypatch.setattr(cv, "_wmi_cpu", lambda: {})
    monkeypatch.setattr(cv, "_proc_cpuinfo", lambda: {})
    p = cv.detect()
    assert p.vendor == cv.UNKNOWN
    assert "not identified" in " ".join(a.title for a in cv.advice_for(p))


def test_amd_advice_leads_with_memory(monkeypatch):
    """Ryzen scales with memory speed more than anything else."""
    p = _cpu(monkeypatch, "AMD Ryzen 5 5600X 6-Core Processor",
             "AuthenticAMD", 6, 12)
    high = [a for a in cv.advice_for(p) if a.impact == "high"]
    assert any("EXPO" in a.title or "DOCP" in a.title for a in high)


def test_hybrid_intel_is_warned_off_manual_affinity(monkeypatch):
    """The single most damaging piece of advice for a hybrid CPU."""
    p = _cpu(monkeypatch, "13th Gen Intel(R) Core(TM) i9-13900K",
             "GenuineIntel", 24, 32)
    advice = cv.advice_for(p)
    affinity = [a for a in advice if "affinity" in a.title.lower()]
    assert affinity, "hybrid CPU gets no affinity warning"
    assert affinity[0].impact == "high"
    assert "efficiency cores" in affinity[0].detail.lower()


def test_neither_vendor_is_told_to_disable_smt(monkeypatch):
    for name, maker, c, t in (
            ("AMD Ryzen 7 5800X 8-Core Processor", "AuthenticAMD", 8, 16),
            ("12th Gen Intel(R) Core(TM) i7-12700K", "GenuineIntel", 12, 20)):
        p = _cpu(monkeypatch, name, maker, c, t)
        text = " ".join(f"{a.title} {a.detail}" for a in cv.advice_for(p))
        assert "leave smt enabled" in text.lower() or \
               "leave hyper-threading enabled" in text.lower()


def test_module_never_overclocks():
    src = Path(cv.__file__).read_text(encoding="utf-8")
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("#", "*", '"""', "'")):
            continue
        for banned in ("runproc.run([\"wmic\"", "SetVoltage", "-pl ",
                       "OverClock"):
            assert banned not in stripped, f"line {i} may change CPU state"


def test_advice_is_vendor_specific(monkeypatch):
    """Giving both vendors the same answer is the failure this fixes."""
    amd = cv.advice_for(_cpu(monkeypatch, "AMD Ryzen 7 5800X", "AuthenticAMD", 8, 16))
    intel = cv.advice_for(_cpu(monkeypatch, "12th Gen Intel Core i7-12700K",
                               "GenuineIntel", 12, 20))
    assert {a.title for a in amd} != {a.title for a in intel}


# --------------------------------------------- power plan OEM fallback

def _powercfg_env(monkeypatch, plans, dup_ok):
    listing = "Existing Power Schemes (* Active)\n" + "".join(
        f"Power Scheme GUID: {g}  ({n})\n" for g, n in plans)
    state = {"made": False}

    def fake(*args, **kw):
        if args and args[0] == "/list":
            out = listing
            if state["made"]:
                out += (f"Power Scheme GUID: 99999999-8888-7777-6666-555555555555"
                        f"  ({pp.PHANTOM_PLAN_NAME})\n")
            return types.SimpleNamespace(stdout=out, stderr="", returncode=0)
        if args and args[0] == "/duplicatescheme":
            if args[1] in dup_ok:
                state["made"] = True
                return types.SimpleNamespace(
                    stdout="Power Scheme GUID: "
                           "99999999-8888-7777-6666-555555555555  (copy)",
                    stderr="", returncode=0)
            return types.SimpleNamespace(
                stdout="", returncode=1,
                stderr="The system cannot find the file specified.")
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)

    from phantom_tweeks.core import platform_info
    monkeypatch.setattr(pp, "IS_WINDOWS", True)
    monkeypatch.setattr(pp.shutil, "which", lambda n: "powercfg.exe")
    monkeypatch.setattr(platform_info, "is_admin", lambda: True)
    monkeypatch.setattr(pp, "is_laptop", lambda: False)
    monkeypatch.setattr(pp, "_powercfg", fake)
    monkeypatch.setattr(pp, "active_plan",
                        lambda: {"guid": plans[0][0], "name": plans[0][1]})


def test_creates_from_balanced_normally(monkeypatch):
    _powercfg_env(monkeypatch, [(pp.BALANCED_GUID, "Balanced")],
                  {pp.BALANCED_GUID})
    ok, msgs, _ = pp.create_plan(True)
    assert ok, msgs


def test_falls_back_when_balanced_is_missing(monkeypatch):
    """OEM machines routinely ship without a Balanced scheme.

    /duplicatescheme then fails with "cannot find the file specified", which
    reads as a permissions error and is not - so plan creation failed
    outright on those machines.
    """
    oem = "11111111-2222-3333-4444-555555555555"
    _powercfg_env(monkeypatch, [(oem, "Dell Optimized")], {oem})
    ok, msgs, _ = pp.create_plan(True)
    assert ok, f"failed on a machine without Balanced: {msgs}"
    assert any("not available" in m for m in msgs), (
        "did not say which scheme it copied instead")


def test_reports_honestly_when_policy_blocks_everything(monkeypatch):
    oem = "11111111-2222-3333-4444-555555555555"
    _powercfg_env(monkeypatch, [(oem, "Corp Policy")], set())
    ok, msgs, _ = pp.create_plan(True)
    assert not ok
    joined = " ".join(msgs).lower()
    assert "group policy" in joined
    assert "everything else on this page still works" in joined
