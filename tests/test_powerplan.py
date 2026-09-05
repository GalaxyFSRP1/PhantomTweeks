"""The custom power plan must be safe, honest and reversible."""
from __future__ import annotations

import pytest

from phantom_tweeks.engine import powerplan as pp


def test_plan_is_derived_from_balanced_not_high_performance():
    assert pp.BALANCED_GUID == "381b4222-f694-41f0-9685-ff5bb260df2e"
    import inspect
    src = inspect.getsource(pp.create_plan)
    assert "duplicatescheme" in src
    assert pp.BALANCED_GUID in src or "BALANCED_GUID" in src


def test_minimum_processor_state_is_not_pinned_to_100():
    """The classic 'gaming plan' mistake: heat and noise, no extra frames."""
    s = next(x for x in pp.PHANTOM_SETTINGS if x.setting == pp.SET_MIN_PROC)
    assert s.ac_value < 100, "min processor state pinned at 100% on AC"
    assert s.dc_value <= s.ac_value, "battery must not be more aggressive than AC"


def test_maximum_processor_state_is_never_capped():
    s = next(x for x in pp.PHANTOM_SETTINGS if x.setting == pp.SET_MAX_PROC)
    assert s.ac_value == 100 and s.dc_value == 100


def test_battery_values_are_never_more_aggressive_than_ac():
    """On battery we must not spend more power than when plugged in."""
    more_is_hungrier = {pp.SET_MIN_PROC, pp.SET_MAX_PROC, pp.SET_CORE_PARK,
                        pp.SET_PERF_BOOST}
    for s in pp.PHANTOM_SETTINGS:
        if s.setting in more_is_hungrier:
            assert s.dc_value <= s.ac_value, f"{s.label} is hungrier on battery"


def test_every_setting_has_a_real_justification():
    for s in pp.PHANTOM_SETTINGS:
        assert s.label and s.reason
        assert len(s.reason) > 40, f"{s.label} has a token explanation"


def test_settings_have_unique_identities():
    seen = {(s.subgroup, s.setting) for s in pp.PHANTOM_SETTINGS}
    assert len(seen) == len(pp.PHANTOM_SETTINGS)


def test_describe_states_what_is_deliberately_excluded():
    text = pp.describe()
    low = text.lower()
    assert "overclock" in low
    assert "not set to 100%" in low or "not 100" in low
    assert "copied from balanced" in low
    for s in pp.PHANTOM_SETTINGS:
        assert s.label in text


def test_describe_promises_existing_plans_are_untouched():
    assert "existing plans are not" in pp.describe().lower()


def test_only_documented_powercfg_settings_are_written():
    """Guard the actual behaviour, not the prose.

    Every value the plan writes must come from PHANTOM_SETTINGS, so a new
    tweak cannot be slipped in without a label and a justification (which
    test_every_setting_has_a_real_justification then enforces).
    """
    import inspect
    src = inspect.getsource(pp.create_plan)
    # The only value-setting calls must iterate PHANTOM_SETTINGS.
    assert "for s in PHANTOM_SETTINGS" in src
    assert src.count("/setacvalueindex") == 1
    assert src.count("/setdcvalueindex") == 1
    # No hard-coded GUID other than the Balanced template may be written.
    import re
    guids = set(re.findall(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                           r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", src))
    assert guids <= {pp.BALANCED_GUID}, f"unexpected GUID written: {guids}"


def test_module_disclaims_overclocking_explicitly():
    doc = (pp.__doc__ or "").lower()
    assert "overclock" in doc and "undervolt" in doc
    assert "nothing here overclocks" in doc


def test_degrades_cleanly_off_windows(monkeypatch):
    monkeypatch.setattr(pp, "IS_WINDOWS", False)
    assert pp.powercfg_available() is False
    assert pp.list_plans() == []
    st = pp.status()
    assert st["available"] is False and "Windows" in st["reason"]
    ok, msgs, changes = pp.create_plan()
    assert ok is False and changes == []
    ok, msgs = pp.delete_plan()
    assert ok is False


def test_create_plan_records_reversible_changes(monkeypatch):
    """Creating the plan must produce ChangeRecords so it can be rolled back."""
    monkeypatch.setattr(pp, "IS_WINDOWS", True)
    monkeypatch.setattr(pp.shutil, "which", lambda n: "/usr/bin/powercfg")
    monkeypatch.setattr(pp, "find_phantom_plan", lambda: None)
    monkeypatch.setattr(pp, "active_plan",
                        lambda: {"guid": pp.BALANCED_GUID, "name": "Balanced"})
    monkeypatch.setattr(pp, "is_laptop", lambda: False)

    class R:
        returncode = 0
        stdout = "Power Scheme GUID: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee (Balanced)"
        stderr = ""

    monkeypatch.setattr(pp, "_powercfg", lambda *a, **k: R())
    ok, msgs, changes = pp.create_plan(activate=True)
    assert ok is True
    kinds = {c.kind for c in changes}
    assert "powercfg" in kinds, "switching plans was not recorded for rollback"
    switch = next(c for c in changes if c.kind == "powercfg")
    assert switch.previous == pp.BALANCED_GUID


def test_plan_name_uses_official_spelling():
    assert "Tweeks" in pp.PHANTOM_PLAN_NAME
    assert "Tweaks" not in pp.PHANTOM_PLAN_NAME
